import json
from src.llm.models import get_model  # Assuming same model setup as previous example

groq_client = get_model(model_provider="GROQ")

investment_filter_rules = """
**Investment Filter Rulebook**

1. **General Investing**: If no specifications given:
   - Market Cap: Large
   - Index: Nifty50

2. **Low Risk Tolerance**:
   - Market Cap: Large
   - Index: Nifty50
   - Dividend Payment: True
   - Volatility: Low
   - P/E Ratio: "Stable compared to sector"

3. **Moderate Risk Tolerance**:
   - Market Cap: Large/Mid
   - Index: Nifty50
   - Dividend Payment: True

4. **High Risk Tolerance**:
   - Market Cap: Small
   - Growth Potential: High
   - Volatility: High

5. **Short-Term High Returns**:
   - Market Cap: Mid/Small
   - Volatility: High
   - Sales Growth: >15% YoY
   - Profit Growth: >20% YoY

6. **Trending Stocks**:
   - Index: Nifty50
   - Market Sentiment: High
   - Sector Trends: Match current trends

7. **Stock Comparison**:
   - If multiple stocks mentioned:
     - Compare sector metrics
     - Relative P/E, ROE, D/E ratios
     - Market position within sector

8. **Long-Term Wealth Building** (5+ years):
   - Revenue Growth: >10% CAGR (5y)
   - ROE: >15%
   - D/E Ratio: <0.5
   - Volatility: <Sector Average

9. **Institutional Favorites**:
   - Mutual Fund Holdings: >30%
   - FII Holdings: >20%
   - Promoter Stake: Increasing trend

10. **Recession-Proof**:
    - D/E Ratio: <0.3
    - Current Ratio: >2
    - Cash Reserves: >10% of Market Cap
"""

def parse_investment_response(response_content):
    """Parse LLM response and validate structure"""
    try:
        # Directly parse the response content as JSON.
        filters = json.loads(response_content)
        
        # Validate required fields
        required_fields = ['market_cap', 'risk_appetite', 'index_inclusion']
        for field in required_fields:
            if field not in filters:
                return {"error": f"Missing required field: {field}"}
        
        return filters
    except json.JSONDecodeError:
        return {"error": "Invalid JSON format"}
    except Exception as e:
        return {"error": f"Parsing error: {str(e)}"}

def get_investment_filters(user_prompt):
    """Main function to get investment filters for a user prompt"""
    system_prompt = f"""You are a financial analyst robot. Analyze the user's investment prompt and generate stock filters based on this rulebook:

{investment_filter_rules}

Return JSON filters with this structure:
{{
  "investment_amount": "null|specific_amount",
  "market_cap": ["large", "mid", "small"],
  "ratios": {{
    "pe_ratio": "value|sector comparison",
    "sales_growth": "percentage",
    "roe": "percentage",
    "de_ratio": "number",
    "current_ratio": "number",
    "cash_reserve": "percentage"
  }},
  "dividend_payment": "boolean",
  "volatility": "low|medium|high",
  "index_inclusion": ["Nifty50", "Sensex", "etc."],
  "sector_trends": ["trending sectors"],
  "risk_appetite": "low|medium|high",
  "reinvestment_rd_capex": "boolean|percentage",
  "institutional_holdings": {{
    "mutual_funds": "percentage",
    "fii": "percentage",
    "promoter_stake": "trend"
  }},
  "foreign_exposure": "percentage"
}}"""

    try:
        completion = groq_client.chat.completions.create(
            model="deepseek-r1-distill-llama-70b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1,
            max_tokens=2000,
            response_format={"type": "json_object"}
        )
        
        response_content = completion.choices[0].message.content
        # Optionally print the raw response for debugging:
        print("RAW RESPONSE:", response_content)
        return parse_investment_response(response_content)
    
    except Exception as e:
        return {"error": str(e)}

# Example usage
if __name__ == "__main__":
    test_prompts = [
        "I have ₹5 lakh to invest with low risk tolerance",
        "Looking for high growth stocks that can double in 1 year",
        "Want recession-proof companies with strong fundamentals",
        "Compare Reliance, TCS, and Infosys for long-term investment"
    ]

    for prompt in test_prompts:
        print(f"\nPrompt: {prompt}")
        filters = get_investment_filters(prompt)
        print("Generated Filters:")
        print(json.dumps(filters, indent=2))