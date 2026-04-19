#!/usr/bin/env python3
"""
Populate Meilisearch and Qdrant with documents from PostgreSQL.

This script:
1. Connects to PostgreSQL and fetches all documents with their topics
2. Loads documents into Meilisearch for full-text search
3. Generates embeddings and loads into Qdrant for semantic search
4. Verifies indexing is complete
"""

import os
import requests
from typing import List, Dict, Any
import hashlib
import asyncpg

# Configuration
MEILISEARCH_URL = os.getenv("MEILISEARCH_URL", "http://localhost:7700")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6335")
MEILISEARCH_INDEX = "documents"  # Must match api config
QDRANT_COLLECTION = "documents"  # Must match api config

# PostgreSQL Configuration
PG_HOST = os.getenv("DB_HOST", "localhost")
PG_PORT = int(os.getenv("DB_PORT", "5433"))
PG_USER = os.getenv("DB_USER", "kb_user")
PG_PASSWORD = os.getenv("DB_PASSWORD", "kb_password")
PG_DATABASE = os.getenv("DB_NAME", "kb_db")


def generate_mock_embedding(text: str) -> List[float]:
    """Generate a deterministic mock embedding from text."""
    hash_obj = hashlib.sha256(text.encode())
    hash_bytes = hash_obj.digest()

    # Create 1536-dimensional vector (matching OpenAI embedding size)
    embedding = []
    for i in range(1536):
        byte_index = i % len(hash_bytes)
        value = hash_bytes[byte_index] / 256.0
        value = (value + (i * 0.001 % 1.0)) / 2.0
        embedding.append(value)

    return embedding


async def fetch_documents_from_postgresql() -> List[Dict[str, Any]]:
    """Fetch all documents and their topics from PostgreSQL."""
    print("\n[*] Connecting to PostgreSQL...")

    try:
        conn = await asyncpg.connect(
            host=PG_HOST,
            port=PG_PORT,
            user=PG_USER,
            password=PG_PASSWORD,
            database=PG_DATABASE,
        )

        # Fetch all documents
        docs_data = await conn.fetch("""
            SELECT
                id, title, content, source, owner, classification,
                status, created_date, updated_date, external_id
            FROM kb_documents
            ORDER BY created_date DESC
        """)

        # Fetch all topics
        topics_data = await conn.fetch("""
            SELECT document_id, topic FROM kb_topics ORDER BY document_id
        """)

        await conn.close()

        # Build a map of document_id -> topics
        topics_map = {}
        for row in topics_data:
            doc_id = str(row["document_id"])
            if doc_id not in topics_map:
                topics_map[doc_id] = []
            topics_map[doc_id].append(row["topic"])

        # Combine documents with their topics
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

        print(f"  [OK] Fetched {len(documents)} documents from PostgreSQL")
        return documents

    except Exception as e:
        print(f"  [ERROR] PostgreSQL error: {e}")
        raise


def seed_meilisearch(documents: List[Dict[str, Any]]) -> bool:
    """Load documents into Meilisearch."""
    print("\n[*] Seeding Meilisearch...")

    try:
        # Delete existing index if it exists
        delete_response = requests.delete(
            f"{MEILISEARCH_URL}/indexes/{MEILISEARCH_INDEX}"
        )
        print(f"  Clean index response: {delete_response.status_code}")

        # Create index
        index_response = requests.post(
            f"{MEILISEARCH_URL}/indexes",
            json={"uid": MEILISEARCH_INDEX, "primaryKey": "id"},
        )
        print(f"  Create index response: {index_response.status_code}")

        # Add documents
        docs_response = requests.post(
            f"{MEILISEARCH_URL}/indexes/{MEILISEARCH_INDEX}/documents",
            json=documents,
            timeout=30,
        )

        if docs_response.status_code in [200, 202]:
            print(f"  [OK] Indexed {len(documents)} documents into Meilisearch")

            # Wait for indexing to complete
            import time

            print("  [*] Waiting for indexing to complete...")
            for i in range(30):
                time.sleep(1)
                stats_resp = requests.get(
                    f"{MEILISEARCH_URL}/indexes/{MEILISEARCH_INDEX}/stats",
                    timeout=10,
                )
                if stats_resp.status_code == 200:
                    doc_count = stats_resp.json().get("numberOfDocuments", 0)
                    if doc_count == len(documents):
                        print(f"  [OK] Indexing complete ({doc_count} documents)")
                        return True
            print("  [*] Indexing in progress (may take longer)...")
            return True
        else:
            print(f"  [ERROR] Failed to load documents: {docs_response.status_code}")
            print(f"     {docs_response.text}")
            return False

    except Exception as e:
        print(f"  [ERROR] Meilisearch error: {e}")
        return False


def seed_qdrant(documents: List[Dict[str, Any]]) -> bool:
    """Load embeddings into Qdrant."""
    print("\n[*] Seeding Qdrant...")

    try:
        # Delete existing collection if it exists
        delete_response = requests.delete(
            f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}"
        )
        print(f"  Clean collection response: {delete_response.status_code}")

        # Create collection with vector size
        collection_config = {"vectors": {"size": 1536, "distance": "Cosine"}}

        create_response = requests.put(
            f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}",
            json=collection_config,
            timeout=30,
        )
        print(f"  Create collection response: {create_response.status_code}")

        # Create points with embeddings
        points = []
        for idx, doc in enumerate(documents):
            embedding = generate_mock_embedding(doc["content"])
            point = {
                "id": idx,  # Qdrant uses integer IDs
                "vector": embedding,
                "payload": {
                    "doc_id": doc["id"],
                    "title": doc["title"],
                    "content": doc["content"][:500],  # Limit payload size
                    "owner": doc["owner"],
                    "classification": doc["classification"],
                    "topics": doc["topics"],
                    "status": doc["status"],
                },
            }
            points.append(point)

        # Upsert points
        upsert_response = requests.put(
            f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points?wait=true",
            json={"points": points},
            timeout=60,
        )

        if upsert_response.status_code in [200, 201]:
            print(f"  [OK] Loaded {len(points)} vectors into Qdrant")
            return True
        else:
            print(f"  [ERROR] Failed to load vectors: {upsert_response.status_code}")
            print(f"     {upsert_response.text}")
            return False

    except Exception as e:
        print(f"  [ERROR] Qdrant error: {e}")
        return False


def verify_seeding() -> bool:
    """Verify that data was loaded correctly."""
    print("\n[*] Verifying seeding...")

    try:
        # Check Meilisearch
        stats_response = requests.get(
            f"{MEILISEARCH_URL}/indexes/{MEILISEARCH_INDEX}/stats",
            timeout=10,
        )
        if stats_response.status_code == 200:
            stats = stats_response.json()
            doc_count = stats.get("numberOfDocuments", 0)
            print(f"  Meilisearch: {doc_count} documents indexed")
        else:
            print(f"  Meilisearch check failed: {stats_response.status_code}")
            return False

        # Check Qdrant
        collection_response = requests.get(
            f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}",
            timeout=10,
        )
        if collection_response.status_code == 200:
            collection_info = collection_response.json()
            points_count = collection_info.get("result", {}).get("points_count", 0)
            print(f"  Qdrant: {points_count} vectors indexed")
        else:
            print(f"  Qdrant check failed: {collection_response.status_code}")
            return False

        return doc_count > 0 and points_count > 0

    except Exception as e:
        print(f"  ❌ Verification error: {e}")
        return False


async def main():
    """Main orchestration."""
    print("=" * 70)
    print("KB Search API - Populate Search Indices from PostgreSQL")
    print("=" * 70)

    try:
        # Fetch documents from PostgreSQL
        documents = await fetch_documents_from_postgresql()

        if not documents:
            print("\n❌ No documents found in PostgreSQL")
            return False

        print(f"\n📄 Preparing {len(documents)} documents for indexing...")

        # Seed search engines
        meilisearch_ok = seed_meilisearch(documents)
        qdrant_ok = seed_qdrant(documents)

        # Verify
        if verify_seeding():
            print("\n" + "=" * 70)
            print("✅ Search indices populated successfully")
            print("=" * 70)
            print("\nYou can now test the search API:")
            print("  curl -X POST http://localhost:8000/api/v1/search \\")
            print("    -H 'Content-Type: application/json' \\")
            print('    -d \'{"query": "postgresql", "limit": 5}\'')
            return True
        else:
            print("\n" + "=" * 70)
            print("⚠️  Indices populated but verification incomplete")
            print("=" * 70)
            return meilisearch_ok and qdrant_ok

    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    import asyncio

    success = asyncio.run(main())
    exit(0 if success else 1)
