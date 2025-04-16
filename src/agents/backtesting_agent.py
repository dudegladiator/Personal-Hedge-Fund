from datetime import datetime, timedelta
import json
from typing import Any, Dict
from src.agents.sentimental_agent import get_recommendation_from_announcements, get_recommendation_from_news
from src.backtesting.technical_indicators import get_basic_technical_indicators
from src.data_source.apis_2 import get_company_dashboard
from src.llm.models import get_model
from utils.app_logger import setup_logger
from utils.config import get_sync_database
from src.prompts import backtesting_strategy_system_prompt, backtesting_analysis_system_prompt, get_prompt_for_backtesting
from src.backtesting.backtesting_engine import BacktestParameters, execute_backtesting
from utils.llm import parse_backtesting_results, parse_strategy_code_response

logger = setup_logger("src/agents/backtesing_agent.py")
db = get_sync_database()

MODEL_PROVIDER = "GEMINI"
MODEL_NAME = "gemini-2.0-flash-thinking-exp-01-21"
FORMAT = { "type": "text" }

def analyze_backtest_results(symbol, backtesting_results):
    logger.info(f"Starting backtest analysis for {symbol}")
    try:
        prompt = f"""Analyze the following backtesting results for symbol: {symbol}.

Please evaluate each strategy based on its performance metrics and provide a consolidated analysis. Follow the instructions and output format specified in the system prompt precisely.

Backtesting Results Data:
{backtesting_results}

**Instruction Recap:** Output ONLY the final JSON object containing the executive_summary and detailed_analysis for each strategy.
"""
        
        logger.debug("Sending analysis request to LLM")
        chat_model = get_model(model_provider=MODEL_PROVIDER)
        completion = chat_model.chat.completions.create(
            messages=[
                {"role": "system", "content": backtesting_analysis_system_prompt},
                {"role": "user", "content": prompt}
            ],
            model=MODEL_NAME,
            temperature=0.6,
            response_format=FORMAT
        )
        parsed_results = parse_backtesting_results(response_content=completion.choices[0].message.content, raw_data =backtesting_results)
        
        logger.info(f"Successfully analyzed backtest results for {symbol}")
        return parsed_results
        
    except Exception as e:
        logger.error(f"Error analyzing backtest results for {symbol}: {str(e)}", exc_info=True)
        return {
            "error": True,
            "details": str(e),
            "raw_data": backtesting_results
        }

def generate_strategy_code(symbol: str, exchange: str, force: bool = False):
    """Generate strategy code using LLM"""
    logger.info(f"Starting strategy code generation for {symbol}")
    try:
        # Fetch required data
        company_dashboard = get_company_dashboard(symbol, exchange, force=force, refresh_days=7)
        
        company_announcement = get_recommendation_from_announcements(symbol, exchange, force=force)
        company_news = get_recommendation_from_news(symbol, exchange, force=force)
        del company_announcement["raw_data"]
        del company_news["raw_data"]
        
        company_basic_technical_indicators = get_basic_technical_indicators(
            symbol=symbol,
            start_date=datetime.now() - timedelta(days=365),
            end_date=datetime.now(),
            interval="1D"
        )
        
        # Format prompt
        profile_prompt = get_prompt_for_backtesting(
            company_dashboard,
            company_announcement,
            company_news,
            company_basic_technical_indicators
        )

        chat_model = get_model(model_provider=MODEL_PROVIDER)
        chat_completion = chat_model.chat.completions.create(
            messages=[
                {"role": "system", "content": backtesting_strategy_system_prompt},
                {"role": "user", "content": profile_prompt}
            ],
            model=MODEL_NAME,
            temperature=0.65,
            response_format=FORMAT
        )
        
        strategy_response = parse_strategy_code_response(chat_completion.choices[0].message.content)
        if isinstance(strategy_response, dict) and strategy_response.get("error"):
            logger.error(f"Strategy generation failed: {strategy_response.get('message')}")
            return strategy_response
            
        logger.info(f"Successfully generated {len(strategy_response)} strategies for {symbol}")
        return strategy_response
    except Exception as e:
        logger.error(f"Error generating strategy code for {symbol}: {str(e)}", exc_info=True)
        return {
            "error": True,
            "message": str(e)
        }
        
def backtesting_agent(
    symbol: str,
    exchange: str = "nse",
    force: bool = False,
    backtesting_days: int = 365*2
) -> Dict[str, Any]:
    logger.info(f"Starting backtesting agent for {symbol}")
    try:
        # Generate strategy code
        strategy_response = generate_strategy_code(symbol, exchange, force=force)
        strategy_response = strategy_response.get("strategies")
        # Test all strategies
        all_results = []
        for i, strategy_code in enumerate(strategy_response, 1):
            logger.info(f"Testing strategy {i} of {len(strategy_response)}")
            params = BacktestParameters(
                symbol=symbol,
                strategy_code=strategy_code.get("strategy_code"),
                start_date=datetime.now() - timedelta(days=backtesting_days),
                end_date=datetime.now(),
                stop_loss=0.05,
                take_profit=0.05
            )
            
            # Execute backtesting
            logger.debug(f"Executing backtest for strategy {i}")
            try:
                backtest_results = execute_backtesting(params)
            
                strategy_result = {
                    "strategy_number": i,
                    "strategy_name": strategy_code.get("strategy_name"),
                    "backtest_parameters": params.model_dump(),
                    "backtest_results": backtest_results.model_dump(),
                }
                # logger.debug(f"Strategy {i} results: {strategy_result}")
                all_results.append(strategy_result)
            except:
                logger.error(f"Backtest execution failed for strategy {i}", exc_info=True)
                continue
        
        if len(all_results) == 0:
            logger.error(f"No strategies were successfully backtested for {symbol}")
            return {
                "error": True,
                "details": "No strategies were successfully backtested.",
                "raw_data": strategy_response
            }
        analyse = analyze_backtest_results(symbol, all_results)
        logger.info(f"Backtesting completed for {symbol}")
        return analyse
        
    except Exception as e:
        error_msg = f"Backtesting failed for {symbol}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "error": True,
            "details": error_msg,
        }

if __name__ == "__main__":
    stock_codes = [
        # "INDUSINDBK",
        # "PATANJALI",
        # "ITC",
        # "AMBUJACEM",
        # "AXISBANK",
        # "HEROMOTOCO",
        # "HAL",
        "UNITDSPR",
        # "TATAMOTORS",
        # "NTPC",
        # "BAJAJFINSV",
        # "RELIANCE"
    ]
    for stock_code in stock_codes:
        result = backtesting_agent(
            symbol=stock_code,
            exchange="nse",
            force=False,
            backtesting_days=365*2
        )
        print(f"Backtesting result for {stock_code}:")
        print(result)
        print("=======================================")
        print("=======================================")