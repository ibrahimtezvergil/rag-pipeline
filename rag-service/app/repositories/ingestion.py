from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import RagChunk, RagChunkDiffLog, RagDocument, RagIngestionJob, RagProject, RagSyncCheckpoint


class IngestionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_project(self, project_id: uuid.UUID) -> RagProject | None:
        return await self.session.get(RagProject, project_id)

    async def create_document(
        self,
        *,
        project_id: uuid.UUID,
        tenant_id: uuid.UUID,
        source_type: str,
        source_ref: str,
        status: str,
        title: str,
        content_hash: str,
        metadata: dict,
        version: int = 1,
        previous_document_id: uuid.UUID | None = None,
        source_connector_id: uuid.UUID | None = None,
    ) -> RagDocument:
        document = RagDocument(
            project_id=project_id,
            tenant_id=tenant_id,
            source_type=source_type,
            source_ref=source_ref,
            status=status,
            title=title,
            content_hash=content_hash,
            version=version,
            previous_document_id=previous_document_id,
            source_connector_id=source_connector_id,
            metadata_json=metadata,
        )
        self.session.add(document)
        await self.session.flush()
        return document

    async def get_latest_document_by_source_ref(
        self,
        project_id: uuid.UUID,
        source_ref: str,
    ) -> RagDocument | None:
        result = await self.session.scalars(
            select(RagDocument)
            .where(
                RagDocument.project_id == project_id,
                RagDocument.source_ref == source_ref,
                RagDocument.status != "deleted",
            )
            .order_by(RagDocument.version.desc(), RagDocument.created_at.desc())
            .limit(1)
        )
        return result.first()

    async def list_latest_documents(self) -> list[RagDocument]:
        latest_versions = (
            select(
                RagDocument.project_id.label("project_id"),
                RagDocument.source_ref.label("source_ref"),
                func.max(RagDocument.version).label("max_version"),
            )
            .where(RagDocument.status != "deleted")
            .group_by(RagDocument.project_id, RagDocument.source_ref)
            .subquery()
        )
        result = await self.session.scalars(
            select(RagDocument)
            .join(
                latest_versions,
                (RagDocument.project_id == latest_versions.c.project_id)
                & (RagDocument.source_ref == latest_versions.c.source_ref)
                & (RagDocument.version == latest_versions.c.max_version),
            )
            .order_by(RagDocument.created_at.desc())
        )
        return list(result)

    async def create_job(
        self,
        *,
        document_id: uuid.UUID,
        status: str,
        job_type: str = "ingest",
    ) -> RagIngestionJob:
        job = RagIngestionJob(
            document_id=document_id,
            job_type=job_type,
            status=status,
        )
        self.session.add(job)
        await self.session.flush()
        return job

    async def update_document_status(self, document: RagDocument, status: str) -> RagDocument:
        document.status = status
        await self.session.flush()
        return document

    async def update_document_after_load(
        self,
        document: RagDocument,
        *,
        status: str,
        title: str,
        chunk_count: int,
        metadata: dict,
        embed_model: str | None = None,
    ) -> RagDocument:
        document.status = status
        document.title = title
        document.chunk_count = chunk_count
        document.metadata_json = metadata
        document.embed_model = embed_model
        await self.session.flush()
        return document

    async def update_job_status(
        self,
        job: RagIngestionJob,
        status: str,
        *,
        retry_count: int | None = None,
        error_message: str | None = None,
        chunks_processed: int | None = None,
        duration_ms: int | None = None,
        completed: bool = False,
    ) -> RagIngestionJob:
        job.status = status
        if retry_count is not None:
            job.retry_count = retry_count
        job.error_message = error_message
        if chunks_processed is not None:
            job.chunks_processed = chunks_processed
        if duration_ms is not None:
            job.duration_ms = duration_ms
        if completed:
            job.completed_at = datetime.now(UTC)
        await self.session.flush()
        return job

    async def commit(self) -> None:
        await self.session.commit()

    async def get_job(self, job_id: uuid.UUID) -> RagIngestionJob | None:
        return await self.session.get(RagIngestionJob, job_id)

    async def get_document(self, document_id: uuid.UUID) -> RagDocument | None:
        return await self.session.get(RagDocument, document_id)

    async def get_document_chunks(self, document_id: uuid.UUID) -> list[RagChunk]:
        result = await self.session.scalars(
            select(RagChunk).where(RagChunk.document_id == document_id).order_by(RagChunk.chunk_index)
        )
        return list(result)

    async def get_child_chunks(self, document_id: uuid.UUID) -> list[RagChunk]:
        result = await self.session.scalars(
            select(RagChunk)
            .where(
                RagChunk.document_id == document_id,
                RagChunk.parent_chunk_id.is_not(None),
            )
            .order_by(RagChunk.chunk_index)
        )
        return list(result)

    async def soft_delete_document(self, document: RagDocument) -> RagDocument:
        document.status = "deleted"
        await self.session.flush()
        return document

    async def supersede_document(self, document: RagDocument) -> RagDocument:
        document.status = "superseded"
        await self.session.flush()
        return document

    async def archive_chunks(self, chunks: list[RagChunk]) -> list[RagChunk]:
        for chunk in chunks:
            chunk.is_archived = True
        await self.session.flush()
        return chunks

    async def create_chunks(self, chunk_rows: list[dict[str, object]]) -> list[RagChunk]:
        chunks: list[RagChunk] = []
        index_map: dict[int, RagChunk] = {}
        for row in chunk_rows:
            parent_chunk_id = row.get("parent_chunk_id")
            if isinstance(parent_chunk_id, str) and parent_chunk_id.startswith("__PARENT_INDEX__:"):
                parent_index = int(parent_chunk_id.split(":", maxsplit=1)[1])
                parent_chunk_id = index_map[parent_index].id
            chunk = RagChunk(
                document_id=row["document_id"],
                chunk_index=row["chunk_index"],
                parent_chunk_id=parent_chunk_id,
                content_hash=row.get("content_hash"),
                content=row.get("content"),
                modality=str(row.get("modality", "text")),
                token_count=row.get("token_count"),
                page_number=row.get("page_number"),
                bbox=row.get("bbox"),
                section_title=row.get("section_title"),
                related_chunk_ids=list(row.get("related_chunk_ids", [])),
                acl=list(row.get("acl", [])),
                embed_model=row.get("embed_model"),
                embed_version=row.get("embed_version"),
                dimension=int(row.get("dimension", 768)),
            )
            self.session.add(chunk)
            await self.session.flush()
            chunks.append(chunk)
            index_map[int(row["chunk_index"])] = chunk
        return chunks

    async def attach_qdrant_point_ids(
        self,
        chunks: list[RagChunk],
        point_ids: list[str],
    ) -> list[RagChunk]:
        for chunk, point_id in zip(chunks, point_ids, strict=False):
            chunk.qdrant_point_id = uuid.UUID(point_id)
        await self.session.flush()
        return chunks

    async def get_chunks_by_ids(self, chunk_ids: list[uuid.UUID]) -> list[RagChunk]:
        if not chunk_ids:
            return []
        result = await self.session.scalars(
            select(RagChunk).where(RagChunk.id.in_(chunk_ids))
        )
        return list(result)

    async def update_related_chunk_ids(
        self,
        relation_map: dict[uuid.UUID, list[uuid.UUID]],
    ) -> None:
        if not relation_map:
            return
        chunks = await self.get_chunks_by_ids(list(relation_map))
        chunk_map = {chunk.id: chunk for chunk in chunks}
        for chunk_id, related_ids in relation_map.items():
            chunk = chunk_map.get(chunk_id)
            if chunk is None:
                continue
            chunk.related_chunk_ids = [str(related_id) for related_id in related_ids]
        await self.session.flush()

    async def create_chunk_diff_logs(
        self,
        job_id: uuid.UUID,
        entries: list[dict[str, object]],
    ) -> list[RagChunkDiffLog]:
        rows: list[RagChunkDiffLog] = []
        for entry in entries:
            row = RagChunkDiffLog(
                job_id=job_id,
                chunk_id=entry.get("chunk_id"),
                operation=str(entry["operation"]),
            )
            self.session.add(row)
            rows.append(row)
        await self.session.flush()
        return rows

    async def upsert_sync_checkpoint(
        self,
        source_connector_id: uuid.UUID,
        cursor_state: dict,
    ) -> RagSyncCheckpoint:
        result = await self.session.scalars(
            select(RagSyncCheckpoint).where(
                RagSyncCheckpoint.source_connector_id == source_connector_id
            )
        )
        checkpoint = result.first()
        if checkpoint is None:
            checkpoint = RagSyncCheckpoint(
                source_connector_id=source_connector_id,
                cursor_state=cursor_state,
                last_synced_at=datetime.now(UTC),
            )
            self.session.add(checkpoint)
        else:
            checkpoint.cursor_state = cursor_state
            checkpoint.last_synced_at = datetime.now(UTC)
        await self.session.flush()
        return checkpoint
