from datetime import datetime, timedelta
import pytz
import requests
from typing import Optional, Dict
from utils.app_logger import setup_logger
from utils.config import settings, get_sync_database

logger = setup_logger("src/data_source/markets_apis.py")
db = get_sync_database()

baseURL = "https://frapi.marketsmojo.com"

def get_stock_sid(symbol: str, exchange: str = "nse", force: bool = False) -> Optional[str]:
    """
    Get stock SID from MarketsMojo
    
    Args:
        symbol (str): Stock symbol (e.g., 'RELIANCE')
        exchange (str): Exchange name ('nse' or 'bse')
        force (bool): Force fetch from API ignoring cache
        
    Returns:
        Optional[str]: Stock SID or None if not found
    """
    try:
        if not force:
            # First check in database
            db_result = db.stock_sids.find_one({
                "symbol": symbol,
                "exchange": exchange.lower()
            })

            if db_result:
                logger.info(f"Found SID in database for {symbol}")
                return db_result['sid']

        # If not in database, fetch from API
        url = f"https://www.marketsmojo.com/common_services/searchScrips?section=stock&SearchPhrase={symbol}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        if len(data)==0:
            logger.warning(f"No SID found for {symbol}")
            return None

        sid = data[0].get("Id", None)
        
        # Store in database
        if sid:
            db.stock_sids.update_one(
                {
                    "symbol": symbol,
                    "exchange": exchange.lower()
                },
                {
                    "$set": {
                        "sid": sid,
                        "script_code": data[0].get("ScriptCode", None),
                        "url": data[0].get("url", None),
                        "updated_at": datetime.now(pytz.UTC)
                    }
                },
                upsert=True
            )

        return sid
    except Exception as e:
        logger.error(f"Error fetching SID for {symbol}: {str(e)}")
        return None

def get_corporate_announcements(
    symbol: str,
    exchange: str = "nse",
    force: bool = False
) -> Optional[Dict]:
    """
    Get corporate announcements from MarketsMojo
    
    Args:
        symbol (str): Stock symbol (e.g., 'RELIANCE')
        exchange (str): Exchange name ('nse' or 'bse')
        force (bool): Force fetch from API ignoring cache
        
    Returns:
        Optional[Dict]: Corporate announcements data or None if error occurs
    """
    try:
        exchange_code = 1 if exchange.lower() == "nse" else 0
        
        # Check in database if force is False
        if not force:
            db_result = db.corporate_announcements_news.find_one({
                "symbol": symbol.upper(),
                "exchange": exchange.lower(),
                "announcements": {"$exists": True},
                "announcements_updated_at": {
                    "$gte": datetime.now(pytz.UTC) - timedelta(hours=24)
                }
            })

            if db_result:
                logger.info(f"Found recent announcements in database for {symbol}")
                return db_result['announcements']
            
        # Get SID first
        sid = get_stock_sid(symbol, exchange)
        if not sid:
            logger.error(f"Could not get SID for {symbol}")
            return None

        # Fetch announcements
        url = f"{baseURL}/Stocks_Corporateactions/Corp_action_Full_Details"
        params = {
            "sid": sid,
            "exchange": exchange_code,
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        raw_data = response.json()
        
        # Process and structure the data
        structured_data = {
            "board_meetings": [],
            "dividends": [],
            "splits": [],
            "bonus": [],
            "rights": [],
            "updated_at": datetime.now(pytz.UTC)
        }

        # Process each announcement type
        for announcement in raw_data.get('data', []):
            title = announcement.get('title', '').lower()
            data = announcement.get('data', [])

            if title == "board meeting":
                structured_data["board_meetings"] = [
                    {
                        "date": meeting[0],
                        "agenda": meeting[1]
                    }
                    for meeting in data
                ]

            elif title == "dividend":
                structured_data["dividends"] = [
                    {
                        "record_date": div[0],
                        "ex_date": div[1],
                        "dividend_percentage": div[2],
                        "details": div[3]
                    }
                    for div in data
                ]

            elif title == "split":
                if data:  # If there's split data
                    structured_data["splits"] = [
                        {
                            "record_date": split[0],
                            "ex_date": split[1],
                            "ratio": split[2]
                        }
                        for split in data
                    ]

            elif title == "bonus":
                structured_data["bonus"] = [
                    {
                        "record_date": bonus[0],
                        "ex_date": bonus[1],
                        "ratio": bonus[2]
                    }
                    for bonus in data
                ]

            elif title == "rights":
                structured_data["rights"] = [
                    {
                        "record_date": rights[0],
                        "ex_date": rights[1],
                        "ratio": rights[2],
                        "premium": rights[3]
                    }
                    for rights in data
                ]

        # Store in database
        db.corporate_announcements_news.update_one(
            {
                "symbol": symbol.upper(),
                "exchange": exchange.lower(),
                "sid": sid
            },
            {"$set": {"announcements": structured_data, "announcements_updated_at": datetime.now(pytz.UTC)}},
            upsert=True
        )

        logger.info(f"Successfully fetched and structured announcements for {symbol}")
        return structured_data

    except requests.RequestException as e:
        logger.error(f"Network error fetching announcements for {symbol}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error processing announcements for {symbol}: {str(e)}")
        return None
    
    
def get_stock_news(
    symbol: str,
    exchange: str = "nse",
    force: bool = False
) -> Optional[Dict]:
    """
    Get stock news from MarketsMojo
    
    Args:
        symbol (str): Stock symbol (e.g., 'RELIANCE')
        exchange (str): Exchange name ('nse' or 'bse')
        force (bool): Force fetch from API ignoring cache
        
    Returns:
        Optional[Dict]: News data or None if error occurs
    """
    try:
        # Check in database if force is False
        if not force:
            db_result = db.corporate_announcements_news.find_one(
                {
                    "symbol": symbol,
                    "exchange": exchange.lower(),
                    "news": {"$exists": True},
                    "news_updated_at": {
                        "$gte": datetime.now(pytz.UTC) - timedelta(hours=24)
                    }
                }
            )

            if db_result and 'news' in db_result:
                logger.info(f"Found recent news in database for {symbol}")
                return db_result['news']

        # Get SID first
        sid = get_stock_sid(symbol, exchange)
        if not sid:
            logger.error(f"Could not get SID for {symbol}")
            return None

        # Fetch news
        url = f"{baseURL}/stocks_news/listNews"
        payload = {
            "sid": sid,
            "exchange": 0 if exchange.lower() == "bse" else 1
        }
        
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('code') != "200":
            logger.error(f"API returned error: {data.get('message')}")
            return None

        # Process news data
        news_list = []
        for news in data.get('data', {}).get('results', []):
            news_item = {
                "news_id": news.get('resultData'),
                "title": news.get('title'),
                "description": news.get('description'),
                "published_date": news.get('publisheddate'),
                "link": news.get('link'),
                "source": news.get('source')
            }
            news_list.append(news_item)

        # Update database with news data
        db.corporate_announcements_news.update_one(
            {
                "symbol": symbol,
                "exchange": exchange.lower(),
                "sid": sid
            },
            {
                "$set": {
                    "news": news_list,
                    "news_updated_at": datetime.now(pytz.UTC)
                }
            },
            upsert=True
        )

        logger.info(f"Successfully fetched and stored news for {symbol}")
        return news_list

    except requests.RequestException as e:
        logger.error(f"Network error fetching news for {symbol}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error processing news for {symbol}: {str(e)}")
        return None
    
    
if __name__ == "__main__":
    # Test get_stock_sid
    # sid = get_stock_sid("SHAKTIPUMP", force=True)
    # print(sid)
    
    # # Test get_corporate_announcements
    print(get_corporate_announcements("RELIANCE"))
    
    print(get_stock_news("RELIANCE"))
    
    

    
    pass