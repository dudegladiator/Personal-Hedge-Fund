import json
import sys
import statistics
from typing import Any, Dict, TypedDict
from src.llm.models import get_model
from langgraph.types import Command
from langgraph.graph import StateGraph, START
from utils.app_logger import setup_logger
from utils.config import settings, get_sync_database

logger = setup_logger("src/agents/fundamental_agent.py")
db = get_sync_database()

# Initialize Groq groq_client
groq_client = get_model(model_provider="GROQ")
model = "llama-3.3-70b-versatile"  # You can change this to your preferred model

class FinancialAnalysisState(TypedDict):
    fundamental_data: Dict[str, Any]  # Input financial data
    operating_ratios: Dict[str, Any]  # Results from operating ratios analysis
    profitability_ratios: Dict[str, Any]  # Results from profitability analysis
    leverage_ratios: Dict[str, Any]  # Results from leverage analysis
    stability_metrics: Dict[str, Any]  # Results from stability analysis
    analysis_complete: bool  # Flag to indicate all analyses are complete

def compute_operating_ratios(fundamental_data):
    """Computes operating ratios, assigns scores, calculates confidence level, and classifies financial health."""

    data = fundamental_data

    # Extract balance sheet, profit/loss, and yearly data
    balance_sheet = data["balance_sheet"]["periods"]
    profit_loss = data["profit_loss"]["periods"]

    # Extract financial metrics for the latest year
    latest_year = "Mar'24"

    # Compute Total Average Assets
    total_assets_list = [values["total_assets"] for values in balance_sheet.values()]
    avg_total_assets = sum(total_assets_list) / len(total_assets_list)

    # Compute Average Working Capital
    working_capital_list = [(values["total_current_assets"] - values["total_current_liabilities"]) for values in balance_sheet.values()]
    avg_working_capital = sum(working_capital_list) / len(working_capital_list)

    # Compute Average Inventory
    inventory_list = [values["inventories"] for values in balance_sheet.values()]
    avg_inventory = sum(inventory_list) / len(inventory_list)

    # Extract values for latest period
    operating_income = profit_loss[latest_year]["operating_income"]
    net_sales = profit_loss[latest_year]["net_sales"]
    operating_profit_pbdit = profit_loss[latest_year]["operating_profit_(pbdit)"]
    raw_materials_consumed = profit_loss[latest_year]["raw_materials_consumed"]
    power_fuel_cost = profit_loss[latest_year]["power_&_fuel_cost"]
    employee_cost = profit_loss[latest_year]["employee_cost"]

    # Calculate Operating Ratios
    fixed_asset_turnover = operating_income / avg_total_assets if avg_total_assets else None
    working_capital_turnover = net_sales / avg_working_capital if avg_working_capital else None
    total_asset_turnover = operating_profit_pbdit / avg_total_assets if avg_total_assets else None
    inventory_turnover = (raw_materials_consumed + power_fuel_cost + employee_cost) / avg_inventory if avg_inventory else None

    # Thresholds for Scoring
    thresholds = {
        "Fixed Asset Turnover": (1.5, 3.0),
        "Working Capital Turnover": (4, 8),
        "Total Asset Turnover": (0.2, 0.6),
        "Inventory Turnover": (3, 7)
    }

    # Calculated Values
    values = {
        "Fixed Asset Turnover": round(fixed_asset_turnover, 2) if fixed_asset_turnover else "N/A",
        "Working Capital Turnover": round(working_capital_turnover, 2) if working_capital_turnover else "N/A",
        "Total Asset Turnover": round(total_asset_turnover, 2) if total_asset_turnover else "N/A",
        "Inventory Turnover": round(inventory_turnover, 2) if inventory_turnover else "N/A"
    }

    # Scoring System
    total_score = 0
    max_score = 8  # 4 parameters, max 2 points each

    for key in thresholds:
        lower, upper = thresholds[key]
        value = values[key]

        if isinstance(value, float):  # Ensure it's a valid number
            if lower <= value <= upper:
                total_score += 2  # ✅ Optimal range
            elif lower * 0.8 <= value < lower or upper < value <= upper * 1.2:
                total_score += 1  # ⚠ Slightly outside range
            else:
                total_score += 0  # ❌ Far outside range

    # Calculate Confidence Level
    confidence_level = round((total_score / max_score) * 100, 2)

    # Determine Final Signal
    if confidence_level >= 80:
        signal = "Bullish (Buy Signal)"
    elif confidence_level >= 50:
        signal = "Healthy"
    else:
        signal = "Bearish (Sell Signal)"

    # Return results
    operating_ratios = {
        "Parameters": values,
        "Confidence Level (%)": confidence_level,
        "Signal": signal
    }

    return operating_ratios

def calculate_profitability_ratios(fundamental_data):
    """
    Function to calculate profitability ratios, confidence level, and classify the company's financial health.
    """
    data = fundamental_data
        
    latest_period = "Mar'24"  # Extract the latest period data
    profit_loss = data["profit_loss"]["periods"][latest_period]
    yearly_data = data["yearly"]["periods"][latest_period]
    stock_quality = data["stock_quality"]["quality_ratios"]
    balance_sheet_data = data["balance_sheet"]["periods"]

    # Compute total average assets over all years
    total_avg_assets = sum(bs["total_assets"] for bs in balance_sheet_data.values()) / len(balance_sheet_data)

    # Extract required fields
    net_sales = profit_loss["net_sales"]
    total_expenditure = profit_loss["total_expenditure"]
    profit_after_tax = profit_loss["profit_after_tax"]
    interest = profit_loss["interest"]
    pat_margin = yearly_data["pat_margin"]
    roe_avg = stock_quality["roe_avg"]
    roce_avg = stock_quality["roce_avg"]

    # Calculate metrics
    ebitda_margin = ((net_sales - total_expenditure) / net_sales) * 100
    roa = (profit_after_tax + interest * (1 - 0.25)) / total_avg_assets

    # Define thresholds
    thresholds = {
        "EBITDA Margin": (15, 25),
        "PAT Margin": (5, 15),
        "ROE": (12, 20),
        "ROCE": (10, 18),
        "ROA": (5, 10)
    }

    # Store calculated values
    values = {
        "EBITDA Margin": round(ebitda_margin, 2),
        "PAT Margin": round(pat_margin, 2),
        "ROE": round(roe_avg, 2),
        "ROCE": round(roce_avg, 2),
        "ROA": round(roa, 2)
    }

    # Scoring system (0-2 per metric)
    total_score = 0
    max_score = 10  # 5 parameters, max 2 points each

    for key in thresholds:
        lower, upper = thresholds[key]
        value = values[key]

        if lower <= value <= upper:
            total_score += 2  # ✅ Optimal range
        elif lower * 0.8 <= value < lower or upper < value <= upper * 1.2:
            total_score += 1  # ⚠ Slightly outside range
        else:
            total_score += 0  # ❌ Far outside range

    # Calculate confidence level (percentage)
    confidence_level = round((total_score / max_score) * 100, 2)

    # Determine final signal based on confidence level
    if confidence_level >= 80:
        signal = "Bullish (Buy Signal)"
    elif confidence_level >= 50:
        signal = "Healthy"
    else:
        signal = "Bearish (Sell Signal)"

    # Return all values along with confidence level and signal
    return {
        "Parameters": values,
        "Confidence Level (%)": confidence_level,
        "Signal": signal
    }

def compute_leverage_ratios(fundamental_data):
    """Computes leverage ratios, assigns scores, calculates confidence level, and classifies financial health."""
    data = fundamental_data
        
    # Extract balance sheet, profit/loss, and yearly data
    balance_sheet = data["balance_sheet"]["periods"]
    profit_loss = data["profit_loss"]["periods"]
    stock_quality = data["stock_quality"]["quality_ratios"]
    
    # Extract financial metrics for the latest year
    latest_year = "Mar'24"
    
    # Interest Coverage Ratio
    pbdit = profit_loss[latest_year]["operating_profit_(pbdit)"]
    depreciation = profit_loss[latest_year]["depreciation"]
    interest = profit_loss[latest_year]["interest"]
    interest_coverage_ratio = (pbdit - depreciation) / interest if interest else None
    
    # Debt-to-Equity Ratio (directly available)
    debt_to_equity = stock_quality.get("net_debt_to_equity_avg")
    
    # Debt-to-Asset Ratio
    total_debt = balance_sheet[latest_year]["total_debt"]
    total_assets = balance_sheet[latest_year]["total_assets"]
    debt_to_asset_ratio = total_debt / total_assets if total_assets else None
    
    # Financial Leverage Ratio (Average Total Assets / Average Total Equity)
    total_assets_list = [values["total_assets"] for values in balance_sheet.values()]
    total_equity_list = [values["shareholder's_funds"] for values in balance_sheet.values()]
    avg_total_assets = sum(total_assets_list) / len(total_assets_list)
    avg_total_equity = sum(total_equity_list) / len(total_equity_list)
    financial_leverage_ratio = avg_total_assets / avg_total_equity if avg_total_equity else None
    
    # Thresholds for Scoring
    thresholds = {
        "Interest Coverage Ratio": (3, 5),
        "Debt-to-Equity Ratio": (0.5, 1.5),
        "Debt-to-Asset Ratio": (0.3, 0.6),
        "Financial Leverage Ratio": (1.5, 2.5)
    }
    
    # Calculated Values
    values = {
        "Interest Coverage Ratio": round(interest_coverage_ratio, 2) if interest_coverage_ratio else "N/A",
        "Debt-to-Equity Ratio": round(debt_to_equity, 2) if debt_to_equity else "N/A",
        "Debt-to-Asset Ratio": round(debt_to_asset_ratio, 2) if debt_to_asset_ratio else "N/A",
        "Financial Leverage Ratio": round(financial_leverage_ratio, 2) if financial_leverage_ratio else "N/A"
    }
    
    # Scoring System
    total_score = 0
    max_score = 8  # 4 parameters, max 2 points each
    
    for key in thresholds:
        lower, upper = thresholds[key]
        value = values[key]
        
        if isinstance(value, float):  # Ensure it's a valid number
            if lower <= value <= upper:
                total_score += 2  # ✅ Optimal range
            elif lower * 0.8 <= value < lower or upper < value <= upper * 1.2:
                total_score += 1  # ⚠ Slightly outside range
            else:
                total_score += 0  # ❌ Far outside range
    
    # Calculate Confidence Level
    confidence_level = round((total_score / max_score) * 100, 2)
    
    # Determine Final Signal
    if confidence_level >= 80:
        signal = "Bullish (Buy Signal)"
    elif confidence_level >= 50:
        signal = "Healthy"
    else:
        signal = "Bearish (Sell Signal)"
    
    # Return results
    leverage_ratios = {
        "Parameters": values,
        "Confidence Level (%)": confidence_level,
        "Signal": signal
    }
    
    return leverage_ratios

def compute_company_stability(fundamental_data):
    """Computes company stability based on cash flow, sales, EBIT, debt, dividends, and promoter holding trends."""

    data = fundamental_data

    # Extract relevant data
    cash_flow = data["cash_flow"]["periods"]
    yearly_data = data["yearly"]["periods"]
    balance_sheet = data["balance_sheet"]["periods"]
    stock_quality = data["stock_quality"]["quality_ratios"]
    shareholding = data["shareholding_pattern"]["periods"]

    # **Extract growth metrics**
    sales_growth_5y = stock_quality.get("sales_growth_5y", 0)
    ebit_growth_5y = stock_quality.get("ebit_growth_5y", 0)
    dividend_payout_ratio = stock_quality.get("dividend_payout_ratio", 0)

    # **1. Cash Flow Stability (OCF Positive ≥80% of time)**
    ocf_list = [year_data["closing_cash_&_cash_equivalent"] for year_data in cash_flow.values()]
    positive_ocf_count = sum(1 for ocf in ocf_list if ocf > 0)
    ocf_percentage = (positive_ocf_count / len(ocf_list)) * 100 if len(ocf_list) > 0 else 0

    # **2. PAT Margin Stability (Standard Deviation % of Mean)**
    pat_margin_list = [year_data["pat_margin"] for year_data in yearly_data.values()]
    pat_margin_mean = sum(pat_margin_list) / len(pat_margin_list)
    pat_margin_std_dev = (statistics.stdev(pat_margin_list) / pat_margin_mean * 100) if len(pat_margin_list) > 1 else 0

    # **3. Debt Level Stability (Standard Deviation % of Mean)**
    liabilities_list = [year_data["total_liabilities"] for year_data in balance_sheet.values()]
    liabilities_mean = sum(liabilities_list) / len(liabilities_list)
    liabilities_std_dev = (statistics.stdev(liabilities_list) / liabilities_mean * 100) if len(liabilities_list) > 1 else 0

    # **4. Promoter Holding Stability (Standard Deviation % of Mean)**
    promoter_list = [year_data["Total Promoter"] for year_data in shareholding.values()]
    promoter_mean = sum(promoter_list) / len(promoter_list)
    promoter_std_dev = (statistics.stdev(promoter_list) / promoter_mean * 100) if len(promoter_list) > 1 else 0

    # **Threshold-based Scoring System**
    def score_metric(value, thresholds):
        """Assigns a score based on predefined thresholds."""
        if value <= thresholds[0]:
            return 2 
        elif value <= thresholds[1]:
            return 1 
        return 0 

    # **Scoring**
    scores = {
        "Sales Growth Stability": score_metric(12 - sales_growth_5y, [4, 7]),  # Higher is better
        "EBIT Growth Stability": score_metric(15 - ebit_growth_5y, [5, 9]),   # Higher is better
        "PAT Margin Stability": score_metric(pat_margin_std_dev, [3, 5]),     # Lower is better
        "Debt Level Stability": score_metric(liabilities_std_dev, [10, 15]),  # Lower is better
        "Dividend Payout Stability": score_metric(abs(dividend_payout_ratio - 30), [10, 20]),  # 20-40% is ideal
        "Promoter Holding Stability": score_metric(promoter_std_dev, [2, 5]),  # Lower is better
        "Cash Flow Stability": score_metric(100 - ocf_percentage, [20, 40])   # Higher is better
    }

    # **Total Score Calculation**
    total_score = sum(scores.values())
    max_score = len(scores) * 2  # 7 metrics, max 2 points each

    # **Calculate Confidence Level**
    confidence_level = round((total_score / max_score) * 100, 2)

    # **Determine Final Signal**
    if confidence_level >= 80:
        signal = "Stable (Buy Signal)"
    elif confidence_level >= 50:
        signal = "Moderate Stability"
    else:
        signal = "Unstable (Sell Signal)"

    # **Return results**
    stability_results = {
        "Metrics": {
            "Sales Growth Stability (%)": sales_growth_5y,
            "EBIT Growth Stability (%)": ebit_growth_5y,
            "PAT Margin Stability (Std Dev % of Mean)": round(pat_margin_std_dev, 2),
            "Debt Level Stability (Std Dev % of Mean)": round(liabilities_std_dev, 2),
            "Dividend Payout Ratio (%)": dividend_payout_ratio,
            "Promoter Holding Stability (Std Dev % of Mean)": round(promoter_std_dev, 2),
            "Cash Flow Stability (OCF Positive % of Time)": round(ocf_percentage, 2)
        },
        "Scores": scores,
        "Confidence Level (%)": confidence_level,
        "Signal": signal
    }

    return stability_results

# Define node functions
def analyze_operating_ratios(state: FinancialAnalysisState) -> dict:
    """Node to compute operating ratios"""
    result = compute_operating_ratios(state["fundamental_data"])
    # Update state with the result
    Command(update={"operating_ratios": result})
    return {"operating_ratios": result}

def analyze_profitability_ratios(state: FinancialAnalysisState) -> dict:
    """Node to compute profitability ratios"""
    result = calculate_profitability_ratios(state["fundamental_data"])
    Command(update={"profitability_ratios": result})
    return {"profitability_ratios": result}

def analyze_leverage_ratios(state: FinancialAnalysisState) -> dict:
    """Node to compute leverage ratios"""
    result = compute_leverage_ratios(state["fundamental_data"])
    Command(update={"leverage_ratios": result})
    return {"leverage_ratios": result}

def analyze_stability(state: FinancialAnalysisState) -> dict:
    """Node to compute company stability metrics"""
    result = compute_company_stability(state["fundamental_data"])
    Command(update={"stability_metrics": result})
    return {"stability_metrics": result}

def mark_analysis_complete(state: FinancialAnalysisState) -> dict:
    """Node to mark analysis as complete"""
    Command(update={"analysis_complete": True})
    return {"analysis_complete": True}

# Create the financial analysis subgraph
def create_financial_analysis_subgraph():
    """Creates a subgraph for financial analysis"""
    # Initialize the graph
    builder = StateGraph(FinancialAnalysisState)
    
    # Add nodes
    builder.add_node("analyze_operating_ratios", analyze_operating_ratios)
    builder.add_node("analyze_profitability_ratios", analyze_profitability_ratios)
    builder.add_node("analyze_leverage_ratios", analyze_leverage_ratios)
    builder.add_node("analyze_stability", analyze_stability)
    builder.add_node("mark_complete", mark_analysis_complete)
    
    # Add edges - create a sequential workflow
    builder.add_edge(START, "analyze_operating_ratios")
    builder.add_edge("analyze_operating_ratios", "analyze_profitability_ratios")
    builder.add_edge("analyze_profitability_ratios", "analyze_leverage_ratios")
    builder.add_edge("analyze_leverage_ratios", "analyze_stability")
    builder.add_edge("analyze_stability", "mark_complete")
    
    # Compile the graph
    return builder.compile(name="Ratios for Fundamental Analysis")

def run_financial_analysis(symbol, fundamental_data):
    """Run the financial analysis subgraph with the provided data"""
    # Create the subgraph
    financial_analysis_graph = create_financial_analysis_subgraph()
    
    config = {
        "tags": ["fundamental_analysis", "fundamental_ratios"],
        "metadata": {"company": symbol, "file": "src/agents/fundamental_agent.py"}
    }
    
    # Define initial state
    initial_state = {
        "fundamental_data": fundamental_data,
        "operating_ratios": None,
        "profitability_ratios": None,
        "leverage_ratios": None,
        "stability_metrics": None,
        "analysis_complete": False
    }
    
    final_state = financial_analysis_graph.invoke(initial_state, config)
    
    # Return the complete analysis results
    return {
        "operating_ratios": final_state["operating_ratios"],
        "profitability_ratios": final_state["profitability_ratios"],
        "leverage_ratios": final_state["leverage_ratios"],
        "stability_metrics": final_state["stability_metrics"]
    }

def fundamental_agent(symbol: str):
    """
    Creates a financial analysis agent using LangGraph subgraph
    
    Args:
        symbol: Stock symbol to analyze
    
    Returns:
        Analysis report from the LLM
    """
    # Get fundamental data from database
    fundamental_data = db.fundamental_data.find_one({"symbol": symbol})
    
    if not fundamental_data:
        logger.error(f"No fundamental data found for symbol: {symbol}")
        return f"No fundamental data found for symbol: {symbol}"
    
    # Run the financial analysis subgraph
    analysis_results = run_financial_analysis(symbol, fundamental_data)
    
    # Initial messages
    messages = [
        {
            "role": "system", 
            "content": """You are a sophisticated financial analyst specializing in fundamental analysis of companies. 
            Your task is to analyze financial data comprehensively and provide an investment recommendation.
            
            The data provided includes key financial metrics organized into four categories:
            1. Operating Ratios - showing how efficiently the company utilizes its assets
            2. Profitability Ratios - indicating the company's ability to generate profits
            3. Leverage Ratios - revealing the company's debt structure and risk
            4. Stability Metrics - demonstrating the consistency of the company's performance
            
            For each category, you'll receive calculated ratios, confidence levels, and signals.
            
            Explain the significance of each ratio and metric and what it indicates about the company's financial health.
            Evaluate the strengths and weaknesses revealed by these metrics.
            Conclude with an overall investment recommendation (Bullish/Buy, Neutral/Hold, or Bearish/Sell) based on
            your comprehensive analysis of all categories."""
        },
        {
            "role": "user", 
            "content": f"Please analyze the financial data for {symbol} and provide a comprehensive fundamental analysis with an investment recommendation based on the following metrics:\n\n{json.dumps(analysis_results, indent=2)}"
        }
    ]
    
    # Make the request to the LLM
    try:
        response = groq_client.chat.completions.create(
            model=model, 
            messages=messages,
            temperature=0.6
        )
        
        return response.choices[0].message.content
            
    except Exception as e:
        logger.error(f"Error in fundamental_agent: {str(e)}")
        return f"An error occurred during financial analysis: {str(e)}"

if __name__ == "__main__":
    # Example usage
    symbol = "RELIANCE"
    analysis_report = fundamental_agent(symbol)
    print(analysis_report)