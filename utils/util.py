from datetime import datetime, time, timedelta
import math
from typing import Any, Dict, Optional
import pytz

def indian_stock_market_open() -> bool:
    """
    Check if Indian stock market is currently open
    Market timing: 9:15 AM to 3:30 PM IST, Monday to Friday
    """
    ist = pytz.timezone('Asia/Kolkata')
    current_time = datetime.now(ist)
    
    # Check if it's weekend
    if current_time.weekday() > 4:  # 5 is Saturday, 6 is Sunday
        return False
    
    market_start = time(9, 15)  # 9:15 AM
    market_end = time(15, 30)   # 3:30 PM
    current_time_ist = current_time.time()
    
    return market_start <= current_time_ist <= market_end

def safe_get(data_dict, keys, default="N/A"):
        """Safely retrieves nested values from a dictionary, returning a default if not found."""
        try:
            for key in keys:
                data_dict = data_dict[key]
            return data_dict
        except (KeyError, TypeError):
            return default
        
def get_latest_announcements(entries, date_field, days=90, date_format="%d-%m-%Y"):
    valid_entries = [entry for entry in entries if date_field in entry]
    if not valid_entries:
        return []
    
    cutoff_date = datetime.now() - timedelta(days=days)
    
    try:
        recent_entries = [
            entry for entry in valid_entries
            if datetime.strptime(entry[date_field], date_format) >= cutoff_date
        ]
        
        sorted_entries = sorted(
            recent_entries,
            key=lambda x: datetime.strptime(x[date_field], date_format),
            reverse=True
        )
        return sorted_entries
    
    except ValueError as e:
        return []

def get_latest_news(news_list, days):
    valid_news = [news for news in news_list if "published_date" in news]
    if not valid_news:
        return []
    
    cutoff_date = datetime.now() - timedelta(days=days)
    
    try:
        recent_news = [
            news for news in valid_news
            if datetime.strptime(news["published_date"], "%Y-%m-%d %H:%M:%S") >= cutoff_date
        ]
        
        sorted_news = sorted(
            recent_news,
            key=lambda x: datetime.strptime(x["published_date"], "%Y-%m-%d %H:%M:%S"),
            reverse=True
        )
        return sorted_news
    
    except ValueError as e:
        return []
    
    
def _safe_get_float(data: Optional[Dict], key: str) -> Optional[float]:
    if data is None:
        return None

    value = data.get(key)

    if value is None or value == "":
        return None

    try:
        # Attempt conversion to float
        float_value = float(value)
        # Check for NaN or infinity which can cause issues later
        if math.isnan(float_value) or math.isinf(float_value):
            return None
        return float_value
    except (ValueError, TypeError):
        # Handle cases where conversion is not possible (e.g., strings like "abc")
        return None