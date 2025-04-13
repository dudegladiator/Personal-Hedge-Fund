import json
import statistics
from typing import Any, Dict, TypedDict, Optional, Tuple
from src.data_source.market_apis import get_overall_fundamental_data
from src.llm.models import get_model
from langgraph.types import Command
from langgraph.graph import StateGraph, START, END
from utils.app_logger import setup_logger
from src.prompts import fundamental_agent_system_prompt
import math

from utils.llm import parse_fundamental_response

logger = setup_logger("src/agents/fundamental_agent.py")

MODEL_PROVIDER = "GEMINI"
MODEL_NAME = "gemini-2.0-flash"
FORMAT = { "type": "json_object" } # json_object # text

class FinancialAnalysisState(TypedDict):
    fundamental_data: Dict[str, Any]  # Input financial data
    lynch_growth: Optional[Dict[str, Any]]  # Results from lynch growth analysis
    lynch_fundamentals: Optional[Dict[str, Any]]  # Results from lynch fundamental analysis
    lynch_valuation: Optional[Dict[str, Any]]  # Results from lynch valuation analysis
    analysis_complete: bool  # Flag to indicate all analyses are complete
    error_message: Optional[str] # To capture errors during processing

def calculate_z_score_and_points(value: Optional[float], mean: float, std_dev: float, score_type: str) -> Tuple[Optional[float], int]:
    """
    Calculates Z-score and assigns points based on score type.

    Args:
        value: The calculated metric value.
        mean: The target mean for the metric.
        std_dev: The target standard deviation for the metric.
        score_type: 'range', 'higher', or 'lower'.

    Returns:
        A tuple containing the Z-score (or None) and the points (0, 1, or 2).
    """
    if value is None or not isinstance(value, (int, float)) or math.isnan(value) or math.isinf(value) or std_dev == 0:
        return None, 0 # Cannot calculate Z-score or assign points

    z_score = (value - mean) / std_dev

    points = 0
    if score_type == 'range':
        # Closer to the mean (Z=0) is better
        if abs(z_score) <= 0.75: # Within ~0.75 SD
            points = 2
        elif abs(z_score) <= 1.5: # Within ~1.5 SD
            points = 1
        else:
            points = 0
    elif score_type == 'higher':
        # Significantly higher than the mean is better
        if z_score >= 0.5: # >= 0.5 SD above mean
            points = 2
        elif z_score > -0.5: # Between -0.5 and 0.5 SD
            points = 1
        else: # < -0.5 SD below mean
            points = 0
    elif score_type == 'lower':
        # Significantly lower than the mean is better
        if z_score <= -0.5: # <= 0.5 SD below mean
            points = 2
        elif z_score < 0.5: # Between -0.5 and 0.5 SD
            points = 1
        else: # >= 0.5 SD above mean
            points = 0

    return round(z_score, 2), points

def lynch_growth(fundamental_data: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluates growth metrics using Z-scores, calculates confidence level, and classifies growth health."""
    results: Dict[str, Any] = {"Parameters": {}, "Confidence Level (%)": 0, "Signal": "Error", "Z-Scores": {}, "Points": {}}
    
    try:
        data = fundamental_data
        profit_loss = data.get("profit_loss", {}).get("periods")
        
        if not profit_loss:
            raise ValueError("Missing balance_sheet or profit_loss data")

        # --- Extract Growth Metrics ---
        revenues = [fi.get("net_sales") for fi in profit_loss.values() if fi.get("net_sales") is not None]
        eps_values = [fi.get("earnings_per_share_(rs.)") for fi in profit_loss.values() if fi.get("earnings_per_share") is not None]

        # Calculate growth rates
        rev_growth = (revenues[0] - revenues[-1]) / abs(revenues[-1]) if len(revenues) >= 2 and revenues[-1] != 0 else None
        eps_growth = (eps_values[0] - eps_values[-1]) / abs(eps_values[-1]) if len(eps_values) >= 2 and eps_values[-1] != 0 else None

        values = {
            "Revenue Growth (%)": round(rev_growth * 100, 2) if rev_growth is not None else None,
            "EPS Growth (%)": round(eps_growth * 100, 2) if eps_growth is not None else None
        }
        results["Parameters"] = {k: v if v is not None else "N/A" for k, v in values.items()}

        # --- Z-Score Parameters ---
        z_score_params = {
            "Revenue Growth (%)": {"mean": 15.0, "std_dev": 5.0, "type": "higher"},
            "EPS Growth (%)": {"mean": 12.0, "std_dev": 4.0, "type": "higher"}
        }

        # --- Scoring System ---
        total_points = 0
        max_points = 0
        z_scores = {}
        points_dict = {}

        for key, params in z_score_params.items():
            value = values.get(key)
            z_score, points = calculate_z_score_and_points(
                value, 
                params["mean"], 
                params["std_dev"], 
                params["type"]
            )
            total_points += points
            max_points += 2  # Max 2 points per metric
            z_scores[key] = z_score if z_score is not None else "N/A"
            points_dict[key] = points

        results["Z-Scores"] = z_scores
        results["Points"] = points_dict

        # --- Calculate Confidence Level & Signal ---
        confidence_level = round((total_points / max_points) * 100, 2) if max_points > 0 else 0
        results["Confidence Level (%)"] = confidence_level

        if confidence_level >= 75:
            signal = "BULLISH"
        elif confidence_level >= 45:
            signal = "NEUTRAL"
        else:
            signal = "BEARISH"
        results["Signal"] = signal

    except Exception as e:
        logger.error(f"Error analyzing Lynch growth metrics: {e}", exc_info=True)
        results["Signal"] = f"Error: {e}"

    return results

def lynch_fundamentals(fundamental_data: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluates fundamental health using Z-scores, calculates confidence level, and classifies financial strength."""
    results: Dict[str, Any] = {"Parameters": {}, "Confidence Level (%)": 0, "Signal": "Error", "Z-Scores": {}, "Points": {}}
    
    try:
        data = fundamental_data
        cash_flow = data.get("cash_flow", {}).get("periods")
        stock_quality = data.get("stock_quality", {}).get("quality_ratios", {})
        profit_loss_periods = data.get("profit_loss", {}).get("periods")
        
        if not profit_loss_periods or not cash_flow or not stock_quality:
             raise ValueError("Missing profit_loss, cash_flow, or stock_quality data")

        # Extract latest financial data
        latest_pl_key = sorted(profit_loss_periods.keys())[-1]
        latest_pl = profit_loss_periods[latest_pl_key]

        # --- Extract Values ---
        net_sales = latest_pl.get("net_sales")
        # Use Operating Profit PBDIT as proxy for EBITDA
        operating_margin = latest_pl.get("operating_profit_margin_(excl_oi)")
        
        # --- Calculate Fundamental Metrics ---
        de_ratio = stock_quality.get("net_debt_to_equity_avg")
        
        ocf_field = 'net_cash_from_operating_activities'
        ocf_list = [p.get(ocf_field) for p in cash_flow.values() if p.get(ocf_field) is not None]

        fcf_latest = ocf_list[0] if ocf_list else None
        fcf_margin = (fcf_latest / net_sales) * 100 if net_sales else None

        values = {
            "Debt-to-Equity": round(de_ratio, 2),
            "Operating Margin (%)": round(operating_margin, 2) if operating_margin is not None else None,
            "FCF Margin (%)": round(fcf_margin, 2) if fcf_margin is not None else None
        }
        results["Parameters"] = {k: v if v is not None else "N/A" for k, v in values.items()}

        # --- Z-Score Parameters ---
        z_score_params = {
            "Debt-to-Equity": {"mean": 0.5, "std_dev": 0.25, "type": "lower"},
            "Operating Margin (%)": {"mean": 15.0, "std_dev": 5.0, "type": "higher"},
            "FCF Margin (%)": {"mean": 10.0, "std_dev": 4.0, "type": "higher"}
        }

        # --- Scoring System ---
        total_points = 0
        max_points = 0
        z_scores = {}
        points_dict = {}

        for key, params in z_score_params.items():
            value = values.get(key)
            z_score, points = calculate_z_score_and_points(
                value, 
                params["mean"], 
                params["std_dev"], 
                params["type"]
            )
            total_points += points
            max_points += 2  # Max 2 points per metric
            z_scores[key] = z_score if z_score is not None else "N/A"
            points_dict[key] = points

        results["Z-Scores"] = z_scores
        results["Points"] = points_dict

        # --- Calculate Confidence Level & Signal ---
        confidence_level = round((total_points / max_points) * 100, 2) if max_points > 0 else 0
        results["Confidence Level (%)"] = confidence_level

        if confidence_level >= 75:
            signal = "BULLISH"
        elif confidence_level >= 45:
            signal = "NEUTRAL"
        else:
            signal = "BEARISH"
        results["Signal"] = signal

    except Exception as e:
        logger.error(f"Error analyzing Lynch fundamentals: {e}", exc_info=True)
        results["Signal"] = f"Error: {e}"

    return results

def lynch_valuation(fundamental_data: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluates valuation health using Z-scores, calculates confidence level, and classifies value attractiveness."""
    results: Dict[str, Any] = {"Parameters": {}, "Confidence Level (%)": 0, "Signal": "Error", "Z-Scores": {}, "Points": {}}
    
    try:
        data = fundamental_data
        cash_flow = data.get("cash_flow", {}).get("periods")
        stock_quality = data.get("stock_quality", {}).get("valuation_ratios", {})
        profit_loss_periods = data.get("profit_loss", {}).get("periods")
        
        if not profit_loss_periods or not cash_flow or not stock_quality:
             raise ValueError("Missing profit_loss, cash_flow, or stock_quality data")

        # Extract latest financial data
        latest_pl_key = sorted(profit_loss_periods.keys())[-1]
        latest_pl = profit_loss_periods[latest_pl_key]     

        # --- Extract Valuation Metrics ---
        net_income = latest_pl.get("net_profit")
        eps_values = [fi.get("earnings_per_share_(rs.)") for fi in profit_loss_periods.values() if fi.get("earnings_per_share") is not None]
        
        # Calculate P/E Ratio
        pe_ratio = stock_quality.get("pe_ratio")
        
        # Calculate EPS Growth Rate
        eps_growth = None
        if len(eps_values) >= 2 and eps_values[-1] > 0:
            eps_growth = (eps_values[0] - eps_values[-1]) / eps_values[-1]
            
        # Calculate PEG Ratio
        peg_ratio = stock_quality.get("peg_ratio")

        values = {
            "P/E Ratio": round(pe_ratio, 2) if pe_ratio else None,
            "PEG Ratio": round(peg_ratio, 2) if peg_ratio else None,
            "EPS Growth (%)": round(eps_growth * 100, 2) if eps_growth else None
        }
        results["Parameters"] = {k: v if v is not None else "N/A" for k, v in values.items()}

        # --- Z-Score Parameters ---
        z_score_params = {
            "P/E Ratio": {"mean": 15.0, "std_dev": 5.0, "type": "lower"},
            "PEG Ratio": {"mean": 1.0, "std_dev": 0.5, "type": "lower"}
        }

        # --- Scoring System ---
        total_points = 0
        max_points = 0
        z_scores = {}
        points_dict = {}

        for key, params in z_score_params.items():
            value = values.get(key)
            z_score, points = calculate_z_score_and_points(
                value, 
                params["mean"], 
                params["std_dev"], 
                params["type"]
            )
            total_points += points
            max_points += 2  # Max 2 points per metric
            z_scores[key] = z_score if z_score is not None else "N/A"
            points_dict[key] = points

        results["Z-Scores"] = z_scores
        results["Points"] = points_dict

        # --- Calculate Confidence Level & Signal ---
        confidence_level = round((total_points / max_points) * 100, 2) if max_points > 0 else 0
        results["Confidence Level (%)"] = confidence_level

        if confidence_level >= 75:
            signal = "BULLISH"
        elif confidence_level >= 45:
            signal = "NEUTRAL"
        else:
            signal = "BEARISH"
        results["Signal"] = signal

    except Exception as e:
        logger.error(f"Error analyzing Lynch valuation: {e}", exc_info=True)
        results["Signal"] = f"Error: {e}"

    return results

def analyze_lynch_valuation(state: FinancialAnalysisState) -> dict:
    """Node to compute Lynch valuation metrics"""
    logger.info("Analyzing Lynch Valuation...")
    result = lynch_valuation(state["fundamental_data"])
    
    if "Error" in result.get("Signal", ""):
        return {"error_message": f"Lynch Valuation Error: {result.get('Signal')}"}
    
    return {"lynch_valuation": result}
def analyze_lynch_growth(state: FinancialAnalysisState) -> dict:
    """Node to compute Lynch Growth metrics"""
    logger.info("Analyzing Lynch Growth...")
    result = lynch_growth(state["fundamental_data"])
    
    if "Error" in result.get("Signal", ""):
        return {"error_message": f"Lynch Growth Error: {result.get('Signal')}"}
    
    return {"lynch_growth": result}
def analyze_lynch_fundamentals(state: FinancialAnalysisState) -> dict:
    """Node to compute Lynch Fundamental metrics"""
    logger.info("Analyzing Lynch Fundamentals...")
    result = lynch_fundamentals(state["fundamental_data"])
    
    if "Error" in result.get("Signal", ""):
        return {"error_message": f"Lynch Fundamental Error: {result.get('Signal')}"}
    
    return {"lynch_fundamental": result}

def mark_analysis_complete(state: FinancialAnalysisState) -> dict:
    """Node to mark analysis as complete"""
    logger.info("Marking analysis as complete.")
    return {"analysis_complete": True}

# --- Graph Definition ---

def create_financial_analysis_subgraph() -> StateGraph:
    """Creates a subgraph for financial analysis"""
    builder = StateGraph(FinancialAnalysisState)

    # Add nodes
    builder.add_node("analyze_lynch_growth", analyze_lynch_growth)
    builder.add_node("analyze_lynch_fundamentals", analyze_lynch_fundamentals)
    builder.add_node("analyze_lynch_valuation", analyze_lynch_valuation)
    builder.add_node("mark_complete", mark_analysis_complete)

    # Define edges
    builder.add_edge(START, "analyze_lynch_growth")
    builder.add_edge("analyze_lynch_growth", "analyze_lynch_fundamentals")
    builder.add_edge("analyze_lynch_fundamentals", "analyze_lynch_valuation")
    builder.add_edge("analyze_lynch_valuation", "mark_complete")
    builder.add_edge("mark_complete", END) # Explicitly end the graph

    # Compile the graph
    # Note: 'name' argument is deprecated or removed in recent versions.
    # If you encounter issues, remove the name argument.
    try:
        return builder.compile()
    except TypeError:
         logger.warning("Graph name argument might be deprecated. Compiling without name.")
         return builder.compile()

def run_financial_analysis(symbol: str, fundamental_data: Dict[str, Any]) -> Dict[str, Any]:
    """Run the financial analysis subgraph with the provided data"""
    logger.info(f"Starting financial analysis run for {symbol}...")
    financial_analysis_graph = create_financial_analysis_subgraph()

    config = {
        "recursion_limit": 10, # Add recursion limit
        "tags": ["fundamental_analysis", "fundamental_ratios"],
        "metadata": {"company": symbol, "file": "src/agents/peter_lynch.py"}
    }

    # Define initial state
    initial_state: FinancialAnalysisState = {
        "fundamental_data": fundamental_data,
        "lynch_growth": None,
        "lynch_fundamentals": None,
        "lynch_valuation": None,
        "analysis_complete": False,
        "error_message": None
    }

    try:
        # Stream events to see the flow
        # print("\n--- Graph Execution Stream ---")
        # for event in financial_analysis_graph.stream(initial_state, config=config):
        #     # print(event)
        #     pass # Process events if needed
        # print("--- End Graph Execution Stream ---\n")

        # Or just invoke to get the final state
        final_state = financial_analysis_graph.invoke(initial_state, config=config)
        logger.info(f"Financial analysis run completed for {symbol}.")

        if final_state.get("error_message"):
             logger.error(f"Error during analysis for {symbol}: {final_state['error_message']}")
             return {"error": final_state['error_message']}


        # Return the complete analysis results
        return {
            "lynch_growth": final_state.get("lynch_growth"),
            "lynch_fundamentals": final_state.get("lynch_fundamentals"),
            "lynch_valuation": final_state.get("lynch_valuation"),
        }
    except Exception as e:
        logger.error(f"Error invoking financial analysis graph for {symbol}: {e}", exc_info=True)
        return {"error": f"Failed to run analysis graph: {str(e)}"}


def peter_lynch_agent(symbol: str, exchange: str = "nse", force: bool = False, refresh_days: int = 7) -> str:
    """
    Creates a financial analysis agent using LangGraph subgraph, Z-scores, and LLM summarization.

    Args:
        symbol: Stock symbol to analyze.
        exchange: Stock exchange.
        force: Force refresh of data.
        refresh_days: Refresh data if older than this many days.

    Returns:
        JSON string containing the analysis report from the LLM or an error message.
    """
    logger.info(f"Starting fundamental agent for {symbol} on {exchange}...")
    # Get fundamental data from database
    fundamental_data = get_overall_fundamental_data(symbol=symbol, exchange=exchange, force=force, refresh_days=refresh_days)

    if not fundamental_data:
        logger.error(f"No fundamental data found for symbol: {symbol}")
        return json.dumps({"error": f"No fundamental data found for symbol: {symbol}"})

    # Run the financial analysis subgraph
    analysis_results = run_financial_analysis(symbol, fundamental_data)

    if "error" in analysis_results:
         # Error already logged in run_financial_analysis
         return json.dumps(analysis_results) # Return the error dict as JSON

    # Filter out None values before sending to LLM for cleaner prompt
    filtered_results = {k: v for k, v in analysis_results.items() if v is not None}

    if not filtered_results:
        logger.error(f"Analysis yielded no results for {symbol}")
        return json.dumps({"error": f"Analysis yielded no results for {symbol}"})


    # Prepare messages for LLM
    messages = [
        {
            "role": "system",
            "content": fundamental_agent_system_prompt # Ensure this prompt asks for JSON output
        },
        {
            "role": "user",
            "content": f"Please perform a comprehensive fundamental analysis for {symbol} based on the following calculated metrics (including parameters, Z-scores relative to typical ranges, points awarded [0-2], confidence levels, and signals). Provide a summary of the company's financial health across operating efficiency, profitability, leverage, and stability. Conclude with an overall investment recommendation (e.g., BULLISH, BEARISH, NEUTRAL) and rationale. Ensure the final output is a single JSON object.\n\nAnalysis Metrics:\n{json.dumps(filtered_results, indent=2)}"
        }
    ]

    try:
        logger.info(f"Sending analysis results for {symbol} to LLM ({MODEL_PROVIDER} - {MODEL_NAME})...")
        chat_model = get_model(model_provider=MODEL_PROVIDER)
        response = chat_model.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=0.5, # Slightly lower temp for more factual summary
            response_format=FORMAT # Request JSON output
        )
        logger.info(f"Received LLM response for {symbol}.")

        # Attempt to parse the LLM output to ensure it's valid JSON
        analyse = parse_fundamental_response(response.choices[0].message.content)
        return analyse

    except Exception as e:
        logger.error(f"Error interacting with LLM for {symbol}: {str(e)}", exc_info=True)
        return {"error": f"An error occurred during LLM interaction: {str(e)}"}

if __name__ == "__main__":
    # Use a common symbol for testing, ensure you have data for it
    # or that get_overall_fundamental_data can fetch it.
    symbol_to_test = "RELIANCE"
    print(f"--- Running Fundamental Agent for {symbol_to_test} ---")
    analysis_report_json = peter_lynch_agent(symbol_to_test, exchange="nse", force=True, refresh_days=30) # Increase refresh days for testing
    print(analysis_report_json)