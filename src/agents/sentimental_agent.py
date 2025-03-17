import pymongo
import json
import os
from datetime import datetime
from groq import Groq
import re
import json
   
# MongoDB connection setup
mongo_uri = "mongodb+srv://begoodop422:unsxxP73YNApLT7Z@cluster0.snkv0qw.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
client = pymongo.MongoClient(mongo_uri)
db = client["hedge_fund_manager"]
collection = db["corporate_announcements_news"]

# Initialize the Groq client
GROQ_API_KEY = "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"
groq_client = Groq(api_key=GROQ_API_KEY)

# Helper function to get the latest announcement entries
from datetime import datetime, timedelta

def get_latest_announcements(entries, date_field, days=90, date_format="%d-%m-%Y"):
    """
    Retrieves all announcement entries from the last specified number of days, sorted by date (newest first).

    Args:
        entries (list): List of announcement dictionaries.
        date_field (str): Key of the date field to filter/sort by (e.g., "date", "ex_date").
        days (int): Number of days to look back (default: 5).
        date_format (str): Format of the date string (default: "%d-%m-%Y" for "dd-mm-yyyy").

    Returns:
        list: Announcements from the last 'days' days, sorted by date_field in descending order.
    """
    valid_entries = [entry for entry in entries if date_field in entry]
    if not valid_entries:
        return []
    
    # Calculate the cutoff date (today - days)
    cutoff_date = datetime.now() - timedelta(days=days)
    
    try:
        # Filter entries within the last 'days' days
        recent_entries = [
            entry for entry in valid_entries
            if datetime.strptime(entry[date_field], date_format) >= cutoff_date
        ]
        
        # Sort by date_field in descending order
        sorted_entries = sorted(
            recent_entries,
            key=lambda x: datetime.strptime(x[date_field], date_format),
            reverse=True
        )
        return sorted_entries
    
    except ValueError as e:
        print(f"Date parsing error: {e}")
        return []

# Helper function to get the latest news entries
from datetime import datetime, timedelta

def get_latest_news(news_list, days=5):
    """
    Retrieves all news items from the last specified number of days, sorted by date (newest first).

    Args:
        news_list (list): List of news dictionaries with 'published_date' field.
        days (int): Number of days to look back (default: 5).

    Returns:
        list: News items from the last 'days' days, sorted by published_date in descending order.
    """
    valid_news = [news for news in news_list if "published_date" in news]
    if not valid_news:
        return []
    
    # Calculate the cutoff date (today - days)
    cutoff_date = datetime.now() - timedelta(days=days)
    
    try:
        # Filter news items within the last 'days' days
        recent_news = [
            news for news in valid_news
            if datetime.strptime(news["published_date"], "%Y-%m-%d %H:%M:%S") >= cutoff_date
        ]
        
        # Sort by published_date in descending order
        sorted_news = sorted(
            recent_news,
            key=lambda x: datetime.strptime(x["published_date"], "%Y-%m-%d %H:%M:%S"),
            reverse=True
        )
        return sorted_news
    
    except ValueError as e:
        print(f"Date parsing error in news: {e}")
        return []

def parse_llm_response(response_content):
    # Search for a JSON object in the response
    json_pattern = r'\{.*\}'
    match = re.search(json_pattern, response_content, re.DOTALL)
    if match:
        json_str = match.group(0)
        try:
            result = json.loads(json_str)
            # Verify required keys are present
            if "recommendation_sign" in result and "analysis_overview" in result and "recommendation_confidence_score" in result:
                return result
            else:
                return {"recommendation": "NA", "details": "LLM response missing required fields."}
        except json.JSONDecodeError:
            return {"recommendation": "NA", "details": "Failed to parse extracted JSON from response."}
    else:
        return {"recommendation": "NA", "details": "No valid JSON object found in LLM response."}
 
# Function 1: Analyze latest announcements using Groq
def get_recommendation_from_announcements(symbol, exchange):
    try:
        # Fetch data from MongoDB (unchanged)
        data = collection.find_one({"symbol": symbol.upper(), "exchange": exchange.lower()})
        if not data:
            return {"recommendation": "NA", "details": "No data found for the given symbol and exchange in the database."}
        
        # Extract announcement categories (unchanged)
        announcements = data.get("announcements", {})
        board_meetings = announcements.get("board_meetings", [])
        dividends = announcements.get("dividends", [])
        splits = announcements.get("splits", [])
        bonus = announcements.get("bonus", [])
        rights = announcements.get("rights", [])
        
        board_meetings_latest = get_latest_announcements(board_meetings, "date")
        dividends_latest = get_latest_announcements(dividends, "ex_date")
        splits_latest = get_latest_announcements(splits, "ex_date")
        bonus_latest = get_latest_announcements(bonus, "ex_date")
        rights_latest = get_latest_announcements(rights, "ex_date")
        
        if not any([board_meetings_latest, dividends_latest, splits_latest, bonus_latest, rights_latest]):
            return {"recommendation": "NA", "details": "No recent announcement data available for analysis."}
        
        # Format data (unchanged)
        data_str = (
            f"Latest Board Meetings:\n{json.dumps(board_meetings_latest, indent=2)}\n\n"
            f"Latest Dividends:\n{json.dumps(dividends_latest, indent=2)}\n\n"
            f"Latest Splits:\n{json.dumps(splits_latest, indent=2)}\n\n"
            f"Latest Bonus Issues:\n{json.dumps(bonus_latest, indent=2)}\n\n"
            f"Latest Rights Issues:\n{json.dumps(rights_latest, indent=2)}"
        )
        
        # Updated prompt
        system_content = "You are a financial analyst API. Your task is to analyze corporate announcements and return a stock recommendation in JSON format."
        user_content = (
            f"Analyze the following latest announcements for {symbol} on {exchange}. "
            f"Based on the data, provide a stock recommendation_sign: 'BULLISH', 'BEARISH', or 'NEUTRAL'. "
            f"Thoroughly analyse the given info in order to make decision for recommendation_sign and recommendation_confidence_score. "
            f"Provide a brief overview of your analysis. "
            f"Provide a confidence score for your recommendation_sign. Must be between 0 and 1. "
            f"\n\nData:\n{data_str}\n\n"
            f"**Critical Instructions:**\n"
            f"- Return **only** a JSON object with three keys: 'recommendation_sign', 'recommendation_confidence_score', and 'analysis_overview.\n"
            f"- Do not include any additional text, explanations, or code outside the JSON object.\n"
            f"- Ensure the JSON is valid and can be parsed directly.\n"
            f"- Example: {{ \"analysis_overview\": \"Strong earnings reported.\", \"recommendation_sign\": \"BUY\",\"recommendation_confidence_score\": 0.85}}\n"
        )
        
        # Call Groq API (unchanged)
        completion = groq_client.chat.completions.create(
            model="deepseek-r1-distill-llama-70b",
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content}
            ],
            temperature=0.05,
            max_tokens=8000,
            top_p=0.9,
            stream=False,
            stop=None,
            reasoning_format="parsed"
        )
        
        # Get response and parse with new logic
        response_content = completion.choices[0].message.content
        reasoning = completion.choices[0].message.reasoning
        result = parse_llm_response(response_content)
        # Add reasoning to the result
        result["analysis"] = reasoning
        # Add datetime of the run
        result["run_datetime"] = datetime.now().isoformat()
        return result
    
    except Exception as e:
        return {"recommendation": "NA", "details": f"An error occurred: {str(e)}"}
    
# Function 2: Analyze latest news using Groq
def get_recommendation_from_news(symbol, exchange):
    try:
        # Fetch data from MongoDB (unchanged)
        data = collection.find_one({"symbol": symbol.upper(), "exchange": exchange.lower()})
        if not data:
            return {"recommendation": "NA", "details": "No data found for the given symbol and exchange in the database."}
        
        # Extract and sort news (unchanged)
        news = data.get("news", [])
        news_latest = get_latest_news(news)
        
        if not news_latest:
            return {"recommendation": "NA", "details": "No recent news data available for analysis."}
        
        # Format data (unchanged)
        data_str = f"Latest News:\n{json.dumps(news_latest, indent=2)}"

        print(data_str)
        
        # Updated prompt
        system_content = "You are a financial analyst API. Your task is to analyze news data and return a stock recommendation in JSON format."
        user_content = (
            f"Analyze the following latest news data for {symbol} on {exchange}. "
            f"Based on the news, provide a stock recommendation_sign: 'BULLISH', 'BEARISH', or 'NEUTRAL'. "
            f"Thoroughly analyse the given info in order to make decision for recommendation_sign and recommendation_confidence_score. "
            f"Provide a confidence score for your recommendation_sign. Must be between 0 and 1. "
            f"\n\nData:\n{data_str}\n\n"
            f"**Critical Instructions:**\n"
            f"- Return **only** a JSON object with three keys: 'recommendation_sign', 'recommendation_confidence_score' and 'analysis_overview.\n"
            f"- Do not include any additional text, explanations, or code outside the JSON object.\n"
            f"- Ensure the JSON is valid and can be parsed directly.\n"
            f"- Example: {{ \"analysis_overview\": \"Strong earnings reported.\", \"recommendation_sign\": \"BUY\",\"recommendation_confidence_score\": 0.85}}\n"        )
        
        # Call Groq API (unchanged)
        completion = groq_client.chat.completions.create(
            model="deepseek-r1-distill-llama-70b",
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content}
            ],
            temperature=0.05,
            max_tokens=8000,
            top_p=0.9,
            stream=False,
            stop=None,
            reasoning_format="parsed"
        )
        
        # Get response and parse with new logic
        response_content = completion.choices[0].message.content
        reasoning = completion.choices[0].message.reasoning
        result = parse_llm_response(response_content)
        # Add reasoning to the result
        result["analysis"] = reasoning
        # Add datetime of the run
        result["run_datetime"] = datetime.now().isoformat()
        return result
    
    except Exception as e:
        return {"recommendation": "NA", "details": f"An error occurred: {str(e)}"}
    
# Example usage
if __name__ == "__main__":
    # Test the announcements function
    result1 = get_recommendation_from_announcements("526961", "NSE")
    print("Recommendation from Announcements:")
    print(json.dumps(result1, indent=2))
    
    # Test the news function
    result2 = get_recommendation_from_news("526961", "NSE")
    print("\nRecommendation from News:")
    print(json.dumps(result2, indent=2))