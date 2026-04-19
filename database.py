"""
Database connection management and session handling.

Provides PostgreSQL and Redis connection utilities with proper cleanup.
"""

import logging
from typing import AsyncGenerator, Optional
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool, QueuePool
from redis.asyncio import Redis, ConnectionPool
from config import get_settings

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages PostgreSQL and Redis connections."""

    def __init__(self):
        """Initialize database manager."""
        self.settings = get_settings()
        self.postgres_engine = None
        self.postgres_session_factory = None
        self.redis_pool: Optional[ConnectionPool] = None
        self.redis_client: Optional[Redis] = None

    async def initialize(self) -> None:
        """
        Initialize database connections.

        Should be called on application startup.
        """
        try:
            # PostgreSQL engine
            database_url = self.settings.database_url.replace("postgresql://", "postgresql+asyncpg://")

            engine_kwargs = {
                "echo": self.settings.db_echo,
                "pool_pre_ping": True,
            }

            if self.settings.environment == "production":
                engine_kwargs["poolclass"] = QueuePool
                engine_kwargs["pool_size"] = self.settings.db_pool_size
                engine_kwargs["max_overflow"] = self.settings.db_max_overflow
                engine_kwargs["pool_recycle"] = self.settings.db_pool_recycle
                engine_kwargs["pool_pre_ping"] = True
            else:
                engine_kwargs["poolclass"] = NullPool

            self.postgres_engine = create_async_engine(database_url, **engine_kwargs)
            self.postgres_session_factory = async_sessionmaker(
                self.postgres_engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )

            logger.info("PostgreSQL engine initialized")

            # Redis connection
            self.redis_client = await Redis.from_url(
                self.settings.redis_url,
                encoding="utf8",
                decode_responses=True,
                socket_keepalive=True,
                socket_keepalive_options={
                    1: 1,  # TCP_KEEPIDLE
                    2: 1,  # TCP_KEEPINTVL
                },
            )

            # Test connection
            await self.redis_client.ping()
            logger.info("Redis connection initialized")

        except Exception as e:
            logger.error(f"Failed to initialize database connections: {e}")
            raise

    async def close(self) -> None:
        """
        Close all database connections.

        Should be called on application shutdown.
        """
        try:
            if self.postgres_engine:
                await self.postgres_engine.dispose()
                logger.info("PostgreSQL engine disposed")

            if self.redis_client:
                await self.redis_client.close()
                logger.info("Redis connection closed")
        except Exception as e:
            logger.error(f"Error closing database connections: {e}")

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get a database session.

        Yields:
            AsyncSession: Database session

        Example:
            async with database.get_session() as session:
                result = await session.execute(query)
        """
        if not self.postgres_session_factory:
            raise RuntimeError("Database not initialized")

        session = self.postgres_session_factory()
        try:
            yield session
        finally:
            await session.close()

    async def get_redis(self) -> Redis:
        """
        Get Redis client.

        Returns:
            Redis: Redis client

        Example:
            redis = await database.get_redis()
            value = await redis.get("key")
        """
        if not self.redis_client:
            raise RuntimeError("Redis not initialized")
        return self.redis_client

    async def health_check(self) -> dict:
        """
        Check health of all database connections.

        Returns:
            dict: Health status for each component

        Example:
            >>> health = await database.health_check()
            >>> print(health)
            {'postgresql': True, 'redis': True}
        """
        health = {}

        # PostgreSQL health check
        try:
            async with self.postgres_engine.connect() as conn:
                await conn.execute("SELECT 1")
            health["postgresql"] = True
        except Exception as e:
            logger.error(f"PostgreSQL health check failed: {e}")
            health["postgresql"] = False

        # Redis health check
        try:
            await self.redis_client.ping()
            health["redis"] = True
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            health["redis"] = False

        return health


# Global database manager instance
_db_manager: Optional[DatabaseManager] = None


def get_database_manager() -> DatabaseManager:
    """
    Get or create the global database manager.

    Returns:
        DatabaseManager: Global database manager instance

    Example:
        >>> db = get_database_manager()
        >>> await db.initialize()
    """
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager
