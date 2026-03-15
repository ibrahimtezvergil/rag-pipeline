from __future__ import annotations

import re
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import RagDocument, RagProject
from app.repositories.ingestion import IngestionRepository
from app.services.embedder import embed_query_text
from app.services.vector_store import QdrantVectorStore


class QueryService:
    def __init__(self, session: AsyncSession, *, vector_store: QdrantVectorStore | None = None):
        self.session = session
        self.repository = IngestionRepository(session)
        self.vector_store = vector_store or QdrantVectorStore()

    async def answer_question(
        self,
        question: str,
        project_id: uuid.UUID,
        *,
        scope_type: str | None = None,
        scope_id: str | None = None,
        entity_id: str | None = None,
        snapshot_date: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, object]:
        query_embedding = await embed_query_text(question)
        retrieval_mode = "metadata_fallback"
        ranked_document_ids, ranked_chunk_ids, chunk_scores = await self._semantic_ranked_document_ids(
            project_id,
            query_vector=list(query_embedding.get("values", [])),
            scope_type=scope_type,
            scope_id=scope_id,
            entity_id=entity_id,
            snapshot_date=snapshot_date,
            tags=tags,
        )
        if ranked_document_ids is not None:
            retrieval_mode = "semantic_qdrant"
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
            top_documents = documents[:3]
        else:
            ranked = self._rank_documents(question, documents)
            top_documents = [document for score, document in ranked if score > 0][:3]
            if not top_documents:
                top_documents = [document for _, document in ranked][:3]

        if not top_documents:
            return {
                "answer": "Bu proje icin sorgulanabilir indexed dokuman bulunamadi.",
                "retrieval_mode": "empty",
                "retrieval_context": [],
                "sources": [],
                "query_embedding": query_embedding,
            }

        source_entries = await self._build_sources(question, top_documents, ranked_chunk_ids, chunk_scores)
        answer = self._compose_answer(top_documents, source_entries)
        if not answer:
            titles = ", ".join(document.title or document.source_ref for document in top_documents)
            answer = f"Ilgili indexed kaynaklar: {titles}"

        return {
            "answer": answer,
            "retrieval_mode": retrieval_mode,
            "retrieval_context": self._build_retrieval_context(source_entries),
            "sources": source_entries,
            "query_embedding": query_embedding,
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
    ) -> tuple[list[uuid.UUID] | None, list[uuid.UUID] | None, dict[uuid.UUID, float]]:
        project = await self.session.get(RagProject, project_id)
        if project is None:
            return [], [], {}

        try:
            search_results = await self.vector_store.search_chunks(
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
            return None, None, {}

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
                if matching_chunk.parent_chunk_id is not None and matching_chunk.parent_chunk_id in parent_map:
                    entry["parent_context"] = (parent_map[matching_chunk.parent_chunk_id].content or "").strip()
            sources.append(entry)
        return sources

    def _compose_answer(
        self,
        documents: list[RagDocument],
        source_entries: list[dict[str, object]],
    ) -> str:
        blocks: list[str] = []
        for document, source in zip(documents, source_entries, strict=False):
            snippet = str(source.get("snippet", "")).strip()
            if not snippet:
                continue
            parent_context = str(source.get("parent_context", "")).strip()
            title = document.title or document.source_ref
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
