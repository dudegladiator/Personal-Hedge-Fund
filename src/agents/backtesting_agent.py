import pymongo
import os
import ast
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

# MongoDB Setup
MONGO_URI = "mongodb+srv://begoodop422:unsxxP73YNApLT7Z@cluster0.snkv0qw.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
DATABASE_NAME = "hedge_fund_manager"
client = pymongo.MongoClient(MONGO_URI)
db = client[DATABASE_NAME]
company_dashboard_collection = db["company_dashboard"]
company_announcements_collection = db["company_announcements_news"]
fundamental_data_collection = db["fundamental_data"]
groww_stock_details_collection = db["groww_stock_details"]

# Fetch Data
def fetch_data_from_mongodb(symbol="RELIANCE"):
    return {
        "company_dashboard": company_dashboard_collection.find_one({"symbol": symbol}),
        "company_announcements": company_announcements_collection.find_one({"symbol": symbol}),
        "fundamental_data": fundamental_data_collection.find_one({"symbol": symbol}),
        "groww_stock_details": groww_stock_details_collection.find_one({"symbol": symbol.lower()})
    }

# Format Data
def format_data_for_llm(data):
    dashboard = data["company_dashboard"]
    announcements = data["company_announcements"]
    fundamentals = data["fundamental_data"]
    groww_details = data["groww_stock_details"]

    # Helper function to handle missing data gracefully
    def safe_get(data_dict, keys, default="N/A"):
        """Safely retrieves nested values from a dictionary, returning a default if not found."""
        try:
            for key in keys:
                data_dict = data_dict[key]
            return data_dict
        except (KeyError, TypeError):
            return default

    # Build the prompt string.  Use triple quotes for multiline strings.
    prompt = f"""
### Company Dashboard
- **Symbol**: {safe_get(dashboard, ['symbol'])}
- **Exchange**: {safe_get(dashboard, ['exchange'])}
- **Market Cap**: {safe_get(dashboard, ['key_metrics', 'market_cap'], default='N/A')} Cr
- **PE Ratio**: {safe_get(dashboard, ['key_metrics', 'pe_ratio'], default='N/A')}
- **Industry PE**: {safe_get(dashboard, ['key_metrics', 'industry_pe'], default='N/A')}
- **Price to Book**: {safe_get(dashboard, ['key_metrics', 'price_to_book'], default='N/A')}
- **Dividend Yield**: {safe_get(dashboard, ['key_metrics', 'dividend_yield'], default='N/A')}%
- **Debt to Equity**: {safe_get(dashboard, ['key_metrics', 'debt_to_equity'], default='N/A')}
- **ROE**: {safe_get(dashboard, ['key_metrics', 'roe'], default='N/A')}%
- **Peers**: {', '.join([peer.get('sname', 'N/A') for peer in safe_get(dashboard, ['peers'], default=[])])}
- **Summary**: {safe_get(dashboard, ['summary'], default='N/A')}

### Announcements & News
- **Recent Board Meeting**: {safe_get(announcements, ['announcements', 'board_meetings', 0, 'date'], default='N/A')} - {safe_get(announcements, ['announcements', 'board_meetings', 0, 'agenda'], default='N/A')}
- **Latest News**: {safe_get(announcements, ['news', 0, 'title'], default='N/A')} ({safe_get(announcements, ['news', 0, 'published_date'], default='N/A')})
  - Description: {safe_get(announcements, ['news', 0, 'description'], default='N/A')}

### Fundamental Data (Latest Year - Mar'24)
- **Net Sales**: {safe_get(fundamentals, ['yearly', 'periods', "Mar'24", 'net_sales'], default='N/A')} Cr
- **Profit After Tax**: {safe_get(fundamentals, ['yearly', 'periods', "Mar'24", 'profit_after_tax'], default='N/A')} Cr
- **EPS**: {safe_get(fundamentals, ['yearly', 'periods', "Mar'24", 'earnings_per_share_(eps)'], default='N/A')} Rs
- **Operating Profit Margin**: {safe_get(fundamentals, ['yearly', 'periods', "Mar'24", 'operating_profit_margin_(excl_oi)'], default='N/A')}%
- **PAT Margin**: {safe_get(fundamentals, ['yearly', 'periods', "Mar'24", 'pat_margin'], default='N/A')}%

### Groww Stock Details
- **Full Name**: {safe_get(groww_details, ['overview', 'details', 'fullName'], default='N/A')}
- **Industry**: {safe_get(groww_details, ['overview', 'header', 'industryName'], default='N/A')}
- **Market Cap**: {safe_get(groww_details, ['overview', 'stats', 'marketCap'], default='N/A')} Cr
- **PE Ratio (TTM)**: {safe_get(groww_details, ['overview', 'stats', 'peRatio'], default='N/A')}
- **Dividend Yield**: {safe_get(groww_details, ['overview', 'stats', 'dividendYieldInPercent'], default='N/A')}%
- **Business Summary**: {safe_get(groww_details, ['overview', 'details', 'businessSummary'], default='N/A')}
"""
    return prompt

def generate_strategy_code(symbol: str) -> str:
    """
    Generate Python code for a trading strategy using the Groq LLM based on a stock's fundamental data.

    Args:
        symbol (str): Stock ticker symbol (e.g., "RELIANCE" for Reliance Industries on NSE).

    Returns:
        str: Python code as a string defining the `generate_signals` function.

    Raises:
        Exception: If fundamental data retrieval or API call fails.
        ValueError: If the GROQ_API_KEY environment variable is not set or if the generated code has syntax errors.
    """
    # Fetch fundamental data using yfinance
    try:
        data = fetch_data_from_mongodb(symbol)
        cleaned_data = format_data_for_llm(data)
    except Exception as e:
        raise Exception(f"Failed to retrieve fundamental data for {symbol}: {str(e)}")

    # Construct the prompt for the Groq LLM
    prompt = f"""
    Generate a Python function named `generate_signals` that takes a pandas DataFrame with stock price data 
    (columns: 'Open', 'High', 'Low', 'Close', 'Volume') and returns a DataFrame with a 'Signal' column 
    where 1 is buy, -1 is sell, and 0 is hold.

    The stock has the following characteristics:
    {{cleaned_data}}

    Use technical indicators from the TA-Lib library (e.g., SMA, RSI, MACD, Bollinger Bands) to generate 
    the signals. The strategy should be suitable for this stock based on its fundamental characteristics. 
    Ensure the code:
    - Imports only pandas, numpy, and talib.
    - Handles the input DataFrame correctly, accounting for potential multi-dimensional data.
    - Produces signals based on a logical combination of indicators.
    - Does not use any other external libraries or functions.

    Output only the Python code, wrapped in triple backticks (```python ... ```).
    """

    # Set up the Groq API client
    api_key = "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"

    groq_client = Groq(api_key=api_key)

    # Send the prompt to the Groq API
    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that generates Python code for trading strategies."
                },
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model="llama-3.3-70b-versatile",  # Or another suitable Groq model
            temperature=0.0,
            max_completion_tokens=7000,  # Adjust as needed
            top_p=1,
            stream=False,
        )

        generated_text = chat_completion.choices[0].message.content
    except Exception as e:
        raise Exception(f"Groq API call failed: {str(e)}")

    # Parse the response to extract the Python code
    if '```python' in generated_text and '```' in generated_text:
        start = generated_text.find('```python') + 9
        end = generated_text.find('```', start)
        generated_code = generated_text[start:end].strip()
    else:
        generated_code = generated_text.strip()

    # Validate the generated code
    try:
        ast.parse(generated_code)
    except SyntaxError as e:
        raise ValueError(f"Generated code has syntax errors: {str(e)}")
    
    # Return the generated code
    return generated_code

# Main Execution
if __name__ == "__main__":
    symbol = "RELIANCE"
    generated_code = generate_strategy_code(symbol)
    print(generated_code)