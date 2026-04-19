#!/usr/bin/env python3
import asyncpg
import asyncio
import requests
import sys


async def main():
    print("[START] Reindexing documents...", file=sys.stderr)
    sys.stderr.flush()

    try:
        print("[1] Connecting...", file=sys.stderr)
        sys.stderr.flush()

        conn = await asyncpg.connect(
            host="postgresql",
            port=5432,
            user="kb_user",
            password="your-secure-password",
            database="kb_db",
        )

        docs_data = await conn.fetch("""
            SELECT id, title, content, source, owner, classification, status,
                   created_date, updated_date, external_id
            FROM kb_documents ORDER BY created_date DESC
        """)

        topics_data = await conn.fetch("""
            SELECT document_id, topic FROM kb_topics ORDER BY document_id
        """)

        await conn.close()

        print(
            f"[OK] Fetched {len(docs_data)} docs, {len(topics_data)} topics",
            file=sys.stderr,
        )
        sys.stderr.flush()

        # Build topics map
        topics_map = {}
        for row in topics_data:
            doc_id = str(row["document_id"])
            if doc_id not in topics_map:
                topics_map[doc_id] = []
            topics_map[doc_id].append(row["topic"])

        # Build documents
        documents = []
        for doc in docs_data:
            doc_id = str(doc["id"])
            documents.append(
                {
                    "id": doc_id,
                    "title": doc["title"],
                    "content": doc["content"],
                    "source": doc["source"],
                    "owner": doc["owner"],
                    "classification": doc["classification"],
                    "status": doc["status"],
                    "created_date": (
                        doc["created_date"].isoformat() if doc["created_date"] else None
                    ),
                    "updated_date": (
                        doc["updated_date"].isoformat() if doc["updated_date"] else None
                    ),
                    "topics": topics_map.get(doc_id, []),
                    "external_id": doc["external_id"],
                }
            )

        headers = {"Authorization": "Bearer a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"}

        print("[2] Indexing to Meilisearch...", file=sys.stderr)
        sys.stderr.flush()

        # Delete index
        r = requests.delete(
            "http://meilisearch:7700/indexes/kb_documents", headers=headers, timeout=10
        )
        print(f"Delete: {r.status_code}", file=sys.stderr)

        # Create index
        r = requests.post(
            "http://meilisearch:7700/indexes",
            json={"uid": "kb_documents", "primaryKey": "id"},
            headers=headers,
            timeout=10,
        )
        print(f"Create: {r.status_code}", file=sys.stderr)

        # Add documents
        r = requests.post(
            "http://meilisearch:7700/indexes/kb_documents/documents",
            json=documents,
            headers=headers,
            timeout=30,
        )
        print(f"Add docs: {r.status_code}", file=sys.stderr)

        if r.status_code >= 400:
            print(f"Error: {r.text}", file=sys.stderr)
        else:
            print(f"[SUCCESS] Indexed {len(documents)} documents", file=sys.stderr)

        sys.stderr.flush()

    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.stderr.flush()


if __name__ == "__main__":
    asyncio.run(main())
