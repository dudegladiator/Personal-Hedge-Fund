from datetime import datetime, timedelta
import pytz
import requests
from typing import List, Optional, Dict
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
                "symbol": symbol,
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
                "symbol": symbol,
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
    
def get_company_dashboard(
    symbol: str,
    exchange: str = "nse",
    force: bool = False
) -> Optional[Dict]:
    """
    Get company dashboard data from MarketsMojo
    
    Args:
        symbol (str): Stock symbol (e.g., 'RELIANCE')
        exchange (str): Exchange name ('nse' or 'bse')
        force (bool): Force fetch from API ignoring cache
        
    Returns:
        Optional[Dict]: Dashboard data or None if error occurs
    """
    try:
        # Check in database if force is False
        if not force:
            db_result = db.company_dashboard.find_one(
                {
                    "symbol": symbol,
                    "exchange": exchange.lower(),
                    "updated_at": {
                        "$gte": datetime.now(pytz.UTC) - timedelta(hours=24)
                    }
                }
            )

            if db_result:
                logger.info(f"Found recent dashboard data for {symbol}")
                return db_result

        # Get SID first
        sid = get_stock_sid(symbol, exchange)
        if not sid:
            logger.error(f"Could not get SID for {symbol}")
            return None

        # Fetch dashboard data
        url = f"{baseURL}/stocks_dashboard/getDashboard/{sid}/{0 if exchange.lower() == 'bse' else 1}"
        response = requests.post(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('code') != "200":
            logger.error(f"API returned error: {data.get('message')}")
            return None

        dashboard_data = data.get('data', {}).get('dashboard', {})
        price_info = dashboard_data.get('priceinfo', {})
        stock_details = dashboard_data.get('stock_details', {})
        
        # Structure important data
        structured_data = {
            "symbol": symbol,
            "exchange": exchange.lower(),
            "company_info": {
                "name": stock_details.get('sname'),
                "short_name": stock_details.get('short_name'),
                "isin": stock_details.get('isin'),
                "industry": stock_details.get('ind_name'),
                "sector": stock_details.get('acc_ind_name'),
                "incorporation_date": f"{stock_details.get('inc_mnth')} {stock_details.get('inc_yr')}",
                "market_cap_category": stock_details.get('amfi_mcapsizerank')
            },
            "key_metrics": {
                "market_cap": price_info.get('mcap'),
                "pe_ratio": price_info.get('pe_ratio'),
                "industry_pe": price_info.get('ind_pe_ratio'),
                "price_to_book": price_info.get('price_to_book'),
                "dividend_yield": price_info.get('div_yeild'),
                "debt_to_equity": price_info.get('deb_equity'),
                "roe": price_info.get('roe')
            },
            "summary": dashboard_data.get('summ_text_mob', ""),
            "what_are_risk": dashboard_data.get('what_are_risk', ""),
            "technical_indicators": {
                "score": dashboard_data.get('dotsummary', {}).get('tech_score'),
                "trend": dashboard_data.get('dotsummary', {}).get('tech_txt')
            },
            "updated_at": datetime.now(pytz.UTC)
        }

        # Store in database
        db.company_dashboard.update_one(
            {
                "symbol": symbol,
                "exchange": exchange.lower(),
                "sid": sid
            },
            {"$set": structured_data},
            upsert=True
        )

        logger.info(f"Successfully fetched and stored dashboard data for {symbol}")
        return structured_data

    except requests.RequestException as e:
        logger.error(f"Network error fetching dashboard for {symbol}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error processing dashboard data for {symbol}: {str(e)}")
        return None
    
    
def get_fundamental_data(
    symbol: str,
    period: str = "q",  # q: quarterly, y: yearly, h: half-yearly, n: nine-months
    page: int = 1,
    result_type: int = 0,  # 0: consolidated, 1: standalone
    exchange: str = "nse",
    force: bool = False
) -> Optional[Dict]:
    """
    Get fundamental data from MarketsMojo
    
    Args:
        symbol (str): Stock symbol (e.g., 'RELIANCE')
        period (str): 'q' for quarterly, 'y' for yearly, 'h' for half-yearly, 'n' for nine-months
        result_type (int): 0 for consolidated, 1 for standalone
        exchange (str): Exchange name ('nse' or 'bse')
        force (bool): Force fetch from API ignoring cache
            
    Returns:
        Optional[Dict]: Fundamental data or None if error occurs
    """
    try:
        period_map = {
            "q": "quarterly",
            "y": "yearly",
            "h": "half_yearly",
            "n": "nine_months"
        }
        
        period_type = period_map.get(period.lower())
        if not period_type:
            logger.error(f"Invalid period type: {period}")
            return None
            
        result_category = "consolidated" if result_type == 0 else "standalone"

        # Check in database if force is False
        if not force and page <= 1:
            db_result = db.fundamental_data.find_one(
                {
                    "symbol": symbol,
                    "exchange": exchange.lower(),
                    f"{period_type}.updated_at": {
                        "$gte": datetime.now(pytz.UTC) - timedelta(days=7)
                    }
                }
            )

            if db_result and period_type in db_result:
                logger.info(f"Found recent {period_type} data for {symbol}")
                return db_result[period_type]

        # Get SID first
        sid = get_stock_sid(symbol, exchange)
        if not sid:
            logger.error(f"Could not get SID for {symbol}")
            return None

        # Fetch fundamental data
        url = f"{baseURL}/Stocks_Periodicresultsfull/get_results_full"
        params = {
            "period": period.lower(),
            "sid": sid,
            "exchange": 1 if exchange.lower() == "nse" else 0,
            "card": 1,
            "type": result_type,
            "page": page
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('code') != "200":
            logger.error(f"API returned error: {data.get('message')}")
            return None

        # Extract data
        highlight_fields = data['data']['highlight']
        period_dates = data['data']['period_dates'][1:]  # Skip the first element which is the title
        raw_data = data['data']['consolidate']['data']

        # Create period-wise structured data
        periods_data = {}
        
        # Process each period
        for i, period_date in enumerate(period_dates):
            period_metrics = {}
            
            # Process each highlighted field
            for field in highlight_fields:
                for row in raw_data:
                    if row[0] == field:
                        try:
                            # Remove '%' and convert to float
                            value = row[i + 1].replace('%', '').replace(',', '')
                            period_metrics[field.lower().replace(' ', '_')] = float(value)
                        except ValueError:
                            period_metrics[field.lower().replace(' ', '_')] = row[i + 1]
                        break
                        
            periods_data[period_date] = period_metrics

        result_data = {
            "type": period_type,
            "result_category": result_category,
            "periods": periods_data,
            "updated_at": datetime.now(pytz.UTC)
        }

        if page == 1:
            # Update database
            db.fundamental_data.update_one(
                {
                    "symbol": symbol,
                    "exchange": exchange.lower(),
                    "sid": sid
                },
                {
                    "$set": {
                        period_type: result_data
                    }
                },
                upsert=True
            )

        logger.info(f"Successfully fetched and stored {period_type} data for {symbol}")
        return result_data

    except requests.RequestException as e:
        logger.error(f"Network error fetching fundamental data for {symbol}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error processing fundamental data for {symbol}: {str(e)}")
        return None
    
def get_balance_sheet_data(
    symbol: str,
    exchange: str = "nse",
    page: int = 1,
    result_type: int = 0,  # 0: consolidated, 1: standalone
    force: bool = False
) -> Optional[Dict]:
    """
    Get balance sheet data from MarketsMojo
    
    Args:
        symbol (str): Stock symbol (e.g., 'RELIANCE')
        exchange (str): Exchange name ('nse' or 'bse')
        result_type (int): 0 for consolidated, 1 for standalone
        force (bool): Force fetch from API ignoring cache
            
    Returns:
        Optional[Dict]: Balance sheet data or None if error occurs
    """
    try:
        if page>1 or result_type == 1:
            dont_store = True
        else:    
            dont_store = False
        
        # Check in database if force is False
        if not force and not dont_store:
            db_result = db.fundamental_data.find_one(
                {
                    "symbol": symbol,
                    "exchange": exchange.lower(),
                    "balance_sheet.updated_at": {
                        "$gte": datetime.now(pytz.UTC) - timedelta(days=7)
                    }
                }
            )

            if db_result and "balance_sheet" in db_result:
                logger.info(f"Found recent balance sheet data for {symbol}")
                return db_result["balance_sheet"]

        # Get SID first
        sid = get_stock_sid(symbol, exchange)
        if not sid:
            logger.error(f"Could not get SID for {symbol}")
            return None

        # Fetch balance sheet data
        url = f"{baseURL}/Stocks_Balancesheetfull/get_results_full"
        params = {
            "sid": sid,
            "exchange": 1 if exchange.lower() == "nse" else 0,
            "page": page,
            "card": 1,
            "type": result_type
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('code') != "200":
            logger.error(f"API returned error: {data.get('message')}")
            return None

        # Extract data
        period_dates = data['data']['period_dates'][1:]  # Skip the first element which is the title
        raw_data = data['data']['consolidate']['data']

        # Create period-wise structured data
        periods_data = {}
        
        # Process each period
        for i, period_date in enumerate(period_dates):
            period_metrics = {}
            
            # Process each row
            for row in raw_data:
                key = row[0]
                value = row[i + 1]
                
                # Skip empty values and title rows
                if value != "" and key != "":
                    try:
                        # Remove commas and convert to float
                        clean_value = value.replace(',', '')
                        period_metrics[key.lower().replace(' ', '_')] = float(clean_value)
                    except ValueError:
                        # If conversion fails, store original value
                        period_metrics[key.lower().replace(' ', '_')] = value

            if period_metrics:  # Only add if there are metrics
                periods_data[period_date] = period_metrics

        result_data = {
            "type": "consolidated" if result_type == 0 else "standalone",
            "periods": periods_data,
            "updated_at": datetime.now(pytz.UTC)
        }

        if not dont_store:
            # Update database
            db.fundamental_data.update_one(
                {
                    "symbol": symbol,
                    "exchange": exchange.lower(),
                    "sid": sid
                },
                {
                    "$set": {
                        "balance_sheet": result_data
                    }
                },
                upsert=True
            )

        logger.info(f"Successfully fetched and stored balance sheet data for {symbol}")
        return result_data

    except requests.RequestException as e:
        logger.error(f"Network error fetching balance sheet data for {symbol}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error processing balance sheet data for {symbol}: {str(e)}")
        return None
    
def get_profit_loss_data(
    symbol: str,
    page: int = 1,
    exchange: str = "nse",
    result_type: int = 0,  # 0: consolidated, 1: standalone
    force: bool = False
) -> Optional[Dict]:
    """
    Get profit & loss data from MarketsMojo
    
    Args:
        symbol (str): Stock symbol (e.g., 'RELIANCE')
        exchange (str): Exchange name ('nse' or 'bse')
        result_type (int): 0 for consolidated, 1 for standalone
        force (bool): Force fetch from API ignoring cache
            
    Returns:
        Optional[Dict]: Profit & loss data or None if error occurs
    """
    try:
        if page>1 or result_type == 1:
            dont_store = True
        else:
            dont_store = False
        
        
        # Check in database if force is False
        if not force and not dont_store:
            db_result = db.fundamental_data.find_one(
                {
                    "symbol": symbol,
                    "exchange": exchange.lower(),
                    "profit_loss.updated_at": {
                        "$gte": datetime.now(pytz.UTC) - timedelta(days=7)
                    }
                }
            )

            if db_result and "profit_loss" in db_result:
                logger.info(f"Found recent profit & loss data for {symbol}")
                return db_result["profit_loss"]

        # Get SID first
        sid = get_stock_sid(symbol, exchange)
        if not sid:
            logger.error(f"Could not get SID for {symbol}")
            return None

        # Fetch profit & loss data
        url = f"{baseURL}/Stocks_Profitlossfull/get_results_full"
        params = {
            "sid": sid,
            "exchange": 1 if exchange.lower() == "nse" else 0,
            "page": page,
            "card": 1,
            "type": result_type
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('code') != "200":
            logger.error(f"API returned error: {data.get('message')}")
            return None

        # Extract data
        period_dates = data['data']['period_dates'][1:]  # Skip the first element which is the title
        raw_data = data['data']['consolidate']['data']

        # Create period-wise structured data
        periods_data = {}
        
        # Process each period
        for i, period_date in enumerate(period_dates):
            period_metrics = {}
            
            # Process each row
            for row in raw_data:
                key = row[0]
                value = row[i + 1]
                
                # Skip empty values and title/header rows
                if value != "" and key != "":
                    try:
                        # Handle percentage values
                        if "%" in value:
                            clean_value = value.replace('%', '').replace(',', '')
                            period_metrics[key.lower().replace(' ', '_')] = float(clean_value)
                        else:
                            # Remove commas and convert to float
                            clean_value = value.replace(',', '')
                            period_metrics[key.lower().replace(' ', '_')] = float(clean_value)
                    except ValueError:
                        # If conversion fails, store original value
                        period_metrics[key.lower().replace(' ', '_')] = value

            if period_metrics:  # Only add if there are metrics
                periods_data[period_date] = period_metrics

        result_data = {
            "type": "consolidated" if result_type == 0 else "standalone",
            "periods": periods_data,
            "updated_at": datetime.now(pytz.UTC)
        }

        if not dont_store:
            # Update database
            db.fundamental_data.update_one(
                {
                    "symbol": symbol,
                    "exchange": exchange.lower(),
                    "sid": sid
                },
                {
                    "$set": {
                        "profit_loss": result_data
                    }
                },
                upsert=True
            )

        logger.info(f"Successfully fetched and stored profit & loss data for {symbol}")
        return result_data

    except requests.RequestException as e:
        logger.error(f"Network error fetching profit & loss data for {symbol}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error processing profit & loss data for {symbol}: {str(e)}")
        return None
    
def get_cash_flow_data(
    symbol: str,
    page: int = 1,
    exchange: str = "nse",
    result_type: int = 0,  # 0: consolidated, 1: standalone
    force: bool = False
) -> Optional[Dict]:
    """
    Get cash flow data from MarketsMojo
    
    Args:
        symbol (str): Stock symbol (e.g., 'RELIANCE')
        exchange (str): Exchange name ('nse' or 'bse')
        result_type (int): 0 for consolidated, 1 for standalone
        force (bool): Force fetch from API ignoring cache
            
    Returns:
        Optional[Dict]: Cash flow data or None if error occurs
    """
    try:
        if page>1 or result_type == 1:
            dont_store = True
        else:
            dont_store = False
            
        # Check in database if force is False
        if not force and not dont_store:
            db_result = db.fundamental_data.find_one(
                {
                    "symbol": symbol,
                    "exchange": exchange.lower(),
                    "cash_flow.updated_at": {
                        "$gte": datetime.now(pytz.UTC) - timedelta(days=7)
                    }
                }
            )

            if db_result and "cash_flow" in db_result:
                logger.info(f"Found recent cash flow data for {symbol}")
                return db_result["cash_flow"]

        # Get SID first
        sid = get_stock_sid(symbol, exchange)
        if not sid:
            logger.error(f"Could not get SID for {symbol}")
            return None

        # Fetch cash flow data
        url = f"{baseURL}/Stocks_Cashflowfull/get_results_full"
        params = {
            "sid": sid,
            "exchange": 1 if exchange.lower() == "nse" else 0,
            "page": page,
            "card": 1,
            "type": result_type
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('code') != "200":
            logger.error(f"API returned error: {data.get('message')}")
            return None

        # Extract data
        period_dates = data['data']['period_dates'][1:]  # Skip the first element which is the title
        raw_data = data['data']['consolidate']['data']

        # Create period-wise structured data
        periods_data = {}
        
        # Process each period
        for i, period_date in enumerate(period_dates):
            # Skip empty period dates
            if not period_date:
                continue
                
            period_metrics = {}
            
            # Process each row
            for row in raw_data:
                key = row[0]
                # Check if we have data for this period
                if len(row) > i + 1:
                    value = row[i + 1]
                    
                    # Skip empty values and title rows
                    if value != "" and key != "":
                        try:
                            # Remove commas and convert to float
                            clean_value = value.replace(',', '')
                            period_metrics[key.lower().replace(' ', '_')] = float(clean_value)
                        except ValueError:
                            # If conversion fails, store original value
                            period_metrics[key.lower().replace(' ', '_')] = value

            if period_metrics:  # Only add if there are metrics
                periods_data[period_date] = period_metrics

        result_data = {
            "type": "consolidated" if result_type == 0 else "standalone",
            "periods": periods_data,
            "updated_at": datetime.now(pytz.UTC)
        }

        if not dont_store:
            # Update database
            db.fundamental_data.update_one(
                {
                    "symbol": symbol,
                    "exchange": exchange.lower(),
                    "sid": sid
                },
                {
                    "$set": {
                        "cash_flow": result_data
                    }
                },
                upsert=True
            )

        logger.info(f"Successfully fetched and stored cash flow data for {symbol}")
        return result_data

    except requests.RequestException as e:
        logger.error(f"Network error fetching cash flow data for {symbol}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error processing cash flow data for {symbol}: {str(e)}")
        return None
    
def get_shareholding_pattern(
    symbol: str,
    exchange: str = "nse",
    force: bool = False
) -> Optional[Dict]:
    """
    Get shareholding pattern data from MarketsMojo
    
    Args:
        symbol (str): Stock symbol (e.g., 'RELIANCE')
        exchange (str): Exchange name ('nse' or 'bse')
        force (bool): Force fetch from API ignoring cache
            
    Returns:
        Optional[Dict]: Shareholding pattern data or None if error occurs
    """
    try:
        # Check in database if force is False
        if not force:
            db_result = db.fundamental_data.find_one(
                {
                    "symbol": symbol,
                    "exchange": exchange.lower(),
                    "shareholding_pattern.updated_at": {
                        "$gte": datetime.now(pytz.UTC) - timedelta(days=7)
                    }
                }
            )

            if db_result and "shareholding_pattern" in db_result:
                logger.info(f"Found recent shareholding pattern data for {symbol}")
                return db_result["shareholding_pattern"]

        # Get SID first
        sid = get_stock_sid(symbol, exchange)
        if not sid:
            logger.error(f"Could not get SID for {symbol}")
            return None

        # Fetch shareholding pattern data
        url = f"{baseURL}/Stocks_Shareholdingfull/get_results"
        params = {
            "sid": sid,
            "exchange": 1 if exchange.lower() == "nse" else 0
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('code') != "200":
            logger.error(f"API returned error: {data.get('message')}")
            return None

        # Get periods from first row
        all_periods = data['data']['all_periods']
        if not all_periods:
            return None
            
        period_keys = ['qurter1', 'qurter2', 'qurter3', 'qurter4', 'qurter5', 'qurter6']
        period_dates = {k: all_periods[0][k] for k in period_keys if all_periods[0][k]}

        # Create period-wise structured data
        periods_data = {date: {} for date in period_dates.values()}
        
        # Process each row
        for row in all_periods[1:]:  # Skip the header row
            category = row['text']
            
            # Skip main headers and empty rows
            if row.get('main_flag') == 1 or not any(row.get(qk) for qk in period_keys):
                continue
                
            # Process each period's value
            for period_key, period_date in period_dates.items():
                value = row.get(period_key, '')
                if value:
                    try:
                        # Convert to float if possible
                        periods_data[period_date][category] = float(value)
                    except ValueError:
                        # Keep as string if not convertible
                        periods_data[period_date][category] = value

        result_data = {
            "periods": periods_data,
            "updated_at": datetime.now(pytz.UTC)
        }

        # Update database
        db.fundamental_data.update_one(
            {
                "symbol": symbol,
                "exchange": exchange.lower()
            },
            {
                "$set": {
                    "shareholding_pattern": result_data
                }
            },
            upsert=True
        )

        logger.info(f"Successfully fetched and stored shareholding pattern data for {symbol}")
        return result_data

    except requests.RequestException as e:
        logger.error(f"Network error fetching shareholding pattern data for {symbol}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error processing shareholding pattern data for {symbol}: {str(e)}")
        return None
    
def get_stock_quality_ratios(
    symbol: str,
    exchange: str = "nse",
    force: bool = False
) -> Optional[Dict]:
    """
    Get stock quality and valuation ratios from MarketsMojo
    
    Args:
        symbol (str): Stock symbol (e.g., 'RELIANCE')
        exchange (str): Exchange name ('nse' or 'bse')
        force (bool): Force fetch from API ignoring cache
            
    Returns:
        Optional[Dict]: Stock quality data or None if error occurs
    """
    try:
        # Check in database if force is False
        if not force:
            db_result = db.fundamental_data.find_one(
                {
                    "symbol": symbol,
                    "exchange": exchange.lower(),
                    "stock_quality.updated_at": {
                        "$gte": datetime.now(pytz.UTC) - timedelta(days=1)
                    }
                }
            )

            if db_result and "stock_quality" in db_result:
                logger.info(f"Found recent stock quality data for {symbol}")
                return db_result["stock_quality"]

        # Get SID first
        sid = get_stock_sid(symbol, exchange, force=True)
        if not sid:
            logger.error(f"Could not get SID for {symbol}")
            return None

        # Fetch quality data
        quality_url = f"{baseURL}/stocks_quality/cardinfo"
        valuation_url = f"{baseURL}/stocks_quality/vcardinfo"
        
        params = {"sid": sid}
        
        # Fetch both endpoints
        quality_response = requests.get(quality_url, params=params, timeout=10)
        valuation_response = requests.get(valuation_url, params=params, timeout=10)
        
        quality_response.raise_for_status()
        valuation_response.raise_for_status()
        
        quality_data = quality_response.json()
        valuation_data = valuation_response.json()
        
        if quality_data.get('code') != 200 or valuation_data.get('code') != 200:
            logger.error(f"API returned error for {symbol}")
            return None

        # Structure the data
        structured_data = {
            "quality_metrics": {
                "rating": quality_data['data']['quality']['q_txt'],
                "direction": quality_data['data']['quality']['q_dir'],
                "messages": quality_data['data']['quality']['q_msg'],
                "factors": {
                    "management_risk": {
                        "grade": quality_data['data']['quality']['q_factor']['managementrisk']['grade'],
                        "direction": quality_data['data']['quality']['q_factor']['managementrisk']['dir']
                    },
                    "growth": {
                        "grade": quality_data['data']['quality']['q_factor']['growth']['grade'],
                        "direction": quality_data['data']['quality']['q_factor']['growth']['dir']
                    },
                    "capital_structure": {
                        "grade": quality_data['data']['quality']['q_factor']['capitalstructure']['grade'],
                        "direction": quality_data['data']['quality']['q_factor']['capitalstructure']['dir']
                    }
                }
            },
            "quality_ratios": {},
            "valuation_metrics": {
                "rating": valuation_data['data']['valuation']['v_txt'],
                "direction": valuation_data['data']['valuation']['v_dir'],
                "messages": valuation_data['data']['valuation']['v_msg']
            },
            "valuation_ratios": {},
            "updated_at": datetime.now(pytz.UTC)
        }

        # Process quality ratios
        for ratio in quality_data['data']['quality_tbl']['list']:
            key = ratio['name'].lower().replace(' ', '_').replace('(', '').replace(')', '')
            value = ratio['value']
            try:
                # Convert percentage values
                if '%' in value:
                    value = float(value.replace('%', ''))
                else:
                    value = float(value)
            except ValueError:
                pass
            structured_data['quality_ratios'][key] = value

        # Process valuation ratios
        for ratio in valuation_data['data']['valuation_tbl']['list']:
            key = ratio['name'].lower().replace(' ', '_').replace('(', '').replace(')', '')
            value = ratio['value']
            try:
                # Convert percentage values
                if '%' in value:
                    value = float(value.replace('%', ''))
                else:
                    value = float(value)
            except ValueError:
                pass
            structured_data['valuation_ratios'][key] = value

        # Update database
        db.fundamental_data.update_one(
            {
                "symbol": symbol,
                "exchange": exchange.lower()
            },
            {
                "$set": {
                    "stock_quality": structured_data
                }
            },
            upsert=True
        )

        logger.info(f"Successfully fetched and stored stock quality data for {symbol}")
        return structured_data

    except requests.RequestException as e:
        logger.error(f"Network error fetching stock quality data for {symbol}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error processing stock quality data for {symbol}: {str(e)}")
        return None
    
def get_company_peers(
    symbol: str,
    exchange: str = "nse",
    force: bool = False
) -> Optional[List[Dict]]:
    """
    Get company peers from MarketsMojo
    
    Args:
        symbol (str): Stock symbol (e.g., 'RELIANCE')
        exchange (str): Exchange name ('nse' or 'bse')
        force (bool): Force fetch from API ignoring cache
            
    Returns:
        Optional[List[Dict]]: List of peer companies or None if error occurs
    """
    try:
        # Check in database if force is False
        if not force:
            db_result = db.company_dashboard.find_one(
                {
                    "symbol": symbol,
                    "exchange": exchange.lower(),
                    "peers": {"$exists": True},
                    "peers_updated_at": {
                        "$gte": datetime.now(pytz.UTC) - timedelta(days=7)
                    }
                }
            )

            if db_result and "peers" in db_result:
                logger.info(f"Found recent peers data for {symbol}")
                return db_result["peers"]

        # Get SID first
        sid = get_stock_sid(symbol, exchange)
        if not sid:
            logger.error(f"Could not get SID for {symbol}")
            return None

        # Fetch peers data
        url = f"{baseURL}/stocks/getPeersDetails"
        payload = {
            "stock_id": int(sid),
            "popup": 1
        }
        
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('code') != '200':
            logger.error(f"API returned error for {symbol}")
            print(data)
            return None

        # Structure peers data
        peers_data = []
        for peer in data.get('data', {}).get('peer', {}).get('list', []):
            peer_info = {
                "sid": peer.get('details', {}).get('sid'),
                "sname": peer.get('details', {}).get('sname'),
                "industry_name": peer.get('details', {}).get('ind_name'),
            }
            peers_data.append(peer_info)

        # Update database
        db.company_dashboard.update_one(
            {
                "symbol": symbol,
                "exchange": exchange.lower(),
                "sid": sid
            },
            {
                "$set": {
                    "peers": peers_data,
                    "peers_updated_at": datetime.now(pytz.UTC)
                }
            },
            upsert=True
        )

        logger.info(f"Successfully fetched and stored peers data for {symbol}")
        return peers_data

    except requests.RequestException as e:
        logger.error(f"Network error fetching peers data for {symbol}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error processing peers data for {symbol}: {str(e)}")
        return None
    
def get_price_movement(
    symbol: str,
    exchange: str = "nse",
    force: bool = False
) -> Optional[Dict]:
    """
    Get price movement data from MarketsMojo
    
    Args:
        symbol (str): Stock symbol (e.g., 'RELIANCE')
        exchange (str): Exchange name ('nse' or 'bse')
        force (bool): Force fetch from API ignoring cache
            
    Returns:
        Optional[Dict]: Price movement data or None if error occurs
    """
    try:
        # Check in database if force is False
        if not force:
            db_result = db.company_dashboard.find_one(
                {
                    "symbol": symbol,
                    "exchange": exchange.lower(),
                    "price_movement": {"$exists": True},
                    "price_movement.updated_at": {
                        "$gte": datetime.now(pytz.UTC) - timedelta(hours=1)  # Cache for 1 hour only
                    }
                }
            )

            if db_result and "price_movement" in db_result:
                logger.info(f"Found recent price movement data for {symbol}")
                return db_result["price_movement"]

        # Get SID first
        sid = get_stock_sid(symbol, exchange)
        if not sid:
            logger.error(f"Could not get SID for {symbol}")
            return None

        # Fetch price movement data
        url = f"{baseURL}/stocks_Pricemovement/pricemovement_info"
        params = {
            "sid": sid,
            "exchange": 1 if exchange.lower() == "nse" else 0,
            "1d": ""
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('code') != "200":
            logger.error(f"API returned error: {data.get('message')}")
            return None

        price_data = data.get('data', {}).get('pricemovement', {})
        other_data = data.get('data', {}).get('pricemovement', {}).get('other_data', {})
        
        # Structure the data
        structured_data = {
            "message": other_data.get('sentence', {}).get('message'),
            "message_direction": other_data.get('sentence', {}).get('dir'),
            "current_price": price_data.get('intraday', {}).get('price'),
            "trading_info": {
                "52_week": {
                    "high": price_data.get('intraday', {}).get('52wk_high'),
                    "low": price_data.get('intraday', {}).get('52wk_low'),
                    "pointer": price_data.get('intraday', {}).get('52wk_pointer')
                },
                "day_range": {
                    "high": price_data.get('intraday', {}).get('high'),
                    "low": price_data.get('intraday', {}).get('low'),
                    "previous_close": price_data.get('intraday', {}).get('previous_close')
                }
            },
            "stock_details": {},
            "returns": {},
            "updated_at": datetime.now(pytz.UTC)
        }

        # Process stock details
        for detail in other_data.get('stock_details', []):
            key = detail['field'].lower().replace(' ', '_')
            value_data = {
                "value": detail['value']
            }
            if 'dir' in detail:
                value_data["direction"] = detail['dir']
            if 'field_suffix' in detail:
                value_data["suffix"] = detail['field_suffix']
                
            structured_data["stock_details"][key] = value_data

        # Process returns data
        for return_data in other_data.get('return_data', []):
            period = return_data['field']
            structured_data["returns"][period] = {
                "stock": {
                    "change": return_data['stock_return']['chg'],
                    "change_percentage": return_data['stock_return']['chgp'],
                    "direction": return_data['stock_return']['dir']
                },
                "sensex": {
                    "change": return_data['sensex_return']['chg'],
                    "change_percentage": return_data['sensex_return']['chgp'],
                    "direction": return_data['sensex_return']['dir']
                }
            }

        # Update database
        db.company_dashboard.update_one(
            {
                "symbol": symbol,
                "exchange": exchange.lower(),
                "sid": sid
            },
            {
                "$set": {
                    "price_movement": structured_data
                }
            },
            upsert=True
        )

        logger.info(f"Successfully fetched and stored price movement data for {symbol}")
        return structured_data

    except requests.RequestException as e:
        logger.error(f"Network error fetching price movement data for {symbol}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error processing price movement data for {symbol}: {str(e)}")
        return None
    
def test_company_data(symbol: str, sector: str):
    """Helper function to test all data fetching functions for a company"""
    print(f"\n{'='*80}")
    print(f"Testing data for {symbol} ({sector})")
    print(f"{'='*80}")

    print("\n1. Corporate Announcements:")
    announcements = get_corporate_announcements(symbol)
    if announcements:
        print(f"Found {len(announcements.get('board_meetings', []))} board meetings")
        print(f"Found {len(announcements.get('dividends', []))} dividend announcements")

    print("\n2. Stock News:")
    news = get_stock_news(symbol)
    if news:
        print(f"Found {len(news)} news items")

    print("\n3. Company Dashboard:")
    dashboard = get_company_dashboard(symbol)
    if dashboard:
        print(f"Company Name: {dashboard['company_info']['name']}")
        print(f"Industry: {dashboard['company_info']['industry']}")
        print(f"Market Cap: ₹{dashboard['key_metrics']['market_cap']:,.2f} Cr")

    print("\n4. Fundamental Data:")
    fundamental = get_fundamental_data(symbol, period="q")
    if fundamental:
        print(f"Found quarterly data for {len(fundamental['periods'])} periods")

    print("\n5. Balance Sheet:")
    balance_sheet = get_balance_sheet_data(symbol)
    if balance_sheet:
        print(f"Found balance sheet data for {len(balance_sheet['periods'])} periods")

    print("\n6. Profit & Loss:")
    pnl = get_profit_loss_data(symbol)
    if pnl:
        print(f"Found P&L data for {len(pnl['periods'])} periods")

    print("\n7. Cash Flow:")
    cash_flow = get_cash_flow_data(symbol)
    if cash_flow:
        print(f"Found cash flow data for {len(cash_flow['periods'])} periods")

    print("\n8. Shareholding Pattern:")
    shareholding = get_shareholding_pattern(symbol)
    if shareholding:
        print(f"Found shareholding data for {len(shareholding['periods'])} periods")

    print("\n9. Stock Quality Ratios:")
    quality = get_stock_quality_ratios(symbol)
    if quality:
        print(f"Quality Rating: {quality['quality_metrics']['rating']}")
        print(f"Valuation Rating: {quality['valuation_metrics']['rating']}")

    print("\n10. Company Peers:")
    peers = get_company_peers(symbol)
    if peers:
        print(f"Found {len(peers)} peer companies")

    print("\n11. Price Movement:")
    price = get_price_movement(symbol)
    if price:
        print(f"Current Price: ₹{price['current_price']}")
        print(f"52W High: ₹{price['trading_info']['52_week']['high']}")
        print(f"52W Low: ₹{price['trading_info']['52_week']['low']}")

if __name__ == "__main__":
    # Test companies from different sectors
    
    # IT Sector
    test_company_data("TCS", "Information Technology")
    
    # Banking Sector
    test_company_data("HDFCBANK", "Banking")
    
    # Automotive Sector
    test_company_data("TATAMOTORS", "Automotive")
    
    # FMCG Sector
    test_company_data("HINDUNILVR", "FMCG")
    
    # Pharmaceutical Sector
    test_company_data("SUNPHARMA", "Pharmaceuticals")
 
    pass