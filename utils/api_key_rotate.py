from time import sleep
from datetime import datetime, timedelta
import random
from typing import List
from utils.app_logger import setup_logger

logger = setup_logger("utils/api_key_rotate.py")

class APIKeyManager:
    def __init__(self, api_keys: List[str], model_name: str = None, rate_limit: int = 10, cooldown_period: int = 60, day_limit: int = 1500):
        self.api_keys = api_keys
        self.current_key_index = 0
        self.request_counts = {key: 0 for key in api_keys}
        self.daily_counts = {key: 0 for key in api_keys}
        self.last_request_time = {key: datetime.now() for key in api_keys}
        self.last_day_reset = {key: datetime.now() for key in api_keys}
        self.rate_limit = rate_limit
        self.cooldown_period = cooldown_period
        self.day_limit = day_limit

    def _check_and_reset_daily_count(self, key: str) -> None:
        current_time = datetime.now()
        time_since_reset = current_time - self.last_day_reset[key]
        
        # Reset daily count if 24 hours have passed
        if time_since_reset >= timedelta(days=1):
            self.daily_counts[key] = 0
            self.last_day_reset[key] = current_time
            logger.info(f"Daily count reset for key {self.api_keys.index(key)}")

    def get_next_available_key(self) -> str:
        start_index = self.current_key_index
        
        while True:
            current_key = self.api_keys[self.current_key_index]
            current_time = datetime.now()
            
            # Check and reset daily count if needed
            self._check_and_reset_daily_count(current_key)
            
            # Check if current key has cooled down
            time_diff = (current_time - self.last_request_time[current_key]).total_seconds()
            
            if time_diff >= self.cooldown_period:
                # Reset rate limit counter if cooldown period has passed
                self.request_counts[current_key] = 0
                
            # Check both rate limit and daily limit
            if (self.request_counts[current_key] < self.rate_limit and 
                self.daily_counts[current_key] < self.day_limit):
                # Key is available
                return current_key, self.current_key_index
            
            # Move to next key
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
            
            # If we've checked all keys and none are available, wait
            if self.current_key_index == start_index:
                logger.warning("All keys at limit, waiting...")
                sleep(10)
                
    def use_and_get_key(self):
        key, index = self.get_next_available_key()
        self.request_counts[key] += 1
        self.daily_counts[key] += 1
        logger.info(f"Using key {index} (Daily count: {self.daily_counts[key]}/{self.day_limit})")
        self.last_request_time[key] = datetime.now()
        return key