from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.utils.logger import logger

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect_mongodb() -> None:
    global _client, _db
    from app.config.settings import settings
    _client = AsyncIOMotorClient(settings.MONGODB_URL)
    _db = _client[settings.MONGODB_DB_NAME]
    await _client.admin.command("ping")
    logger.info(f"Connected to MongoDB Atlas — database: {settings.MONGODB_DB_NAME}")


async def close_mongodb() -> None:
    global _client
    if _client:
        _client.close()
        logger.info("MongoDB connection closed")


def get_mongodb() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("MongoDB not initialized")
    return _db


async def get_db() -> AsyncIOMotorDatabase:
    yield get_mongodb()


def col(name: str):
    return get_mongodb()[name]
