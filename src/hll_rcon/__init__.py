from loguru import logger
import sys
import os

logger.remove()  # Remove the default handler.
logger.add(sys.stderr, level=os.getenv("LOGGING_LEVEL", "INFO"))
