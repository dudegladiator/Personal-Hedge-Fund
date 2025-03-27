import ast
from datetime import datetime
from src.agents.sentimental_agent import get_recommendation_from_announcements, get_recommendation_from_news
from src.backtesting.technical_indicators import get_basic_technical_indicators
from utils.llm import parse_llm_response
from utils.util import safe_get
import json
import statistics
from typing import Any, Dict, TypedDict
from src.llm.models import get_model
from langgraph.types import Command
from langgraph.graph import StateGraph, START
from utils.app_logger import setup_logger
from utils.config import settings, get_sync_database

logger = setup_logger("src/agents/fundamental_agent.py")
db = get_sync_database()

MODEL_PROVIDER = "GEMINI"
MODEL_NAME = "gemini-2.0-flash"
Format = "json_object" # json_object # text

def format_data_for_backtesting(company_dashboard, company_annoucement, company_news, company_basic_technical_indicators):
    
    system_prompt = ""

    prompt = f"""
### Company Dashboard
- **Symbol**: {safe_get(company_dashboard, ['symbol'])}
- **Name**: {safe_get(company_dashboard, ['company_info', 'name'])}
- **Industry**: {safe_get(company_dashboard, ['company_info', 'industry'])}
- **Sector**: {safe_get(company_dashboard, ['company_info', 'sector'])}
- **Market Cap Category**: {safe_get(company_dashboard, ['company_info', 'market_cap_category'])}
- **Market Cap**: {safe_get(company_dashboard, ['key_metrics', 'market_cap'], default='N/A')}
- **PE Ratio**: {safe_get(company_dashboard, ['key_metrics', 'pe_ratio'], default='N/A')}

### Announcements & News
company_annoucement_overview = {company_annoucement.get("analysis_overview")}
company_news_overview = {company_news.get("analysis_overview")}

### Basic Technical Indicators
"""
    return system_prompt, prompt

def generate_strategy_code(symbol: str):
    try:
        company_dashboard = db.company_dashboard.find_one({"symbol": symbol})
        company_annoucement = get_recommendation_from_announcements(symbol)
        company_news = get_recommendation_from_news(symbol)
        company_basic_technical_indicators = get_basic_technical_indicators(symbol=symbol, start_date=datetime(2023, 1, 1), end_date=datetime(2024, 1, 1))
        
        system_prompt, profile_prompt = format_data_for_backtesting(company_dashboard, company_annoucement, company_news, company_basic_technical_indicators)

        chat_model = get_model(model_provider=MODEL_PROVIDER)
        chat_completion = chat_model.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": profile_prompt,
                }
            ],
            model=MODEL_NAME,
            temperature=0.65,
            response_format=Format
        )

        response_content = chat_completion.choices[0].message.content
        
        result = parse_llm_response(response_content)
        # Add datetime of the run
        result["run_datetime"] = datetime.now().isoformat()
        return result
    except Exception as e:
        logger.error(f"Error generating strategy code: {str(e)}")
        return {
            "error": True,
        }
    

if __name__ == "__main__":
    print(generate_strategy_code("RELIANCE"))
