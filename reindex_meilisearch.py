#!/usr/bin/env python3
import asyncpg
import asyncio
import requests


async def main():
    PG_HOST = "kb_postgresql"
    PG_PORT = 5432
    PG_USER = "kb_user"
    PG_PASSWORD = "kb_password"
    PG_DATABASE = "kb_db"

    MEILISEARCH_URL = "http://kb_meilisearch:7700"
    MEILISEARCH_KEY = "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
    MEILISEARCH_INDEX = "kb_documents"

    print("[*] Connecting to PostgreSQL...")
    conn = await asyncpg.connect(
        host=PG_HOST,
        port=PG_PORT,
        user=PG_USER,
        password=PG_PASSWORD,
        database=PG_DATABASE,
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
    print(f"[OK] Fetched {len(docs_data)} documents, {len(topics_data)} topics")

    topics_map = {}
    for row in topics_data:
        doc_id = str(row["document_id"])
        if doc_id not in topics_map:
            topics_map[doc_id] = []
        topics_map[doc_id].append(row["topic"])

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

    headers = {"Authorization": f"Bearer {MEILISEARCH_KEY}"}

    print(f'[*] Seeding Meilisearch index "{MEILISEARCH_INDEX}"...')

    r = requests.delete(
        f"{MEILISEARCH_URL}/indexes/{MEILISEARCH_INDEX}", headers=headers
    )
    print(f"Delete: {r.status_code}")

    r = requests.post(
        f"{MEILISEARCH_URL}/indexes",
        json={"uid": MEILISEARCH_INDEX, "primaryKey": "id"},
        headers=headers,
    )
    print(f"Create: {r.status_code}")

    r = requests.post(
        f"{MEILISEARCH_URL}/indexes/{MEILISEARCH_INDEX}/documents",
        json=documents,
        headers=headers,
        timeout=30,
    )
    print(f"Add docs: {r.status_code}")
    if r.status_code >= 400:
        print(f"Error: {r.text}")
    else:
        print(f"[OK] Indexed {len(documents)} documents into kb_documents")


if __name__ == "__main__":
    asyncio.run(main())
