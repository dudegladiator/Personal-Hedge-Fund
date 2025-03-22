from datetime import datetime, time
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