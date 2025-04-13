import json
from src.data_source.apis_2 import get_corporate_announcements, get_stock_news
from utils.app_logger import setup_logger
from src.llm.models import get_model
from datetime import datetime
from src.prompts import announcements_system_prompt, news_system_prompt
from utils.llm import parse_sentimental_response
from utils.util import get_latest_announcements, get_latest_news

logger = setup_logger("src/agents/sentimental_agent.py")
MODEL_PROVIDER = "GEMINI"
MODEL_NAME = "gemini-2.0-flash"
FORMAT = { "type": "json_object" }
 
def get_recommendation_from_announcements(symbol, exchange="nse", past_days=90, force = False):
    logger.info(f"Getting announcement recommendations for {symbol} on {exchange} for past {past_days} days")
    try:
        data = get_corporate_announcements(symbol, exchange, refresh_days=1, force=force)
        if not data:
            logger.warning(f"No data found for symbol {symbol} on {exchange}")
            return {"recommendation_sign": "NEUTRAL", "details": "No data found for the given symbol and exchange in the database."}
        
        announcements = data
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
        
        logger.info(f"Latest announcements found for {symbol}: "
                    f"Board Meetings: {len(board_meetings_latest)}, "
                    f"Dividends: {len(dividends_latest)}, "
                    f"Splits: {len(splits_latest)}, "
                    f"Bonus Issues: {len(bonus_latest)}, "
                    f"Rights Issues: {len(rights_latest)}")
        
        if not any([board_meetings_latest, dividends_latest, splits_latest, bonus_latest, rights_latest]):
            logger.warning(f"No recent announcements found for {symbol}")
            return {"recommendation_sign": "NEUTRAL", "details": "No recent announcement data available for analysis."}
        
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
        chat_model = get_model(model_provider=MODEL_PROVIDER)
        completion = chat_model.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": announcements_system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.05,
            response_format=FORMAT
        )
        
        response_content = completion.choices[0].message.content
        result = parse_sentimental_response(response_content)
        result["run_datetime"] = datetime.now().isoformat()
        
        logger.info(f"Successfully generated announcement recommendation for {symbol}")
        return result
    
    except Exception as e:
        logger.error(f"Error in announcement analysis for {symbol}: {str(e)}", exc_info=True)
        return {"recommendation_sign": "NEUTRAL", "details": f"An error occurred: {str(e)}", "error": True}
    
def get_recommendation_from_news(symbol, exchange="nse", past_days=5, force = False):
    logger.info(f"Getting news recommendations for {symbol} on {exchange} for past {past_days} days")
    try:
        data = get_stock_news(symbol, exchange, refresh_days=1, force=force)
        if not data:
            logger.warning(f"No data found for symbol {symbol} on {exchange}")
            return {"recommendation_sign": "NEUTRAL", "details": "No data found for the given symbol and exchange in the database."}
        
        news = data
        news_latest = get_latest_news(news, days=past_days)
        
        if not news_latest:
            logger.warning(f"No recent news found for {symbol}")
            return {"recommendation_sign": "NEUTRAL", "details": "No recent news data available for analysis."}
        
        logger.info(f"Latest news found for {symbol}: {len(news_latest)}")
        
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
        
        logger.info(f"Sending news analysis request to LLM for {symbol}")
        chat_model = get_model(model_provider=MODEL_PROVIDER)
        completion = chat_model.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": news_system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.05,
            response_format=FORMAT
        )

        response_content = completion.choices[0].message.content
        result = parse_sentimental_response(response_content)
        result["run_datetime"] = datetime.now().isoformat()
        
        logger.info(f"Successfully generated news recommendation for {symbol}")
        return result
    
    except Exception as e:
        logger.error(f"Error in news analysis for {symbol}: {str(e)}", exc_info=True)
        return {"recommendation_sign": "NEUTRAL", "details": f"An error occurred: {str(e)}", "error": True}
    
#Add the Agent
    
# Example usage
if __name__ == "__main__":
    # Test the announcements function
    result1 = get_recommendation_from_announcements("RELIANCE", "nse")
    print("Recommendation from Announcements:")
    print(json.dumps(result1, indent=2))
    
    # Test the news function
    result2 = get_recommendation_from_news("RELIANCE", "nse", 200)
    print("\nRecommendation from News:")
    print(json.dumps(result2, indent=2))
