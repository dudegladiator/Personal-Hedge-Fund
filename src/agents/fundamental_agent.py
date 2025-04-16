import json
import statistics
from typing import Any, Dict, TypedDict, Optional, Tuple
from src.data_source.apis_2 import get_overall_fundamental_data
from src.llm.models import get_model
from langgraph.graph import StateGraph, START, END
from utils.app_logger import setup_logger
from src.prompts import fundamental_agent_system_prompt
import math
from utils.llm import parse_fundamental_response
from utils.util import _safe_get_float

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
    """Computes operating ratios safely, handling missing/invalid data."""
    results: Dict[str, Any] = {"Parameters": {}, "Confidence Level (%)": 0, "Signal": "Error", "Z-Scores": {}, "Points": {}}
    values = {} # Initialize values dict here
    try:
        balance_sheet_periods = fundamental_data.get("balance_sheet", {}).get("periods", {})
        profit_loss_periods = fundamental_data.get("profit_loss", {}).get("periods", {})

        if not balance_sheet_periods or not profit_loss_periods:
            raise ValueError("Missing balance_sheet or profit_loss periods data")

        # --- Safely Calculate Averages ---
        total_assets_list = [_safe_get_float(p, "total_assets") for p in balance_sheet_periods.values()]
        total_current_assets_list = [_safe_get_float(p, "total_current_assets") for p in balance_sheet_periods.values()]
        total_current_liabilities_list = [_safe_get_float(p, "total_current_liabilities") for p in balance_sheet_periods.values()]
        inventory_list = [_safe_get_float(p, "inventories") for p in balance_sheet_periods.values()]

        # Filter None before calculating stats
        valid_total_assets = [v for v in total_assets_list if v is not None]
        valid_inventories = [v for v in inventory_list if v is not None]

        # Calculate working capital safely for each period first
        working_capital_list = []
        for ca, cl in zip(total_current_assets_list, total_current_liabilities_list):
            if ca is not None and cl is not None:
                working_capital_list.append(ca - cl)
            # else: # Optionally handle pairs where one is None if needed
            #     pass

        # Calculate net fixed assets safely for each period
        net_fixed_assets_list = []
        for ta, tca in zip(total_assets_list, total_current_assets_list):
             if ta is not None and tca is not None:
                 net_fixed_assets_list.append(ta - tca)

        avg_total_assets = statistics.mean(valid_total_assets) if len(valid_total_assets) > 0 else None
        avg_net_fixed_assets = statistics.mean(net_fixed_assets_list) if len(net_fixed_assets_list) > 0 else None
        avg_working_capital = statistics.mean(working_capital_list) if len(working_capital_list) > 0 else None
        avg_inventory = statistics.mean(valid_inventories) if len(valid_inventories) > 0 else None

        # --- Extract Latest Period Values Safely ---
        latest_pl_period_key = sorted(profit_loss_periods.keys())[-1]
        latest_pl = profit_loss_periods.get(latest_pl_period_key, {})

        net_sales = _safe_get_float(latest_pl, "net_sales")
        # COGS Proxy: Treat missing components as 0 cost
        cogs_proxy = (_safe_get_float(latest_pl, "raw_materials_consumed") or 0.0) + \
                     (_safe_get_float(latest_pl, "power_&_fuel_cost") or 0.0) + \
                     (_safe_get_float(latest_pl, "employee_cost") or 0.0)
        if cogs_proxy == 0.0: cogs_proxy = None # If all components were missing/zero, set proxy to None

        # --- Calculate Ratios Safely ---
        fixed_asset_turnover = (net_sales / avg_net_fixed_assets) if net_sales is not None and avg_net_fixed_assets is not None and avg_net_fixed_assets != 0 else None
        working_capital_turnover = (net_sales / avg_working_capital) if net_sales is not None and avg_working_capital is not None and avg_working_capital != 0 else None
        total_asset_turnover = (net_sales / avg_total_assets) if net_sales is not None and avg_total_assets is not None and avg_total_assets != 0 else None
        inventory_turnover = (cogs_proxy / avg_inventory) if cogs_proxy is not None and avg_inventory is not None and avg_inventory != 0 else None

        values = {
            "Fixed Asset Turnover": fixed_asset_turnover,
            "Working Capital Turnover": working_capital_turnover,
            "Total Asset Turnover": total_asset_turnover,
            "Inventory Turnover (COGS Proxy)": inventory_turnover
        }
        # Round only if not None
        results["Parameters"] = {k: round(v, 2) if v is not None else "N/A" for k, v in values.items()}

        # --- Z-Score Parameters (Keep as before) ---
        z_score_params = {
            "Fixed Asset Turnover": {"mean": 2.25, "std_dev": 0.75, "type": "higher"},
            "Working Capital Turnover": {"mean": 6.0, "std_dev": 2.0, "type": "higher"},
            "Total Asset Turnover": {"mean": 1.0, "std_dev": 0.5, "type": "higher"},
            "Inventory Turnover (COGS Proxy)": {"mean": 5.0, "std_dev": 2.0, "type": "higher"}
        }

        # --- Scoring System (Keep as before, calculate_z_score handles None) ---
        total_points = 0
        max_points = 0
        z_scores = {}
        points_dict = {}
        for key, params in z_score_params.items():
            value = values.get(key) # Will be None if calculation failed
            z_score, points = calculate_z_score_and_points(value, params["mean"], params["std_dev"], params["type"])
            total_points += points
            max_points += 2
            z_scores[key] = z_score if z_score is not None else "N/A"
            points_dict[key] = points

        results["Z-Scores"] = z_scores
        results["Points"] = points_dict

        # --- Calculate Confidence Level & Signal (Keep as before) ---
        confidence_level = round((total_points / max_points) * 100, 2) if max_points > 0 else 0
        results["Confidence Level (%)"] = confidence_level
        if confidence_level >= 75: signal = "BULLISH"
        elif confidence_level >= 45: signal = "NEUTRAL"
        else: signal = "BEARISH"
        results["Signal"] = signal
    except Exception as e:
        # logger.error(f"Error computing operating ratios: {e}", exc_info=True) # Use your logger
        print(f"Error computing operating ratios: {e}") # Placeholder if logger not available
        results["Signal"] = f"Error: {str(e)[:100]}" # Keep error message concise
        # Ensure Parameters dict reflects calculation failure if values dict wasn't populated
        if not values:
             results["Parameters"] = {
                "Fixed Asset Turnover": "Error",
                "Working Capital Turnover": "Error",
                "Total Asset Turnover": "Error",
                "Inventory Turnover (COGS Proxy)": "Error"
            }


    return results
        
def calculate_profitability_ratios(fundamental_data: Dict[str, Any]) -> Dict[str, Any]:
    """Calculates profitability ratios safely, handling missing/invalid data."""
    results: Dict[str, Any] = {"Parameters": {}, "Confidence Level (%)": 0, "Signal": "Error", "Z-Scores": {}, "Points": {}}
    values = {}
    try:
        profit_loss_periods = fundamental_data.get("profit_loss", {}).get("periods", {})
        yearly_periods = fundamental_data.get("yearly", {}).get("periods", {})
        stock_quality = fundamental_data.get("stock_quality", {}).get("quality_ratios", {})
        balance_sheet_periods = fundamental_data.get("balance_sheet", {}).get("periods", {})

        if not profit_loss_periods or not yearly_periods or not balance_sheet_periods:
             raise ValueError("Missing profit_loss, yearly, or balance_sheet data")

        latest_pl_key = sorted(profit_loss_periods.keys())[-1]
        latest_pl = profit_loss_periods.get(latest_pl_key, {})
        latest_yearly_key = sorted(yearly_periods.keys())[-1]
        latest_yearly = yearly_periods.get(latest_yearly_key, {})

        # --- Calculate Averages Safely ---
        total_assets_list = [_safe_get_float(p, "total_assets") for p in balance_sheet_periods.values()]
        valid_total_assets = [v for v in total_assets_list if v is not None]
        avg_total_assets = statistics.mean(valid_total_assets) if len(valid_total_assets) > 0 else None

        # --- Extract Values Safely ---
        net_sales = _safe_get_float(latest_pl, "net_sales")
        operating_profit_pbdit = _safe_get_float(latest_pl, "operating_profit_(pbdit)")
        profit_after_tax = _safe_get_float(latest_pl, "profit_after_tax")
        # Treat missing interest as 0 for ROA calculation, but None otherwise if needed
        interest = _safe_get_float(latest_pl, "interest") or 0.0
        tax_rate = 0.25 # Assuming constant

        pat_margin = _safe_get_float(latest_yearly, "pat_margin") # From yearly data
        # Use _safe_get_float for stock quality ratios too
        roe_avg = _safe_get_float(stock_quality, "roe_avg")
        roce_avg = _safe_get_float(stock_quality, "roce_avg")

        # --- Calculate Metrics Safely ---
        ebitda_margin = (operating_profit_pbdit / net_sales * 100) if net_sales is not None and net_sales != 0 and operating_profit_pbdit is not None else None
        roa = ((profit_after_tax + interest * (1 - tax_rate)) / avg_total_assets * 100) if avg_total_assets is not None and avg_total_assets != 0 and profit_after_tax is not None else None

        values = {
            "EBITDA Margin (%)": ebitda_margin,
            "PAT Margin (%)": pat_margin, # Already a percentage
            "ROE Avg (%)": roe_avg,       # Already a percentage
            "ROCE Avg (%)": roce_avg,     # Already a percentage
            "ROA (%)": roa
        }
        results["Parameters"] = {k: round(v, 2) if v is not None else "N/A" for k, v in values.items()}

        # --- Z-Score Parameters (Keep as before) ---
        z_score_params = {
            "EBITDA Margin (%)": {"mean": 20.0, "std_dev": 5.0, "type": "higher"},
            "PAT Margin (%)": {"mean": 10.0, "std_dev": 5.0, "type": "higher"},
            "ROE Avg (%)": {"mean": 16.0, "std_dev": 4.0, "type": "higher"},
            "ROCE Avg (%)": {"mean": 14.0, "std_dev": 4.0, "type": "higher"},
            "ROA (%)": {"mean": 7.5, "std_dev": 2.5, "type": "higher"}
        }

        # --- Scoring System (Keep as before) ---
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

        # --- Calculate Confidence Level & Signal (Keep as before) ---
        confidence_level = round((total_points / max_points) * 100, 2) if max_points > 0 else 0
        results["Confidence Level (%)"] = confidence_level
        if confidence_level >= 75: signal = "BULLISH"
        elif confidence_level >= 45: signal = "NEUTRAL"
        else: signal = "BEARISH"
        results["Signal"] = signal

    except Exception as e:
        # logger.error(f"Error calculating profitability ratios: {e}", exc_info=True)
        print(f"Error calculating profitability ratios: {e}")
        results["Signal"] = f"Error: {str(e)[:100]}"
        if not values:
             results["Parameters"] = { # Default to error if calculation failed early
                "EBITDA Margin (%)": "Error", "PAT Margin (%)": "Error", "ROE Avg (%)": "Error",
                "ROCE Avg (%)": "Error", "ROA (%)": "Error"
             }

    return results

def compute_leverage_ratios(fundamental_data: Dict[str, Any]) -> Dict[str, Any]:
    """Computes leverage ratios safely, handling missing/invalid data."""
    results: Dict[str, Any] = {"Parameters": {}, "Confidence Level (%)": 0, "Signal": "Error", "Z-Scores": {}, "Points": {}}
    values = {}
    try:
        balance_sheet_periods = fundamental_data.get("balance_sheet", {}).get("periods", {})
        profit_loss_periods = fundamental_data.get("profit_loss", {}).get("periods", {})
        stock_quality = fundamental_data.get("stock_quality", {}).get("quality_ratios", {})

        if not balance_sheet_periods or not profit_loss_periods:
            raise ValueError("Missing balance_sheet or profit_loss periods data")

        latest_pl_key = sorted(profit_loss_periods.keys())[-1]
        latest_pl = profit_loss_periods.get(latest_pl_key, {})
        latest_bs_key = sorted(balance_sheet_periods.keys())[-1]
        latest_bs = balance_sheet_periods.get(latest_bs_key, {})

        # --- Extract Values Safely ---
        pbdit = _safe_get_float(latest_pl, "operating_profit_(pbdit)")
        depreciation = _safe_get_float(latest_pl, "depreciation") or 0.0 # Treat missing depreciation as 0
        interest = _safe_get_float(latest_pl, "interest")
        ebit = (pbdit - depreciation) if pbdit is not None else None

        debt_to_equity = _safe_get_float(stock_quality, "net_debt_to_equity_avg")
        total_debt = _safe_get_float(latest_bs, "total_debt")
        total_assets_latest = _safe_get_float(latest_bs, "total_assets")

        # --- Calculate Averages Safely ---
        total_assets_list = [_safe_get_float(p, "total_assets") for p in balance_sheet_periods.values()]
        total_equity_list = [_safe_get_float(p, "shareholder's_funds") for p in balance_sheet_periods.values()] # Proxy

        valid_total_assets = [v for v in total_assets_list if v is not None]
        valid_total_equity = [v for v in total_equity_list if v is not None]

        avg_total_assets = statistics.mean(valid_total_assets) if len(valid_total_assets) > 0 else None
        avg_total_equity = statistics.mean(valid_total_equity) if len(valid_total_equity) > 0 else None

        # --- Calculate Ratios Safely ---
        interest_coverage_ratio = (ebit / interest) if ebit is not None and interest is not None and interest != 0 else None
        debt_to_asset_ratio = (total_debt / total_assets_latest) if total_debt is not None and total_assets_latest is not None and total_assets_latest != 0 else None
        financial_leverage_ratio = (avg_total_assets / avg_total_equity) if avg_total_assets is not None and avg_total_equity is not None and avg_total_equity != 0 else None

        # print(f"Debt to Equity: {debt_to_equity}, Financial Leverage Ratio: {financial_leverage_ratio}, Debt to Asset Ratio: {debt_to_asset_ratio}, Interest Coverage Ratio: {interest_coverage_ratio}")

        values = {
            "Interest Coverage Ratio": interest_coverage_ratio,
            "Net Debt-to-Equity Avg": debt_to_equity,
            "Debt-to-Asset Ratio": debt_to_asset_ratio,
            "Financial Leverage Ratio": financial_leverage_ratio
        }
        results["Parameters"] = {k: round(v, 2) if v is not None else "N/A" for k, v in values.items()}

        # --- Z-Score Parameters (Keep as before) ---
        z_score_params = {
            "Interest Coverage Ratio": {"mean": 4.0, "std_dev": 1.0, "type": "higher"},
            "Net Debt-to-Equity Avg": {"mean": 1.0, "std_dev": 0.5, "type": "lower"},
            "Debt-to-Asset Ratio": {"mean": 0.45, "std_dev": 0.15, "type": "lower"},
            "Financial Leverage Ratio": {"mean": 2.0, "std_dev": 0.5, "type": "range"}
        }

        # --- Scoring System (Keep as before, handles D/E < 0) ---
        total_points = 0
        max_points = 0
        z_scores = {}
        points_dict = {}
        for key, params in z_score_params.items():
            value = values.get(key)
            z_score, points = None, 0 # Default
            if key == "Net Debt-to-Equity Avg" and isinstance(value, (int, float)) and value < 0:
                 z_score, points = None, 2 # Assign max points directly
                 z_scores[key] = "Negative (Good)"
                 points_dict[key] = points
            else:
                z_score, points = calculate_z_score_and_points(value, params["mean"], params["std_dev"], params["type"])
                z_scores[key] = z_score if z_score is not None else "N/A"
                points_dict[key] = points

            total_points += points
            max_points += 2

        results["Z-Scores"] = z_scores
        results["Points"] = points_dict

        # --- Calculate Confidence Level & Signal (Keep as before) ---
        confidence_level = round((total_points / max_points) * 100, 2) if max_points > 0 else 0
        results["Confidence Level (%)"] = confidence_level
        if confidence_level >= 75: signal = "BULLISH" # Low leverage good
        elif confidence_level >= 45: signal = "NEUTRAL"
        else: signal = "BEARISH" # High leverage bad
        results["Signal"] = signal

    except Exception as e:
        # logger.error(f"Error computing leverage ratios: {e}", exc_info=True)
        print(f"Error computing leverage ratios: {e}")
        results["Signal"] = f"Error: {str(e)[:100]}"
        if not values:
            results["Parameters"] = { # Default to error
                "Interest Coverage Ratio": "Error", "Net Debt-to-Equity Avg": "Error",
                "Debt-to-Asset Ratio": "Error", "Financial Leverage Ratio": "Error"
            }

    return results

def compute_company_stability(fundamental_data: Dict[str, Any]) -> Dict[str, Any]:
    """Computes company stability metrics safely, handling missing/invalid data."""
    results: Dict[str, Any] = {"Metrics": {}, "Confidence Level (%)": 0, "Signal": "Error", "Z-Scores": {}, "Points": {}}
    metrics = {} # Initialize metrics dict here
    try:
        cash_flow_periods = fundamental_data.get("cash_flow", {}).get("periods", {})
        yearly_periods = fundamental_data.get("yearly", {}).get("periods", {})
        balance_sheet_periods = fundamental_data.get("balance_sheet", {}).get("periods", {})
        stock_quality = fundamental_data.get("stock_quality", {}).get("quality_ratios", {})
        shareholding_periods = fundamental_data.get("shareholding_pattern", {}).get("periods", {})

        # Check only essential period data
        if not cash_flow_periods or not yearly_periods or not balance_sheet_periods or not shareholding_periods:
            raise ValueError("Missing essential periods data (cash_flow, yearly, balance_sheet, or shareholding)")

        # --- Extract Growth Metrics Safely ---
        metrics["Sales Growth 5Y (%)"] = _safe_get_float(stock_quality, "sales_growth_5y")
        metrics["EBIT Growth 5Y (%)"] = _safe_get_float(stock_quality, "ebit_growth_5y")
        metrics["Dividend Payout Ratio (%)"] = _safe_get_float(stock_quality, "dividend_payout_ratio")

        # --- Calculate Stability Metrics Safely ---

        # 1. Cash Flow Stability
        ocf_field = 'cash_flow_from_operating_activities'
        ocf_list = [_safe_get_float(p, ocf_field) for p in cash_flow_periods.values()]
        valid_ocf_list = [v for v in ocf_list if v is not None]

        if not valid_ocf_list:
             # logger.warning(f"OCF field '{ocf_field}' not found or only contains invalid data.")
             print(f"Warning: OCF field '{ocf_field}' not found or only contains invalid data.")
             metrics["Cash Flow Stability (% Positive OCF)"] = None
        else:
            positive_ocf_count = sum(1 for ocf in valid_ocf_list if ocf > 0)
            ocf_percentage = (positive_ocf_count / len(valid_ocf_list)) * 100
            metrics["Cash Flow Stability (% Positive OCF)"] = ocf_percentage # Already a percentage

        # Helper for calculating stability (CV %) - Safe version
        def calculate_stability_metric(data_list: list) -> Optional[float]:
            valid_data = [v for v in data_list if v is not None] # Ensure only valid floats
            if len(valid_data) < 2: return None
            try:
                mean = statistics.mean(valid_data)
                if mean == 0: return 0.0 # Stable at zero
                std_dev = statistics.stdev(valid_data)
                cv = abs(std_dev / mean) * 100 # CV as percentage
                return cv
            except statistics.StatisticsError: # Should not happen if len >= 2, but belts and suspenders
                return None

        # 2. PAT Margin Stability
        pat_margin_list = [_safe_get_float(p, "pat_margin") for p in yearly_periods.values()]
        metrics["PAT Margin Stability (CV %)"] = calculate_stability_metric(pat_margin_list)

        # 3. Debt Level Stability
        debt_list = [_safe_get_float(p, "total_debt") for p in balance_sheet_periods.values()]
        metrics["Debt Level Stability (CV %)"] = calculate_stability_metric(debt_list)

        # 4. Promoter Holding Stability
        promoter_field = "Total Promoter"
        promoter_list = [_safe_get_float(p, promoter_field) for p in shareholding_periods.values()]
        metrics["Promoter Holding Stability (CV %)"] = calculate_stability_metric(promoter_list)

        results["Metrics"] = {k: round(v, 2) if v is not None else "N/A" for k, v in metrics.items()}

        # --- Z-Score Parameters (Keep as before) ---
        z_score_params = {
            "Sales Growth 5Y (%)": {"mean": 12.5, "std_dev": 5.0, "type": "higher"},
            "EBIT Growth 5Y (%)": {"mean": 15.0, "std_dev": 6.0, "type": "higher"},
            "PAT Margin Stability (CV %)": {"mean": 15.0, "std_dev": 10.0, "type": "lower"},
            "Debt Level Stability (CV %)": {"mean": 20.0, "std_dev": 10.0, "type": "lower"},
            "Dividend Payout Ratio (%)": {"mean": 30.0, "std_dev": 15.0, "type": "range"},
            "Promoter Holding Stability (CV %)": {"mean": 2.5, "std_dev": 2.5, "type": "lower"},
            "Cash Flow Stability (% Positive OCF)": {"mean": 85.0, "std_dev": 15.0, "type": "higher"}
        }

        # --- Scoring System (Keep as before) ---
        total_points = 0
        max_points = 0
        z_scores = {}
        points_dict = {}
        for key, params in z_score_params.items():
            value = metrics.get(key) # Value might be None if calculation failed
            z_score, points = calculate_z_score_and_points(value, params["mean"], params["std_dev"], params["type"])
            total_points += points
            max_points += 2
            z_scores[key] = z_score if z_score is not None else "N/A"
            points_dict[key] = points

        results["Z-Scores"] = z_scores
        results["Points"] = points_dict

        # --- Calculate Confidence Level & Signal (Keep as before) ---
        confidence_level = round((total_points / max_points) * 100, 2) if max_points > 0 else 0
        results["Confidence Level (%)"] = confidence_level
        if confidence_level >= 75: signal = "BULLISH"
        elif confidence_level >= 45: signal = "NEUTRAL"
        else: signal = "BEARISH"
        results["Signal"] = signal

    except Exception as e:
        # logger.error(f"Error computing company stability: {e}", exc_info=True)
        print(f"Error computing company stability: {e}")
        results["Signal"] = f"Error: {str(e)[:100]}"
        if not metrics: # Default to error if calculation failed early
            results["Metrics"] = {
                 "Sales Growth 5Y (%)": "Error", "EBIT Growth 5Y (%)": "Error",
                 "Dividend Payout Ratio (%)": "Error", "Cash Flow Stability (% Positive OCF)": "Error",
                 "PAT Margin Stability (CV %)": "Error", "Debt Level Stability (CV %)": "Error",
                 "Promoter Holding Stability (CV %)": "Error"
            }

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
        analyse = parse_fundamental_response(response.choices[0].message.content, raw_data = filtered_results)
        return analyse

    except Exception as e:
        logger.error(f"Error interacting with LLM for {symbol}: {str(e)}", exc_info=True)
        return {"error": f"An error occurred during LLM interaction: {str(e)}"}

if __name__ == "__main__":
    stock_codes = [
        # "INDUSINDBK",
        # "PATANJALI",
        # "ITC",
        # "AMBUJACEM",
        # "AXISBANK",
        # "HEROMOTOCO",
        # "HAL",
        # "UNITDSPR",
        # "TATAMOTORS",
        # "NTPC",
        # "BAJAJFINSV",
        "RELIANCE"
    ]
    for stock in stock_codes:
        print(f"Running analysis for {stock}...")
        result = fundamental_agent(stock)
        print(f"Result for {stock}: {result}")
        print("-" * 80)