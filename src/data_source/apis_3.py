import requests
from typing import List, Optional, Dict

from requests_ratelimiter import Tuple
from utils.app_logger import setup_logger
from utils.config import settings, get_sync_database

logger = setup_logger("src/data_source/ticker_tape_apis.py")
db = get_sync_database()

def _fetch_tickertape_data(
    universe: str,
    mover_type: str, # 'gainers' or 'losers'
    count: int
) -> Optional[List[Dict]]:
    """Helper function to fetch data for either gainers or losers."""
    params = {
        "universe": universe,
        "type": mover_type,
        "count": count,
        "offset": 0
    }
    try:
        logger.info(f"Fetching {mover_type} for {universe} from Tickertape API...")
        response = requests.get(
            "https://analyze.api.tickertape.in/homepage/stocks",
            params=params
      )
        response.raise_for_status()
        data = response.json()

        if data.get("success"):
            raw_list = data.get("data", {}).get(mover_type, [])
            if not raw_list:
                 logger.info(f"No {mover_type} data found for {universe} in the response.")
                 return []

            formatted_list = []
            for item in raw_list:
                try:
                    formatted_item = {
                        "Ticker": item.get("ticker"),
                        "Name": item.get("name"),
                        "Cap": item.get("marketCap", "N/A"),
                        "Price": float(item.get("price", 0.0)),
                        "Change": float(item.get("change", 0.0))
                    }
                    if formatted_item["Ticker"]:
                        formatted_list.append(formatted_item)
                    else:
                        continue

                except (ValueError, TypeError, KeyError) as e:
                    continue

            logger.info(f"Successfully processed {len(formatted_list)} {mover_type} for {universe}.")
            return formatted_list
        else:
            logger.error(f"Tickertape API indicated failure for {mover_type} ({universe}). Response: {data}")
            return None

    except requests.exceptions.Timeout:
        logger.error(f"Timeout error fetching Tickertape {mover_type} for {universe}.")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error fetching Tickertape {mover_type} for {universe}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error processing Tickertape {mover_type} for {universe}: {e}", exc_info=True)
        return None
    
def get_tickertape_movers(
    universe: str = "LargeCap",
    count: int = 5
) -> Tuple[Optional[List[Dict]], Optional[List[Dict]]]:
    valid_universes = ["LargeCap", "MidCap", "SmallCap"]
    if universe not in valid_universes:
        logger.error(f"Invalid universe specified: {universe}. Use one of {valid_universes}")
        # Return None for both lists to indicate invalid input
        return None, None

    gainers = _fetch_tickertape_data(universe, "gainers", count)
    losers = _fetch_tickertape_data(universe, "losers", count)

    return gainers, losers

def search_tickertape_stocks(
    query: str,
    limit: int = 10 # Limit the number of results
) -> Optional[Dict[str, Dict]]:
    if not query:
        logger.warning("Search query cannot be empty.")
        return []
    
    params = {
        "text": query,
        "types": "stock", # Only search for stocks
        "pageNumber": 0
    }

    try:
        logger.info(f"Searching Tickertape for stocks matching '{query}'...")
        response = requests.get(
            "https://api.tickertape.in/search",
            params=params,
            headers={
                'accept-version': '8.14.0',
            }
        )
        response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)
        data = response.json()

        if data.get("success"):
            items = data.get("data", {}).get("items", [])
            if not items:
                 logger.info(f"No stock results found for '{query}'.")
                 return [] # Return empty list if API returns no items

            results_list = []
            count = 0
            for item in items:
                # Filter for type 'stock' and exchange 'NSE'
                if item.get('type') == 'stock' and item.get('exchanges') == 'NSE':
                    if count >= limit: # Apply limit
                        break

                    ticker = item.get('ticker')
                    # Use 'name' field, fallback to 'name_suggest' if needed
                    name = item.get('name', item.get('name_suggest', 'N/A'))
                    quote_data = item.get('quote', {})
                    price_str = quote_data.get('price')
                    change_abs_str = quote_data.get('change')
                    close_price_str = quote_data.get('close')

                    # Validate required data exists
                    if not all([ticker, price_str is not None, change_abs_str is not None, close_price_str is not None]):
                        logger.warning(f"Skipping item due to missing quote data: {item.get('ticker', 'N/A')}")
                        continue

                    try:
                        price = float(price_str)
                        change_abs = float(change_abs_str)
                        close_price = float(close_price_str)

                        # Calculate percentage change
                        if close_price != 0:
                            change_pct = (change_abs / close_price) * 100.0
                        else:
                            change_pct = 0.0 # Avoid division by zero

                        # Append to results list
                        results_list.append({
                            "Ticker": ticker,
                            "Name": name,
                            "Price": price,
                            "Change %": change_pct
                            # We don't have 'Cap' info from this endpoint
                        })
                        count += 1

                    except (ValueError, TypeError) as e:
                        logger.warning(f"Could not parse numeric data for item {ticker}: {e}. Item: {item}")
                        continue # Skip items with parsing errors

            logger.info(f"Successfully processed {len(results_list)} NSE stock results for '{query}'.")
            return results_list # Return the list
        else:
            logger.error(f"Tickertape Search API indicated failure for query '{query}'. Response: {data}")
            return None # Return None for API failure

    except requests.exceptions.Timeout:
        logger.error(f"Timeout error during Tickertape search for '{query}'.")
        return None # Return None for timeout
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error during Tickertape search for '{query}': {e}")
        return None # Return None for network error
    except Exception as e:
        logger.error(f"Unexpected error during Tickertape search for '{query}': {e}", exc_info=True)
        return None # Return None for other errors
    
if __name__ == "__main__":

    # search_results = search_tickertape_stocks("adani", 5)
    # if search_results:
    #     print("Search Results for 'RELIANCE':", search_results)
    
    
    pass