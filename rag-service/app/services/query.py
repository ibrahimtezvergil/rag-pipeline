from __future__ import annotations

import re
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.db import RagDocument, RagProject
from app.repositories.ingestion import IngestionRepository
from app.services.embedder import embed_query_text
from app.services.llm import generate as generate_text
from app.services.prompts import build_query_answer_prompt, get_empty_query_answer
from app.services.reranker import CohereRerankerService
from app.services.sparse_encoder import encode_sparse_text
from app.services.vector_store import QdrantVectorStore


class QueryService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        vector_store: QdrantVectorStore | None = None,
        reranker: CohereRerankerService | None = None,
        vector_store_factory=None,
    ):
        self.session = session
        self.repository = IngestionRepository(session)
        self.vector_store = vector_store or QdrantVectorStore()
        self.reranker = reranker or CohereRerankerService()
        self.vector_store_factory = vector_store_factory or (lambda collection_name: QdrantVectorStore(collection_name=collection_name))

    async def answer_question(
        self,
        question: str,
        project_id: uuid.UUID,
        *,
        retrieval_mode: str = "hybrid",
        collections: list[str] | None = None,
        merge_strategy: str = "rrf",
        exclude_sources: list[str] | None = None,
        exclude_documents: list[str] | None = None,
        acl: list[str] | None = None,
        scope_type: str | None = None,
        scope_id: str | None = None,
        entity_id: str | None = None,
        snapshot_date: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, object]:
        project = await self.session.get(RagProject, project_id)
        retrieval_config = self._resolve_retrieval_config(
            project.config if project is not None else {},
            retrieval_mode,
        )
        query_embedding = await embed_query_text(question)
        response_retrieval_mode = "metadata_fallback"
        target_collections = collections or [None]
        if retrieval_mode == "hybrid":
            dense_hits = await self._semantic_ranked_document_ids(
                project_id,
                query_vector=list(query_embedding.get("values", [])),
                scope_type=scope_type,
                scope_id=scope_id,
                entity_id=entity_id,
                snapshot_date=snapshot_date,
                tags=tags,
                acl=acl,
                collections=target_collections,
            )
            sparse_hits = await self._sparse_ranked_document_ids(
                project_id,
                question=question,
                scope_type=scope_type,
                scope_id=scope_id,
                entity_id=entity_id,
                snapshot_date=snapshot_date,
                tags=tags,
                acl=acl,
                collections=target_collections,
            )
            ranked_document_ids, ranked_chunk_ids, chunk_scores = self._rrf_merge_hits(dense_hits, sparse_hits) if merge_strategy == "rrf" else dense_hits
            if ranked_document_ids is not None:
                response_retrieval_mode = "hybrid_rrf"
        elif retrieval_mode == "sparse":
            ranked_document_ids, ranked_chunk_ids, chunk_scores = await self._sparse_ranked_document_ids(
                project_id,
                question=question,
                scope_type=scope_type,
                scope_id=scope_id,
                entity_id=entity_id,
                snapshot_date=snapshot_date,
                tags=tags,
                acl=acl,
                collections=target_collections,
            )
            if ranked_document_ids is not None:
                response_retrieval_mode = "sparse_qdrant"
        else:
            ranked_document_ids, ranked_chunk_ids, chunk_scores = await self._semantic_ranked_document_ids(
                project_id,
                query_vector=list(query_embedding.get("values", [])),
                scope_type=scope_type,
                scope_id=scope_id,
                entity_id=entity_id,
                snapshot_date=snapshot_date,
                tags=tags,
                acl=acl,
                collections=target_collections,
            )
            if ranked_document_ids is not None:
                response_retrieval_mode = "semantic_qdrant"
        documents = await self._get_indexed_documents(
            project_id,
            ranked_document_ids=ranked_document_ids,
            scope_type=scope_type,
            scope_id=scope_id,
            entity_id=entity_id,
            snapshot_date=snapshot_date,
            tags=tags,
        )
        if ranked_document_ids is not None:
            top_documents = documents[: int(retrieval_config.get("candidate_limit", 8))]
        else:
            ranked = self._rank_documents(question, documents)
            top_documents = [document for score, document in ranked if score > 0][
                : int(retrieval_config.get("candidate_limit", 8))
            ]
            if not top_documents:
                top_documents = [document for _, document in ranked][:3]

        if not top_documents:
            return {
                "answer": get_empty_query_answer(),
                "retrieval_mode": "empty",
                "retrieval_context": [],
                "sources": [],
            }

        source_entries = await self._build_sources(question, top_documents, ranked_chunk_ids, chunk_scores)
        source_entries = self._apply_score_threshold(
            source_entries,
            threshold=float(retrieval_config.get("score_threshold", 0.0)),
        )
        source_entries, reranked = await self._maybe_rerank_sources(
            question,
            source_entries,
            project_config=(project.config if project is not None else {}),
            top_n=int(retrieval_config.get("rerank_top_n", 8)),
        )
        source_entries = self._apply_negative_filters(
            source_entries,
            exclude_sources=exclude_sources,
            exclude_documents=exclude_documents,
        )
        source_entries = self._apply_acl_filter(source_entries, acl=acl)
        final_sources = source_entries[: int(retrieval_config.get("top_k", 3))]
        answer = ""
        if final_sources:
            try:
                prompt = build_query_answer_prompt(question=question, sources=final_sources)
                answer = await generate_text(prompt)
            except Exception:
                answer = self._fallback_answer(final_sources)
        if not answer:
            titles = ", ".join(str(source.get("title", "")) for source in final_sources)
            answer = f"Ilgili indexed kaynaklar: {titles}"

        return {
            "answer": answer,
            "retrieval_mode": "hybrid_rrf_rerank" if reranked else response_retrieval_mode,
            "retrieval_context": self._build_retrieval_context(final_sources),
            "sources": final_sources,
        }

    async def _get_indexed_documents(
        self,
        project_id: uuid.UUID,
        *,
        ranked_document_ids: list[uuid.UUID] | None = None,
        scope_type: str | None = None,
        scope_id: str | None = None,
        entity_id: str | None = None,
        snapshot_date: str | None = None,
        tags: list[str] | None = None,
    ) -> list[RagDocument]:
        query = select(RagDocument).where(
            RagDocument.project_id == project_id,
            RagDocument.status == "indexed",
        )
        if ranked_document_ids is not None:
            if not ranked_document_ids:
                return []
            query = query.where(RagDocument.id.in_(ranked_document_ids))
        result = await self.session.scalars(query)
        documents = list(result)
        if scope_type is not None:
            documents = [
                document
                for document in documents
                if document.metadata_json.get("scope_type") == scope_type
            ]
        if scope_id is not None:
            documents = [
                document for document in documents if document.metadata_json.get("scope_id") == scope_id
            ]
        if entity_id is not None:
            documents = [
                document
                for document in documents
                if document.metadata_json.get("entity_id") == entity_id
            ]
        if snapshot_date is not None:
            documents = [
                document
                for document in documents
                if document.metadata_json.get("snapshot_date") == snapshot_date
            ]
        if tags:
            requested_tags = set(tags)
            documents = [
                document
                for document in documents
                if requested_tags.issubset(set(document.metadata_json.get("tags", [])))
            ]
        if ranked_document_ids is not None:
            document_map = {document.id: document for document in documents}
            documents = [
                document_map[document_id]
                for document_id in ranked_document_ids
                if document_id in document_map
            ]
        return documents

    async def _semantic_ranked_document_ids(
        self,
        project_id: uuid.UUID,
        *,
        query_vector: list[float],
        scope_type: str | None,
        scope_id: str | None,
        entity_id: str | None,
        snapshot_date: str | None,
        tags: list[str] | None,
        acl: list[str] | None,
        collections: list[str | None],
    ) -> tuple[list[uuid.UUID] | None, list[uuid.UUID] | None, dict[uuid.UUID, float]]:
        project = await self.session.get(RagProject, project_id)
        if project is None:
            return [], [], {}

        collection_hits = []
        for collection_name in collections:
            store = self._vector_store_for(collection_name)
            try:
                try:
                    search_results = await store.search_chunks(
                        query_vector=query_vector,
                        tenant_id=str(project.tenant_id),
                        scope_type=scope_type,
                        scope_id=scope_id,
                        entity_id=entity_id,
                        snapshot_date=snapshot_date,
                        tags=tags,
                        acl=acl,
                        limit=6,
                    )
                except TypeError:
                    search_results = await store.search_chunks(
                        query_vector=query_vector,
                        tenant_id=str(project.tenant_id),
                        scope_type=scope_type,
                        scope_id=scope_id,
                        entity_id=entity_id,
                        snapshot_date=snapshot_date,
                        tags=tags,
                        limit=6,
                    )
            except httpx.HTTPError:
                continue
            collection_hits.append(self._collect_ranked_hits(search_results))
        if not collection_hits:
            return None, None, {}
        return self._merge_collection_hit_sets(collection_hits)

    def _rrf_merge_hits(
        self,
        dense_hits: tuple[list[uuid.UUID] | None, list[uuid.UUID] | None, dict[uuid.UUID, float]],
        sparse_hits: tuple[list[uuid.UUID] | None, list[uuid.UUID] | None, dict[uuid.UUID, float]],
        *,
        k: int = 60,
    ) -> tuple[list[uuid.UUID] | None, list[uuid.UUID] | None, dict[uuid.UUID, float]]:
        dense_document_ids, dense_chunk_ids, _dense_scores = dense_hits
        sparse_document_ids, sparse_chunk_ids, _sparse_scores = sparse_hits

        if sparse_document_ids is None:
            return dense_hits
        if dense_document_ids is None:
            return sparse_hits

        dense_chunk_ids = dense_chunk_ids or []
        sparse_chunk_ids = sparse_chunk_ids or []
        fused_scores: dict[uuid.UUID, float] = {}
        chunk_to_document: dict[uuid.UUID, uuid.UUID] = {}

        for rank, chunk_id in enumerate(dense_chunk_ids, start=1):
            fused_scores[chunk_id] = fused_scores.get(chunk_id, 0.0) + (1.0 / (k + rank))
        for rank, chunk_id in enumerate(sparse_chunk_ids, start=1):
            fused_scores[chunk_id] = fused_scores.get(chunk_id, 0.0) + (1.0 / (k + rank))

        if not fused_scores:
            return [], [], {}

        dense_doc_map = dict(zip(dense_chunk_ids, dense_document_ids or [], strict=False))
        sparse_doc_map = dict(zip(sparse_chunk_ids, sparse_document_ids or [], strict=False))
        chunk_to_document.update(dense_doc_map)
        chunk_to_document.update(sparse_doc_map)

        ranked_chunk_ids = sorted(fused_scores, key=lambda chunk_id: fused_scores[chunk_id], reverse=True)
        ranked_document_ids: list[uuid.UUID] = []
        for chunk_id in ranked_chunk_ids:
            document_id = chunk_to_document.get(chunk_id)
            if document_id is not None and document_id not in ranked_document_ids:
                ranked_document_ids.append(document_id)
        return ranked_document_ids, ranked_chunk_ids, fused_scores

    async def _sparse_ranked_document_ids(
        self,
        project_id: uuid.UUID,
        *,
        question: str,
        scope_type: str | None,
        scope_id: str | None,
        entity_id: str | None,
        snapshot_date: str | None,
        tags: list[str] | None,
        acl: list[str] | None,
        collections: list[str | None],
    ) -> tuple[list[uuid.UUID] | None, list[uuid.UUID] | None, dict[uuid.UUID, float]]:
        project = await self.session.get(RagProject, project_id)
        if project is None:
            return [], [], {}

        sparse_query = encode_sparse_text(question)
        if not sparse_query["indices"]:
            return None, None, {}

        if not hasattr(self.vector_store, "search_sparse_chunks"):
            return None, None, {}

        collection_hits = []
        for collection_name in collections:
            store = self._vector_store_for(collection_name)
            if not hasattr(store, "search_sparse_chunks"):
                continue
            try:
                try:
                    search_results = await store.search_sparse_chunks(
                        sparse_query=sparse_query,
                        tenant_id=str(project.tenant_id),
                        scope_type=scope_type,
                        scope_id=scope_id,
                        entity_id=entity_id,
                        snapshot_date=snapshot_date,
                        tags=tags,
                        acl=acl,
                        limit=6,
                    )
                except TypeError:
                    search_results = await store.search_sparse_chunks(
                        sparse_query=sparse_query,
                        tenant_id=str(project.tenant_id),
                        scope_type=scope_type,
                        scope_id=scope_id,
                        entity_id=entity_id,
                        snapshot_date=snapshot_date,
                        tags=tags,
                        limit=6,
                    )
            except httpx.HTTPError:
                continue
            collection_hits.append(self._collect_ranked_hits(search_results))
        if not collection_hits:
            return None, None, {}
        return self._merge_collection_hit_sets(collection_hits)

    def _vector_store_for(self, collection_name: str | None):
        if collection_name is None:
            return self.vector_store
        return self.vector_store_factory(collection_name)

    def _merge_collection_hit_sets(
        self,
        hit_sets: list[tuple[list[uuid.UUID] | None, list[uuid.UUID] | None, dict[uuid.UUID, float]]],
    ) -> tuple[list[uuid.UUID] | None, list[uuid.UUID] | None, dict[uuid.UUID, float]]:
        if len(hit_sets) == 1:
            return hit_sets[0]

        merged_scores: dict[uuid.UUID, float] = {}
        chunk_to_document: dict[uuid.UUID, uuid.UUID] = {}
        for document_ids, chunk_ids, _scores in hit_sets:
            if document_ids is None or chunk_ids is None:
                continue
            for rank, chunk_id in enumerate(chunk_ids, start=1):
                merged_scores[chunk_id] = merged_scores.get(chunk_id, 0.0) + (1.0 / (60 + rank))
            chunk_to_document.update(dict(zip(chunk_ids, document_ids, strict=False)))

        ranked_chunk_ids = sorted(merged_scores, key=lambda chunk_id: merged_scores[chunk_id], reverse=True)
        ranked_document_ids: list[uuid.UUID] = []
        for chunk_id in ranked_chunk_ids:
            document_id = chunk_to_document.get(chunk_id)
            if document_id is not None and document_id not in ranked_document_ids:
                ranked_document_ids.append(document_id)
        if not ranked_chunk_ids:
            return [], [], {}
        return ranked_document_ids, ranked_chunk_ids, merged_scores

    def _collect_ranked_hits(
        self,
        search_results: list[dict[str, object]],
    ) -> tuple[list[uuid.UUID], list[uuid.UUID], dict[uuid.UUID, float]]:
        ranked_document_ids: list[uuid.UUID] = []
        ranked_chunk_ids: list[uuid.UUID] = []
        chunk_scores: dict[uuid.UUID, float] = {}
        for result in search_results:
            document_id = result.get("document_id")
            if document_id is None:
                continue
            chunk_id = result.get("chunk_id")
            parsed_document_id = uuid.UUID(str(document_id))
            if parsed_document_id not in ranked_document_ids:
                ranked_document_ids.append(parsed_document_id)
            if chunk_id is not None:
                try:
                    parsed_chunk_id = uuid.UUID(str(chunk_id))
                except ValueError:
                    parsed_chunk_id = None
                if parsed_chunk_id is not None and parsed_chunk_id not in ranked_chunk_ids:
                    ranked_chunk_ids.append(parsed_chunk_id)
                    chunk_scores[parsed_chunk_id] = float(result.get("score") or 0.0)
        return ranked_document_ids, ranked_chunk_ids, chunk_scores

    async def _build_sources(
        self,
        question: str,
        documents: list[RagDocument],
        ranked_chunk_ids: list[uuid.UUID] | None,
        chunk_scores: dict[uuid.UUID, float],
    ) -> list[dict[str, object]]:
        chunk_map = {}
        parent_map = {}
        if ranked_chunk_ids:
            chunks = await self.repository.get_chunks_by_ids(ranked_chunk_ids)
            chunk_map = {chunk.id: chunk for chunk in chunks}
            parent_ids = [
                chunk.parent_chunk_id
                for chunk in chunks
                if chunk.parent_chunk_id is not None
            ]
            if parent_ids:
                parents = await self.repository.get_chunks_by_ids(parent_ids)
                parent_map = {chunk.id: chunk for chunk in parents}

        sources: list[dict[str, object]] = []
        used_document_ids: set[uuid.UUID] = set()
        for document in documents:
            if document.id in used_document_ids:
                continue
            used_document_ids.add(document.id)
            matching_chunk = next(
                (
                    chunk_map[chunk_id]
                    for chunk_id in ranked_chunk_ids or []
                    if chunk_id in chunk_map and chunk_map[chunk_id].document_id == document.id
                ),
                None,
            )
            snippet = self._snippet_for(question, document, matching_chunk_content=getattr(matching_chunk, "content", None))
            entry: dict[str, object] = {
                "document_id": str(document.id),
                "title": document.title or document.source_ref,
                "source_ref": document.source_ref,
                "snippet": snippet,
            }
            if matching_chunk is not None:
                entry["chunk_id"] = str(matching_chunk.id)
                entry["page_number"] = matching_chunk.page_number
                entry["section_title"] = matching_chunk.section_title
                entry["score"] = chunk_scores.get(matching_chunk.id)
                entry["acl"] = list(matching_chunk.acl or [])
                if matching_chunk.parent_chunk_id is not None and matching_chunk.parent_chunk_id in parent_map:
                    entry["resolved_chunk_id"] = str(matching_chunk.parent_chunk_id)
                    entry["parent_context"] = (parent_map[matching_chunk.parent_chunk_id].content or "").strip()
            sources.append(entry)
        return sources

    async def _maybe_rerank_sources(
        self,
        question: str,
        source_entries: list[dict[str, object]],
        *,
        project_config: dict[str, object],
        top_n: int,
    ) -> tuple[list[dict[str, object]], bool]:
        settings = get_settings()
        if not source_entries:
            return source_entries, False
        if not settings.cohere_api_key.strip():
            return source_entries, False
        if not bool(project_config.get("use_reranker", True)):
            return source_entries, False

        documents = [self._rerank_document_text(source) for source in source_entries]
        try:
            results = await self.reranker.rerank(
                query=question,
                documents=documents,
                top_n=min(len(documents), top_n),
            )
        except httpx.HTTPError:
            return source_entries, False

        reranked_sources: list[dict[str, object]] = []
        used_indices: set[int] = set()
        for result in results:
            index = int(result["index"])
            if index < 0 or index >= len(source_entries):
                continue
            used_indices.add(index)
            reranked = dict(source_entries[index])
            reranked["score"] = float(result["score"])
            reranked_sources.append(reranked)
        reranked_sources.extend(
            source for idx, source in enumerate(source_entries) if idx not in used_indices
        )
        return reranked_sources, True

    def _resolve_retrieval_config(
        self,
        project_config: dict[str, object],
        retrieval_mode: str,
    ) -> dict[str, object]:
        resolved = {
            "top_k": 3,
            "candidate_limit": 8,
            "rerank_top_n": 8,
            "score_threshold": 0.0,
        }
        for key in ("top_k", "candidate_limit", "rerank_top_n", "score_threshold"):
            if key in project_config:
                resolved[key] = project_config[key]

        retrieval_overrides = project_config.get("retrieval", {})
        if isinstance(retrieval_overrides, dict):
            mode_overrides = retrieval_overrides.get(retrieval_mode, {})
            if isinstance(mode_overrides, dict):
                for key in ("top_k", "candidate_limit", "rerank_top_n", "score_threshold"):
                    if key in mode_overrides:
                        resolved[key] = mode_overrides[key]
        return resolved

    def _apply_score_threshold(
        self,
        source_entries: list[dict[str, object]],
        *,
        threshold: float,
    ) -> list[dict[str, object]]:
        if threshold <= 0 or not source_entries:
            return source_entries
        filtered = [
            source for source in source_entries if float(source.get("score") or 0.0) >= threshold
        ]
        if filtered:
            return filtered
        return source_entries[:1]

    def _apply_negative_filters(
        self,
        source_entries: list[dict[str, object]],
        *,
        exclude_sources: list[str] | None,
        exclude_documents: list[str] | None,
    ) -> list[dict[str, object]]:
        excluded_sources = set(exclude_sources or [])
        excluded_documents = set(exclude_documents or [])
        if not excluded_sources and not excluded_documents:
            return source_entries
        return [
            source
            for source in source_entries
            if str(source.get("source_ref", "")) not in excluded_sources
            and str(source.get("document_id", "")) not in excluded_documents
        ]

    def _apply_acl_filter(
        self,
        source_entries: list[dict[str, object]],
        *,
        acl: list[str] | None,
    ) -> list[dict[str, object]]:
        if not acl:
            return source_entries
        requested_acl = set(acl)
        filtered = [
            source
            for source in source_entries
            if requested_acl.intersection(set(source.get("acl", []) or []))
        ]
        return filtered

    def _rerank_document_text(self, source: dict[str, object]) -> str:
        parts = [
            str(source.get("title", "")).strip(),
            str(source.get("parent_context", "")).strip(),
            str(source.get("snippet", "")).strip(),
        ]
        return "\n\n".join(part for part in parts if part)

    def _fallback_answer(
        self,
        source_entries: list[dict[str, object]],
    ) -> str:
        blocks: list[str] = []
        for source in source_entries:
            snippet = str(source.get("snippet", "")).strip()
            if not snippet:
                continue
            parent_context = str(source.get("parent_context", "")).strip()
            title = str(source.get("title", "")).strip()
            if parent_context:
                blocks.append(f"{title}: {parent_context} {snippet}")
            else:
                blocks.append(snippet)
        return " ".join(blocks)

    def _build_retrieval_context(self, source_entries: list[dict[str, object]]) -> list[dict[str, str]]:
        return [
            {
                "title": str(source.get("title", "")),
                "snippet": str(source.get("snippet", "")),
                "parent_context": str(source.get("parent_context", "")),
                "score": source.get("score"),
            }
            for source in source_entries
            if str(source.get("snippet", "")).strip()
        ]

    def _rank_documents(self, question: str, documents: list[RagDocument]) -> list[tuple[int, RagDocument]]:
        terms = self._query_terms(question)

        def score(document: RagDocument) -> tuple[int, str]:
            haystack = " ".join(
                [
                    (document.title or "").lower(),
                    document.source_ref.lower(),
                    str(document.metadata_json.get("content_text", "")).lower(),
                ]
            )
            return (sum(term in haystack for term in terms), document.source_ref)

        ranked = sorted(documents, key=score, reverse=True)
        return [(score(document)[0], document) for document in ranked]

    def _snippet_for(self, question: str, document: RagDocument, *, matching_chunk_content: str | None = None) -> str:
        content = str(matching_chunk_content or document.metadata_json.get("content_text", "")).strip()
        if not content:
            return ""
        if matching_chunk_content is not None:
            return content

        terms = self._query_terms(question)
        lower_content = content.lower()
        for term in terms:
            index = lower_content.find(term)
            if index >= 0:
                start = max(0, index - 40)
                end = min(len(content), index + 160)
                return content[start:end].strip()
        return content[:180].strip()

    def _query_terms(self, text: str) -> list[str]:
        stopwords = {"the", "and", "for", "with", "what", "when", "where", "this", "that", "rapor", "ne", "icin", "ile", "in"}
        terms: list[str] = []
        for term in re.findall(r"[A-Za-z0-9]+", text.lower()):
            if term in stopwords:
                continue
            if len(term) >= 3 or any(character.isdigit() for character in term):
                terms.append(term)
        return terms
