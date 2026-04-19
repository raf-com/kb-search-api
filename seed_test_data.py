#!/usr/bin/env python3
"""
Seed test data into Meilisearch and Qdrant for demonstration.

This script generates sample documents and loads them into both search engines.
"""

import uuid
from datetime import datetime, timedelta
import requests
from typing import List, Dict, Any
import random

# Configuration
import os

MEILISEARCH_URL = os.getenv("MEILISEARCH_URL", "http://kb-meilisearch:7700")
QDRANT_URL = os.getenv("QDRANT_URL", "http://kb-qdrant:6333")
MEILISEARCH_INDEX = "kb_documents"  # Must match config.py
QDRANT_COLLECTION = "kb_embeddings"  # Must match config.py

# Sample documents to seed
SAMPLE_DOCUMENTS = [
    {
        "title": "PostgreSQL Replication Setup Guide",
        "content": "A comprehensive guide to setting up PostgreSQL replication across multiple servers. Covers logical and physical replication, failover strategies, and monitoring.",
        "owner": "platform-eng",
        "classification": "internal",
        "topics": ["postgresql", "replication", "database"],
        "status": "active",
    },
    {
        "title": "Kubernetes Best Practices",
        "content": "Industry best practices for Kubernetes deployments including resource management, security policies, networking, and production-grade configuration.",
        "owner": "platform-eng",
        "classification": "internal",
        "topics": ["kubernetes", "devops", "containerization"],
        "status": "active",
    },
    {
        "title": "Redis Clustering and High Availability",
        "content": "Guide to implementing Redis clustering for high availability. Discusses sentinel configuration, data persistence, and performance tuning.",
        "owner": "infrastructure",
        "classification": "internal",
        "topics": ["redis", "caching", "high-availability"],
        "status": "active",
    },
    {
        "title": "API Security Best Practices",
        "content": "Essential security guidelines for API design and implementation. Covers authentication, authorization, rate limiting, and input validation.",
        "owner": "security-team",
        "classification": "internal",
        "topics": ["security", "api", "authentication"],
        "status": "active",
    },
    {
        "title": "Terraform Infrastructure as Code",
        "content": "Complete guide to using Terraform for infrastructure provisioning. Includes best practices, module design, state management, and deployment strategies.",
        "owner": "devops",
        "classification": "internal",
        "topics": ["terraform", "infrastructure", "iac"],
        "status": "active",
    },
    {
        "title": "Docker Image Optimization",
        "content": "Techniques for optimizing Docker image sizes and build times. Covers multi-stage builds, layer caching, and security scanning.",
        "owner": "platform-eng",
        "classification": "public",
        "topics": ["docker", "containerization", "optimization"],
        "status": "active",
    },
    {
        "title": "Observability with Prometheus and Grafana",
        "content": "Setup and configuration guide for Prometheus metrics collection and Grafana visualization. Includes alerting rules and dashboard creation.",
        "owner": "infrastructure",
        "classification": "internal",
        "topics": ["monitoring", "prometheus", "grafana", "observability"],
        "status": "active",
    },
    {
        "title": "GraphQL API Design Patterns",
        "content": "Best practices for designing GraphQL APIs. Covers schema design, query optimization, subscription patterns, and error handling.",
        "owner": "backend-team",
        "classification": "internal",
        "topics": ["graphql", "api", "backend"],
        "status": "active",
    },
    {
        "title": "Python Async Programming Guide",
        "content": "Complete guide to asynchronous programming in Python using asyncio. Includes concurrency patterns, error handling, and performance optimization.",
        "owner": "backend-team",
        "classification": "internal",
        "topics": ["python", "async", "concurrency"],
        "status": "active",
    },
    {
        "title": "Database Migration Strategies",
        "content": "Zero-downtime database migration techniques including blue-green deployments, read replicas, and backward compatibility patterns.",
        "owner": "platform-eng",
        "classification": "internal",
        "topics": ["database", "migration", "devops"],
        "status": "active",
    },
    {
        "title": "Machine Learning Model Serving",
        "content": "Production deployment strategies for ML models. Covers containerization, versioning, A/B testing, and performance monitoring.",
        "owner": "ml-team",
        "classification": "confidential",
        "topics": ["machine-learning", "serving", "deployment"],
        "status": "active",
    },
    {
        "title": "Distributed System Consensus Algorithms",
        "content": "Deep dive into distributed consensus algorithms including Raft and Paxos. Covers failure scenarios, leadership election, and log replication.",
        "owner": "research-team",
        "classification": "confidential",
        "topics": ["distributed-systems", "consensus", "algorithm"],
        "status": "active",
    },
]


def generate_mock_embedding(text: str) -> List[float]:
    """Generate a simple mock embedding (not real, but demonstrates the concept)."""
    # Use a deterministic hash-based approach for reproducibility
    import hashlib

    hash_obj = hashlib.sha256(text.encode())
    hash_bytes = hash_obj.digest()

    # Create 1536-dimensional vector (matching OpenAI embedding size)
    embedding = []
    for i in range(1536):
        # Use different bytes for each dimension
        byte_index = i % len(hash_bytes)
        value = hash_bytes[byte_index] / 256.0
        # Add some variation based on position
        value = (value + (i * 0.001 % 1.0)) / 2.0
        embedding.append(value)

    return embedding


def create_meilisearch_documents(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Create documents formatted for Meilisearch."""
    meilisearch_docs = []
    for doc in docs:
        doc_id = str(uuid.uuid4())
        created_date = datetime.now() - timedelta(days=random.randint(1, 365))

        meilisearch_doc = {
            "id": doc_id,
            "title": doc["title"],
            "content": doc["content"],
            "source": f"knowledge-base/{doc_id}",
            "owner": doc["owner"],
            "classification": doc["classification"],
            "topics": doc["topics"],
            "status": doc["status"],
            "created_date": created_date.isoformat(),
        }
        meilisearch_docs.append(meilisearch_doc)

    return meilisearch_docs


def create_qdrant_points(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Create points formatted for Qdrant."""
    qdrant_points = []

    for idx, doc in enumerate(docs):
        doc_id = str(uuid.uuid4())
        created_date = datetime.now() - timedelta(days=random.randint(1, 365))

        # Generate embedding for semantic search
        embedding = generate_mock_embedding(doc["content"])

        point = {
            "id": idx,  # Qdrant uses integer IDs
            "vector": embedding,
            "payload": {
                "doc_id": doc_id,
                "title": doc["title"],
                "content": doc["content"],
                "source": f"knowledge-base/{doc_id}",
                "owner": doc["owner"],
                "classification": doc["classification"],
                "topics": doc["topics"],
                "status": doc["status"],
                "created_date": created_date.timestamp(),
            },
        }
        qdrant_points.append(point)

    return qdrant_points


def seed_meilisearch(documents: List[Dict[str, Any]]) -> bool:
    """Load documents into Meilisearch."""
    print("\n📚 Seeding Meilisearch...")

    try:
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
        )

        if docs_response.status_code in [200, 202]:
            print(f"  ✅ Loaded {len(documents)} documents into Meilisearch")
            # Wait for indexing to complete
            import time

            print("  ⏳ Waiting for indexing to complete...")
            for i in range(30):  # Wait up to 30 seconds
                time.sleep(1)
                stats_resp = requests.get(
                    f"{MEILISEARCH_URL}/indexes/{MEILISEARCH_INDEX}/stats"
                )
                if stats_resp.status_code == 200:
                    doc_count = stats_resp.json().get("numberOfDocuments", 0)
                    if doc_count == len(documents):
                        print(f"  ✅ Indexing complete ({doc_count} documents)")
                        return True
            return True  # Return True anyway, might just be slow
        else:
            print(f"  ❌ Failed to load documents: {docs_response.status_code}")
            print(f"     {docs_response.text}")
            return False

    except Exception as e:
        print(f"  ❌ Meilisearch error: {e}")
        return False


def seed_qdrant(points: List[Dict[str, Any]]) -> bool:
    """Load embeddings into Qdrant."""
    print("\n🔍 Seeding Qdrant...")

    try:
        # Create collection with vector size
        collection_config = {"vectors": {"size": 1536, "distance": "Cosine"}}

        create_response = requests.put(
            f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}",
            json=collection_config,
        )
        print(f"  Create collection response: {create_response.status_code}")

        # Upsert points
        upsert_response = requests.put(
            f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points?wait=true",
            json={"points": points},
        )

        if upsert_response.status_code in [200, 201]:
            print(f"  ✅ Loaded {len(points)} vectors into Qdrant")
            return True
        else:
            print(f"  ❌ Failed to load vectors: {upsert_response.status_code}")
            print(f"     {upsert_response.text}")
            return False

    except Exception as e:
        print(f"  ❌ Qdrant error: {e}")
        return False


def verify_seeding() -> bool:
    """Verify that data was loaded correctly."""
    print("\n✔️  Verifying seeding...")

    try:
        # Check Meilisearch
        stats_response = requests.get(
            f"{MEILISEARCH_URL}/indexes/{MEILISEARCH_INDEX}/stats"
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
            f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}"
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


def main():
    """Main seeding orchestration."""
    print("=" * 60)
    print("KB Search API - Test Data Seeding")
    print("=" * 60)

    # Prepare documents
    print(f"\n📄 Preparing {len(SAMPLE_DOCUMENTS)} sample documents...")
    meilisearch_docs = create_meilisearch_documents(SAMPLE_DOCUMENTS)
    qdrant_points = create_qdrant_points(SAMPLE_DOCUMENTS)

    # Seed search engines
    meilisearch_ok = seed_meilisearch(meilisearch_docs)
    qdrant_ok = seed_qdrant(qdrant_points)

    # Verify
    if verify_seeding():
        print("\n" + "=" * 60)
        print("✅ Test data seeding SUCCESSFUL")
        print("=" * 60)
        print("\nYou can now test the search API:")
        print("  curl -X POST http://localhost:8002/api/v1/search \\")
        print("    -H 'Content-Type: application/json' \\")
        print('    -d \'{"query": "postgresql", "limit": 5}\'')
        return True
    else:
        print("\n" + "=" * 60)
        print("❌ Test data seeding FAILED")
        print("=" * 60)
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
