"""
Verification tests for RRF and Hybrid Pagination fixes.
"""
import pytest
from datetime import datetime
from search_utils import SearchUtils

@pytest.mark.asyncio
async def test_rrf_rank_logic():
    """Verify that RRF correctly uses ranks from keyword and semantic results."""
    # Setup
    # Results with different ranks
    results = [
        {
            "doc_id": "doc1",
            "title": "Keyword Doc",
            "rank": 1, # Top keyword
            "search_type": "keyword",
            "relevance_score": 0.9,
            "source": "/test",
            "owner": "team",
            "classification": "internal",
            "created_date": datetime.now(),
            "excerpt": "...",
            "highlighted_excerpt": None,
            "topics": []
        },
        {
            "doc_id": "doc1",
            "title": "Keyword Doc",
            "rank": 5, # Low semantic
            "search_type": "semantic",
            "relevance_score": 0.4,
            "source": "/test",
            "owner": "team",
            "classification": "internal",
            "created_date": datetime.now(),
            "excerpt": "...",
            "highlighted_excerpt": None,
            "topics": []
        }
    ]
    
    # Execute fusion
    # RRF = 1/(60+1) + 1/(60+5) for doc1
    combined = SearchUtils.reciprocal_rank_fusion(results, 0.5, 10, 0)
    
    assert len(combined) == 1
    # Check that it didn't use the default 1000 rank
    # 1/61 + 1/65 ~= 0.01639 + 0.01538 = 0.03177
    # Weighted: (0.01639 * 0.5) + (0.01538 * 0.5) = 0.01588
    assert combined[0]["relevance_score"] > 0.01

@pytest.mark.asyncio
async def test_hybrid_pagination_slicing():
    """Verify that RRF handles offset correctly."""
    # 5 results
    from datetime import datetime
    results = [
        {
            "doc_id": f"doc{i}",
            "title": f"Doc {i}",
            "rank": i,
            "search_type": "keyword",
            "relevance_score": 0.9 - i * 0.1,
            "source": "/test",
            "owner": "team",
            "classification": "internal",
            "created_date": datetime.now(),
            "excerpt": "...",
            "highlighted_excerpt": None,
            "topics": [],
        }
        for i in range(1, 6)
    ]
    
    # Request limit 2, offset 2
    # Should return doc3, doc4
    combined = SearchUtils.reciprocal_rank_fusion(results, 0.5, 2, 2)
    
    assert len(combined) == 2
    assert combined[0]["title"] == "Doc 3"
    assert combined[1]["title"] == "Doc 4"

if __name__ == "__main__":
    pytest.main([__file__])
