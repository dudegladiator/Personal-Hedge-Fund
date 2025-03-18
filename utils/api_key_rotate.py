from time import sleep
from datetime import datetime, timedelta
import random
from typing import List
from utils.app_logger import setup_logger

logger = setup_logger("utils/api_key_rotate.py")

class APIKeyManager:
    def __init__(self, api_keys: List[str], model_name: str = None, rate_limit: int = 10, cooldown_period: int = 60):
        self.api_keys = api_keys
        self.current_key_index = 0
        self.request_counts = {key: 0 for key in api_keys}
        self.last_request_time = {key: datetime.now() for key in api_keys}
        self.rate_limit = rate_limit
        self.cooldown_period = cooldown_period

    def get_next_available_key(self) -> str:
        start_index = self.current_key_index
        
        while True:
            current_key = self.api_keys[self.current_key_index]
            current_time = datetime.now()
            
            # Check if current key has cooled down
            time_diff = (current_time - self.last_request_time[current_key]).total_seconds()
            
            if time_diff >= self.cooldown_period:
                # Reset counter if cooldown period has passed
                self.request_counts[current_key] = 0
                
            if self.request_counts[current_key] < self.rate_limit:
                # Key is available
                return current_key, self.current_key_index
            
            # Move to next key
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
            
            # If we've checked all keys and none are available, wait
            if self.current_key_index == start_index:
                sleep(10)
                
    def use_and_get_key(self):
        key, index = self.get_next_available_key()
        self.request_counts[key] += 1
        logger.info(f"Using key {index}")
        self.last_request_time[key] = datetime.now()
        return key