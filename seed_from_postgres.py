#!/usr/bin/env python3
import asyncio
import asyncpg
import requests
import hashlib
import traceback


async def main():
    MEILISEARCH_URL = "http://kb-meilisearch:7700"
    QDRANT_URL = "http://kb-qdrant:6335"
    PG_HOST = "kb_postgresql"
    PG_PORT = 5432
    PG_USER = "kb_user"
    PG_PASSWORD = "your-secure-password"
    PG_DATABASE = "kb_db"
    MEILI_KEY = "your-32-char-secret-key-minimum"

    try:
        print("[*] Connecting to PostgreSQL...")
        conn = await asyncpg.connect(
            host=PG_HOST,
            port=PG_PORT,
            user=PG_USER,
            password=PG_PASSWORD,
            database=PG_DATABASE,
        )
        print("[OK] Connected")

        docs_data = await conn.fetch(
            "SELECT id, title, content, source, owner, classification, status, created_date, updated_date, external_id FROM kb_documents ORDER BY created_date DESC"
        )
        topics_data = await conn.fetch(
            "SELECT document_id, topic FROM kb_topics ORDER BY document_id"
        )
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
                    "topics": topics_map.get(doc_id, []),
                    "external_id": doc["external_id"],
                }
            )

        print("[*] Seeding Meilisearch...")
        headers = {"Authorization": f"Bearer {MEILI_KEY}"}

        r = requests.delete(f"{MEILISEARCH_URL}/indexes/documents", headers=headers)
        print(f"Delete: {r.status_code}")

        r = requests.post(
            f"{MEILISEARCH_URL}/indexes",
            json={"uid": "documents", "primaryKey": "id"},
            headers=headers,
        )
        print(f"Create: {r.status_code}")

        r = requests.post(
            f"{MEILISEARCH_URL}/indexes/documents/documents",
            json=documents,
            headers=headers,
            timeout=30,
        )
        print(f"Add docs: {r.status_code}")

        r = requests.get(f"{MEILISEARCH_URL}/indexes/documents/stats", headers=headers)
        if r.status_code == 200:
            stats = r.json()
            print(f'[OK] Meilisearch: {stats.get("numberOfDocuments", 0)} documents')
        else:
            print(f"Stats check failed: {r.status_code}")

        print("[*] Seeding Qdrant...")

        r = requests.delete(f"{QDRANT_URL}/collections/documents")
        print(f"Delete collection: {r.status_code}")

        r = requests.put(
            f"{QDRANT_URL}/collections/documents",
            json={"vectors": {"size": 1536, "distance": "Cosine"}},
        )
        print(f"Create collection: {r.status_code}")

        points = []
        for idx, doc in enumerate(documents):
            hash_obj = hashlib.sha256(doc["content"].encode())
            hash_bytes = hash_obj.digest()
            embedding = [
                (hash_bytes[i % len(hash_bytes)] / 256.0 + (i * 0.001 % 1.0)) / 2.0
                for i in range(1536)
            ]
            points.append(
                {
                    "id": idx,
                    "vector": embedding,
                    "payload": {"doc_id": doc["id"], "title": doc["title"]},
                }
            )

        r = requests.put(
            f"{QDRANT_URL}/collections/documents/points?wait=true",
            json={"points": points},
            timeout=60,
        )
        print(f"Add vectors: {r.status_code}")

        r = requests.get(f"{QDRANT_URL}/collections/documents")
        if r.status_code == 200:
            info = r.json()
            print(
                f'[OK] Qdrant: {info.get("result", {}).get("points_count", 0)} vectors'
            )
        else:
            print(f"Collection check failed: {r.status_code}")

        print("[OK] Seeding complete!")

    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
