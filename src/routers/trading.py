import datetime
from typing import Optional, Dict, Any
from utils.app_logger import setup_logger
from utils.config import get_sync_database

logger = setup_logger("src/routers/trading.py")
db = get_sync_database()

