import json
import os
import sys
import statistics
from src.llm.models import get_model

# Initialize Groq groq_client
groq_client = get_model(model_provider="GROQ")
model = "llama-3.3-70b-versatile"  # You can change this to your preferred model


def compute_operating_ratios(json_file):
    """Computes operating ratios, assigns scores, calculates confidence level, and classifies financial health."""

    # Load JSON data
    with open(json_file, "r") as file:
        data = json.load(file)

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

def calculate_profitability_ratios(json_file):
    """
    Function to calculate profitability ratios, confidence level, and classify the company's financial health.
    """
    # Load JSON data
    with open(json_file, "r") as file:
        data = json.load(file)
        
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

def compute_leverage_ratios(json_file):
    """Computes leverage ratios, assigns scores, calculates confidence level, and classifies financial health."""
    # Load JSON data
    with open(json_file, "r") as file:
        data = json.load(file)
        
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

def compute_company_stability(json_file):
    """Computes company stability based on cash flow, sales, EBIT, debt, dividends, and promoter holding trends."""

    # Load JSON data
    with open(json_file, "r") as file:
        data = json.load(file)

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
            return 2  # ✅ Good/Stable
        elif value <= thresholds[1]:
            return 1  # ⚠ Moderate
        return 0  # ❌ Risky/Concerning

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

# Define system messages and tools
def create_financial_analysis_agent(json_file_path=None):
    """
    Creates and runs a financial analysis agent that uses various ratio analysis tools.
    
    Args:
        json_file_path: Path to the financial data JSON file
    """
    
    # Ensure we have a file path
    if not json_file_path:
        print("Error: JSON file path is required")
        return None
    
    # Check if file exists
    if not os.path.exists(json_file_path):
        print(f"Error: File not found at {json_file_path}")
        return None
    
    # Define tools
    tools = [
        {
            "type": "function",
            "function": {
                "name": "compute_operating_ratios",
                "description": "Calculate operating ratios like Fixed Asset Turnover, Working Capital Turnover, Total Asset Turnover, and Inventory Turnover. Returns the values, confidence level, and investment signal.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "json_file": {
                            "type": "string",
                            "description": "Path to the JSON file containing financial data",
                        }
                    },
                    "required": ["json_file"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "calculate_profitability_ratios",
                "description": "Calculate profitability ratios like EBITDA Margin, PAT Margin, ROE, ROCE, and ROA. Returns the values, confidence level, and investment signal.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "json_file": {
                            "type": "string",
                            "description": "Path to the JSON file containing financial data",
                        }
                    },
                    "required": ["json_file"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "compute_leverage_ratios",
                "description": "Calculate leverage ratios like Interest Coverage Ratio, Debt-to-Equity Ratio, Debt-to-Asset Ratio, and Financial Leverage Ratio. Returns the values, confidence level, and investment signal.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "json_file": {
                            "type": "string",
                            "description": "Path to the JSON file containing financial data",
                        }
                    },
                    "required": ["json_file"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "compute_company_stability",
                "description": "Compute company stability based on cash flow, sales, EBIT, debt, dividends, and promoter holding trends. Returns a JSON string with metrics, scores, confidence level, and investment signal.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "json_file": {
                            "type": "string",
                            "description": "Path to the JSON file containing financial data",
                        }
                    },
                    "required": ["json_file"],
                },
            },
        }
    ]
    
    # Map functions to their implementations
    available_functions = {
        "compute_operating_ratios": compute_operating_ratios,
        "calculate_profitability_ratios": calculate_profitability_ratios,
        "compute_leverage_ratios": compute_leverage_ratios,
        "compute_company_stability": compute_company_stability
    }
    
    # Initial messages
    messages = [
        {
            "role": "system", 
            "content": """You are a sophisticated financial analyst specializing in fundamental analysis of companies. 
            Your task is to analyze financial data using operating ratios, profitability ratios, leverage ratios, and company stability metrics.
            Based on the analysis, you should provide an overall investment recommendation.
            
            You have access to tools that can calculate various financial ratios and stability metrics from JSON financial data.
            You should use these tools to perform a comprehensive analysis, and then provide a detailed report
            with your findings and recommendations. Use all available tools to get a complete picture.
            
            Explain the significance of each ratio and metric and what it indicates about the company's financial health and stability.
            Conclude with an overall investment recommendation (Bullish/Buy, Neutral/Hold, or Bearish/Sell) based on
            your comprehensive analysis of all ratio categories and stability factors."""
        },
        {
            "role": "user", 
            "content": f"Please analyze the financial data in the file {json_file_path} and provide a comprehensive fundamental analysis with an investment recommendation and all the relevant numbers."
        }
    ]
    
    # Make the initial request
    try:
        response = groq_client.chat.completions.create(
            model=model, 
            messages=messages, 
            tools=tools, 
            tool_choice="auto", 
            max_completion_tokens=8192
        )
        
        response_message = response.choices[0].message
        messages.append(response_message)
        
        # Process tool calls if any
        if hasattr(response_message, 'tool_calls') and response_message.tool_calls:
            tool_calls = response_message.tool_calls
            
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                print(f"Function Call: {function_name}")
                function_to_call = available_functions[function_name]
                function_args = json.loads(tool_call.function.arguments)
                
                try:
                    function_response = function_to_call(**function_args)
                    print(f"Function Response: {function_response}")
                    messages.append(
                        {
                            "role": "tool",
                            "content": json.dumps(function_response),
                            "tool_call_id": tool_call.id,
                        }
                    )
                except Exception as e:
                    messages.append(
                        {
                            "role": "tool",
                            "content": f"Error: {str(e)}",
                            "tool_call_id": tool_call.id,
                        }
                    )
            
            # Make the final request with tool call results
            final_response = groq_client.chat.completions.create(
                model=model, 
                messages=messages, 
                tools=tools, 
                tool_choice="auto", 
                max_completion_tokens=8192
            )
            
            return final_response.choices[0].message.content
        else:
            # If no tool calls were made
            return response_message.content
            
    except Exception as e:
        print(f"Error: {str(e)}")
        return f"An error occurred: {str(e)}"

# Example usage
if __name__ == "__main__":
    # Check if file path is provided as command line argument
    if len(sys.argv) > 1:
        json_file_path = sys.argv[1]
    else:
        json_file_path = "example.json"  # Default file name
    
    analysis_result = create_financial_analysis_agent(json_file_path)
    print("\n=== FINANCIAL ANALYSIS REPORT ===\n")
    print(analysis_result)