import streamlit as st
import pandas as pd
import numpy as np
import time
import random

# --- Page Configuration ---
st.set_page_config(
    page_title="AI Portfolio Manager",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# --- Constants for Page Names ---
PAGE_LOGIN = "login"
PAGE_INPUT = "input"
PAGE_SCREENING = "screening"
PAGE_FUNDAMENTAL = "fundamental"
PAGE_SENTIMENT = "sentiment"
PAGE_TECHNICAL = "technical"
PAGE_STRATEGY_DEV = "strategy_dev"
PAGE_FINAL_RESULTS = "final_results"

# Define the sequence of pages for navigation (excluding login)
PAGE_SEQUENCE = [
    PAGE_INPUT,
    PAGE_SCREENING,
    PAGE_FUNDAMENTAL,
    PAGE_SENTIMENT,
    PAGE_TECHNICAL,
    PAGE_STRATEGY_DEV,
    PAGE_FINAL_RESULTS,
]

# --- Authentication Check Function ---
def check_password():
    """Returns `True` if the user had the correct password."""

    # Use st.secrets if available, otherwise fallback to a default (NOT RECOMMENDED for production)
    try:
        correct_password = st.secrets["PASSWORD"]
    except FileNotFoundError:
        st.error("Password configuration (`secrets.toml`) not found. Using default (unsafe).")
        correct_password = "password123" # Fallback - CHANGE THIS
    except KeyError:
        st.error("`PASSWORD` not found in `secrets.toml`. Using default (unsafe).")
        correct_password = "password123" # Fallback - CHANGE THIS


    if st.session_state.get("logged_in", False):
        return True

    with st.form("credentials"):
        st.text_input("Password", type="password", key="password")
        submitted = st.form_submit_button("Log in")

        if submitted:
            if st.session_state["password"] == correct_password:
                st.session_state["logged_in"] = True
                st.session_state.current_page = PAGE_INPUT # Go to input page after login
                st.rerun() # Rerun to clear the login form and show the app
            else:
                st.error("😕 Password incorrect")
                st.session_state["logged_in"] = False
    return False

# --- Helper Functions for Navigation ---

def go_to_page(page_name):
    """Sets the session state to navigate to the specified page."""
    if page_name in PAGE_SEQUENCE:
        st.session_state.current_page = page_name
        st.rerun()
    elif page_name == PAGE_LOGIN:
         st.session_state.current_page = PAGE_LOGIN
         st.session_state.logged_in = False # Ensure logged out state
         # Clear sensitive data on logout
         st.session_state.user_inputs = {}
         st.session_state.screening_results = None
         st.session_state.fundamental_results = None
         st.session_state.sentiment_results = None
         st.session_state.technical_results = None
         st.session_state.strategy_dev_results = None
         st.session_state.final_portfolio = None
         st.session_state.selected_stock_strategy_dev = None
         st.rerun()


def go_next():
    """Navigates to the next page in the sequence."""
    try:
        current_index = PAGE_SEQUENCE.index(st.session_state.current_page)
        if current_index < len(PAGE_SEQUENCE) - 1:
            go_to_page(PAGE_SEQUENCE[current_index + 1])
    except ValueError:
        # If current page isn't in sequence (e.g., login), go to first page
        go_to_page(PAGE_INPUT)


def go_back():
    """Navigates to the previous page in the sequence."""
    try:
        current_index = PAGE_SEQUENCE.index(st.session_state.current_page)
        if current_index > 0:
            go_to_page(PAGE_SEQUENCE[current_index - 1])
    except ValueError:
        # Should not happen if navigation is correct, but handle defensively
        go_to_page(PAGE_INPUT)


def reset_app():
    """Resets the app to the initial input page and clears data (keeps login state)."""
    # Keep user inputs if desired, or clear them
    # st.session_state.user_inputs = {}
    st.session_state.screening_results = None
    st.session_state.fundamental_results = None
    st.session_state.sentiment_results = None
    st.session_state.technical_results = None
    st.session_state.strategy_dev_results = None
    st.session_state.final_portfolio = None
    st.session_state.selected_stock_strategy_dev = None # Reset selected stock
    go_to_page(PAGE_INPUT)


# --- Backend Simulation Functions (Modified for Descriptions & Data Structure) ---

def simulate_screening(budget, risk_score, sectors, market_caps, instructions):
    """Simulates initial stock screening. Returns list of tickers."""
    st.write("---")
    st.write(f"**Screening Criteria:** Budget: ${budget:,.0f}, Risk Score: {risk_score}/100, Sectors: {sectors or 'Any'}, Caps: {market_caps or 'Any'}, Instr: '{instructions or 'None'}'")
    with st.spinner("🔍 Applying initial filters (market cap, sector, liquidity, risk)..."):
        time.sleep(random.uniform(3, 6))
        all_tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "JPM", "JNJ", "V", "PG", "META", "XOM", "BRK-B", "LLY", "WMT", "UNH", "MA", "BAC", "CVX", "PFE"]
        # Simulate risk influence - higher risk score allows more volatile/smaller stocks?
        num_potential = int(len(all_tickers) * (0.6 + risk_score / 250)) # Simple risk influence
        num_screened = random.randint(min(15, num_potential), min(30, num_potential))
        screened_tickers = random.sample(all_tickers, min(num_screened, len(all_tickers)))
    st.success(f"Screening complete. Identified {len(screened_tickers)} potential stocks.")
    return {"screened_tickers": screened_tickers} # Return list directly

def simulate_fundamental_analysis(screened_tickers):
    """Simulates fundamental analysis. Returns list of dicts."""
    st.write("---")
    st.write(f"Performing fundamental analysis on {len(screened_tickers)} stocks...")
    results = []
    with st.spinner("📊 Calculating P/E, ROE, Debt-to-Equity..."):
        time.sleep(random.uniform(4, 8))
        for ticker in screened_tickers:
            if random.random() > 0.15: # Keep ~85%
                results.append({
                    "Ticker": ticker,
                    "P/E Ratio": round(random.uniform(10, 50), 2),
                    "ROE (%)": round(random.uniform(5, 25), 2),
                    "Debt/Equity": round(random.uniform(0.1, 1.5), 2),
                    "Analyst Rating": random.choice(["Buy", "Hold", "Strong Buy", "Hold"]),
                    "Dividend Yield (%)": round(random.uniform(0, 4.5), 2) if random.random() > 0.3 else 0.0,
                })
    st.success(f"Fundamental analysis complete. {len(results)} stocks passed.")
    # Return list of dictionaries, store tickers passing this stage
    passing_tickers = [r["Ticker"] for r in results]
    return {"fundamental_data": results, "passing_tickers": passing_tickers}

def simulate_sentiment_analysis(fundamental_results):
    """Simulates sentiment analysis. Returns list of dicts."""
    tickers = fundamental_results["passing_tickers"]
    st.write("---")
    st.write(f"Analyzing news and social media sentiment for {len(tickers)} stocks...")
    results = []
    with st.spinner("📰 Aggregating news headlines and social media mentions..."):
        time.sleep(random.uniform(5, 10))
        for ticker in tickers:
            if random.random() > 0.1: # Keep ~90%
                results.append({
                    "Ticker": ticker,
                    "Sentiment Score": round(random.uniform(-0.5, 0.8), 2), # e.g., -1 to 1
                    "Trending Keywords": ", ".join(random.sample(["AI", "Earnings", "Growth", "Competition", "New Product", "Regulations", "Partnership", "Outlook"], random.randint(1,3))),
                    "News Volume (24h)": random.randint(5, 50),
                    "Social Media Buzz": random.choice(["High", "Medium", "Low"]),
                })
    st.success(f"Sentiment analysis complete. {len(results)} stocks remain relevant.")
    passing_tickers = [r["Ticker"] for r in results]
    return {"sentiment_data": results, "passing_tickers": passing_tickers}

def simulate_technical_analysis(sentiment_results):
    """Simulates technical analysis. Returns list of dicts."""
    tickers = sentiment_results["passing_tickers"]
    st.write("---")
    st.write(f"Performing technical analysis (RSI, MACD, Moving Averages) for {len(tickers)} stocks...")
    results = []
    with st.spinner("📈 Calculating technical indicators..."):
        time.sleep(random.uniform(6, 12))
        for ticker in tickers:
            if random.random() > 0.05: # Keep ~95%
                results.append({
                    "Ticker": ticker,
                    "RSI (14)": round(random.uniform(30, 70), 1),
                    "MACD Signal": random.choice(["Bullish Crossover", "Bearish Crossover", "Neutral"]),
                    "Price vs MA(50)": random.choice(["Above", "Below", "Touching"]),
                    "Trend (Short Term)": random.choice(["Uptrend", "Downtrend", "Sideways"]),
                    "Volatility (ATR)": round(random.uniform(0.5, 5.0), 2),
                })
    st.success(f"Technical analysis complete. {len(results)} stocks selected for strategy development.")
    passing_tickers = [r["Ticker"] for r in results]
    return {"technical_data": results, "passing_tickers": passing_tickers}

def simulate_strategy_dev(technical_results):
    """Simulates developing and backtesting strategies for each stock. Includes descriptions."""
    tickers = technical_results["passing_tickers"]
    st.write("---")
    st.write(f"Developing and backtesting strategies for {len(tickers)} stocks...")
    strategy_results = {}
    strategy_descriptions = {
        "Momentum": "Buys stocks showing strong upward price trends, aiming to ride the wave.",
        "Mean Reversion": "Buys stocks after a significant price drop, expecting a rebound towards their average price.",
        "MA Crossover": "Uses moving average crossovers (e.g., 50-day crossing 200-day) as buy/sell signals.",
        "Value Dip Buy": "Identifies fundamentally sound stocks that have experienced a temporary price dip.",
        "Volatility Breakout": "Enters positions when price breaks out of a defined range, indicating potential strong movement.",
        "Dividend Growth": "Focuses on stocks with a history of consistently increasing dividend payouts."
    }

    with st.spinner("⚙️ Backtesting multiple strategies..."):
        time.sleep(random.uniform(8, 15))
        for ticker in tickers:
            stock_strategies = []
            possible_strategy_names = list(strategy_descriptions.keys())
            num_strategies_per_stock = random.randint(2, 3)

            for i in range(num_strategies_per_stock):
                strategy_name_base = random.choice(possible_strategy_names)
                strategy_name = f"{strategy_name_base} #{i+1}"
                description = strategy_descriptions.get(strategy_name_base, "A custom strategy based on analysis.")

                # Simulate backtesting performance data (same as before)
                dates = pd.date_range(end=pd.Timestamp.now()-pd.Timedelta(days=1), periods=60, freq='M')
                start_value = 10000
                returns = np.random.normal(loc=random.uniform(0.005, 0.02), scale=random.uniform(0.04, 0.1), size=len(dates)-1)
                cumulative_returns = (1 + returns).cumprod()
                portfolio_values = start_value * np.insert(cumulative_returns, 0, 1.0)
                backtest_df = pd.DataFrame({'Date': dates, 'Value': portfolio_values}).set_index('Date')

                total_return = (portfolio_values[-1] / start_value - 1) * 100
                annualized_return = ((1 + total_return / 100)**(1 / 5) - 1) * 100
                volatility = returns.std() * np.sqrt(12) * 100
                sharpe_ratio = (annualized_return - 2.0) / volatility if volatility > 0 else 0
                max_drawdown = (1 - (portfolio_values / np.maximum.accumulate(portfolio_values))).max() * 100

                stock_strategies.append({
                    "strategy_name": strategy_name,
                    "description": description, # Added description
                    "metrics": {
                        "Total Return (%)": total_return,
                        "Annualized Return (%)": annualized_return,
                        "Volatility (%)": volatility,
                        "Sharpe Ratio": sharpe_ratio,
                        "Max Drawdown (%)": max_drawdown,
                    },
                    "chart_data": backtest_df
                })
            strategy_results[ticker] = stock_strategies
    st.success("Strategy development and backtesting complete.")
    return {"strategies_per_stock": strategy_results, "final_stock_list": tickers}

def simulate_final_selection(strategy_dev_data, risk_score):
    """Simulates selecting the best stock/strategy combinations. Returns list of dicts."""
    strategies_per_stock = strategy_dev_data["strategies_per_stock"]
    tickers = strategy_dev_data["final_stock_list"]
    st.write("---")
    st.write(f"Selecting best strategies based on performance and risk score ({risk_score}/100)...")
    final_portfolio = []
    # Higher risk score might allow selection of slightly more stocks or higher return/volatility strategies
    num_final_stocks = random.randint(max(3, int(6 * (risk_score / 100))), min(max(5, int(15 * (risk_score / 100))), len(tickers)))
    selected_tickers = random.sample(tickers, min(num_final_stocks, len(tickers)))

    with st.spinner("🏆 Choosing optimal stock/strategy pairs and calculating allocations..."):
        time.sleep(random.uniform(3, 6))
        for ticker in selected_tickers:
            if ticker in strategies_per_stock and strategies_per_stock[ticker]:
                # Risk-adjusted selection: Higher risk score favors Sharpe, lower might favor lower Volatility?
                # Simple example: Use Sharpe, but could be more complex
                best_strategy = max(strategies_per_stock[ticker], key=lambda s: s["metrics"]["Sharpe Ratio"])

                # Could add logic here: if risk_score < 30, maybe prefer strategies with Volatility < X?

                final_portfolio.append({
                    "Ticker": ticker,
                    "Chosen Strategy": best_strategy["strategy_name"],
                    "Strategy Description": best_strategy["description"],
                    "Annualized Return (%)": best_strategy["metrics"]["Annualized Return (%)"],
                    "Volatility (%)": best_strategy["metrics"]["Volatility (%)"],
                    "Sharpe Ratio": best_strategy["metrics"]["Sharpe Ratio"],
                    # Allocation would be determined by a portfolio optimization step
                    "Allocation (%)": round(100 / num_final_stocks + random.uniform(-5, 5), 2) # Dummy allocation
                })
        # Normalize allocations
        if final_portfolio:
            total_alloc = sum(item["Allocation (%)"] for item in final_portfolio)
            if total_alloc > 0:
                 for item in final_portfolio:
                    item["Allocation (%)"] = round(max(0, item["Allocation (%)"] * 100 / total_alloc), 2)

    st.success("Final portfolio constructed.")
    return {"final_portfolio": final_portfolio} # Return list of dicts


# --- Initialize Session State ---
if 'current_page' not in st.session_state:
    st.session_state.current_page = PAGE_LOGIN # Start at login
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
# ... (initialize other state variables as before) ...
if 'user_inputs' not in st.session_state:
    st.session_state.user_inputs = {}
if 'screening_results' not in st.session_state:
    st.session_state.screening_results = None
if 'fundamental_results' not in st.session_state:
    st.session_state.fundamental_results = None
if 'sentiment_results' not in st.session_state:
    st.session_state.sentiment_results = None
if 'technical_results' not in st.session_state:
    st.session_state.technical_results = None
if 'strategy_dev_results' not in st.session_state:
    st.session_state.strategy_dev_results = None
if 'final_portfolio' not in st.session_state:
    st.session_state.final_portfolio = None
if 'selected_stock_strategy_dev' not in st.session_state:
     st.session_state.selected_stock_strategy_dev = None


# --- Main App Logic ---

# Check login status first
if not check_password():
    st.stop() # Stop execution if not logged in

# --- Logout Button (appears on all pages after login) ---
st.sidebar.button("Logout", on_click=go_to_page, args=(PAGE_LOGIN,))
st.sidebar.markdown("---") # Separator

# --- Page Rendering Logic (Only if logged in) ---

# --- Page 1: Input Page ---
if st.session_state.current_page == PAGE_INPUT:
    st.title("🤖 AI Portfolio Manager - Input Your Preferences")
    st.markdown("Describe your investment goals or specific stocks. Use advanced filters for more control.")

    with st.form("portfolio_input_form"):
        instructions = st.text_area(
            "**Describe your investment goals or instructions:**",
            height=150,
            placeholder="e.g., 'Invest $20,000 in high-growth tech stocks with good environmental ratings', 'Focus on dividend-paying stocks in the healthcare sector', 'Analyze potential for AAPL and MSFT'"
        )

        with st.expander("Advanced Filters (Optional)"):
            budget = st.number_input("Budget ($)", min_value=1000, value=10000, step=1000, format="%d")
            # --- Risk Slider ---
            risk_score = st.slider("Risk Score (1=Low Risk, 100=High Risk)", min_value=1, max_value=100, value=50)
            sectors = st.multiselect("Preferred Sectors", ["Technology", "Healthcare", "Finance", "Consumer Discretionary", "Consumer Staples", "Industrials", "Energy", "Utilities", "Real Estate", "Materials"])
            market_caps = st.multiselect("Preferred Market Cap", ["Small-Cap", "Mid-Cap", "Large-Cap"], default=["Mid-Cap", "Large-Cap"])

        submitted = st.form_submit_button("🚀 Start AI Analysis")

        if submitted:
            # Store inputs
            st.session_state.user_inputs = {
                "budget": budget,
                "risk_score": risk_score, # Store risk score
                "sectors": sectors,
                "market_caps": market_caps,
                "instructions": instructions
            }
            # Clear previous results
            st.session_state.screening_results = None
            st.session_state.fundamental_results = None
            st.session_state.sentiment_results = None
            st.session_state.technical_results = None
            st.session_state.strategy_dev_results = None
            st.session_state.final_portfolio = None
            st.session_state.selected_stock_strategy_dev = None

            go_to_page(PAGE_SCREENING)

# --- Page 2: Screening Page ---
elif st.session_state.current_page == PAGE_SCREENING:
    st.title("Step 1: Initial Stock Screening")
    inputs = st.session_state.user_inputs

    if not inputs:
        st.error("User inputs not found. Please start again.")
        st.button("Go Back to Input", on_click=reset_app)
    else:
        if st.session_state.screening_results is None:
            st.session_state.screening_results = simulate_screening(
                inputs["budget"], inputs["risk_score"], inputs["sectors"], inputs["market_caps"], inputs["instructions"]
            )

        results = st.session_state.screening_results
        if results and "screened_tickers" in results and results["screened_tickers"]:
            st.subheader("Screened Stock Tickers:")
            # --- Display tickers as text ---
            ticker_string = ", ".join(results["screened_tickers"])
            st.markdown(f"> {ticker_string}")
            st.caption(f"Found {len(results['screened_tickers'])} potential stocks matching initial criteria.")
            can_proceed = True
        else:
            st.warning("Screening did not yield results based on the criteria.")
            can_proceed = False

        # Navigation buttons
        col1, col2 = st.columns([1, 1])
        with col1:
            st.button("⬅️ Back to Input", on_click=go_back, use_container_width=True)
        with col2:
            st.button("Next: Fundamental Analysis ➡️", on_click=go_next, use_container_width=True, type="primary", disabled=not can_proceed)

# --- Page 3: Fundamental Analysis Page ---
elif st.session_state.current_page == PAGE_FUNDAMENTAL:
    st.title("Step 2: Fundamental Analysis")
    prev_results = st.session_state.screening_results

    if not prev_results or "screened_tickers" not in prev_results or not prev_results["screened_tickers"]:
        st.error("Screening results not found or empty. Please go back.")
        st.button("⬅️ Back to Screening", on_click=go_back)
    else:
        if st.session_state.fundamental_results is None:
            st.session_state.fundamental_results = simulate_fundamental_analysis(prev_results["screened_tickers"])

        results = st.session_state.fundamental_results
        if results and "fundamental_data" in results and results["fundamental_data"]:
            st.subheader(f"Fundamental Analysis Results ({len(results['fundamental_data'])} Stocks Passed):")
            # --- Display using expanders and metrics ---
            for stock_data in results["fundamental_data"]:
                with st.expander(f"**{stock_data['Ticker']}** - Rating: {stock_data['Analyst Rating']}"):
                    col1, col2, col3 = st.columns(3)
                    col1.metric("P/E Ratio", f"{stock_data['P/E Ratio']:.2f}")
                    col2.metric("ROE", f"{stock_data['ROE (%)']:.2f}%")
                    col3.metric("Debt/Equity", f"{stock_data['Debt/Equity']:.2f}")
                    col1.metric("Dividend Yield", f"{stock_data['Dividend Yield (%)']:.2f}%")
            can_proceed = True
        else:
            st.warning("Fundamental analysis did not yield results or filter out all stocks.")
            can_proceed = False

        # Navigation buttons
        col1, col2 = st.columns([1, 1])
        with col1:
            st.button("⬅️ Back to Screening", on_click=go_back, use_container_width=True)
        with col2:
            st.button("Next: Sentiment Analysis ➡️", on_click=go_next, use_container_width=True, type="primary", disabled=not can_proceed)

# --- Page 4: Sentiment Analysis Page ---
elif st.session_state.current_page == PAGE_SENTIMENT:
    st.title("Step 3: Sentiment & News Analysis")
    prev_results = st.session_state.fundamental_results

    if not prev_results or "passing_tickers" not in prev_results or not prev_results["passing_tickers"]:
        st.error("Fundamental analysis results not found or empty. Please go back.")
        st.button("⬅️ Back to Fundamental Analysis", on_click=go_back)
    else:
        if st.session_state.sentiment_results is None:
            st.session_state.sentiment_results = simulate_sentiment_analysis(prev_results)

        results = st.session_state.sentiment_results
        if results and "sentiment_data" in results and results["sentiment_data"]:
            st.subheader(f"Sentiment Analysis Results ({len(results['sentiment_data'])} Stocks Passed):")
             # --- Display using expanders and metrics/text ---
            for stock_data in results["sentiment_data"]:
                 with st.expander(f"**{stock_data['Ticker']}** - Score: {stock_data['Sentiment Score']:.2f}"):
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Sentiment Score", f"{stock_data['Sentiment Score']:.2f}")
                    col2.metric("News Volume (24h)", stock_data['News Volume (24h)'])
                    col3.metric("Social Buzz", stock_data['Social Media Buzz'])
                    st.markdown(f"**Trending Keywords:** {stock_data['Trending Keywords']}")
            can_proceed = True
        else:
            st.warning("Sentiment analysis did not yield results or filter out all stocks.")
            can_proceed = False

        # Navigation buttons
        col1, col2 = st.columns([1, 1])
        with col1:
            st.button("⬅️ Back to Fundamental Analysis", on_click=go_back, use_container_width=True)
        with col2:
            st.button("Next: Technical Analysis ➡️", on_click=go_next, use_container_width=True, type="primary", disabled=not can_proceed)

# --- Page 5: Technical Analysis Page ---
elif st.session_state.current_page == PAGE_TECHNICAL:
    st.title("Step 4: Technical Analysis")
    prev_results = st.session_state.sentiment_results

    if not prev_results or "passing_tickers" not in prev_results or not prev_results["passing_tickers"]:
        st.error("Sentiment analysis results not found or empty. Please go back.")
        st.button("⬅️ Back to Sentiment Analysis", on_click=go_back)
    else:
        if st.session_state.technical_results is None:
            st.session_state.technical_results = simulate_technical_analysis(prev_results)

        results = st.session_state.technical_results
        if results and "technical_data" in results and results["technical_data"]:
            st.subheader(f"Technical Analysis Results ({len(results['technical_data'])} Stocks Passed):")
            # --- Display using expanders and metrics/text ---
            for stock_data in results["technical_data"]:
                 with st.expander(f"**{stock_data['Ticker']}** - Trend: {stock_data['Trend (Short Term)']}"):
                    col1, col2, col3 = st.columns(3)
                    col1.metric("RSI (14)", f"{stock_data['RSI (14)']:.1f}")
                    col2.metric("Volatility (ATR)", f"{stock_data['Volatility (ATR)']:.2f}")
                    col3.write(f"**MACD:** {stock_data['MACD Signal']}")
                    st.write(f"**Price vs MA(50):** {stock_data['Price vs MA(50)']}")
            can_proceed = True
        else:
            st.warning("Technical analysis did not yield results or filter out all stocks.")
            can_proceed = False

        # Navigation buttons
        col1, col2 = st.columns([1, 1])
        with col1:
            st.button("⬅️ Back to Sentiment Analysis", on_click=go_back, use_container_width=True)
        with col2:
            st.button("Next: Strategy Development ➡️", on_click=go_next, use_container_width=True, type="primary", disabled=not can_proceed)

# --- Page 6: Strategy Development Page ---
elif st.session_state.current_page == PAGE_STRATEGY_DEV:
    st.title("Step 5: Stock-Wise Strategy Development & Backtesting")
    prev_results = st.session_state.technical_results

    if not prev_results or "passing_tickers" not in prev_results or not prev_results["passing_tickers"]:
        st.error("Technical analysis results not found or empty. Please go back.")
        st.button("⬅️ Back to Technical Analysis", on_click=go_back)
    else:
        if st.session_state.strategy_dev_results is None:
            st.session_state.strategy_dev_results = simulate_strategy_dev(prev_results)

        results = st.session_state.strategy_dev_results
        if results and "strategies_per_stock" in results and results["strategies_per_stock"]:
            st.subheader("Backtested Strategies per Stock")
            stock_list = results["final_stock_list"]

            if not stock_list:
                 st.warning("No stocks remaining after technical analysis for strategy development.")
                 can_proceed = False
            else:
                # Use session state to remember the selected stock
                if 'selected_stock_strategy_dev' not in st.session_state or st.session_state.selected_stock_strategy_dev not in stock_list:
                    st.session_state.selected_stock_strategy_dev = stock_list[0]

                selected_stock = st.selectbox(
                    "Select a stock to view its backtested strategies:",
                    stock_list,
                    index=stock_list.index(st.session_state.selected_stock_strategy_dev) if st.session_state.selected_stock_strategy_dev in stock_list else 0,
                    key="strategy_stock_selector" # Add key for stability
                )
                # Update state immediately if selection changes (selectbox handles this implicitly with key)
                st.session_state.selected_stock_strategy_dev = selected_stock


                if selected_stock and selected_stock in results["strategies_per_stock"]:
                    st.markdown(f"#### Strategies for {selected_stock}:")
                    stock_strategies = results["strategies_per_stock"][selected_stock]
                    if not stock_strategies:
                        st.write("No specific strategies developed or backtested successfully for this stock.")

                    for i, strategy in enumerate(stock_strategies):
                        with st.container(border=True): # Use container with border instead of expander
                            st.subheader(f"Strategy: {strategy['strategy_name']}")
                            # --- Display Strategy Description ---
                            st.markdown(f"*{strategy['description']}*")
                            st.markdown("**Performance Metrics:**")
                            metrics = strategy["metrics"]
                            m_col1, m_col2, m_col3 = st.columns(3)
                            m_col1.metric("Ann. Return", f"{metrics['Annualized Return (%)']:.2f}%")
                            m_col2.metric("Volatility", f"{metrics['Volatility (%)']:.2f}%")
                            m_col3.metric("Sharpe Ratio", f"{metrics['Sharpe Ratio']:.2f}")
                            m_col1.metric("Total Return", f"{metrics['Total Return (%)']:.2f}%")
                            m_col2.metric("Max Drawdown", f"{metrics['Max Drawdown (%)']:.2f}%")

                            st.markdown("**Backtest Performance Chart:**")
                            st.line_chart(strategy["chart_data"])
                    can_proceed = True
                else:
                    st.warning(f"No strategy data found for {selected_stock}")
                    can_proceed = False # Or True if other stocks exist? Decide UX.

        else:
            st.warning("Strategy development did not yield results.")
            can_proceed = False

        # Navigation buttons
        col1, col2 = st.columns([1, 1])
        with col1:
            st.button("⬅️ Back to Technical Analysis", on_click=go_back, use_container_width=True)
        with col2:
            st.button("Next: Final Portfolio ➡️", on_click=go_next, use_container_width=True, type="primary", disabled=not can_proceed)


# --- Page 7: Final Results Page ---
elif st.session_state.current_page == PAGE_FINAL_RESULTS:
    st.title("🏆 Final AI-Generated Portfolio")
    prev_results = st.session_state.strategy_dev_results
    inputs = st.session_state.user_inputs

    if not prev_results or "strategies_per_stock" not in prev_results or not prev_results["strategies_per_stock"]:
        st.error("Strategy development results not found or empty. Please go back.")
        st.button("⬅️ Back to Strategy Development", on_click=go_back)
    elif not inputs:
         st.error("User inputs not found. Please start again.")
         st.button("Go Back to Input", on_click=reset_app)
    else:
        if st.session_state.final_portfolio is None:
            st.session_state.final_portfolio = simulate_final_selection(prev_results, inputs["risk_score"])

        results_data = st.session_state.final_portfolio
        if results_data and "final_portfolio" in results_data and results_data["final_portfolio"]:
            st.subheader("Recommended Portfolio Allocation")
            final_portfolio_list = results_data["final_portfolio"]
            budget = inputs.get('budget', 10000) # Default budget if not found

            total_allocated_amount = 0
            # --- Display using containers/metrics ---
            for stock_info in final_portfolio_list:
                with st.container(border=True):
                    alloc_percent = stock_info['Allocation (%)']
                    amount = alloc_percent / 100 * budget
                    total_allocated_amount += amount

                    st.subheader(f"{stock_info['Ticker']} ({alloc_percent:.2f}%)")
                    st.markdown(f"**Strategy:** {stock_info['Chosen Strategy']}")
                    st.caption(f"{stock_info['Strategy Description']}")

                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Allocation", f"{alloc_percent:.2f}%")
                    col2.metric("Amount", f"${amount:,.2f}")
                    col3.metric("Exp. Ann. Return", f"{stock_info['Annualized Return (%)']:.2f}%")
                    # col4.metric("Exp. Volatility", f"{stock_info['Volatility (%)']:.2f}%") # Optional
                    col4.metric("Exp. Sharpe Ratio", f"{stock_info['Sharpe Ratio']:.2f}")

            st.markdown("---")
            st.subheader("Portfolio Summary")
            summary_col1, summary_col2 = st.columns(2)
            summary_col1.metric("Total Budget", f"${budget:,.2f}")
            summary_col2.metric("Total Allocated", f"${total_allocated_amount:,.2f}")
            # You could calculate weighted average expected return/risk here if desired
            st.caption(f"Based on Risk Score: {inputs.get('risk_score', 'N/A')}/100")

        else:
            st.warning("Could not construct a final portfolio based on the analysis.")

        # Navigation buttons
        col1, col2 = st.columns([1, 1])
        with col1:
            st.button("⬅️ Back to Strategy Development", on_click=go_back, use_container_width=True)
        with col2:
            st.button("🔄 Start New Analysis", on_click=reset_app, use_container_width=True, type="primary")


# --- Fallback for unknown state ---
else:
    # This case should ideally not be reached if login and navigation are correct
    st.error("An unexpected error occurred or page state is invalid. Resetting to login.")
    time.sleep(2)
    go_to_page(PAGE_LOGIN) # Reset to login page
