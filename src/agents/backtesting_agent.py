from datetime import datetime, timedelta
import json
from typing import Any, Dict
from src.agents.sentimental_agent import get_recommendation_from_announcements, get_recommendation_from_news
from src.backtesting.technical_indicators import get_basic_technical_indicators
from src.data_source.market_apis import get_company_dashboard
from utils.llm import parse_llm_response
from src.llm.models import get_model
from utils.app_logger import setup_logger
from utils.config import get_sync_database
from src.prompts import backtesting_strategy_system_prompt, backtesting_analysis_system_prompt, get_prompt_for_backtesting
from src.backtesting.backtesting_engine import BacktestParameters, execute_backtesting

logger = setup_logger("src/agents/backtesing_agent.py")
db = get_sync_database()

MODEL_PROVIDER = "GEMINI"
MODEL_NAME = "gemini-2.0-flash"
# MODEL_PROVIDER = "GROQ"
# MODEL_NAME = "llama-3.3-70b-versatile"
FORMAT = { "type": "json_object" }

def analyze_backtest_results(symbol: str, results: Dict[str, Any]) -> Dict[str, Any]:
    logger.info(f"Starting backtest analysis for {symbol}")
    try:
        prompt = f"""
        Analyze the following backtesting results for {symbol} and provide detailed insights:
        
        {json.dumps(results, indent=2)}
        
        Provide analysis including:
        1. Overall strategy performance
        2. Risk metrics analysis
        3. Trading statistics evaluation
        4. Recommendations for improvement
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
        
        analysis_result = json.loads(completion.choices[0].message.content)
        logger.info(f"Successfully analyzed backtest results for {symbol}")
        logger.debug(f"Analysis result: {json.dumps(analysis_result, indent=2)}")
        return analysis_result
        
    except Exception as e:
        logger.error(f"Error analyzing backtest results for {symbol}: {str(e)}", exc_info=True)
        return {
            "error": True,
            "message": str(e)
        }

def generate_strategy_code(symbol: str, exchange: str, force: bool = False):
    """Generate strategy code using LLM"""
    logger.info(f"Starting strategy code generation for {symbol}")
    try:
        # Fetch required data
        company_dashboard = get_company_dashboard(symbol, exchange, force=force, refresh_days=7)
        
        company_announcement = get_recommendation_from_announcements(symbol, exchange, force=force)
        
        company_news = get_recommendation_from_news(symbol, exchange, force=force)
        
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

        response_content = json.loads(chat_completion.choices[0].message.content)
        logger.info(f"Successfully generated strategy code for {symbol}")
        return response_content
        
    except Exception as e:
        logger.error(f"Error generating strategy code for {symbol}: {str(e)}", exc_info=True)
        return {
            "error": True,
            "message": str(e)
        }
        
def backtesting_agent(
    symbol: str,
    exchange: str = "nse",
    force: bool = False
) -> Dict[str, Any]:
    logger.info(f"Starting backtesting agent for {symbol}")
    try:
            
        # Generate strategy code
        strategy_response = generate_strategy_code(symbol, exchange, force=force)
        
        if isinstance(strategy_response, dict) and strategy_response.get("error"):
            logger.error(f"Strategy generation failed: {strategy_response.get('message')}")
            return strategy_response
            
        logger.info(f"Successfully generated {len(strategy_response)} strategies for {symbol}")
        
        # Test all strategies
        all_results = []
        for i, strategy_code in enumerate(strategy_response, 1):
            logger.info(f"Testing strategy {i} of {len(strategy_response)}")
            
            try:
                start_date = datetime.strptime(strategy_code.get("start_date"), "%Y-%m-%d")
                end_date = datetime.strptime(strategy_code.get("end_date"), "%Y-%m-%d")
            except:
                # Fallback to default dates if conversion fails
                start_date = datetime.now() - timedelta(days=365)
                end_date = datetime.now()
            
            logger.debug(f"Backtesting strategy {i} with dates {start_date} to {end_date}")
            
            params = BacktestParameters(
                symbol=symbol,
                strategy_code=strategy_code.get("strategy_code"),
                start_date=strategy_code.get("start_date"),
                end_date=strategy_code.get("end_date"),
                stop_loss=0.05,
                take_profit=0.05
            )
            
            # Execute backtesting
            logger.debug(f"Executing backtest for strategy {i}")
            backtest_results = execute_backtesting(params)
            
            # Analyze results
            # logger.debug(f"Analyzing results for strategy {i}")
            # analysis = analyze_backtest_results(symbol, backtest_results.model_dump())
            
            strategy_result = {
                "strategy_number": i,
                "strategy_name": strategy_code.get("strategy_name"),
                "backtest_parameters": params.model_dump(),
                "backtest_results": backtest_results.model_dump(),
                # "analysis": analysis
            }
            
            logger.debug(f"Strategy {i} results: {strategy_result}")
            all_results.append(strategy_result)
        
        # Compile final results
        final_results = {
            "symbol": symbol,
            "strategies": all_results,
            "run_datetime": datetime.now().isoformat()
        }
        
        logger.info(f"Successfully completed backtesting process for {symbol} "
                   f"with {len(all_results)} strategies")
        logger.debug(f"Final results: {final_results}")
        return final_results
        
    except Exception as e:
        error_msg = f"Backtesting failed for {symbol}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "error": True,
            "symbol": symbol,
            "message": error_msg
        }

if __name__ == "__main__":
    print(backtesting_agent("RELIANCE"))