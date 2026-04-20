"""
Custom exception classes for the Knowledge Base Search API.
"""
from typing import Any, Dict, Optional

class KBSearchError(Exception):
    """Base exception for all KB Search API errors."""
    def __init__(
        self, 
        message: str, 
        code: str = "INTERNAL_ERROR", 
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}

class AuthenticationError(KBSearchError):
    """Raised when API key or other auth fails."""
    def __init__(self, message: str = "Invalid or missing API Key"):
        super().__init__(message, code="AUTH_ERROR", status_code=401)

class ValidationError(KBSearchError):
    """Raised when request validation fails."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="VALIDATION_ERROR", status_code=422, details=details)

class SearchEngineError(KBSearchError):
    """Raised when Meilisearch or Qdrant fail."""
    def __init__(self, message: str, engine: str):
        super().__init__(
            message, 
            code=f"{engine.upper()}_ERROR", 
            status_code=502,
            details={"engine": engine}
        )

class ResourceNotFoundError(KBSearchError):
    """Raised when a document or index is not found."""
    def __init__(self, message: str, resource_type: str, resource_id: str):
        super().__init__(
            message, 
            code="NOT_FOUND", 
            status_code=404,
            details={"type": resource_type, "id": resource_id}
        )
