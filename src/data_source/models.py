from datetime import datetime
from typing import Optional
from pydantic import BaseModel
import pytz

class LivePrice(BaseModel):
    symbol: str
    exchange: str
    open: float
    high: float
    low: float
    close: float
    ltp: float
    volume: int
    timestamp: int  
    day_change: float
    day_change_percentage: float
    updated_at: datetime = datetime.now(pytz.UTC)

class GrowwStockDetails(BaseModel):
    """Combined model for basic and detailed stock information"""
    # Basic Information
    symbol: str                    # Stock symbol/query used
    search_id: str                 # Unique identifier for the stock
    title: str                     # Company title
    bse_scrip_code: Optional[str]  # BSE scrip code
    nse_scrip_code: Optional[str]  # NSE scrip code
    isin: Optional[str]            # International Securities Identification Number
    entity_type: str               # Type of entity (e.g., Stocks, ETF)
    
    # Metadata
    updated_at: datetime = datetime.now(pytz.UTC)


