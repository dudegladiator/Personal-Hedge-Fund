import json
import re
from utils.config import settings, get_sync_database
from utils.app_logger import setup_logger
from src.llm.models import get_model
from datetime import datetime, timedelta
from src.prompts import announcements_system_prompt, news_system_prompt

logger = setup_logger("src/agents/sentimental_agent.py")
db = get_sync_database()
groq_client = get_model(model_provider="GROQ")

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

def get_latest_news(news_list, days):
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
    # Extract thinking/reasoning part
    thinking_pattern = r'<think>(.*?)</think>'
    thinking_match = re.search(thinking_pattern, response_content, re.DOTALL)
    reasoning = thinking_match.group(1).strip() if thinking_match else ""

    # Extract JSON part
    json_pattern = r'```json\s*(\{.*?\})\s*```'
    json_match = re.search(json_pattern, response_content, re.DOTALL)
    
    if json_match:
        json_str = json_match.group(1)
        try:
            result = json.loads(json_str)
            # Verify required keys are present
            if "recommendation_sign" in result and "analysis_overview" in result and "recommendation_confidence_score" in result:
                # Add reasoning to the result
                result["reasoning"] = reasoning
                return result
            else:
                return {
                    "recommendation_sign": "NEUTRAL", 
                    "details": "LLM response missing required fields.",
                    "reasoning": reasoning
                }
        except json.JSONDecodeError:
            return {
                "recommendation_sign": "NEUTRAL", 
                "details": "Failed to parse extracted JSON from response.",
                "reasoning": reasoning
            }
    else:
        return {
            "recommendation_sign": "NEUTRAL", 
            "details": "No valid JSON object found in LLM response.",
            "reasoning": reasoning
        }
 
# Function 1: Analyze latest announcements using Groq
def get_recommendation_from_announcements(symbol, exchange, past_days=90):
    try:
        # Fetch data from MongoDB (unchanged)
        data = db.corporate_announcements_news.find_one({"symbol": symbol.upper(), "exchange": exchange.lower()})
        if not data:
            return {"recommendation_sign": "NEUTRAL", "details": "No data found for the given symbol and exchange in the database."}
        
        # Extract announcement categories (unchanged)
        announcements = data.get("announcements", {})
        board_meetings = announcements.get("board_meetings", [])
        dividends = announcements.get("dividends", [])
        splits = announcements.get("splits", [])
        bonus = announcements.get("bonus", [])
        rights = announcements.get("rights", [])
        
        board_meetings_latest = get_latest_announcements(board_meetings, "date", days=past_days)
        dividends_latest = get_latest_announcements(dividends, "ex_date", days=past_days)
        splits_latest = get_latest_announcements(splits, "ex_date", days=past_days)
        bonus_latest = get_latest_announcements(bonus, "ex_date", days=past_days)
        rights_latest = get_latest_announcements(rights, "ex_date", days=past_days)
        
        if not any([board_meetings_latest, dividends_latest, splits_latest, bonus_latest, rights_latest]):
            return {"recommendation_sign": "NEUTRAL", "details": "No recent announcement data available for analysis."}
        
        # Format data (unchanged)
        data_str = (
            f"Latest Board Meetings:\n{json.dumps(board_meetings_latest, indent=2)}\n\n"
            f"Latest Dividends:\n{json.dumps(dividends_latest, indent=2)}\n\n"
            f"Latest Splits:\n{json.dumps(splits_latest, indent=2)}\n\n"
            f"Latest Bonus Issues:\n{json.dumps(bonus_latest, indent=2)}\n\n"
            f"Latest Rights Issues:\n{json.dumps(rights_latest, indent=2)}"
        )

        user_content = (
            f"Analyze the following latest announcements for {symbol} on {exchange}. "
            f"Based on the data, provide a stock recommendation_sign: 'BULLISH', 'BEARISH', or 'NEUTRAL'. "
            f"Follow the confidence score guidelines strictly when assigning recommendation_confidence_score. "
            f"Consider the weight factors for different types of announcements. "
            f"\n\nData:\n{data_str}\n\n"
            f"**Critical Instructions:**\n"
            f"1. Analyze each announcement type's impact separately first\n"
            f"2. Consider the recency and significance of each announcement\n"
            f"3. Provide clear reasoning for the confidence score\n"
            f"4. Return a JSON object with exactly these keys:\n"
            f"   - recommendation_sign: 'BULLISH', 'BEARISH', or 'NEUTRAL'\n"
            f"   - recommendation_confidence_score: float between 0-1\n"
            f"   - analysis_overview: detailed analysis summary\n"
            f"Example: {{\n"
            f"  \"recommendation_sign\": \"BULLISH\",\n"
            f"  \"recommendation_confidence_score\": 0.85,\n"
            f"  \"analysis_overview\": \"Strong dividend announcement with clear growth signals\"\n"
            f"}}"
        )
        
        # Call Groq API (unchanged)
        completion = groq_client.chat.completions.create(
            model="deepseek-r1-distill-llama-70b",
            messages=[
                {"role": "system", "content": announcements_system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.05,
            max_tokens=8000,
            top_p=0.9,
            response_format={ "type": "json_object" }
        )
        
        # Get response and parse with new logic
        response_content = completion.choices[0].message.content
        result = parse_llm_response(response_content)
        # Add datetime of the run
        result["run_datetime"] = datetime.now().isoformat()
        return result
    
    except Exception as e:
        return {"recommendation_sign": "NEUTRAL", "details": f"An error occurred: {str(e)}", "error": True}
    
# Function 2: Analyze latest news using Groq
def get_recommendation_from_news(symbol, exchange, past_days=5):
    try:
        # Fetch data from MongoDB (unchanged)
        data = db.corporate_announcements_news.find_one({"symbol": symbol.upper(), "exchange": exchange.lower()})
        if not data:
            return {"recommendation_sign": "NEUTRAL", "details": "No data found for the given symbol and exchange in the database."}
        
        # Extract and sort news (unchanged)
        news = data.get("news", [])
        news_latest = get_latest_news(news, days = past_days)
        
        if not news_latest:
            return {"recommendation_sign": "NEUTRAL", "details": "No recent news data available for analysis."}
        
        # Format data (unchanged)
        data_str = f"Latest News:\n{json.dumps(news_latest, indent=2)}"

        user_content = (
            f"Analyze the following latest news for {symbol} on {exchange}. "
            f"Based on the news, provide a stock recommendation_sign: 'BULLISH', 'BEARISH', or 'NEUTRAL'. "
            f"Follow the confidence score guidelines strictly when assigning recommendation_confidence_score. "
            f"Consider the weight factors for different news aspects. "
            f"\n\nData:\n{data_str}\n\n"
            f"**Critical Instructions:**\n"
            f"1. Evaluate news credibility and impact\n"
            f"2. Consider news recency and relevance\n"
            f"3. Assess market sentiment across multiple sources\n"
            f"4. Return a JSON object with exactly these keys:\n"
            f"   - recommendation_sign: 'BULLISH', 'BEARISH', or 'NEUTRAL'\n"
            f"   - recommendation_confidence_score: float between 0-1\n"
            f"   - analysis_overview: detailed analysis summary\n"
            f"Example: {{\n"
            f"  \"recommendation_sign\": \"BULLISH\",\n"
            f"  \"recommendation_confidence_score\": 0.85,\n"
            f"  \"analysis_overview\": \"Strong positive news coverage with consistent market impact\"\n"
            f"}}"
        )
        
        # Call Groq API (unchanged)
        completion = groq_client.chat.completions.create(
            model="deepseek-r1-distill-llama-70b",
            messages=[
                {"role": "system", "content": news_system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.05,
            max_tokens=8000,
            top_p=0.9
        )
        # Get response and parse with new logic
        response_content = completion.choices[0].message.content
        result = parse_llm_response(response_content)
        # Add datetime of the run
        result["run_datetime"] = datetime.now().isoformat()
        return result
    
    except Exception as e:
        return {"recommendation_sign": "NEUTRAL", "details": f"An error occurred: {str(e)}", "error": True}
    
#Add the Agent
    
# Example usage
if __name__ == "__main__":
    # Test the announcements function
    result1 = get_recommendation_from_announcements("526961", "NSE")
    print("Recommendation from Announcements:")
    print(json.dumps(result1, indent=2))
    
    # Test the news function
    result2 = get_recommendation_from_news("526961", "NSE", 200)
    print("\nRecommendation from News:")
    print(json.dumps(result2, indent=2))
