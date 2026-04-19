"""
Metadata service for document management and standardization.

Handles CRUD operations for document metadata with audit logging.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, String, Text, DateTime, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

logger = logging.getLogger(__name__)

# SQLAlchemy Base
Base = declarative_base()


class KBDocument(Base):
    """Document metadata model."""

    __tablename__ = "kb_documents"

    id = Column(PG_UUID(as_uuid=True), primary_key=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    summary = Column(String(500))
    source = Column(String(512), nullable=False, unique=True)
    owner = Column(String(128), nullable=False)
    classification = Column(String(32), nullable=False)
    status = Column(String(32), default="active")
    created_date = Column(DateTime, nullable=False)
    updated_date = Column(DateTime, nullable=False)
    created_by = Column(String(128))
    updated_by = Column(String(128))
    content_hash = Column(String(64))
    external_id = Column(String(256))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class KBTopic(Base):
    """Topics for documents (many-to-many)."""

    __tablename__ = "kb_topics"

    id = Column(Integer, primary_key=True)
    document_id = Column(PG_UUID(as_uuid=True), nullable=False)
    topic = Column(String(128), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class KBAuditLog(Base):
    """Audit log for document changes."""

    __tablename__ = "kb_audit_log"

    id = Column(Integer, primary_key=True)
    document_id = Column(PG_UUID(as_uuid=True))
    action = Column(String(32), nullable=False)
    actor = Column(String(128), nullable=False)
    changes = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)


class MetadataService:
    """Service for document metadata management."""

    def __init__(self, session: AsyncSession):
        """
        Initialize metadata service.

        Args:
            session: SQLAlchemy async session
        """
        self.session = session

    async def get_document(self, doc_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get document by ID.

        Args:
            doc_id: Document ID

        Returns:
            dict: Document metadata or None if not found

        Example:
            >>> doc = await metadata_service.get_document(UUID("550e8400..."))
            >>> print(doc['title'])
            'PostgreSQL Replication Best Practices'
        """
        try:
            result = await self.session.execute(
                select(KBDocument).where(KBDocument.id == doc_id)
            )
            doc = result.scalar_one_or_none()

            if not doc:
                return None

            # Get topics
            topics_result = await self.session.execute(
                select(KBTopic).where(KBTopic.document_id == doc_id)
            )
            topics = [t.topic for t in topics_result.scalars()]

            return {
                "id": str(doc.id),
                "title": doc.title,
                "content": doc.content,
                "summary": doc.summary,
                "source": doc.source,
                "owner": doc.owner,
                "classification": doc.classification,
                "status": doc.status,
                "created_date": doc.created_date.isoformat(),
                "updated_date": doc.updated_date.isoformat(),
                "created_by": doc.created_by,
                "updated_by": doc.updated_by,
                "topics": topics,
                "external_id": doc.external_id,
            }

        except Exception as e:
            logger.error(f"Failed to get document {doc_id}: {e}")
            raise

    async def get_metadata(self, doc_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get document metadata only (no content).

        Args:
            doc_id: Document ID

        Returns:
            dict: Document metadata or None

        Example:
            >>> metadata = await metadata_service.get_metadata(UUID("550e8400..."))
            >>> print(metadata.keys())
            dict_keys(['id', 'title', 'owner', ...])
        """
        try:
            result = await self.session.execute(
                select(KBDocument).where(KBDocument.id == doc_id)
            )
            doc = result.scalar_one_or_none()

            if not doc:
                return None

            # Get topics
            topics_result = await self.session.execute(
                select(KBTopic).where(KBTopic.document_id == doc_id)
            )
            topics = [t.topic for t in topics_result.scalars()]

            return {
                "id": str(doc.id),
                "title": doc.title,
                "source": doc.source,
                "owner": doc.owner,
                "classification": doc.classification,
                "status": doc.status,
                "created_date": doc.created_date.isoformat(),
                "updated_date": doc.updated_date.isoformat(),
                "created_by": doc.created_by,
                "updated_by": doc.updated_by,
                "topics": topics,
                "external_id": doc.external_id,
            }

        except Exception as e:
            logger.error(f"Failed to get metadata for {doc_id}: {e}")
            raise

    async def update_metadata(
        self,
        doc_id: UUID,
        updates: Dict[str, Any],
        actor: str = "system",
    ) -> bool:
        """
        Update document metadata.

        Args:
            doc_id: Document ID
            updates: Fields to update
            actor: User making the change (for audit log)

        Returns:
            bool: Success

        Example:
            >>> success = await metadata_service.update_metadata(
            ...     UUID("550e8400..."),
            ...     {"owner": "new-team", "status": "archived"}
            ... )
        """
        try:
            # Get current document
            result = await self.session.execute(
                select(KBDocument).where(KBDocument.id == doc_id)
            )
            doc = result.scalar_one_or_none()

            if not doc:
                return False

            # Prepare update data
            update_data = {}
            for key, value in updates.items():
                if key == "topics":
                    # Handle topics separately
                    continue
                if hasattr(doc, key):
                    update_data[key] = value

            # Add updated_date
            update_data["updated_date"] = datetime.utcnow()
            update_data["updated_by"] = actor

            # Update document
            await self.session.execute(
                update(KBDocument).where(KBDocument.id == doc_id).values(**update_data)
            )

            # Update topics if provided
            if "topics" in updates:
                await self.session.execute(
                    delete(KBTopic).where(KBTopic.document_id == doc_id)
                )
                for topic in updates["topics"]:
                    topic_obj = KBTopic(document_id=doc_id, topic=topic)
                    self.session.add(topic_obj)

            # Log change
            await self._log_change(doc_id, "updated", actor, updates)

            await self.session.commit()
            return True

        except Exception as e:
            logger.error(f"Failed to update metadata for {doc_id}: {e}")
            await self.session.rollback()
            return False

    async def bulk_update_metadata(
        self,
        updates: List[Dict[str, Any]],
        actor: str = "system",
    ) -> Dict[str, Any]:
        """
        Bulk update multiple documents.

        Args:
            updates: List of {doc_id, changes} dicts
            actor: User making changes

        Returns:
            dict: Update results

        Example:
            >>> result = await metadata_service.bulk_update_metadata([
            ...     {"doc_id": UUID("550e..."), "changes": {"owner": "team1"}},
            ...     {"doc_id": UUID("660e..."), "changes": {"status": "archived"}},
            ... ])
            >>> print(result['updated'])
            2
        """
        total = len(updates)
        updated = 0
        failed = 0
        results = []

        for update_item in updates:
            doc_id = update_item["doc_id"]
            changes = update_item["changes"]

            try:
                success = await self.update_metadata(doc_id, changes, actor)
                if success:
                    updated += 1
                    results.append({"doc_id": str(doc_id), "status": "updated"})
                else:
                    failed += 1
                    results.append({"doc_id": str(doc_id), "status": "not_found"})

            except Exception as e:
                failed += 1
                results.append(
                    {
                        "doc_id": str(doc_id),
                        "status": "failed",
                        "error": str(e),
                    }
                )

        return {
            "total": total,
            "updated": updated,
            "failed": failed,
            "results": results,
        }

    async def _log_change(
        self,
        doc_id: UUID,
        action: str,
        actor: str,
        changes: Dict[str, Any],
    ) -> None:
        """
        Log document change to audit log.

        Args:
            doc_id: Document ID
            action: Action type (created, updated, deleted, indexed)
            actor: User making change
            changes: What changed
        """
        try:
            log_entry = KBAuditLog(
                document_id=doc_id,
                action=action,
                actor=actor,
                changes=changes,
            )
            self.session.add(log_entry)
            await self.session.flush()
            logger.debug(f"Logged {action} for document {doc_id} by {actor}")

        except Exception as e:
            logger.error(f"Failed to log change: {e}")

    async def search_by_filter(
        self,
        owner: Optional[str] = None,
        classification: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Search documents by metadata filters.

        Args:
            owner: Filter by owner
            classification: Filter by classification
            status: Filter by status
            limit: Result limit

        Returns:
            list: Matching documents

        Example:
            >>> docs = await metadata_service.search_by_filter(
            ...     owner="platform-eng",
            ...     classification="internal"
            ... )
        """
        try:
            query = select(KBDocument)

            if owner:
                query = query.where(KBDocument.owner == owner)
            if classification:
                query = query.where(KBDocument.classification == classification)
            if status:
                query = query.where(KBDocument.status == status)

            result = await self.session.execute(query.limit(limit))
            docs = result.scalars().all()

            return [await self.get_metadata(doc.id) for doc in docs]

        except Exception as e:
            logger.error(f"Search by filter failed: {e}")
            return []
