import asyncio
import logging

logger = logging.getLogger(__name__)


async def cleanup_loop(database, interval_seconds: int = 300):
    while True:
        try:
            deleted = await database.cleanup_expired(3600)
            if deleted:
                logger.info("Removed %s expired user states", deleted)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("User-state cleanup failed")
        await asyncio.sleep(interval_seconds)
