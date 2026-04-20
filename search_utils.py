"""
Search utility functions for ranking and fusion.
"""
from typing import List, Dict, Any
from models import SearchResultItem

class SearchUtils:
    """Utility class for search operations."""
    
    @staticmethod
    def reciprocal_rank_fusion(
        results: List[Dict[str, Any]],
        semantic_weight: float,
        limit: int,
        offset: int = 0,
        k: int = 60
    ) -> List[Dict[str, Any]]:
        """
        Combine results using Reciprocal Rank Fusion (RRF).
        
        Args:
            results: Combined list of keyword and semantic results
            semantic_weight: Weight to apply to semantic scores
            limit: Number of results to return
            offset: Number of results to skip
            k: RRF constant (default 60)
            
        Returns:
            List[Dict[str, Any]]: Ranked and fused results
        """
        doc_scores: Dict[str, Dict[str, Any]] = {}

        for result in results:
            doc_id = str(result["doc_id"])

            if doc_id not in doc_scores:
                doc_scores[doc_id] = {
                    "doc_id": result["doc_id"],
                    "title": result["title"],
                    "source": result["source"],
                    "owner": result["owner"],
                    "classification": result["classification"],
                    "created_date": result["created_date"],
                    "excerpt": result.get("excerpt", ""),
                    "highlighted_excerpt": result.get("highlighted_excerpt"),
                    "topics": result.get("topics", []),
                    "keyword_score": 0.0,
                    "keyword_rank": 1000,
                    "semantic_score": 0.0,
                    "semantic_rank": 1000,
                }

            # Apply weights based on search type
            if result["search_type"] == "keyword":
                doc_scores[doc_id]["keyword_score"] += result.get(
                    "relevance_score", 0.5
                )
                doc_scores[doc_id]["keyword_rank"] = min(
                    doc_scores[doc_id]["keyword_rank"], result.get("rank", 1000)
                )
            elif result["search_type"] == "semantic":
                doc_scores[doc_id]["semantic_score"] += result.get(
                    "relevance_score", 0.5
                )
                doc_scores[doc_id]["semantic_rank"] = min(
                    doc_scores[doc_id]["semantic_rank"], result.get("rank", 1000)
                )

        # Calculate final scores
        final_results = []
        for doc_id, scores in doc_scores.items():
            keyword_rrf = (
                1 / (k + scores.get("keyword_rank", 1000))
                if scores.get("keyword_score", 0) > 0
                else 0
            )
            semantic_rrf = (
                1 / (k + scores.get("semantic_rank", 1000))
                if scores.get("semantic_score", 0) > 0
                else 0
            )

            # Apply semantic weight
            combined_score = (keyword_rrf * (1.0 - semantic_weight)) + (
                semantic_rrf * semantic_weight
            )

            final_results.append(
                SearchResultItem(
                    doc_id=str(scores["doc_id"]),
                    rank=len(final_results) + 1,
                    title=scores["title"],
                    source=scores["source"],
                    owner=scores["owner"],
                    classification=scores["classification"],
                    created_date=scores["created_date"] if isinstance(scores["created_date"], str) else scores["created_date"].isoformat(),
                    relevance_score=combined_score,
                    search_type="hybrid",
                    excerpt=scores["excerpt"],
                    highlighted_excerpt=scores["highlighted_excerpt"],
                    topics=scores["topics"],
                )
            )

        # Sort by relevance score, apply offset, and limit
        final_results.sort(key=lambda x: x.relevance_score, reverse=True)
        return [r.model_dump() for r in final_results[offset : offset + limit]]
