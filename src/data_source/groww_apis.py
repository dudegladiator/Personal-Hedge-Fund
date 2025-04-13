from datetime import datetime, timedelta
from typing import Dict, Optional
import pytz
import requests
from utils.app_logger import setup_logger
from utils.config import get_sync_database

logger = setup_logger("src/data_source/groww_apis.py")
db = get_sync_database()

def get_live_price(symbol: str, exchange: str = "NSE") -> Optional[Dict]:
    """
    Get live price for a given symbol
    If market is open: Fetch from API
    If market is closed: Fetch from DB
    """
    try: 
        # If market is open, fetch from API
        url = f"https://groww.in/v1/api/stocks_data/v1/accord_points/exchange/{exchange}/segment/CASH/latest_prices_ohlc/{symbol}"
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            logger.error(f"Failed to fetch price for {symbol}. Status code: {response.status_code}")
            return None
            
        data = response.json()
        live_price = {
            "symbol": symbol,
            "exchange": exchange,
            "open": data['open'],
            "high": data['high'],
            "low": data['low'],
            "close": data['close'],
            "ltp": data['ltp'],   # last traded price
            "volume": data['volume'],
            "timestamp": data['tsInMillis'],
            "day_change": data['dayChange'],
            "day_change_percentage": data['dayChangePerc'],
            "updated_at": datetime.now(pytz.UTC)
        }
        
        
        logger.info(f"Successfully fetched and stored live price for {symbol}")
        return live_price
        
    except requests.RequestException as e:
        logger.error(f"Network error while fetching price for {symbol}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error while fetching price for {symbol}: {str(e)}")
        return None
    
def groww_stock_details(query: str) -> Optional[Dict]:
    """
    Search for a company on Groww platform and fetch detailed information

    Parameters:
        query (str): Company name or symbol to search for

    Returns:
        Dictionary containing comprehensive company details or None if not found
    """
    try:
        # Check if we have recent data in database (not older than 3 days)
        query_lower = query.lower()
        db_result = db.groww_stock_details.find_one({
            "$or": [
                {"symbol": {"$regex": query_lower, "$options": "i"}}
            ],
        })

        if db_result:
            logger.info(f"Found recent company details in database for: {query}")
            db_result.pop('_id', None)
            return db_result

        # First API call - Search for company
        search_url = f"https://groww.in/v1/api/search/v3/query/global/st_p_query?query={query}"
        search_response = requests.get(search_url, timeout=10)
        
        if search_response.status_code != 200:
            logger.error(f"Failed to fetch company details. Status code: {search_response.status_code}")
            return None

        search_data = search_response.json()
        
        if not search_data.get('data', {}).get('content', []):
            logger.warning(f"No results found for query: {query}")
            return None

        # Get the first result
        first_result = search_data['data']['content'][0]
        search_id = first_result.get('search_id', '')
        
        stock_details = {
            "symbol": query,
            "search_id": search_id,
            "title": first_result.get('title', ''),
            "bse_scrip_code": first_result.get('bse_scrip_code'),
            "nse_scrip_code": first_result.get('nse_scrip_code'),
            "isin": first_result.get('isin'),
            "entity_type": first_result.get('entity_type', ''),
            "updated_at": datetime.now(pytz.UTC)
        }

        # Update database
        db.groww_stock_details.update_one(
            {"search_id": stock_details.search_id},
            {
                "$set": stock_details
            },
            upsert=True
        )

        logger.info(f"Successfully fetched and stored comprehensive details for: {query}")
        return stock_details

    except requests.RequestException as e:
        logger.error(f"Network error while fetching details for {query}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error while fetching details for {query}: {str(e)}")
        return None
    
def stock_full_info(search_id: str) -> Optional[Dict]:
    """
    Fetch stock overview data and store in database
    
    Args:
        search_id (str): Stock search ID (e.g., 'reliance-industries-ltd')
    
    Returns:
        Optional[Dict]: Stock overview data or None if error occurs
    """
    try:
        # Check if we have recent data (less than 24 hours old)
        db_result = db.groww_stock_details.find_one(
            {
                "search_id": search_id,
                "overview.updated_at": {
                    "$gte": datetime.now(pytz.UTC) - timedelta(hours=72)
                }
            }
        )

        if db_result and 'overview' in db_result:
            logger.info(f"Found recent overview data for {search_id}")
            return db_result['overview']

        # If not in DB or too old, fetch from API
        url = f"https://groww.in/v1/api/stocks_data/v1/company/search_id/{search_id}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # Add timestamp to the data
        overview_data = {
            "header": data.get("header", {}),
            "details": data.get("details", {}),
            "stats": data.get("stats", {}),
            "brandDtos": data.get("brandDtos", []),
            "fundamentals": data.get("fundamentals", []),
            "shareHoldingPattern": data.get("shareHoldingPattern", {}),
            "fundsInvested": data.get("fundsInvested", []),
            "priceData": data.get("priceData", {}),
            "financialStatement": data.get("financialStatement", []),
            "similarAssets": data.get("similarAssets", {}),
            "expertRating": data.get("expertRating", {}),
            "updated_at": datetime.now(pytz.UTC)
        }

        # Update database
        db.groww_stock_details.update_one(
            {"search_id": search_id},
            {
                "$set": {
                    "overview": overview_data,
                    "last_overview_update": datetime.now(pytz.UTC)
                }
            },
            upsert=True
        )

        logger.info(f"Successfully updated overview data for {search_id}")
        return overview_data

    except requests.RequestException as e:
        logger.error(f"Network error fetching overview for {search_id}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error processing overview data for {search_id}: {str(e)}")
        return None

if __name__ == "__main__":
    # print(groww_stock_details("reliance"))
    # print(stock_full_info("reliance-industries-ltd"))
    pass

    print(get_live_price("RELIANCE", "NSE"))