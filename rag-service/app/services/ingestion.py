from __future__ import annotations

import hashlib
import uuid
from time import monotonic
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.ingestion import IngestionRepository
from app.schemas.ingest import IngestRequest
from app.services.chunking import build_chunks
from app.services.dispatch import IngestionDispatcher, NullIngestionDispatcher
from app.services.embedder import embed_image_content, embed_text_content, resolve_pdf_embedding
from app.services.loaders import decode_base64_source, load_source
from app.services.sparse_encoder import encode_sparse_text
from app.services.vector_store import QdrantVectorStore


class IngestionService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        dispatcher: IngestionDispatcher | None = None,
        vector_store: QdrantVectorStore | None = None,
    ):
        self.repository = IngestionRepository(session)
        self.dispatcher = dispatcher or NullIngestionDispatcher()
        self.vector_store = vector_store or QdrantVectorStore()

    async def create_ingestion_job(
        self,
        payload: IngestRequest,
        project_id: uuid.UUID,
    ) -> dict[str, str]:
        project = await self.repository.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        initial_status = "indexing" if payload.mode == "sync" else "pending"
        job_status = "running" if payload.mode == "sync" else "pending"
        document = await self.repository.create_document(
            project_id=project.id,
            tenant_id=project.tenant_id,
            source_type=payload.source_type,
            source_ref=self._source_ref(payload),
            status=initial_status,
            title=self._derive_title(payload),
            content_hash=self._content_hash(self._source_ref(payload)),
            metadata={
                "ingest_mode": payload.mode,
                **({"source_base64": payload.source_base64} if payload.source_base64 else {}),
                **({"source_sql": payload.source_sql} if payload.source_sql else {}),
                **({"title": payload.title} if payload.title else {}),
                **({"records": payload.records} if payload.records else {}),
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

        if payload.mode == "sync":
            await self._process_document_job(
                document,
                job,
                retry_count=0,
            )
        else:
            await self.dispatcher.enqueue(
                {
                    "document_id": str(document.id),
                    "ingestion_job_id": str(job.id),
                    "project_id": str(project.id),
                    "source_type": payload.source_type,
                    "source_ref": self._source_ref(payload),
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
        project_id: uuid.UUID,
    ) -> list[dict[str, str]]:
        if any(payload.mode != "async" for payload in payloads):
            raise HTTPException(status_code=400, detail="Batch ingestion only supports async mode")

        results: list[dict[str, str]] = []
        for payload in payloads:
            result = await self.create_ingestion_job(payload, project_id)
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

        return {
            "document_id": str(document.id),
            "ingestion_job_id": str(job.id),
            "archived_chunk_count": len(chunks),
            "qdrant_point_ids": point_ids,
        }

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

    def _source_ref(self, payload: IngestRequest) -> str:
        if payload.source_ref is not None:
            return str(payload.source_ref)
        if payload.records is not None:
            return "inline://structured-records"
        if payload.source_sql is not None:
            return "inline://sql-query"
        assert payload.source_filename is not None
        return f"inline://{payload.source_filename}"

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

        chunk_rows, vector_chunk_indices = await self._build_chunk_rows(document, loaded)
        chunks = await self.repository.create_chunks(chunk_rows)
        await self.vector_store.ensure_collection()
        vector_chunks = [chunks[index] for index in vector_chunk_indices]
        vector_rows = [chunk_rows[index] for index in vector_chunk_indices]
        point_ids = await self.vector_store.upsert_chunks(
            [
                {
                    "document_id": str(document.id),
                    "chunk_id": str(chunk.id),
                    "tenant_id": str(document.tenant_id),
                    "scope_type": document.metadata_json.get("scope_type", "project"),
                    "scope_id": document.metadata_json.get("scope_id", str(document.project_id)),
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

    async def _build_chunk_rows(self, document, loaded: dict[str, object]) -> tuple[list[dict[str, object]], list[int]]:
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
            return [parent_row, vector_row], [1]

        raw_chunks = build_chunks(document.source_type, content, metadata)
        chunk_rows: list[dict[str, object]] = []
        vector_chunk_indices: list[int] = []
        for raw_chunk in raw_chunks:
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
                "content_hash": self._content_hash(raw_chunk["content"]),
                "content": raw_chunk["content"],
                "vector": [],
            }
            chunk_rows.append(parent_row)
            embedding = await embed_text_content(raw_chunk["content"], title)
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
                    "embed_version": "v1",
                    "dimension": int(embedding.get("dimension") or len(embedding.get("values", []))),
                    "content_hash": self._content_hash(raw_chunk["content"]),
                    "content": raw_chunk["content"],
                    "vector": embedding["values"],
                    "sparse_vector": encode_sparse_text(raw_chunk["content"]),
                }
            )
        return chunk_rows, vector_chunk_indices
