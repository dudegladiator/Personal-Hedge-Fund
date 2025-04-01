from datetime import datetime, timedelta, date
import json
import traceback # Import traceback to get detailed error info
from typing import Any, Dict, Optional
import pandas as pd

# Assuming these imports are correct relative to your project structure
from src.agents.sentimental_agent import get_recommendation_from_announcements, get_recommendation_from_news
from src.backtesting.technical_indicators import get_basic_technical_indicators
from src.data_source.market_apis import get_company_dashboard
# from utils.llm import parse_llm_response # Not used directly in the provided snippet
from src.llm.models import get_model
from utils.app_logger import setup_logger
from utils.config import get_sync_database
from src.prompts import (
    backtesting_strategy_system_prompt,
    backtesting_analysis_system_prompt,
    get_prompt_for_backtesting,
    backtesting_debug_system_prompt 
)
from src.backtesting.backtesting_engine import BacktestParameters, execute_backtesting, BacktestResult

logger = setup_logger("src/agents/backtesing_agent.py")
db = get_sync_database()

MODEL_PROVIDER = "GEMINI"
MODEL_NAME = "gemini-2.0-flash" # Using flash as it's faster/cheaper for potential multiple calls
# MODEL_PROVIDER = "GROQ"
# MODEL_NAME = "llama3-70b-8192" # Adjusted name if using Groq Llama3 70b
FORMAT = { "type": "json_object" }

MAX_DEBUG_ATTEMPTS = 5 # Maximum number of debugging attempts per strategy

# --- New Function: Debug Strategy Code ---
def debug_strategy_code(original_code: str, error_message: str, symbol: str) -> Optional[str]:
    """Attempts to fix the strategy code using an LLM based on the error."""
    logger.warning(f"Attempting to debug strategy code for {symbol} due to error.")
    logger.debug(f"Original code:\n{original_code}")
    logger.debug(f"Error message: {error_message}")

    # You need to create this prompt in src/prompts.py
    # It should instruct the LLM to act as a Python/backtesting expert,
    # receive the code and error, and return *only* the fixed code in a JSON format.
    debug_prompt = f"""
    You are an expert Python programmer specializing in the 'backtesting.py' library.
    The following Python code for a trading strategy failed during execution with the provided error message.
    Analyze the code and the error, then provide the corrected Python code.

    **Constraints:**
    - Only fix the errors indicated by the error message or obvious syntax/logic errors related to the backtesting framework (e.g., incorrect method names, missing imports like 'from backtesting import Strategy').
    - Do NOT change the core trading logic unless it's directly causing the error.
    - Ensure the output is a valid Python class inheriting from `backtesting.Strategy`.
    - The corrected code should be runnable within the `backtesting.py` framework.
    - Respond ONLY with a JSON object containing the corrected code under the key "fixed_code". Example: {{"fixed_code": "import backtesting\\n..."}}

    **Original Python Code:**
    ```python
    {original_code}
    ```

    **Error Message Encountered:**
    ```
    {error_message}
    ```

    Provide the corrected code in the specified JSON format.
    """

    try:
        chat_model = get_model(model_provider=MODEL_PROVIDER)
        completion = chat_model.chat.completions.create(
            messages=[
                # Consider adding a system prompt specifically for debugging if needed
                {"role": "system", "content": backtesting_debug_system_prompt}, # Define this prompt
                {"role": "user", "content": debug_prompt}
            ],
            model=MODEL_NAME,
            temperature=0, # Low temperature for deterministic fixes
            response_format=FORMAT
        )

        response_content = json.loads(completion.choices[0].message.content)
        fixed_code = response_content.get("fixed_code")

        if fixed_code and isinstance(fixed_code, str):
            logger.info(f"LLM provided a potential fix for {symbol} strategy.")
            logger.debug(f"Fixed code:\n{fixed_code}")
            # Basic validation: Check if it's non-empty and maybe contains 'class' and 'Strategy'
            if "class" in fixed_code and "Strategy" in fixed_code:
                 return fixed_code
            else:
                logger.warning("LLM fix seems invalid (missing 'class' or 'Strategy'). Discarding fix.")
                return None
        else:
            logger.warning(f"LLM did not return valid fixed code for {symbol}. Response: {response_content}")
            return None

    except json.JSONDecodeError as json_err:
        logger.error(f"Failed to parse LLM response during debugging for {symbol}: {json_err}")
        logger.debug(f"Raw LLM response content: {completion.choices[0].message.content if 'completion' in locals() else 'N/A'}")
        return None
    except Exception as e:
        logger.error(f"Error calling LLM during debugging for {symbol}: {str(e)}", exc_info=True)
        return None

# --- Existing Function: Analyze Backtest Results (Unchanged) ---
def default_serializer(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, (datetime, date, pd.Timestamp)):
        return obj.isoformat()
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

def analyze_backtest_results(symbol: str, results: Dict[str, Any]) -> Dict[str, Any]:
    logger.info(f"Starting backtest analysis for {symbol}")
    try:
        # Use the custom serializer when dumping results for the prompt
        results_json_string = json.dumps(results, indent=2, default=default_serializer)

        prompt = f"""
        Analyze the following backtesting results for {symbol} and provide detailed insights:

        {results_json_string}

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
            model=MODEL_NAME, # Can use a more powerful model for analysis if needed
            temperature=0.2,
            response_format=FORMAT
        )

        # The LLM response should already be JSON, no need for default_serializer here
        analysis_result = json.loads(completion.choices[0].message.content)
        logger.info(f"Successfully analyzed backtest results for {symbol}")
        logger.debug(f"Analysis result: {json.dumps(analysis_result, indent=2)}") # Standard dump is fine here
        return analysis_result

    except Exception as e:
        logger.error(f"Error analyzing backtest results for {symbol}: {str(e)}", exc_info=True)
        return {
            "error": True,
            "message": f"Analysis failed: {str(e)}"
        }

# --- Existing Function: Generate Strategy Code (Unchanged) ---
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
            start_date=datetime.now() - timedelta(days=365*2), # Fetch more data for backtest
            end_date=datetime.now(),
            interval="1d" # Ensure interval matches backtesting needs
        )

        # Format prompt
        profile_prompt = get_prompt_for_backtesting(
            company_dashboard,
            company_announcement,
            company_news,
            company_basic_technical_indicators
        )

        chat_model = get_model(model_provider=MODEL_PROVIDER)
        # Use a potentially more capable model for generation if flash struggles
        generation_model_name = "gemini-2.0-flash" if MODEL_PROVIDER == "GEMINI" else MODEL_NAME
        logger.info(f"Using model {generation_model_name} for strategy generation.")

        chat_completion = chat_model.chat.completions.create(
            messages=[
                {"role": "system", "content": backtesting_strategy_system_prompt},
                {"role": "user", "content": profile_prompt}
            ],
            model=generation_model_name,
            temperature=0.2, # Slightly higher temp for potentially more diverse strategies
            response_format=FORMAT
        )

        response_content = json.loads(chat_completion.choices[0].message.content)

        # Validate response structure
        if not isinstance(response_content, list):
             logger.error(f"LLM response is not a list: {response_content}")
             raise ValueError("LLM response for strategy generation was not a list as expected.")
        if not all(isinstance(item, dict) and "strategy_code" in item and "strategy_name" in item for item in response_content):
             logger.error(f"LLM response items lack required keys ('strategy_code', 'strategy_name'): {response_content}")
             raise ValueError("LLM response items lack required keys.")


        logger.info(f"Successfully generated {len(response_content)} strategy structures for {symbol}")
        # print(response_content) # Keep for debugging if needed
        return response_content

    except Exception as e:
        logger.error(f"Error generating strategy code for {symbol}: {str(e)}", exc_info=True)
        return {
            "error": True,
            "message": f"Strategy generation failed: {str(e)}"
        }

# --- Modified Function: Backtesting Agent ---
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
            # Return the error structure from generate_strategy_code
            return strategy_response

        if not isinstance(strategy_response, list) or not strategy_response:
             logger.error(f"Strategy generation returned empty or invalid result for {symbol}.")
             return {
                 "error": True,
                 "symbol": symbol,
                 "message": "Strategy generation returned no valid strategies."
             }

        logger.info(f"Successfully generated {len(strategy_response)} potential strategies for {symbol}")

        # Test all strategies with debugging loop
        all_results = []
        for i, strategy_details in enumerate(strategy_response, 1):
            logger.info(f"--- Processing Strategy {i} of {len(strategy_response)}: {strategy_details.get('strategy_name', 'Unnamed Strategy')} ---")

            current_strategy_code = strategy_details.get("strategy_code")
            strategy_name = strategy_details.get("strategy_name", f"Strategy_{i}")
            original_strategy_code = current_strategy_code # Keep original for reference

            if not current_strategy_code or not isinstance(current_strategy_code, str):
                logger.error(f"Strategy {i} has missing or invalid 'strategy_code'. Skipping.")
                all_results.append({
                    "strategy_number": i,
                    "strategy_name": strategy_name,
                    "status": "skipped",
                    "reason": "Missing or invalid strategy code from generation.",
                    "backtest_parameters": None,
                    "backtest_results": None,
                    "analysis": None
                })
                continue

            # --- Debugging Loop ---
            backtest_successful = False
            last_error = None
            backtest_results: Optional[BacktestResult] = None
            final_params_dump = None # To store params used for successful backtest

            for attempt in range(MAX_DEBUG_ATTEMPTS + 1): # +1 to allow initial try
                if attempt > 0: # This means the previous attempt failed
                    logger.info(f"Retrying strategy {i} - Attempt {attempt}/{MAX_DEBUG_ATTEMPTS}")
                    fixed_code = debug_strategy_code(current_strategy_code, str(last_error), symbol)
                    if fixed_code:
                        current_strategy_code = fixed_code
                    else:
                        logger.error(f"Debugging failed to produce new code for strategy {i} on attempt {attempt}. Stopping debug attempts.")
                        break # Stop debugging if LLM fails to provide a fix

                try:
                    # Determine dates - Use provided or default
                    try:
                        start_date_str = strategy_details.get("start_date", (datetime.now() - timedelta(days=365*2)).strftime("%Y-%m-%d"))
                        end_date_str = strategy_details.get("end_date", datetime.now().strftime("%Y-%m-%d"))
                        start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
                        end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
                        # Basic date validation
                        if start_date >= end_date:
                            logger.warning(f"Start date ({start_date_str}) is not before end date ({end_date_str}). Using default dates.")
                            start_date = datetime.now() - timedelta(days=365*2)
                            end_date = datetime.now()
                            start_date_str = start_date.strftime("%Y-%m-%d")
                            end_date_str = end_date.strftime("%Y-%m-%d")

                    except ValueError as date_err:
                        logger.warning(f"Invalid date format in strategy details: {date_err}. Using default dates.")
                        start_date = datetime.now() - timedelta(days=365*2)
                        end_date = datetime.now()
                        start_date_str = start_date.strftime("%Y-%m-%d")
                        end_date_str = end_date.strftime("%Y-%m-%d")

                    logger.debug(f"Backtesting strategy {i} (Attempt {attempt}) with dates {start_date_str} to {end_date_str}")

                    params = BacktestParameters(
                        symbol=symbol,
                        strategy_code=current_strategy_code, # Use potentially fixed code
                        start_date=start_date_str,
                        end_date=end_date_str,
                        # Make SL/TP potentially configurable or part of strategy generation?
                        stop_loss=strategy_details.get("stop_loss", 0.05),
                        take_profit=strategy_details.get("take_profit", 0.10),
                        cash=strategy_details.get("initial_cash", 100000),
                        commission=strategy_details.get("commission", 0.001)
                    )
                    final_params_dump = params.model_dump() # Store params used in this attempt

                    # Execute backtesting
                    logger.debug(f"Executing backtest for strategy {i}, attempt {attempt}")
                    backtest_results_obj = execute_backtesting(params) # Expects this to raise Exception on failure

                    # If execute_backtesting completes without error:
                    backtest_results = backtest_results_obj.model_dump()
                    backtest_successful = True
                    logger.info(f"Strategy {i} backtest successful on attempt {attempt}.")
                    break # Exit the debugging loop on success

                except Exception as e:
                    last_error = e
                    error_traceback = traceback.format_exc()
                    logger.warning(f"Backtest execution failed for strategy {i} on attempt {attempt}: {str(e)}")
                    logger.debug(f"Traceback:\n{error_traceback}") # Log full traceback for debugging
                    if attempt >= MAX_DEBUG_ATTEMPTS:
                        logger.error(f"Strategy {i} failed after {MAX_DEBUG_ATTEMPTS} debug attempts. Scraping strategy.")
                        break # Exit loop after max attempts

            # --- End Debugging Loop ---

            # Process results based on success or failure
            if backtest_successful and backtest_results:
                # Analyze results
                logger.debug(f"Analyzing results for strategy {i}")
                analysis = analyze_backtest_results(symbol, backtest_results)

                strategy_result = {
                    "strategy_number": i,
                    "strategy_name": strategy_name,
                    "status": "success",
                    "debug_attempts_used": attempt, # How many retries were needed (0 if first try worked)
                    "original_strategy_code": original_strategy_code,
                    "final_strategy_code": current_strategy_code if current_strategy_code != original_strategy_code else "Original code used",
                    "backtest_parameters": final_params_dump,
                    "backtest_results": backtest_results,
                    "analysis": analysis
                }
                all_results.append(strategy_result)
            else:
                # Strategy failed even after debugging attempts
                 all_results.append({
                    "strategy_number": i,
                    "strategy_name": strategy_name,
                    "status": "failed",
                    "reason": f"Execution failed after {attempt} attempts.",
                    "last_error": str(last_error),
                    "original_strategy_code": original_strategy_code,
                    "backtest_parameters": final_params_dump, # Params from the last failed attempt
                    "backtest_results": None,
                    "analysis": None
                })

        # Compile final results
        final_results = {
            "symbol": symbol,
            "strategies": all_results,
            "run_datetime": datetime.now().isoformat()
        }

        logger.info(f"Successfully completed backtesting process for {symbol} "
                   f"with {len(all_results)} strategies processed.")
        # logger.debug(f"Final results: {json.dumps(final_results, indent=2)}") # Can be very verbose
        return final_results

    except Exception as e:
        error_msg = f"Backtesting agent failed for {symbol}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "error": True,
            "symbol": symbol,
            "message": error_msg
        }

# --- Main Execution Block (Unchanged) ---
if __name__ == "__main__":
    # Example run:
    results = backtesting_agent("RELIANCE", exchange="nse")
    print(json.dumps(results, indent=2, default=default_serializer))

    # Example with a symbol likely to have less data/potentially cause issues
    # results_small_cap = backtesting_agent("SUZLON", exchange="nse")
    # print(json.dumps(results_small_cap, indent=2))