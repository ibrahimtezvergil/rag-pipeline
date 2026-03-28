from __future__ import annotations

import hashlib
import uuid
from time import monotonic
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.repositories.ingestion import IngestionRepository
from app.schemas.ingest import IngestRequest
from app.services.audio_metadata import extract_audio_metadata
from app.services.chunking import build_chunks
from app.services.dispatch import IngestionDispatcher, NullIngestionDispatcher
from app.services.embedder import (
    embed_audio_content,
    embed_image_content,
    embed_text_content,
    resolve_pdf_embedding,
)
from app.services.loaders import decode_base64_source, load_source
from app.services.observability import emit_event
from app.services.query_cache import RedisQueryCache
from app.services.sparse_encoder import encode_sparse_text
from app.services.tracing import observe, update_current_observation
from app.services.vector_store import QdrantVectorStore


class IngestionService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        dispatcher: IngestionDispatcher | None = None,
        vector_store: QdrantVectorStore | None = None,
        query_cache: RedisQueryCache | None = None,
    ):
        self.repository = IngestionRepository(session)
        self.dispatcher = dispatcher or NullIngestionDispatcher()
        self.vector_store = vector_store or QdrantVectorStore()
        self.query_cache = query_cache or RedisQueryCache()

    @observe(name="ingestion-service", as_type="chain")
    async def create_ingestion_job(
        self,
        payload: IngestRequest,
        application_id: uuid.UUID,
    ) -> dict[str, str]:
        project = await self.repository.get_application(application_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        source_ref = self._source_ref(payload)
        previous_document = await self.repository.get_latest_document_by_source_ref(project.id, source_ref)
        version = (int(previous_document.version) + 1) if previous_document is not None else 1
        initial_status = "indexing" if payload.mode == "sync" else "pending"
        job_status = "running" if payload.mode == "sync" else "pending"
        document = await self.repository.create_document(
            application_id=project.id,
            tenant_id=project.tenant_id,
            source_type=payload.source_type,
            source_ref=source_ref,
            status=initial_status,
            title=self._derive_title(payload),
            content_hash=self._content_hash(source_ref),
            version=version,
            previous_document_id=previous_document.id if previous_document is not None else None,
            source_connector_id=uuid.UUID(payload.source_connector_id) if payload.source_connector_id else None,
            metadata={
                "ingest_mode": payload.mode,
                **({"source_base64": payload.source_base64} if payload.source_base64 else {}),
                **({"source_sql": payload.source_sql} if payload.source_sql else {}),
                **({"title": payload.title} if payload.title else {}),
                **({"records": payload.records} if payload.records else {}),
                **({"cursor_state": payload.cursor_state} if payload.cursor_state else {}),
                **({"callback_url": str(payload.callback_url)} if payload.callback_url else {}),
                **({"origin": payload.origin} if payload.origin else {}),
                **({"scope_type": payload.scope_type} if payload.scope_type else {}),
                **({"scope_id": payload.scope_id} if payload.scope_id else {}),
                **({"entity_type": payload.entity_type} if payload.entity_type else {}),
                **({"entity_id": payload.entity_id} if payload.entity_id else {}),
                **({"record_ids": payload.record_ids} if payload.record_ids else {}),
                **({"snapshot_date": payload.snapshot_date} if payload.snapshot_date else {}),
                **({"tags": payload.tags} if payload.tags else {}),
                **({"acl": payload.acl} if payload.acl else {}),
            },
        )
        job = await self.repository.create_job(
            document_id=document.id,
            status=job_status,
        )
        update_current_observation(
            metadata={
                "tenant_id": str(project.tenant_id),
                "application_id": str(project.id),
                "document_id": str(document.id),
                "source_type": payload.source_type,
                "mode": payload.mode,
            }
        )

        if payload.mode == "sync":
            try:
                await self._process_document_job(
                    document,
                    job,
                    retry_count=0,
                )
            except Exception as exc:
                await self.repository.update_document_status(document, "failed")
                await self.repository.update_job_status(
                    job,
                    "failed",
                    retry_count=0,
                    error_message=str(exc),
                    completed=True,
                )
                await self.repository.commit()
                raise
        else:
            await self.dispatcher.enqueue(
                {
                    "document_id": str(document.id),
                    "ingestion_job_id": str(job.id),
                    "application_id": str(project.id),
                    "source_type": payload.source_type,
                    "source_ref": self._source_ref(payload),
                    **({"callback_url": str(payload.callback_url)} if payload.callback_url else {}),
                }
            )

        await self.repository.commit()

        return {
            "document_id": str(document.id),
            "ingestion_job_id": str(job.id),
            "status": job.status,
            "mode": payload.mode,
            "source_type": payload.source_type,
        }

    async def create_ingestion_batch(
        self,
        payloads: list[IngestRequest],
        application_id: uuid.UUID,
    ) -> list[dict[str, str]]:
        if any(payload.mode != "async" for payload in payloads):
            raise HTTPException(status_code=400, detail="Batch ingestion only supports async mode")

        results: list[dict[str, str]] = []
        for payload in payloads:
            result = await self.create_ingestion_job(payload, application_id)
            results.append(result)
        return results

    async def get_ingestion_job(self, job_id: str) -> dict[str, str]:
        job_uuid = self._parse_uuid(job_id, "Invalid ingestion job id")
        job = await self.repository.get_job(job_uuid)
        if job is None:
            raise HTTPException(status_code=404, detail="Ingestion job not found")

        document = None
        if job.document_id is not None:
            document = await self.repository.get_document(job.document_id)

        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")

        return {
            "document_id": str(document.id),
            "ingestion_job_id": str(job.id),
            "status": self._public_job_status(job.status, document.status),
            "job_type": job.job_type,
            "source_type": document.source_type,
        }

    async def process_ingestion_job(self, job_id: str, *, retry_count: int = 0) -> dict[str, str]:
        job_uuid = self._parse_uuid(job_id, "Invalid ingestion job id")
        job = await self.repository.get_job(job_uuid)
        if job is None:
            raise HTTPException(status_code=404, detail="Ingestion job not found")
        if job.document_id is None:
            raise HTTPException(status_code=404, detail="Document not found")

        document = await self.repository.get_document(job.document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")

        await self._process_document_job(document, job, retry_count=retry_count)
        return {
            "document_id": str(document.id),
            "ingestion_job_id": str(job.id),
            "status": job.status,
        }

    async def record_retry(self, job_id: str, *, retry_count: int, error_message: str) -> None:
        job, document = await self._get_job_with_document(job_id)
        await self.repository.update_document_status(document, "pending")
        await self.repository.update_job_status(
            job,
            "pending",
            retry_count=retry_count,
            error_message=error_message,
        )
        await self.repository.commit()

    async def record_failure(self, job_id: str, *, retry_count: int, error_message: str) -> None:
        job, document = await self._get_job_with_document(job_id)
        await self.repository.update_document_status(document, "failed")
        await self.repository.update_job_status(
            job,
            "failed",
            retry_count=retry_count,
            error_message=error_message,
            completed=True,
        )
        await self.repository.commit()

    async def delete_ingestion_job(self, job_id: str) -> dict[str, object]:
        job_uuid = self._parse_uuid(job_id, "Invalid ingestion job id")
        job = await self.repository.get_job(job_uuid)
        if job is None:
            raise HTTPException(status_code=404, detail="Ingestion job not found")
        if job.document_id is None:
            raise HTTPException(status_code=404, detail="Document not found")

        document = await self.repository.get_document(job.document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")

        chunks = await self.repository.get_document_chunks(document.id)
        await self.repository.soft_delete_document(document)
        await self.repository.archive_chunks(chunks)
        point_ids = [str(chunk.qdrant_point_id) for chunk in chunks if chunk.qdrant_point_id is not None]
        await self.vector_store.delete_points(point_ids)
        await self.repository.commit()
        await self.query_cache.invalidate_application(str(document.application_id))

        return {
            "document_id": str(document.id),
            "ingestion_job_id": str(job.id),
            "archived_chunk_count": len(chunks),
            "qdrant_point_ids": point_ids,
        }

    async def requeue_stale_documents(self, *, limit: int = 100) -> dict[str, int]:
        current_embed_version = self._current_embed_version()
        latest_documents = await self.repository.list_latest_documents()
        stale_document_count = 0

        for document in latest_documents:
            if stale_document_count >= limit:
                break
            if document.status != "indexed":
                continue

            child_chunks = await self.repository.get_child_chunks(document.id)
            if not child_chunks:
                continue
            if all((chunk.embed_version or "") == current_embed_version for chunk in child_chunks):
                continue

            payload = self._payload_from_document(document)
            await self.create_ingestion_job(payload, document.application_id)
            stale_document_count += 1

        return {"stale_document_count": stale_document_count}

    def _parse_uuid(self, raw_value: str, detail: str) -> uuid.UUID:
        try:
            return uuid.UUID(raw_value)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=detail) from exc

    def _derive_title(self, payload: IngestRequest) -> str:
        if payload.title:
            return payload.title
        if payload.source_filename:
            return payload.source_filename
        if payload.source_type == "db":
            return "SQL Query Result"
        assert payload.source_ref is not None
        path = Path(str(payload.source_ref))
        return path.name or str(payload.source_ref)

    def _content_hash(self, source_ref: str) -> str:
        return hashlib.sha256(source_ref.encode("utf-8")).hexdigest()

    def _current_embed_version(self) -> str:
        settings = get_settings()
        return f"{settings.embed_model}-{settings.embed_dimension}"

    def _source_ref(self, payload: IngestRequest) -> str:
        if payload.source_ref is not None:
            return str(payload.source_ref)
        if payload.records is not None:
            return "inline://structured-records"
        if payload.source_sql is not None:
            return "inline://sql-query"
        assert payload.source_filename is not None
        return f"inline://{payload.source_filename}"

    def _payload_from_document(self, document) -> IngestRequest:
        metadata = dict(document.metadata_json or {})
        source_ref = None if str(document.source_ref).startswith("inline://") else str(document.source_ref)
        source_filename = None
        if str(document.source_ref).startswith("inline://"):
            source_filename = str(document.source_ref).removeprefix("inline://")
        return IngestRequest.model_validate(
            {
                "source_type": document.source_type,
                "source_ref": source_ref,
                "source_base64": metadata.get("source_base64"),
                "source_filename": source_filename,
                "source_sql": metadata.get("source_sql"),
                "title": metadata.get("title") or document.title,
                "records": metadata.get("records"),
                "callback_url": metadata.get("callback_url"),
                "origin": metadata.get("origin"),
                "scope_type": metadata.get("scope_type"),
                "scope_id": metadata.get("scope_id"),
                "entity_type": metadata.get("entity_type"),
                "entity_id": metadata.get("entity_id"),
                "record_ids": metadata.get("record_ids"),
                "snapshot_date": metadata.get("snapshot_date"),
                "source_connector_id": (
                    str(document.source_connector_id) if document.source_connector_id else None
                ),
                "cursor_state": metadata.get("cursor_state"),
                "tags": metadata.get("tags"),
                "acl": metadata.get("acl"),
                "mode": "async",
            }
        )

    async def _find_semantic_duplicate(
        self,
        document,
        embedding: dict[str, object],
    ) -> dict[str, object] | None:
        vector = embedding.get("values")
        if not isinstance(vector, list) or not vector:
            return None
        settings = get_settings()
        return await self.vector_store.find_semantic_duplicate(
            query_vector=vector,
            tenant_id=str(document.tenant_id),
            scope_type=document.metadata_json.get("scope_type", "project"),
            scope_id=document.metadata_json.get("scope_id", str(document.application_id)),
            entity_id=document.metadata_json.get("entity_id"),
            snapshot_date=document.metadata_json.get("snapshot_date"),
            tags=document.metadata_json.get("tags"),
            acl=document.metadata_json.get("acl"),
            threshold=settings.semantic_dedup_similarity_threshold,
        )

    def _public_job_status(self, job_status: str, document_status: str) -> str:
        if job_status == "failed":
            return "failed"
        if document_status in {"pending", "indexing", "indexed", "failed"}:
            return document_status
        if job_status == "running":
            return "indexing"
        if job_status == "completed":
            return "indexed"
        return job_status

    async def _process_document_job(self, document, job, *, retry_count: int) -> None:
        started = monotonic()
        await self.repository.update_document_status(document, "indexing")
        await self.repository.update_job_status(
            job,
            "running",
            retry_count=retry_count,
            error_message=None,
        )
        await self.repository.commit()

        source_bytes = None
        source_filename = None
        if document.source_ref.startswith("inline://"):
            source_filename = document.source_ref.removeprefix("inline://")
            if document.source_type == "db":
                loaded = await load_source(
                    document.source_type,
                    None,
                    source_sql=str(document.metadata_json.get("source_sql")),
                )
            elif document.source_type == "structured":
                loaded = await load_source(
                    document.source_type,
                    None,
                    title=str(document.metadata_json.get("title") or document.title or "Structured Records"),
                    records=list(document.metadata_json.get("records") or []),
                    scope_type=document.metadata_json.get("scope_type"),
                    scope_id=document.metadata_json.get("scope_id"),
                    entity_type=document.metadata_json.get("entity_type"),
                    origin=document.metadata_json.get("origin"),
                    entity_id=document.metadata_json.get("entity_id"),
                    record_ids=document.metadata_json.get("record_ids"),
                    snapshot_date=document.metadata_json.get("snapshot_date"),
                    tags=document.metadata_json.get("tags"),
                )
            else:
                source_bytes = decode_base64_source(str(document.metadata_json.get("source_base64")))
                loaded = await load_source(
                    document.source_type,
                    None,
                    source_bytes=source_bytes,
                    source_filename=source_filename,
                )
        else:
            loaded = await load_source(document.source_type, document.source_ref)
        document_metadata = {
            **(document.metadata_json or {}),
            "loader": loaded["metadata"],
            "content_text": str(loaded.get("content", ""))[:5000],
        }
        document.content_hash = self._content_hash(str(loaded.get("content", "")))
        if (
            document.source_type == "pdf"
            and loaded["metadata"].get("loader_strategy") in {"direct_small_pdf", "gemini_direct_pdf"}
        ):
            document_metadata["embedding"] = await resolve_pdf_embedding(
                document.source_ref,
                str(loaded.get("content", "")),
                loaded["metadata"],
            )
        if document.source_type == "image":
            document_metadata["embedding"] = await embed_image_content(
                image_bytes=loaded["image_bytes"],
                title=str(loaded["metadata"]["title"]),
                mime_type=str(loaded["metadata"]["mime_type"]),
            )
            loaded["embedding"] = document_metadata["embedding"]

        previous_child_snapshot = await self._load_previous_child_snapshot(document.previous_document_id)
        await self.vector_store.ensure_collection()
        chunk_rows, vector_chunk_indices, diff_entries = await self._build_chunk_rows(
            document,
            loaded,
            previous_child_snapshot=previous_child_snapshot,
        )
        document_metadata["loader"] = loaded["metadata"]
        if loaded["metadata"].get("audio_metadata") is not None:
            document_metadata["audio_metadata"] = loaded["metadata"]["audio_metadata"]
        chunks = await self.repository.create_chunks(chunk_rows)
        update_related_chunk_ids = getattr(self.repository, "update_related_chunk_ids", None)
        if update_related_chunk_ids is not None:
            await update_related_chunk_ids(self._build_related_chunk_map(chunks))
        vector_chunks = [chunks[index] for index in vector_chunk_indices]
        vector_rows = [chunk_rows[index] for index in vector_chunk_indices]
        embed_ms = max(0, int((monotonic() - started) * 1000))
        point_ids = await self.vector_store.upsert_chunks(
            [
                {
                    "document_id": str(document.id),
                    "chunk_id": str(chunk.id),
                    "tenant_id": str(document.tenant_id),
                    "scope_type": document.metadata_json.get("scope_type", "project"),
                    "scope_id": document.metadata_json.get("scope_id", str(document.application_id)),
                    "origin": document.metadata_json.get("origin"),
                    "entity_type": document.metadata_json.get("entity_type"),
                    "entity_id": document.metadata_json.get("entity_id"),
                    "record_ids": document.metadata_json.get("record_ids", []),
                    "snapshot_date": document.metadata_json.get("snapshot_date"),
                    "tags": document.metadata_json.get("tags", []),
                    "source_type": document.source_type,
                    "modality": chunk.modality,
                    "page_number": chunk.page_number,
                    "acl": chunk.acl,
                    "content": row["content"],
                    "vector": row["vector"],
                    "sparse_vector": row.get("sparse_vector"),
                }
                for chunk, row in zip(vector_chunks, vector_rows, strict=False)
            ]
        )
        await self.repository.attach_qdrant_point_ids(vector_chunks, point_ids)
        await self.repository.create_chunk_diff_logs(
            job.id,
            self._resolve_diff_chunk_ids(diff_entries, chunks, chunk_rows),
        )
        for row_index, (chunk, row) in enumerate(zip(vector_chunks, vector_rows, strict=False)):
            emit_event(
                "ingestion.chunk_indexed",
                {
                    "tenant_id": str(document.tenant_id),
                    "application_id": str(document.application_id),
                    "document_id": str(document.id),
                    "chunk_id": str(chunk.id),
                    "chunk_index": row_index,
                    "modality": chunk.modality,
                    "embed_ms": embed_ms,
                    "token_count": (len(str(row.get("content", "")).strip()) // 4) or None,
                    "vector_dimension": int(row.get("dimension") or len(row.get("vector", []))),
                },
            )
        await self.repository.update_document_after_load(
            document,
            status="indexed",
            title=str(loaded["metadata"]["title"]),
            chunk_count=len(vector_chunks),
            metadata=document_metadata,
            embed_model=str(vector_rows[0]["embed_model"]) if vector_rows else None,
        )
        await self.repository.update_job_status(
            job,
            "completed",
            retry_count=retry_count,
            error_message=None,
            chunks_processed=len(vector_chunks),
            duration_ms=int((monotonic() - started) * 1000),
            completed=True,
        )
        await self.repository.commit()
        await self._update_sync_checkpoint(document)
        await self._supersede_previous_document(document.previous_document_id)
        await self.query_cache.invalidate_application(str(document.application_id))

    def _build_related_chunk_map(self, chunks) -> dict[uuid.UUID, list[uuid.UUID]]:
        child_chunks = [chunk for chunk in chunks if getattr(chunk, "parent_chunk_id", None) is not None]
        by_parent: dict[uuid.UUID, list[object]] = {}
        by_section: dict[str, list[object]] = {}
        for chunk in sorted(child_chunks, key=lambda item: int(item.chunk_index)):
            by_parent.setdefault(chunk.parent_chunk_id, []).append(chunk)
            section_title = str(getattr(chunk, "section_title", "") or "").strip().lower()
            if section_title:
                by_section.setdefault(section_title, []).append(chunk)

        relation_map: dict[uuid.UUID, list[uuid.UUID]] = {}
        for chunk in child_chunks:
            related_ids: list[uuid.UUID] = []
            siblings = by_parent.get(chunk.parent_chunk_id, [])
            for sibling in siblings:
                if sibling.id == chunk.id:
                    continue
                if abs(int(sibling.chunk_index) - int(chunk.chunk_index)) <= 1 and sibling.id not in related_ids:
                    related_ids.append(sibling.id)
            section_title = str(getattr(chunk, "section_title", "") or "").strip().lower()
            if section_title:
                for related in by_section.get(section_title, []):
                    if related.id == chunk.id or related.id in related_ids:
                        continue
                    related_ids.append(related.id)
            if related_ids:
                relation_map[chunk.id] = related_ids[:2]
        return relation_map

    async def _get_job_with_document(self, job_id: str):
        job_uuid = self._parse_uuid(job_id, "Invalid ingestion job id")
        job = await self.repository.get_job(job_uuid)
        if job is None:
            raise HTTPException(status_code=404, detail="Ingestion job not found")
        if job.document_id is None:
            raise HTTPException(status_code=404, detail="Document not found")

        document = await self.repository.get_document(job.document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return job, document

    async def _build_chunk_rows(
        self,
        document,
        loaded: dict[str, object],
        *,
        previous_child_snapshot: dict[str, dict[str, object]] | None = None,
    ) -> tuple[list[dict[str, object]], list[int], list[dict[str, object]]]:
        content = str(loaded.get("content", "")).strip()
        metadata = loaded["metadata"]
        title = str(metadata.get("title") or document.title or document.source_ref)
        if document.source_type == "image":
            embedding = loaded.get("embedding") or loaded["metadata"].get("embedding")
            if embedding is None:
                embedding = await embed_image_content(
                    image_bytes=loaded["image_bytes"],
                    title=title,
                    mime_type=str(metadata["mime_type"]),
                )
            parent_row = {
                "document_id": document.id,
                "chunk_index": 0,
                "parent_chunk_id": None,
                "modality": "image",
                "token_count": len(content.split()) if content else 0,
                "page_number": None,
                "bbox": None,
                "section_title": title,
                "acl": list(document.metadata_json.get("acl", [])),
                "embed_model": None,
                "embed_version": None,
                "dimension": 0,
                "content_hash": self._content_hash(content or title),
                "content": content or title,
                "vector": [],
            }
            vector_row = {
                "document_id": document.id,
                "chunk_index": 1,
                "parent_chunk_id": "__PARENT_INDEX__:0",
                "modality": "image",
                "token_count": len(content.split()) if content else 0,
                "page_number": None,
                "bbox": None,
                "section_title": title,
                "acl": list(document.metadata_json.get("acl", [])),
                "embed_model": str(embedding.get("model") or ""),
                "embed_version": str(embedding.get("embed_version") or "v1"),
                "dimension": int(embedding.get("dimension") or len(embedding.get("values", []))),
                "content_hash": self._content_hash(content or title),
                "content": content or title,
                "vector": embedding["values"],
            }
            return [parent_row, vector_row], [1], []
        if document.source_type == "audio":
            chunk_rows: list[dict[str, object]] = []
            vector_chunk_indices: list[int] = []
            audio_bytes = loaded["audio_bytes"]
            mime_type = str(metadata["mime_type"])
            metadata["audio_metadata"] = await self._extract_audio_metadata(
                audio_bytes=audio_bytes,
                filename=title,
            )
            for clip in list(metadata.get("clips") or []):
                clip_label = f"{title} clip {clip['clip_index'] + 1}"
                clip_summary = self._audio_clip_content(
                    title=title,
                    clip=clip,
                    audio_metadata=dict(metadata.get("audio_metadata") or {}),
                )
                parent_index = len(chunk_rows)
                chunk_rows.append(
                    {
                        "document_id": document.id,
                        "chunk_index": len(chunk_rows),
                        "parent_chunk_id": None,
                        "modality": "audio",
                        "token_count": 0,
                        "page_number": None,
                        "bbox": None,
                        "section_title": clip_label,
                        "acl": [],
                        "embed_model": None,
                        "embed_version": None,
                        "dimension": 0,
                        "content_hash": self._content_hash(clip_summary),
                        "content": clip_summary,
                        "vector": [],
                    }
                )
                embedding = await embed_audio_content(
                    audio_bytes=audio_bytes,
                    title=clip_label,
                    mime_type=mime_type,
                )
                vector_chunk_indices.append(len(chunk_rows))
                chunk_rows.append(
                    {
                        "document_id": document.id,
                        "chunk_index": len(chunk_rows),
                        "parent_chunk_id": "__PARENT_INDEX__:" + str(parent_index),
                        "modality": "audio",
                        "token_count": 0,
                        "page_number": None,
                        "bbox": None,
                        "section_title": clip_label,
                        "acl": [],
                        "embed_model": str(embedding.get("model") or ""),
                        "embed_version": str(embedding.get("embed_version") or "v1"),
                        "dimension": int(embedding.get("dimension") or len(embedding.get("values", []))),
                        "content_hash": self._content_hash(clip_summary),
                        "content": clip_summary,
                        "vector": embedding["values"],
                    }
                )
            return chunk_rows, vector_chunk_indices, []

        raw_chunks = build_chunks(document.source_type, content, metadata)
        chunk_rows: list[dict[str, object]] = []
        vector_chunk_indices: list[int] = []
        diff_entries: list[dict[str, object]] = []
        previous_child_snapshot = previous_child_snapshot or {}
        seen_hashes: set[str] = set()
        for raw_chunk in raw_chunks:
            content_hash = self._content_hash(raw_chunk["content"])
            seen_hashes.add(content_hash)
            parent_row_index = len(chunk_rows)
            parent_row = {
                "document_id": document.id,
                "chunk_index": len(chunk_rows),
                "parent_chunk_id": None,
                "modality": "text",
                "token_count": len(raw_chunk["content"].split()),
                "page_number": raw_chunk.get("page_number"),
                "bbox": raw_chunk.get("bbox"),
                "section_title": title,
                "acl": list(document.metadata_json.get("acl", [])),
                "embed_model": None,
                "embed_version": None,
                "dimension": 0,
                "content_hash": content_hash,
                "content": raw_chunk["content"],
                "vector": [],
            }
            chunk_rows.append(parent_row)
            previous_match = previous_child_snapshot.get(content_hash)
            if previous_match is not None and previous_match.get("vector") is not None:
                embedding = {
                    "values": previous_match["vector"],
                    "model": previous_match.get("embed_model") or "",
                    "embed_version": previous_match.get("embed_version") or "v1",
                    "dimension": previous_match.get("dimension") or len(previous_match["vector"]),
                }
                operation = "unchanged"
            else:
                embedding = await embed_text_content(raw_chunk["content"], title)
                duplicate_match = await self._find_semantic_duplicate(document, embedding)
                if duplicate_match is not None:
                    continue
                operation = "modified" if document.previous_document_id is not None else "new"
            vector_chunk_indices.append(len(chunk_rows))
            chunk_rows.append(
                {
                    "document_id": document.id,
                    "chunk_index": len(chunk_rows),
                    "parent_chunk_id": "__PARENT_INDEX__:" + str(parent_row_index),
                    "modality": "text",
                    "token_count": len(raw_chunk["content"].split()),
                    "page_number": raw_chunk.get("page_number"),
                    "bbox": raw_chunk.get("bbox"),
                    "section_title": title,
                    "acl": list(document.metadata_json.get("acl", [])),
                    "embed_model": str(embedding.get("model") or ""),
                    "embed_version": str(embedding.get("embed_version") or "v1"),
                    "dimension": int(embedding.get("dimension") or len(embedding.get("values", []))),
                    "content_hash": content_hash,
                    "content": raw_chunk["content"],
                    "vector": embedding["values"],
                    "sparse_vector": encode_sparse_text(raw_chunk["content"]),
                }
            )
            diff_entries.append(
                {
                    "chunk_row_index": len(chunk_rows) - 1,
                    "operation": operation,
                }
            )

        for previous_hash, previous_match in previous_child_snapshot.items():
            if previous_hash not in seen_hashes:
                diff_entries.append(
                    {
                        "chunk_id": previous_match["chunk_id"],
                        "operation": "deleted",
                    }
                )

        return chunk_rows, vector_chunk_indices, diff_entries

    async def _supersede_previous_document(self, previous_document_id: uuid.UUID | None) -> None:
        if previous_document_id is None:
            return

        previous_document = await self.repository.get_document(previous_document_id)
        if previous_document is None:
            return

        previous_chunks = await self.repository.get_document_chunks(previous_document.id)
        await self.repository.archive_chunks(previous_chunks)
        await self.repository.supersede_document(previous_document)
        point_ids = [
            str(chunk.qdrant_point_id)
            for chunk in previous_chunks
            if chunk.qdrant_point_id is not None
        ]
        await self.vector_store.delete_points(point_ids)
        await self.repository.commit()

    async def _load_previous_child_snapshot(
        self,
        previous_document_id: uuid.UUID | None,
    ) -> dict[str, dict[str, object]]:
        if previous_document_id is None:
            return {}

        previous_chunks = await self.repository.get_document_chunks(previous_document_id)
        child_chunks = [
            chunk
            for chunk in previous_chunks
            if chunk.parent_chunk_id is not None and chunk.modality == "text" and chunk.content_hash
        ]
        point_ids = [str(chunk.qdrant_point_id) for chunk in child_chunks if chunk.qdrant_point_id is not None]
        vectors = await self.vector_store.fetch_dense_vectors(point_ids)
        snapshot: dict[str, dict[str, object]] = {}
        for chunk in child_chunks:
            point_id = str(chunk.qdrant_point_id) if chunk.qdrant_point_id is not None else None
            snapshot[str(chunk.content_hash)] = {
                "chunk_id": chunk.id,
                "embed_model": chunk.embed_model,
                "embed_version": chunk.embed_version,
                "dimension": chunk.dimension,
                "vector": vectors.get(point_id) if point_id is not None else None,
            }
        return snapshot

    def _resolve_diff_chunk_ids(self, diff_entries, chunks, chunk_rows):
        resolved: list[dict[str, object]] = []
        row_index_to_chunk_id = {
            int(row["chunk_index"]): chunk.id
            for row, chunk in zip(chunk_rows, chunks, strict=False)
        }
        for entry in diff_entries:
            if entry.get("chunk_id") is not None:
                resolved.append(entry)
                continue
            chunk_row_index = entry.get("chunk_row_index")
            resolved.append(
                {
                    "chunk_id": row_index_to_chunk_id.get(int(chunk_row_index)) if chunk_row_index is not None else None,
                    "operation": entry["operation"],
                }
            )
        return resolved

    async def _update_sync_checkpoint(self, document) -> None:
        source_connector_id = getattr(document, "source_connector_id", None)
        if source_connector_id is None:
            return

        cursor_state = dict((document.metadata_json or {}).get("cursor_state") or {})
        cursor_state.update(
            {
                "document_id": str(document.id),
                "source_ref": str(document.source_ref),
                "content_hash": str(document.content_hash),
            }
        )
        await self.repository.upsert_sync_checkpoint(source_connector_id, cursor_state)
        await self.repository.commit()

    async def _extract_audio_metadata(
        self,
        *,
        audio_bytes: bytes,
        filename: str,
    ) -> dict[str, object]:
        settings = get_settings()
        if not settings.audio_metadata_enabled:
            return {
                "status": "unavailable",
                "provider": "disabled",
                "transcript": None,
                "segments": [],
            }
        try:
            metadata = await extract_audio_metadata(audio_bytes, filename=filename)
        except Exception:
            return {
                "status": "error",
                "provider": "whisper",
                "transcript": None,
                "segments": [],
            }
        if not isinstance(metadata, dict):
            return {
                "status": "unavailable",
                "provider": "whisper",
                "transcript": None,
                "segments": [],
            }
        return {
            "status": metadata.get("status", "unavailable"),
            "provider": metadata.get("provider", "whisper"),
            "transcript": metadata.get("transcript"),
            "segments": list(metadata.get("segments", [])),
        }

    def _audio_clip_content(
        self,
        *,
        title: str,
        clip: dict[str, object],
        audio_metadata: dict[str, object],
    ) -> str:
        start_second = int(clip["start_second"])
        end_second = int(clip["end_second"])
        segments = [
            segment
            for segment in list(audio_metadata.get("segments") or [])
            if int(segment.get("start_second", -1)) < end_second
            and int(segment.get("end_second", -1)) > start_second
            and str(segment.get("text", "")).strip()
        ]
        if segments:
            return " ".join(str(segment["text"]).strip() for segment in segments)
        return f"{title} clip {int(clip['clip_index']) + 1} ({start_second}-{end_second}s)"
