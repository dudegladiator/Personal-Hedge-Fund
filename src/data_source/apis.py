from utils.app_logger import setup_logger
from utils.config import settings, get_sync_database, get_async_database

db = get_sync_database()
async_db = get_async_database()
