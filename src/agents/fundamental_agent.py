import json
import statistics
from typing import Any, Dict, TypedDict, Optional, Tuple
from src.data_source.market_apis import get_overall_fundamental_data
from src.llm.models import get_model
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
    operating_ratios: Optional[Dict[str, Any]]  # Results from operating ratios analysis
    profitability_ratios: Optional[Dict[str, Any]]  # Results from profitability analysis
    leverage_ratios: Optional[Dict[str, Any]]  # Results from leverage analysis
    stability_metrics: Optional[Dict[str, Any]]  # Results from stability analysis
    analysis_complete: bool  # Flag to indicate all analyses are complete
    error_message: Optional[str] # To capture errors during processing

# --- Z-Score Helper Function ---
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

def compute_operating_ratios(fundamental_data: Dict[str, Any]) -> Dict[str, Any]:
    """Computes operating ratios, assigns scores using Z-score, calculates confidence level, and classifies financial health."""
    results: Dict[str, Any] = {"Parameters": {}, "Confidence Level (%)": 0, "Signal": "Error", "Z-Scores": {}, "Points": {}}
    try:
        data = fundamental_data
        balance_sheet = data.get("balance_sheet", {}).get("periods")
        profit_loss = data.get("profit_loss", {}).get("periods")

        if not balance_sheet or not profit_loss:
            raise ValueError("Missing balance_sheet or profit_loss data")

        # --- Calculate Averages ---
        total_assets_list = [p.get("total_assets") for p in balance_sheet.values() if p.get("total_assets") is not None]
        net_fixed_assets_list = [(p.get("total_assets", 0) - p.get("total_current_assets", 0)) for p in balance_sheet.values() if p.get("total_assets") is not None and p.get("total_current_assets") is not None]
        working_capital_list = [(p.get("total_current_assets", 0) - p.get("total_current_liabilities", 0)) for p in balance_sheet.values() if p.get("total_current_assets") is not None and p.get("total_current_liabilities") is not None]
        inventory_list = [p.get("inventories") for p in balance_sheet.values() if p.get("inventories") is not None]

        avg_total_assets = statistics.mean(total_assets_list) if total_assets_list else 0
        avg_net_fixed_assets = statistics.mean(net_fixed_assets_list) if net_fixed_assets_list else 0
        avg_working_capital = statistics.mean(working_capital_list) if working_capital_list else 0
        avg_inventory = statistics.mean(inventory_list) if inventory_list else 0

        # --- Extract Latest Period Values ---
        latest_pl_period_key = sorted(profit_loss.keys())[-1]
        latest_pl = profit_loss[latest_pl_period_key]

        net_sales = latest_pl.get("net_sales")
        # COGS Proxy: Sum of material, power, employee costs
        cogs_proxy = latest_pl.get("raw_materials_consumed", 0) + latest_pl.get("power_&_fuel_cost", 0) + latest_pl.get("employee_cost", 0)

        # --- Calculate Ratios ---
        # Corrected: Net Sales / Avg Net Fixed Assets
        fixed_asset_turnover = net_sales / avg_net_fixed_assets if avg_net_fixed_assets and net_sales is not None else None
        # Correct: Net Sales / Avg Working Capital
        working_capital_turnover = net_sales / avg_working_capital if avg_working_capital and net_sales is not None else None
        # Corrected: Net Sales / Avg Total Assets
        total_asset_turnover = net_sales / avg_total_assets if avg_total_assets and net_sales is not None else None
        # Using COGS Proxy / Avg Inventory
        inventory_turnover = cogs_proxy / avg_inventory if avg_inventory and cogs_proxy is not None else None

        values = {
            "Fixed Asset Turnover": round(fixed_asset_turnover, 2) if fixed_asset_turnover is not None else None,
            "Working Capital Turnover": round(working_capital_turnover, 2) if working_capital_turnover is not None else None,
            "Total Asset Turnover": round(total_asset_turnover, 2) if total_asset_turnover is not None else None,
            "Inventory Turnover (COGS Proxy)": round(inventory_turnover, 2) if inventory_turnover is not None else None
        }
        results["Parameters"] = {k: v if v is not None else "N/A" for k, v in values.items()}

        # --- Z-Score Parameters (Mean, Std Dev, Type) ---
        # Type: 'range', 'higher', 'lower'
        # Mean: Midpoint of typical healthy range
        # Std Dev: Half the width of the typical healthy range (adjust as needed)
        z_score_params = {
            "Fixed Asset Turnover": {"mean": 2.25, "std_dev": 0.75, "type": "higher"}, # e.g., Ideal > 1.5-3.0
            "Working Capital Turnover": {"mean": 6.0, "std_dev": 2.0, "type": "higher"}, # e.g., Ideal > 4-8
            "Total Asset Turnover": {"mean": 1.0, "std_dev": 0.5, "type": "higher"}, # e.g., Ideal > 0.5-1.5 (Varies greatly by industry)
            "Inventory Turnover (COGS Proxy)": {"mean": 5.0, "std_dev": 2.0, "type": "higher"} # e.g., Ideal > 3-7
        }

        # --- Scoring System ---
        total_points = 0
        max_points = 0
        z_scores = {}
        points_dict = {}

        for key, params in z_score_params.items():
            value = values.get(key)
            z_score, points = calculate_z_score_and_points(value, params["mean"], params["std_dev"], params["type"])
            total_points += points
            max_points += 2 # Max 2 points per metric
            z_scores[key] = z_score if z_score is not None else "N/A"
            points_dict[key] = points

        results["Z-Scores"] = z_scores
        results["Points"] = points_dict

        # --- Calculate Confidence Level & Signal ---
        confidence_level = round((total_points / max_points) * 100, 2) if max_points > 0 else 0
        results["Confidence Level (%)"] = confidence_level

        if confidence_level >= 75: # Adjusted threshold for Z-score
            signal = "BULLISH"
        elif confidence_level >= 45: # Adjusted threshold
            signal = "NEUTRAL"
        else:
            signal = "BEARISH"
        results["Signal"] = signal

    except Exception as e:
        logger.error(f"Error computing operating ratios: {e}", exc_info=True)
        results["Signal"] = f"Error: {e}"

    return results

def calculate_profitability_ratios(fundamental_data: Dict[str, Any]) -> Dict[str, Any]:
    """Calculates profitability ratios, assigns scores using Z-score, calculates confidence level, and classifies financial health."""
    results: Dict[str, Any] = {"Parameters": {}, "Confidence Level (%)": 0, "Signal": "Error", "Z-Scores": {}, "Points": {}}
    try:
        data = fundamental_data
        profit_loss_periods = data.get("profit_loss", {}).get("periods")
        yearly_periods = data.get("yearly", {}).get("periods")
        stock_quality = data.get("stock_quality", {}).get("quality_ratios", {})
        balance_sheet_periods = data.get("balance_sheet", {}).get("periods")

        if not profit_loss_periods or not yearly_periods or not balance_sheet_periods:
             raise ValueError("Missing profit_loss, yearly, or balance_sheet data")

        latest_pl_key = sorted(profit_loss_periods.keys())[-1]
        latest_pl = profit_loss_periods[latest_pl_key]
        latest_yearly_key = sorted(yearly_periods.keys())[-1]
        latest_yearly = yearly_periods[latest_yearly_key]

        # --- Calculate Averages ---
        total_assets_list = [p.get("total_assets") for p in balance_sheet_periods.values() if p.get("total_assets") is not None]
        avg_total_assets = statistics.mean(total_assets_list) if total_assets_list else 0

        # --- Extract Values ---
        net_sales = latest_pl.get("net_sales")
        # Use Operating Profit PBDIT as proxy for EBITDA
        operating_profit_pbdit = latest_pl.get("operating_profit_(pbdit)")
        profit_after_tax = latest_pl.get("profit_after_tax")
        interest = latest_pl.get("interest", 0) # Default interest to 0 if missing
        # Assuming a constant tax rate for ROA calculation if not directly available
        tax_rate = 0.25

        pat_margin = latest_yearly.get("pat_margin") # From yearly data
        roe_avg = stock_quality.get("roe_avg") # From stock quality data
        roce_avg = stock_quality.get("roce_avg") # From stock quality data

        # --- Calculate Metrics ---
        # Corrected: Use PBDIT / Net Sales for EBITDA Margin Proxy
        ebitda_margin = (operating_profit_pbdit / net_sales) * 100 if net_sales and operating_profit_pbdit is not None else None
        # ROA: (PAT + Interest * (1 - Tax Rate)) / Avg Total Assets
        roa = ((profit_after_tax + interest * (1 - tax_rate)) / avg_total_assets) * 100 if avg_total_assets and profit_after_tax is not None else None

        values = {
            "EBITDA Margin (%)": round(ebitda_margin, 2) if ebitda_margin is not None else None,
            "PAT Margin (%)": round(pat_margin, 2) if pat_margin is not None else None,
            "ROE Avg (%)": round(roe_avg, 2) if roe_avg is not None else None,
            "ROCE Avg (%)": round(roce_avg, 2) if roce_avg is not None else None,
            "ROA (%)": round(roa, 2) if roa is not None else None
        }
        results["Parameters"] = {k: v if v is not None else "N/A" for k, v in values.items()}

        # --- Z-Score Parameters ---
        z_score_params = {
            "EBITDA Margin (%)": {"mean": 20.0, "std_dev": 5.0, "type": "higher"}, # e.g., Ideal > 15-25%
            "PAT Margin (%)": {"mean": 10.0, "std_dev": 5.0, "type": "higher"},    # e.g., Ideal > 5-15%
            "ROE Avg (%)": {"mean": 16.0, "std_dev": 4.0, "type": "higher"},       # e.g., Ideal > 12-20%
            "ROCE Avg (%)": {"mean": 14.0, "std_dev": 4.0, "type": "higher"},      # e.g., Ideal > 10-18%
            "ROA (%)": {"mean": 7.5, "std_dev": 2.5, "type": "higher"}             # e.g., Ideal > 5-10%
        }

        # --- Scoring System ---
        total_points = 0
        max_points = 0
        z_scores = {}
        points_dict = {}

        for key, params in z_score_params.items():
            value = values.get(key)
            z_score, points = calculate_z_score_and_points(value, params["mean"], params["std_dev"], params["type"])
            total_points += points
            max_points += 2
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
        logger.error(f"Error calculating profitability ratios: {e}", exc_info=True)
        results["Signal"] = f"Error: {e}"

    return results

def compute_leverage_ratios(fundamental_data: Dict[str, Any]) -> Dict[str, Any]:
    """Computes leverage ratios, assigns scores using Z-score, calculates confidence level, and classifies financial health."""
    results: Dict[str, Any] = {"Parameters": {}, "Confidence Level (%)": 0, "Signal": "Error", "Z-Scores": {}, "Points": {}}
    try:
        data = fundamental_data
        balance_sheet = data.get("balance_sheet", {}).get("periods")
        profit_loss = data.get("profit_loss", {}).get("periods")
        stock_quality = data.get("stock_quality", {}).get("quality_ratios", {})

        if not balance_sheet or not profit_loss:
            raise ValueError("Missing balance_sheet or profit_loss data")

        latest_pl_key = sorted(profit_loss.keys())[-1]
        latest_pl = profit_loss[latest_pl_key]
        latest_bs_key = sorted(balance_sheet.keys())[-1]
        latest_bs = balance_sheet[latest_bs_key]

        # --- Extract Values ---
        pbdit = latest_pl.get("operating_profit_(pbdit)")
        depreciation = latest_pl.get("depreciation", 0)  # Default depreciation to 0 if missing
        interest = latest_pl.get("interest")
        # EBIT approximation
        ebit = pbdit - depreciation if pbdit is not None else None

        # Debt-to-Equity Ratio (using net debt from stock quality if available)
        debt_to_equity = stock_quality.get("net_debt_to_equity_avg")

        # Debt-to-Asset Ratio
        total_debt = latest_bs.get("total_debt")
        total_assets_latest = latest_bs.get("total_assets")

        # Financial Leverage Ratio (Average Total Assets / Average Total Equity)
        total_assets_list = [p.get("total_assets") for p in balance_sheet.values() if p.get("total_assets") is not None]
        # Use shareholder's_funds as proxy for total equity
        total_equity_list = [p.get("shareholder's_funds") for p in balance_sheet.values() if p.get("shareholder's_funds") is not None]

        avg_total_assets = statistics.mean(total_assets_list) if total_assets_list else 0
        avg_total_equity = statistics.mean(total_equity_list) if total_equity_list else 0

        # --- Calculate Ratios ---
        # Interest Coverage Ratio: EBIT / Interest
        interest_coverage_ratio = ebit / interest if interest and ebit is not None and interest != 0 else None
        # Debt-to-Asset Ratio: Total Debt / Total Assets (Latest)
        debt_to_asset_ratio = total_debt / total_assets_latest if total_assets_latest and total_debt is not None and total_assets_latest != 0 else None
        # Financial Leverage Ratio: Avg Total Assets / Avg Total Equity
        financial_leverage_ratio = avg_total_assets / avg_total_equity if avg_total_equity and avg_total_equity != 0 else None

        values = {
            "Interest Coverage Ratio": round(interest_coverage_ratio, 2) if interest_coverage_ratio is not None else None,
            "Net Debt-to-Equity Avg": debt_to_equity if debt_to_equity is not None else None,  # Renamed for clarity
            "Debt-to-Asset Ratio": round(debt_to_asset_ratio, 2) if debt_to_asset_ratio is not None else None,
            "Financial Leverage Ratio": round(financial_leverage_ratio, 2) if financial_leverage_ratio is not None else None
        }
        results["Parameters"] = {k: v if v is not None else "N/A" for k, v in values.items()}

        # --- Z-Score Parameters ---
        z_score_params = {
            "Interest Coverage Ratio": {"mean": 4.0, "std_dev": 1.0, "type": "higher"},
            "Net Debt-to-Equity Avg": {"mean": 1.0, "std_dev": 0.5, "type": "lower"},
            "Debt-to-Asset Ratio": {"mean": 0.45, "std_dev": 0.15, "type": "lower"},
            "Financial Leverage Ratio": {"mean": 2.0, "std_dev": 0.5, "type": "range"}
        }

        # --- Scoring System ---
        total_points = 0
        max_points = 0
        z_scores = {}
        points_dict = {}

        for key, params in z_score_params.items():
            value = values.get(key)
            z_score = None
            points = 0  # Default points to 0 if value is None or handling fails

            if value is not None:
                # Special handling for Net Debt-to-Equity Avg with negative value
                if key == "Net Debt-to-Equity Avg":
                    if isinstance(value, (int, float)) and value < 0:
                        points = 2
                        z_score = "Negative (Good)"
                    else:
                        z_score, points = calculate_z_score_and_points(value, params["mean"], params["std_dev"], params["type"])
                else:
                    z_score, points = calculate_z_score_and_points(value, params["mean"], params["std_dev"], params["type"])
            else:
                # Value is None, ensure points are 0 and Z-score is marked N/A
                z_score = "N/A"

            # Ensure points are valid integers (handle cases where calculate_z_score_and_points might return None)
            points = points if isinstance(points, (int, float)) else 0
            total_points += points
            max_points += 2

            z_scores[key] = z_score
            points_dict[key] = points

        results["Z-Scores"] = z_scores
        results["Points"] = points_dict

        # --- Calculate Confidence Level & Signal ---
        confidence_level = 0
        if max_points > 0:
            confidence_level = round((total_points / max_points) * 100, 2)
        results["Confidence Level (%)"] = confidence_level

        if confidence_level >= 75:
            signal = "BULLISH"
        elif confidence_level >= 45:
            signal = "NEUTRAL"
        else:
            signal = "BEARISH"
        results["Signal"] = signal

    except Exception as e:
        logger.error(f"Error computing leverage ratios: {e}", exc_info=True)
        results["Signal"] = f"Error: {e}"

    return results

def compute_company_stability(fundamental_data: Dict[str, Any]) -> Dict[str, Any]:
    """Computes company stability metrics, assigns scores using Z-score, calculates confidence level, and classifies stability."""
    results: Dict[str, Any] = {"Metrics": {}, "Confidence Level (%)": 0, "Signal": "Error", "Z-Scores": {}, "Points": {}}
    try:
        data = fundamental_data
        cash_flow = data.get("cash_flow", {}).get("periods")
        yearly_data = data.get("yearly", {}).get("periods")
        balance_sheet = data.get("balance_sheet", {}).get("periods")
        stock_quality = data.get("stock_quality", {}).get("quality_ratios", {})
        shareholding = data.get("shareholding_pattern", {}).get("periods")

        if not cash_flow or not yearly_data or not balance_sheet or not shareholding:
            raise ValueError("Missing cash_flow, yearly, balance_sheet, or shareholding data")

        # --- Extract Growth Metrics ---
        sales_growth_5y = stock_quality.get("sales_growth_5y")
        ebit_growth_5y = stock_quality.get("ebit_growth_5y")
        dividend_payout_ratio = stock_quality.get("dividend_payout_ratio") # Use latest or average? Using value from stock_quality

        # --- Calculate Stability Metrics ---
        metrics = {}
        metrics["Sales Growth 5Y (%)"] = sales_growth_5y
        metrics["EBIT Growth 5Y (%)"] = ebit_growth_5y
        metrics["Dividend Payout Ratio (%)"] = dividend_payout_ratio

        # 1. Cash Flow Stability (Positive Operating Cash Flow %)
        # *** IMPORTANT: Adjust 'net_cash_from_operating_activities' to the actual field name in your data ***
        ocf_field = 'net_cash_from_operating_activities'
        ocf_list = [p.get(ocf_field) for p in cash_flow.values() if p.get(ocf_field) is not None]
        if not ocf_list:
             logger.warning(f"OCF field '{ocf_field}' not found or empty in cash_flow data.")
             metrics["Cash Flow Stability (% Positive OCF)"] = None
        else:
            positive_ocf_count = sum(1 for ocf in ocf_list if ocf > 0)
            ocf_percentage = (positive_ocf_count / len(ocf_list)) * 100 if ocf_list else 0
            metrics["Cash Flow Stability (% Positive OCF)"] = round(ocf_percentage, 2)

        # Helper for calculating stability (Coefficient of Variation)
        def calculate_stability_metric(data_list: list) -> Optional[float]:
            if len(data_list) < 2: return None # Need at least 2 points for stdev
            try:
                mean = statistics.mean(data_list)
                if mean == 0: return 0.0 # Avoid division by zero if mean is 0
                std_dev = statistics.stdev(data_list)
                # Coefficient of Variation as %
                cv = abs(std_dev / mean) * 100
                return round(cv, 2)
            except statistics.StatisticsError:
                return None # Handle cases with insufficient data for stdev

        # 2. PAT Margin Stability (Lower CV is better)
        pat_margin_list = [p.get("pat_margin") for p in yearly_data.values() if p.get("pat_margin") is not None]
        metrics["PAT Margin Stability (CV %)"] = calculate_stability_metric(pat_margin_list)

        # 3. Debt Level Stability (Lower CV is better)
        debt_list = [p.get("total_debt") for p in balance_sheet.values() if p.get("total_debt") is not None]
        metrics["Debt Level Stability (CV %)"] = calculate_stability_metric(debt_list)

        # 4. Promoter Holding Stability (Lower CV is better)
        promoter_list = [p.get("Total Promoter") for p in shareholding.values() if p.get("Total Promoter") is not None]
        metrics["Promoter Holding Stability (CV %)"] = calculate_stability_metric(promoter_list)

        results["Metrics"] = {k: v if v is not None else "N/A" for k, v in metrics.items()}

        # --- Z-Score Parameters ---
        z_score_params = {
            "Sales Growth 5Y (%)": {"mean": 12.5, "std_dev": 5.0, "type": "higher"}, # Target > 10-15%
            "EBIT Growth 5Y (%)": {"mean": 15.0, "std_dev": 6.0, "type": "higher"},  # Target > 12-18%
            "PAT Margin Stability (CV %)": {"mean": 15.0, "std_dev": 10.0, "type": "lower"}, # Target CV < 10-20% (Lower is better)
            "Debt Level Stability (CV %)": {"mean": 20.0, "std_dev": 10.0, "type": "lower"}, # Target CV < 15-25% (Lower is better)
            "Dividend Payout Ratio (%)": {"mean": 30.0, "std_dev": 15.0, "type": "range"}, # Target 20-40%, allow wider range
            "Promoter Holding Stability (CV %)": {"mean": 2.5, "std_dev": 2.5, "type": "lower"}, # Target CV < 1-4% (Lower is better)
            "Cash Flow Stability (% Positive OCF)": {"mean": 85.0, "std_dev": 15.0, "type": "higher"} # Target > 80-90%
        }

        # --- Scoring System ---
        total_points = 0
        max_points = 0
        z_scores = {}
        points_dict = {}

        for key, params in z_score_params.items():
            value = metrics.get(key)
            z_score, points = calculate_z_score_and_points(value, params["mean"], params["std_dev"], params["type"])
            total_points += points
            max_points += 2
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
        logger.error(f"Error computing company stability: {e}", exc_info=True)
        results["Signal"] = f"Error: {e}"

    return results

# --- LangGraph Node Functions (Corrected State Update) ---

def analyze_operating_ratios(state: FinancialAnalysisState) -> dict:
    """Node to compute operating ratios"""
    logger.info("Analyzing Operating Ratios...")
    result = compute_operating_ratios(state["fundamental_data"])
    if "Error" in result.get("Signal", ""):
         return {"error_message": f"Operating Ratios Error: {result.get('Signal')}"}
    return {"operating_ratios": result}

def analyze_profitability_ratios(state: FinancialAnalysisState) -> dict:
    """Node to compute profitability ratios"""
    logger.info("Analyzing Profitability Ratios...")
    result = calculate_profitability_ratios(state["fundamental_data"])
    if "Error" in result.get("Signal", ""):
         return {"error_message": f"Profitability Ratios Error: {result.get('Signal')}"}
    return {"profitability_ratios": result}

def analyze_leverage_ratios(state: FinancialAnalysisState) -> dict:
    """Node to compute leverage ratios"""
    logger.info("Analyzing Leverage Ratios...")
    result = compute_leverage_ratios(state["fundamental_data"])
    if "Error" in result.get("Signal", ""):
         return {"error_message": f"Leverage Ratios Error: {result.get('Signal')}"}
    return {"leverage_ratios": result}

def analyze_stability(state: FinancialAnalysisState) -> dict:
    """Node to compute company stability metrics"""
    logger.info("Analyzing Company Stability...")
    result = compute_company_stability(state["fundamental_data"])
    if "Error" in result.get("Signal", ""):
         return {"error_message": f"Stability Metrics Error: {result.get('Signal')}"}
    return {"stability_metrics": result}

def mark_analysis_complete(state: FinancialAnalysisState) -> dict:
    """Node to mark analysis as complete"""
    logger.info("Marking analysis as complete.")
    return {"analysis_complete": True}

# --- Graph Definition ---

def create_financial_analysis_subgraph() -> StateGraph:
    """Creates a subgraph for financial analysis"""
    builder = StateGraph(FinancialAnalysisState)

    # Add nodes
    builder.add_node("analyze_operating_ratios", analyze_operating_ratios)
    builder.add_node("analyze_profitability_ratios", analyze_profitability_ratios)
    builder.add_node("analyze_leverage_ratios", analyze_leverage_ratios)
    builder.add_node("analyze_stability", analyze_stability)
    builder.add_node("mark_complete", mark_analysis_complete)

    # Define edges
    builder.add_edge(START, "analyze_operating_ratios")
    builder.add_edge("analyze_operating_ratios", "analyze_profitability_ratios")
    builder.add_edge("analyze_profitability_ratios", "analyze_leverage_ratios")
    builder.add_edge("analyze_leverage_ratios", "analyze_stability")
    builder.add_edge("analyze_stability", "mark_complete")
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
        "metadata": {"company": symbol, "file": "src/agents/fundamental_agent.py"}
    }

    # Define initial state
    initial_state: FinancialAnalysisState = {
        "fundamental_data": fundamental_data,
        "operating_ratios": None,
        "profitability_ratios": None,
        "leverage_ratios": None,
        "stability_metrics": None,
        "analysis_complete": False,
        "error_message": None
    }

    try:

        # Or just invoke to get the final state
        final_state = financial_analysis_graph.invoke(initial_state, config=config)
        logger.info(f"Financial analysis run completed for {symbol}.")

        if final_state.get("error_message"):
             logger.error(f"Error during analysis for {symbol}: {final_state['error_message']}")
             return {"error": final_state['error_message']}


        # Return the complete analysis results
        return {
            "operating_ratios": final_state.get("operating_ratios"),
            "profitability_ratios": final_state.get("profitability_ratios"),
            "leverage_ratios": final_state.get("leverage_ratios"),
            "stability_metrics": final_state.get("stability_metrics")
        }
    except Exception as e:
        logger.error(f"Error invoking financial analysis graph for {symbol}: {e}", exc_info=True)
        return {"error": f"Failed to run analysis graph: {str(e)}"}


def fundamental_agent(symbol: str, exchange: str = "nse", force: bool = False, refresh_days: int = 7) -> str:
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
    symbol_to_test = "REDINGTON"
    print(f"--- Running Fundamental Agent for {symbol_to_test} ---")
    analysis_report_json = fundamental_agent(symbol_to_test, exchange="nse", force=True, refresh_days=30) # Increase refresh days for testing
    print(analysis_report_json)