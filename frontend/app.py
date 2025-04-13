import streamlit as st
import pandas as pd
import numpy as np
import time
import random
import uuid
from datetime import datetime, timedelta
import os
import json
from streamlit_cookies_manager import EncryptedCookieManager

from src.data_source.apis_1 import get_live_price
from src.data_source.apis_2 import get_live_indices_pricing
from src.data_source.apis_3 import get_tickertape_movers, search_tickertape_stocks
from src.routers.auth import authenticate_user
from src.routers.trading import add_funds_to_portfolio, execute_paper_trade, get_detailed_paper_portfolio, get_paper_portfolio, get_paper_transactions

# --- Page Configuration ---
st.set_page_config(
    page_title="AI Portfolio Manager", # Page title in the browser tab
    layout="wide", # "wide" or "centered" or "full"
    initial_sidebar_state="expanded", # "expanded" or "collapsed" or "auto"
    page_icon="💰", # Icon in the browser tab
)

# --- Constants ---
PAGE_LOGIN = "login"
PAGE_HOME = "home" # New Home Page
PAGE_DASHBOARD = "dashboard"
PAGE_NEW_ANALYSIS = "new_analysis"
PAGE_JOB_STATUS = "job_status"
PAGE_PAPER_TRADE = "paper_trade" # New Paper Trading Page
LOGIN_COOKIE_NAME = "ai_hedge_fund_user_session" # Choose a name
COOKIE_EXPIRY_DAYS = 7 # How long the login persists

# Job Statuses
STATUS_PENDING = "⏳ Pending"
STATUS_RUNNING = "⚙️ Running"
STATUS_COMPLETED = "✅ Completed"
STATUS_FAILED = "❌ Failed"

# Analysis Steps (Order Matters!)
STEP_SCREENING = "Screening"
STEP_FUNDAMENTAL = "Fundamental Analysis"
STEP_SENTIMENT = "Sentiment Analysis"
STEP_TECHNICAL = "Technical Analysis"
STEP_STRATEGY_DEV = "Strategy Development"
STEP_FINAL_SELECTION = "Final Portfolio Selection"
STEP_COMPLETE = "Complete" # Represents the end state

ANALYSIS_STEPS = [
    STEP_SCREENING,
    STEP_FUNDAMENTAL,
    STEP_SENTIMENT,
    STEP_TECHNICAL,
    STEP_STRATEGY_DEV,
    STEP_FINAL_SELECTION,
    STEP_COMPLETE,
]

# --- Initialize Cookie Manager ---
# IMPORTANT: Set a secret password. Use environment variables or secrets management for production.
cookie_password = os.environ.get("STREAMLIT_COOKIE_PASSWORD", "admin")
# Use EncryptedCookieManager for better security than plain CookieManager
cookies = EncryptedCookieManager(
    password=cookie_password, # Must be set!
    prefix="ai_hedge_fund/",
)
if not cookies.ready():
    # Wait for cookie manager hydration
    st.spinner("Loading session...")
    st.stop()

# --- File Paths for Persistent Data ---
DATA_DIR = "data" # Store data in a sub-directory
JOBS_FILE = os.path.join(DATA_DIR, "jobs_data.json")

# --- Ensure Data Directory Exists ---
os.makedirs(DATA_DIR, exist_ok=True)

_persistent_jobs_data = None

def load_jobs_data():
    """Loads the entire jobs data structure from the JSON file."""
    global _persistent_jobs_data
    if _persistent_jobs_data is None:
        try:
            with open(JOBS_FILE, 'r') as f:
                _persistent_jobs_data = json.load(f)
                if not isinstance(_persistent_jobs_data, dict): _persistent_jobs_data = {}
        except (FileNotFoundError, json.JSONDecodeError):
            _persistent_jobs_data = {}
    return _persistent_jobs_data

def save_jobs_data():
    """Saves the current state of jobs data to the JSON file."""
    global _persistent_jobs_data
    if _persistent_jobs_data is None: return
    try:
        def convert_datetime(obj):
            if isinstance(obj, datetime): return obj.isoformat()
            if isinstance(obj, pd.Timestamp): return obj.isoformat()
            if isinstance(obj, pd.DataFrame): return None # Omit DataFrames
            if isinstance(obj, np.ndarray): return obj.tolist()
            return obj
        with open(JOBS_FILE, 'w') as f:
            json.dump(_persistent_jobs_data, f, indent=4, default=convert_datetime)
    except (IOError, TypeError) as e: st.error(f"Error saving jobs data: {e}")

# --- Initialize Persistent Data on App Start ---
load_jobs_data()

# --- Session State Initialization ---
def initialize_session():
    """Initializes session state variables."""
    if 'logged_in_user' not in st.session_state:
        if cookies.get(LOGIN_COOKIE_NAME) is not None and cookies.get(LOGIN_COOKIE_NAME) != "logout":
            st.session_state.logged_in_user = cookies.get(LOGIN_COOKIE_NAME)
        else:
            st.session_state.logged_in_user = None
    if 'current_page' not in st.session_state:
        st.session_state.current_page = PAGE_LOGIN
    if 'selected_job_id' not in st.session_state:
        st.session_state.selected_job_id = None
    if 'home_market_cap_filter' not in st.session_state:
        st.session_state.home_market_cap_filter = "LargeCap"
    # State for proposed trades on paper trading page
    if 'proposed_trades' not in st.session_state:
        st.session_state.proposed_trades = None # Stores list of dicts like {"Ticker": "AAPL", "Target Amount": 10000}
    if 'reviewed_trades' not in st.session_state:
        st.session_state.reviewed_trades = None # Stores calculated trades for final confirmation
    # State for home page stock search
    if 'home_search_query' not in st.session_state: # <-- ADD THIS
        st.session_state.home_search_query = ""     # <-- ADD THIS

initialize_session()

# --- User/Job Data Access Functions (using persistent storage) ---

def get_user_jobs(username):
    """Retrieves jobs for a specific user from the persistent store."""
    all_jobs = load_jobs_data()
    return all_jobs.get(username, {}).copy()

def save_job(username, job_id, job_data):
    """Saves/updates job data for a user in the persistent store."""
    global _persistent_jobs_data
    if _persistent_jobs_data is None: _persistent_jobs_data = {}
    if username not in _persistent_jobs_data: _persistent_jobs_data[username] = {}
    _persistent_jobs_data[username][job_id] = job_data
    save_jobs_data()

def create_new_job(username, inputs):
    """Creates a new job record and saves it persistently."""
    job_id = f"job_{uuid.uuid4().hex[:8]}"
    job_data = {
        "id": job_id, "user": username, "inputs": inputs, "status": STATUS_PENDING,
        "current_step": None, "submitted_at": datetime.now(), "started_at": None,
        "completed_at": None,
        "progress_log": [f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Job created and queued."],
        "results": {}, "error_message": None,
    }
    save_job(username, job_id, job_data)
    return job_id

# --- Authentication ---

def check_login():
    """Handles user login using hashed passwords from the persistent store."""
    if st.session_state.logged_in_user:
        return True

    st.title("🔒 AI Portfolio Manager Login")
    with st.form("login_form"):
        username = st.text_input("Username").lower()
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

        if submitted:
            authenticated_user_info = authenticate_user(username, password)
            if authenticated_user_info:
                st.session_state.logged_in_user = username
                st.session_state.current_page = PAGE_HOME # Default to home after login
                # Clear any leftover proposed trades from previous sessions/users
                st.session_state.proposed_trades = None
                st.session_state.reviewed_trades = None
                # --- SET COOKIE ---
                cookies[LOGIN_COOKIE_NAME] = username
                cookies.save()
                # --- End SET COOKIE ---

                st.success(f"Welcome, {username}!") # Show feedback before rerun
                time.sleep(0.5) # Short delay for user to see message
                st.rerun() # Rerun to show the main app UI
            else:
                st.error("Invalid username or password.")

    return False

def navigate_to(page_name, job_id=None, clear_proposed=False):
    st.session_state.current_page = page_name
    st.session_state.selected_job_id = job_id
    if clear_proposed: # Option to clear proposed trades when navigating away
        st.session_state.proposed_trades = None
        st.session_state.reviewed_trades = None
    st.rerun()

def display_sidebar():
    if not st.session_state.logged_in_user: return

    st.sidebar.header(f"Welcome, {st.session_state.logged_in_user}!")
    st.sidebar.button("🏠 Home", on_click=navigate_to, args=(PAGE_HOME, None, True), use_container_width=True, type="primary" if st.session_state.current_page == PAGE_HOME else "secondary")
    # st.sidebar.button("⚙️ AI Analysis Dashboard", on_click=navigate_to, args=(PAGE_DASHBOARD, None, True), use_container_width=True, type="primary" if st.session_state.current_page == PAGE_DASHBOARD else "secondary")
    st.sidebar.button("➕ Start New Analysis", on_click=navigate_to, args=(PAGE_NEW_ANALYSIS, None, True), use_container_width=True, type="primary" if st.session_state.current_page == PAGE_NEW_ANALYSIS else "secondary")
    st.sidebar.button("📊 View Analysis Jobs", on_click=navigate_to, args=(PAGE_JOB_STATUS, None, True), use_container_width=True, type="primary" if st.session_state.current_page == PAGE_JOB_STATUS else "secondary")
    st.sidebar.button("📄 Paper Trading", on_click=navigate_to, args=(PAGE_PAPER_TRADE, None, False), use_container_width=True, type="primary" if st.session_state.current_page == PAGE_PAPER_TRADE else "secondary") # Don't clear proposed trades when going here
    
    st.sidebar.markdown("---") # Separator

    # --- Refresh Button ---
    if st.sidebar.button("🔄 Refresh Data", use_container_width=True, key="manual_refresh"):
        st.rerun() # Trigger a full rerun to refresh data
        
    st.sidebar.markdown("---")
    st.sidebar.button("🚪 Logout", on_click=logout, use_container_width=True)

def logout():
    if LOGIN_COOKIE_NAME in cookies: # Check if the cookie exists before deleting
        cookies[LOGIN_COOKIE_NAME]  = "logout"
        cookies.save() # Save the changes
        print(f"Deleted cookie: {LOGIN_COOKIE_NAME}") # Optional: for debugging
    else:
        print(f"Cookie {LOGIN_COOKIE_NAME} not found to delete.") # Optional: for debugging
    keys_to_clear = ['logged_in_user', 'selected_job_id', 'current_page', 'proposed_trades', 'reviewed_trades']
    for key in keys_to_clear:
        if key in st.session_state: del st.session_state[key]
    st.session_state.current_page = PAGE_LOGIN
    initialize_session()
    st.rerun()


# --- Backend Simulation Functions (Step-by-Step Execution) ---
# (run_screening_step updated to include more info, others conceptually same)
def run_screening_step(job_data):
    inputs = job_data["inputs"]
    job_data["progress_log"].append(f"[{datetime.now():%H:%M:%S}] Starting Screening...")
    time.sleep(random.uniform(1, 2))

    all_tickers_info = { # Add dummy info
        "AAPL": {"Sector": "Technology", "Market Cap": "Large-Cap"}, "MSFT": {"Sector": "Technology", "Market Cap": "Large-Cap"},
        "GOOGL": {"Sector": "Technology", "Market Cap": "Large-Cap"}, "AMZN": {"Sector": "Consumer Discretionary", "Market Cap": "Large-Cap"},
        "TSLA": {"Sector": "Consumer Discretionary", "Market Cap": "Large-Cap"}, "NVDA": {"Sector": "Technology", "Market Cap": "Large-Cap"},
        "JPM": {"Sector": "Finance", "Market Cap": "Large-Cap"}, "JNJ": {"Sector": "Healthcare", "Market Cap": "Large-Cap"},
        "V": {"Sector": "Finance", "Market Cap": "Large-Cap"}, "PG": {"Sector": "Consumer Staples", "Market Cap": "Large-Cap"},
        "META": {"Sector": "Technology", "Market Cap": "Large-Cap"}, "XOM": {"Sector": "Energy", "Market Cap": "Large-Cap"},
        "BRK-B": {"Sector": "Finance", "Market Cap": "Large-Cap"}, "LLY": {"Sector": "Healthcare", "Market Cap": "Large-Cap"},
        "WMT": {"Sector": "Consumer Staples", "Market Cap": "Large-Cap"}, "UNH": {"Sector": "Healthcare", "Market Cap": "Large-Cap"},
        "MA": {"Sector": "Finance", "Market Cap": "Large-Cap"}, "BAC": {"Sector": "Finance", "Market Cap": "Large-Cap"},
        "CVX": {"Sector": "Energy", "Market Cap": "Large-Cap"}, "PFE": {"Sector": "Healthcare", "Market Cap": "Large-Cap"},
        "MRNA": {"Sector": "Healthcare", "Market Cap": "Mid-Cap"}, "ETSY": {"Sector": "Consumer Discretionary", "Market Cap": "Mid-Cap"},
        "DOCN": {"Sector": "Technology", "Market Cap": "Mid-Cap"}, "PLTR": {"Sector": "Technology", "Market Cap": "Mid-Cap"},
        "RBLX": {"Sector": "Technology", "Market Cap": "Mid-Cap"}, "SAVA": {"Sector": "Healthcare", "Market Cap": "Small-Cap"},
        "GME": {"Sector": "Consumer Discretionary", "Market Cap": "Small-Cap"}, "AMC": {"Sector": "Consumer Discretionary", "Market Cap": "Small-Cap"},
    }
    all_tickers = list(all_tickers_info.keys())
    risk_score = inputs.get("risk_score", 50)
    num_potential = int(len(all_tickers) * (0.6 + risk_score / 250))
    num_screened = random.randint(min(10, num_potential), min(25, num_potential))
    screened_tickers = random.sample(all_tickers, min(num_screened, len(all_tickers)))

    if not screened_tickers:
         job_data["status"] = STATUS_FAILED
         job_data["error_message"] = "Screening failed: No stocks matched initial criteria."
         job_data["progress_log"].append(f"[{datetime.now():%H:%M:%S}] Screening Failed.")
         job_data["completed_at"] = datetime.now()
    else:
        screening_results_list = []
        for ticker in screened_tickers:
            info = all_tickers_info.get(ticker, {"Sector": "N/A", "Market Cap": "N/A"})
            screening_results_list.append({
                "Ticker": ticker, "Sector": info["Sector"], "Market Cap": info["Market Cap"],
                "Liquidity Score": round(random.uniform(50, 100), 1)
            })
        # Store tickers passing this stage separately for easier access later
        passing_tickers = [res["Ticker"] for res in screening_results_list]
        job_data["results"][STEP_SCREENING] = {"screening_data": screening_results_list, "passing_tickers": passing_tickers}
        job_data["progress_log"].append(f"[{datetime.now():%H:%M:%S}] Screening complete. Found {len(passing_tickers)} tickers.")
        job_data["current_step"] = STEP_FUNDAMENTAL
    return job_data

def run_fundamental_step(job_data):
    # Use passing_tickers from previous step
    if STEP_SCREENING not in job_data["results"] or "passing_tickers" not in job_data["results"][STEP_SCREENING]:
        job_data["status"] = STATUS_FAILED
        job_data["error_message"] = "Fundamental Analysis failed: No tickers from screening step."
        job_data["progress_log"].append(f"[{datetime.now():%H:%M:%S}] Fundamental Analysis Failed (Missing Input).")
        job_data["completed_at"] = datetime.now()
        return job_data

    tickers = job_data["results"][STEP_SCREENING]["passing_tickers"]
    if not tickers: # Handle empty list case
        job_data["status"] = STATUS_FAILED
        job_data["error_message"] = "Fundamental Analysis failed: No tickers passed screening."
        job_data["progress_log"].append(f"[{datetime.now():%H:%M:%S}] Fundamental Analysis Failed (No Input Tickers).")
        job_data["completed_at"] = datetime.now()
        return job_data

    job_data["progress_log"].append(f"[{datetime.now():%H:%M:%S}] Starting Fundamental Analysis for {len(tickers)} tickers...")
    time.sleep(random.uniform(2, 3))
    results = []
    for ticker in tickers:
        if random.random() > 0.15:
            results.append({
                "Ticker": ticker, "P/E Ratio": round(random.uniform(10, 50), 2),
                "ROE (%)": round(random.uniform(5, 25), 2), "Debt/Equity": round(random.uniform(0.1, 1.5), 2),
                "Analyst Rating": random.choice(["Buy", "Hold", "Strong Buy"]),
                "Dividend Yield (%)": round(random.uniform(0, 4.5), 2) if random.random() > 0.3 else 0.0,
            })
    passing_tickers = [r["Ticker"] for r in results]
    if not passing_tickers:
        job_data["status"] = STATUS_FAILED
        job_data["error_message"] = "Fundamental Analysis failed: All stocks filtered out."
        job_data["progress_log"].append(f"[{datetime.now():%H:%M:%S}] Fundamental Analysis Failed (All Filtered).")
        job_data["completed_at"] = datetime.now()
    else:
        job_data["results"][STEP_FUNDAMENTAL] = {"fundamental_data": results, "passing_tickers": passing_tickers}
        job_data["progress_log"].append(f"[{datetime.now():%H:%M:%S}] Fundamental Analysis complete. {len(passing_tickers)} stocks passed.")
        job_data["current_step"] = STEP_SENTIMENT
    return job_data

# ... (run_sentiment_step, run_technical_step, run_strategy_dev_step, run_final_selection_step remain conceptually the same, ensuring they use/update 'passing_tickers' and return job_data) ...
def run_sentiment_step(job_data):
    if STEP_FUNDAMENTAL not in job_data["results"] or "passing_tickers" not in job_data["results"][STEP_FUNDAMENTAL]:
        job_data["status"] = STATUS_FAILED
        job_data["error_message"] = "Sentiment Analysis failed: No tickers from fundamental step."
        job_data["progress_log"].append(f"[{datetime.now():%H:%M:%S}] Sentiment Analysis Failed (Missing Input).")
        job_data["completed_at"] = datetime.now()
        return job_data

    tickers = job_data["results"][STEP_FUNDAMENTAL]["passing_tickers"]
    if not tickers:
        job_data["status"] = STATUS_FAILED
        job_data["error_message"] = "Sentiment Analysis failed: No tickers passed fundamental analysis."
        job_data["progress_log"].append(f"[{datetime.now():%H:%M:%S}] Sentiment Analysis Failed (No Input Tickers).")
        job_data["completed_at"] = datetime.now()
        return job_data

    job_data["progress_log"].append(f"[{datetime.now():%H:%M:%S}] Starting Sentiment Analysis for {len(tickers)} tickers...")
    time.sleep(random.uniform(2, 4))
    results = []
    for ticker in tickers:
        if random.random() > 0.1:
            results.append({
                "Ticker": ticker, "Sentiment Score": round(random.uniform(-0.5, 0.8), 2),
                "Trending Keywords": ", ".join(random.sample(["AI", "Earnings", "Growth", "Competition", "New Product", "Regulations"], random.randint(1,3))),
                "News Volume (24h)": random.randint(5, 50), "Social Media Buzz": random.choice(["High", "Medium", "Low"]),
            })
    passing_tickers = [r["Ticker"] for r in results]
    if not passing_tickers:
        job_data["status"] = STATUS_FAILED
        job_data["error_message"] = "Sentiment Analysis failed: All stocks filtered out."
        job_data["progress_log"].append(f"[{datetime.now():%H:%M:%S}] Sentiment Analysis Failed (All Filtered).")
        job_data["completed_at"] = datetime.now()
    else:
        job_data["results"][STEP_SENTIMENT] = {"sentiment_data": results, "passing_tickers": passing_tickers}
        job_data["progress_log"].append(f"[{datetime.now():%H:%M:%S}] Sentiment Analysis complete. {len(passing_tickers)} stocks passed.")
        job_data["current_step"] = STEP_TECHNICAL
    return job_data

def run_technical_step(job_data):
    if STEP_SENTIMENT not in job_data["results"] or "passing_tickers" not in job_data["results"][STEP_SENTIMENT]:
        job_data["status"] = STATUS_FAILED
        job_data["error_message"] = "Technical Analysis failed: No tickers from sentiment step."
        job_data["progress_log"].append(f"[{datetime.now():%H:%M:%S}] Technical Analysis Failed (Missing Input).")
        job_data["completed_at"] = datetime.now()
        return job_data

    tickers = job_data["results"][STEP_SENTIMENT]["passing_tickers"]
    if not tickers:
        job_data["status"] = STATUS_FAILED
        job_data["error_message"] = "Technical Analysis failed: No tickers passed sentiment analysis."
        job_data["progress_log"].append(f"[{datetime.now():%H:%M:%S}] Technical Analysis Failed (No Input Tickers).")
        job_data["completed_at"] = datetime.now()
        return job_data

    job_data["progress_log"].append(f"[{datetime.now():%H:%M:%S}] Starting Technical Analysis for {len(tickers)} tickers...")
    time.sleep(random.uniform(3, 5))
    results = []
    for ticker in tickers:
        if random.random() > 0.05:
            results.append({
                "Ticker": ticker, "RSI (14)": round(random.uniform(30, 70), 1),
                "MACD Signal": random.choice(["Bullish Crossover", "Bearish Crossover", "Neutral"]),
                "Price vs MA(50)": random.choice(["Above", "Below", "Touching"]),
                "Trend (Short Term)": random.choice(["Uptrend", "Downtrend", "Sideways"]),
                "Volatility (ATR)": round(random.uniform(0.5, 5.0), 2),
            })
    passing_tickers = [r["Ticker"] for r in results]
    if not passing_tickers:
        job_data["status"] = STATUS_FAILED
        job_data["error_message"] = "Technical Analysis failed: All stocks filtered out."
        job_data["progress_log"].append(f"[{datetime.now():%H:%M:%S}] Technical Analysis Failed (All Filtered).")
        job_data["completed_at"] = datetime.now()
    else:
        job_data["results"][STEP_TECHNICAL] = {"technical_data": results, "passing_tickers": passing_tickers}
        job_data["progress_log"].append(f"[{datetime.now():%H:%M:%S}] Technical Analysis complete. {len(passing_tickers)} stocks passed.")
        job_data["current_step"] = STEP_STRATEGY_DEV
    return job_data

def run_strategy_dev_step(job_data):
    if STEP_TECHNICAL not in job_data["results"] or "passing_tickers" not in job_data["results"][STEP_TECHNICAL]:
        job_data["status"] = STATUS_FAILED
        job_data["error_message"] = "Strategy Dev failed: No tickers from technical step."
        job_data["progress_log"].append(f"[{datetime.now():%H:%M:%S}] Strategy Dev Failed (Missing Input).")
        job_data["completed_at"] = datetime.now()
        return job_data

    tickers = job_data["results"][STEP_TECHNICAL]["passing_tickers"]
    if not tickers:
        job_data["status"] = STATUS_FAILED
        job_data["error_message"] = "Strategy Dev failed: No tickers passed technical analysis."
        job_data["progress_log"].append(f"[{datetime.now():%H:%M:%S}] Strategy Dev Failed (No Input Tickers).")
        job_data["completed_at"] = datetime.now()
        return job_data

    job_data["progress_log"].append(f"[{datetime.now():%H:%M:%S}] Starting Strategy Development for {len(tickers)} tickers...")
    time.sleep(random.uniform(5, 8))
    strategy_results = {}
    strategy_descriptions = { "Momentum": "...", "Mean Reversion": "...", "MA Crossover": "...", "Value Dip Buy": "...", "Volatility Breakout": "...", "Dividend Growth": "..."}
    for ticker in tickers:
        stock_strategies = []
        possible_strategy_names = list(strategy_descriptions.keys())
        num_strategies_per_stock = random.randint(1, 2)
        for i in range(num_strategies_per_stock):
            strategy_name_base = random.choice(possible_strategy_names)
            metrics = { "Annualized Return (%)": round(random.uniform(5, 25), 2), "Volatility (%)": round(random.uniform(10, 30), 2), "Sharpe Ratio": round(random.uniform(0.5, 1.5), 2) }
            stock_strategies.append({ "strategy_name": f"{strategy_name_base} #{i+1}", "description": strategy_descriptions.get(strategy_name_base, "..."), "metrics": metrics })
        if stock_strategies: strategy_results[ticker] = stock_strategies

    if not strategy_results:
        job_data["status"] = STATUS_FAILED
        job_data["error_message"] = "Strategy Dev failed: No strategies developed for any stock."
        job_data["progress_log"].append(f"[{datetime.now():%H:%M:%S}] Strategy Dev Failed (No Strategies).")
        job_data["completed_at"] = datetime.now()
    else:
        final_stock_list = list(strategy_results.keys())
        job_data["results"][STEP_STRATEGY_DEV] = {"strategies_per_stock": strategy_results, "final_stock_list": final_stock_list}
        job_data["progress_log"].append(f"[{datetime.now():%H:%M:%S}] Strategy Development complete for {len(final_stock_list)} stocks.")
        job_data["current_step"] = STEP_FINAL_SELECTION
    return job_data

def run_final_selection_step(job_data):
    if STEP_STRATEGY_DEV not in job_data["results"] or "final_stock_list" not in job_data["results"][STEP_STRATEGY_DEV]:
        job_data["status"] = STATUS_FAILED
        job_data["error_message"] = "Final Selection failed: No strategies/stock list from previous step."
        job_data["progress_log"].append(f"[{datetime.now():%H:%M:%S}] Final Selection Failed (Missing Input).")
        job_data["completed_at"] = datetime.now()
        return job_data

    strategies_per_stock = job_data["results"][STEP_STRATEGY_DEV]["strategies_per_stock"]
    tickers = job_data["results"][STEP_STRATEGY_DEV]["final_stock_list"]
    if not tickers:
        job_data["status"] = STATUS_FAILED
        job_data["error_message"] = "Final Selection failed: No stocks available after strategy development."
        job_data["progress_log"].append(f"[{datetime.now():%H:%M:%S}] Final Selection Failed (No Stocks).")
        job_data["completed_at"] = datetime.now()
        return job_data

    risk_score = job_data["inputs"].get("risk_score", 50)
    job_data["progress_log"].append(f"[{datetime.now():%H:%M:%S}] Starting Final Portfolio Selection...")
    time.sleep(random.uniform(2, 3))
    final_portfolio = []
    max_possible_stocks = len(tickers)
    num_final_stocks = random.randint(max(1, min(3, max_possible_stocks)), min(max(5, int(12 * (risk_score / 100))), max_possible_stocks))
    selected_tickers = random.sample(tickers, num_final_stocks)

    for ticker in selected_tickers:
        if ticker in strategies_per_stock and strategies_per_stock[ticker]:
            best_strategy = max(strategies_per_stock[ticker], key=lambda s: s["metrics"]["Sharpe Ratio"])
            final_portfolio.append({
                "Ticker": ticker, "Chosen Strategy": best_strategy["strategy_name"],
                "Strategy Description": best_strategy["description"],
                "Annualized Return (%)": best_strategy["metrics"]["Annualized Return (%)"],
                "Volatility (%)": best_strategy["metrics"]["Volatility (%)"],
                "Sharpe Ratio": best_strategy["metrics"]["Sharpe Ratio"],
                "Allocation (%)": 0
            })
    if final_portfolio:
        equal_weight = 100 / len(final_portfolio)
        for item in final_portfolio: item["Allocation (%)"] = round(equal_weight, 2)
        diff = 100.0 - sum(item["Allocation (%)"] for item in final_portfolio)
        if final_portfolio: final_portfolio[0]["Allocation (%)"] += round(diff, 2)

    if not final_portfolio:
        job_data["status"] = STATUS_FAILED
        job_data["error_message"] = "Final Selection failed: Could not construct portfolio from selected strategies."
        job_data["progress_log"].append(f"[{datetime.now():%H:%M:%S}] Final Selection Failed (No Portfolio).")
        job_data["completed_at"] = datetime.now()
    else:
        job_data["results"][STEP_FINAL_SELECTION] = {"final_portfolio": final_portfolio}
        job_data["progress_log"].append(f"[{datetime.now():%H:%M:%S}] Final Portfolio Selection complete.")
        job_data["current_step"] = STEP_COMPLETE
        job_data["status"] = STATUS_COMPLETED
        job_data["completed_at"] = datetime.now()
    return job_data


# --- Job Processing Simulation ---

def run_next_job_step(job_data):
    """Simulates running the next step of the analysis job and saves persistently."""
    if job_data["status"] not in [STATUS_PENDING, STATUS_RUNNING]: return job_data

    original_status = job_data["status"]
    if original_status == STATUS_PENDING:
        job_data["status"] = STATUS_RUNNING
        job_data["current_step"] = ANALYSIS_STEPS[0]
        job_data["started_at"] = datetime.now()
        job_data["progress_log"].append(f"[{datetime.now():%H:%M:%S}] Job started.")
        save_job(job_data["user"], job_data["id"], job_data)
        return job_data

    current_step = job_data["current_step"]
    step_functions = {
        STEP_SCREENING: run_screening_step, STEP_FUNDAMENTAL: run_fundamental_step,
        STEP_SENTIMENT: run_sentiment_step, STEP_TECHNICAL: run_technical_step,
        STEP_STRATEGY_DEV: run_strategy_dev_step, STEP_FINAL_SELECTION: run_final_selection_step,
    }
    updated_job_data = job_data
    if current_step in step_functions:
        try:
            updated_job_data = step_functions[current_step](updated_job_data)
        except Exception as e:
            updated_job_data["status"] = STATUS_FAILED
            updated_job_data["error_message"] = f"Error during {current_step}: {str(e)}"
            updated_job_data["progress_log"].append(f"[{datetime.now():%H:%M:%S}] CRITICAL ERROR: {e}")
            updated_job_data["completed_at"] = datetime.now()
            st.error(f"Simulation Error in step {current_step}: {e}")

    save_job(updated_job_data["user"], updated_job_data["id"], updated_job_data)
    return updated_job_data


# --- UI Rendering Functions ---

def render_dashboard():
    st.title("🏠 AI Analysis Dashboard")
    st.write(f"Welcome back, {st.session_state.logged_in_user}!")
    st.markdown("Start a new portfolio analysis or view the status of your existing jobs.")
    col1, col2 = st.columns(2)
    with col1: st.button("➕ Start New Analysis", on_click=navigate_to, args=(PAGE_NEW_ANALYSIS,), use_container_width=True, type="primary")
    with col2: st.button("📊 View Analysis Jobs", on_click=navigate_to, args=(PAGE_JOB_STATUS,), use_container_width=True, type="primary")
    st.subheader("Recent Jobs")
    user_jobs = get_user_jobs(st.session_state.logged_in_user)
    if not user_jobs: st.info("You haven't started any analysis jobs yet.")
    else:
        def parse_dt(dt_str): return datetime.fromisoformat(dt_str) if isinstance(dt_str, str) else datetime.min
        sorted_jobs = sorted(user_jobs.values(), key=lambda j: parse_dt(j.get("submitted_at", "")), reverse=True)
        for job in sorted_jobs[:5]:
            submitted_dt = parse_dt(job.get("submitted_at", ""))
            with st.container(border=True):
                st.markdown(f"**Job ID:** `{job['id']}`")
                st.markdown(f"**Status:** {job['status']}")
                st.markdown(f"**Submitted:** {submitted_dt:%Y-%m-%d %H:%M}" if submitted_dt != datetime.min else "N/A")
                st.button("View Details", key=f"dash_view_{job['id']}", on_click=navigate_to, args=(PAGE_JOB_STATUS, job['id']))

def render_new_analysis():
    st.title("➕ Start New Portfolio Analysis")
    st.markdown("Define your investment parameters, and the AI will generate portfolio options.")
    with st.form("new_analysis_form"):
        instructions = st.text_area("**Instructions:**", height=150, placeholder="e.g., Invest ₹50k...")
        with st.expander("Advanced Filters (Optional)"):
            budget = st.number_input("Budget (₹)", min_value=1000, value=25000, step=1000, format="%d")
            risk_score = st.slider("Risk Score (1-100)", 1, 100, 60)
            sectors = st.multiselect("Sectors", ["Tech", "Health", "Finance", "Energy", "Industrials", "Utilities", "Consumer", "Materials"])
            market_caps = st.multiselect("Market Cap", ["Small", "Mid", "Large"], default=["Mid", "Large"])
        submitted = st.form_submit_button("🚀 Start AI Analysis Job")
        if submitted:
            inputs = {"budget": budget, "risk_score": risk_score, "sectors": sectors, "market_caps": market_caps, "instructions": instructions}
            job_id = create_new_job(st.session_state.logged_in_user, inputs)
            st.success(f"✅ Job submitted! ID: `{job_id}`")
            st.balloons()
            time.sleep(1)
            navigate_to(PAGE_JOB_STATUS, job_id)

# --- Intermediate Results Rendering Functions ---
# (Updated render_screening_results, added selectbox to others)
def render_screening_results(data):
    screening_data = data.get("screening_data", [])
    st.markdown(f"##### {STEP_SCREENING} Results")
    if screening_data:
        st.markdown(f"**Tickers Passed ({len(screening_data)}):**")
        df = pd.DataFrame(screening_data)
        st.dataframe(df, hide_index=True, use_container_width=True,
                     column_config={"Liquidity Score": st.column_config.ProgressColumn(min_value=0, max_value=100)})
    else: st.warning("No tickers passed screening.")

def render_fundamental_results(data):
    fund_data = data.get("fundamental_data", [])
    st.markdown(f"##### {STEP_FUNDAMENTAL} Results")
    if fund_data:
        tickers = [stock['Ticker'] for stock in fund_data]
        if len(tickers) > 1:
            selected_ticker = st.selectbox(f"View Details for:", tickers, key="fundamental_select", index=0) # Default to first
            stock_to_show = next((stock for stock in fund_data if stock['Ticker'] == selected_ticker), None)
        elif tickers: stock_to_show = fund_data[0]; st.markdown(f"Showing details for **{stock_to_show['Ticker']}**")
        else: stock_to_show = None

        if stock_to_show:
            with st.container(border=True):
                st.subheader(f"{stock_to_show['Ticker']} - Rating: {stock_to_show.get('Analyst Rating', 'N/A')}")
                col1, col2, col3 = st.columns(3)
                col1.metric("P/E Ratio", f"{stock_to_show.get('P/E Ratio', 'N/A'):.2f}" if isinstance(stock_to_show.get('P/E Ratio'), (int, float)) else "N/A")
                col2.metric("ROE", f"{stock_to_show.get('ROE (%)', 'N/A'):.2f}%" if isinstance(stock_to_show.get('ROE (%)'), (int, float)) else "N/A")
                col3.metric("Debt/Equity", f"{stock_to_show.get('Debt/Equity', 'N/A'):.2f}" if isinstance(stock_to_show.get('Debt/Equity'), (int, float)) else "N/A")
                col1.metric("Dividend Yield", f"{stock_to_show.get('Dividend Yield (%)', 'N/A'):.2f}%" if isinstance(stock_to_show.get('Dividend Yield (%)'), (int, float)) else "N/A")
        elif len(tickers) > 1: st.caption("Select a ticker to view details.")
    else: st.warning("No stocks passed fundamental analysis.")

# ... (render_sentiment_results, render_technical_results, render_strategy_dev_results updated similarly with selectbox) ...
def render_sentiment_results(data):
    sentiment_data = data.get("sentiment_data", [])
    st.markdown(f"##### {STEP_SENTIMENT} Results")
    if sentiment_data:
        tickers = [stock['Ticker'] for stock in sentiment_data]
        if len(tickers) > 1:
            selected_ticker = st.selectbox(f"View Details for:", tickers, key="sentiment_select", index=0)
            stock_to_show = next((stock for stock in sentiment_data if stock['Ticker'] == selected_ticker), None)
        elif tickers: stock_to_show = sentiment_data[0]; st.markdown(f"Showing details for **{stock_to_show['Ticker']}**")
        else: stock_to_show = None

        if stock_to_show:
            with st.container(border=True):
                st.subheader(f"{stock_to_show['Ticker']} - Score: {stock_to_show.get('Sentiment Score', 'N/A'):.2f}" if isinstance(stock_to_show.get('Sentiment Score'), (int, float)) else "N/A")
                col1, col2, col3 = st.columns(3)
                col1.metric("Sentiment Score", f"{stock_to_show.get('Sentiment Score', 'N/A'):.2f}" if isinstance(stock_to_show.get('Sentiment Score'), (int, float)) else "N/A")
                col2.metric("News Volume (24h)", stock_to_show.get('News Volume (24h)', 'N/A'))
                col3.metric("Social Buzz", stock_to_show.get('Social Media Buzz', 'N/A'))
                st.markdown(f"**Trending Keywords:** {stock_to_show.get('Trending Keywords', 'N/A')}")
        elif len(tickers) > 1: st.caption("Select a ticker to view details.")
    else: st.warning("No stocks passed sentiment analysis.")

def render_technical_results(data):
    tech_data = data.get("technical_data", [])
    st.markdown(f"##### {STEP_TECHNICAL} Results")
    if tech_data:
        tickers = [stock['Ticker'] for stock in tech_data]
        if len(tickers) > 1:
            selected_ticker = st.selectbox(f"View Details for:", tickers, key="technical_select", index=0)
            stock_to_show = next((stock for stock in tech_data if stock['Ticker'] == selected_ticker), None)
        elif tickers: stock_to_show = tech_data[0]; st.markdown(f"Showing details for **{stock_to_show['Ticker']}**")
        else: stock_to_show = None

        if stock_to_show:
            with st.container(border=True):
                st.subheader(f"{stock_to_show['Ticker']} - Trend: {stock_to_show.get('Trend (Short Term)', 'N/A')}")
                col1, col2, col3 = st.columns(3)
                col1.metric("RSI (14)", f"{stock_to_show.get('RSI (14)', 'N/A'):.1f}" if isinstance(stock_to_show.get('RSI (14)'), (int, float)) else "N/A")
                col2.metric("Volatility (ATR)", f"{stock_to_show.get('Volatility (ATR)', 'N/A'):.2f}" if isinstance(stock_to_show.get('Volatility (ATR)'), (int, float)) else "N/A")
                col3.write(f"**MACD:** {stock_to_show.get('MACD Signal', 'N/A')}")
                st.write(f"**Price vs MA(50):** {stock_to_show.get('Price vs MA(50)', 'N/A')}")
        elif len(tickers) > 1: st.caption("Select a ticker to view details.")
    else: st.warning("No stocks passed technical analysis.")

def render_strategy_dev_results(data):
    strategies = data.get("strategies_per_stock", {})
    st.markdown(f"##### {STEP_STRATEGY_DEV} Results")
    if strategies:
        stock_options = list(strategies.keys())
        st.markdown(f"**Strategies Developed for {len(stock_options)} Stocks:**")
        if len(stock_options) > 1:
             job_id_suffix = data.get('id', 'default_strat_select')
             selected_stock = st.selectbox("View strategies for stock:", stock_options, key=f"strat_view_{job_id_suffix}", index=0)
             stocks_to_show = [selected_stock] if selected_stock else []
        elif stock_options: stocks_to_show = stock_options
        else: stocks_to_show = []

        if not stocks_to_show and len(stock_options) > 1: st.caption("Select a stock to view strategies.")
        elif not stocks_to_show and not stock_options: st.caption("No stocks available.")

        for stock_ticker in stocks_to_show:
            st.markdown(f"**{stock_ticker}:**")
            stock_strats = strategies.get(stock_ticker, [])
            if not stock_strats: st.caption("No strategies developed for this stock."); continue
            for strategy in stock_strats:
                 with st.container(border=True):
                    st.subheader(f"Strategy: {strategy['strategy_name']}")
                    st.markdown(f"*{strategy['description']}*")
                    metrics = strategy["metrics"]
                    m_col1, m_col2, m_col3 = st.columns(3)
                    m_col1.metric("Ann. Return", f"{metrics.get('Annualized Return (%)', 'N/A'):.2f}%" if isinstance(metrics.get('Annualized Return (%)'), (int, float)) else "N/A")
                    m_col2.metric("Volatility", f"{metrics.get('Volatility (%)', 'N/A'):.2f}%" if isinstance(metrics.get('Volatility (%)'), (int, float)) else "N/A")
                    m_col3.metric("Sharpe Ratio", f"{metrics.get('Sharpe Ratio', 'N/A'):.2f}" if isinstance(metrics.get('Sharpe Ratio'), (int, float)) else "N/A")
                    st.caption("Backtest chart data not displayed (omitted for persistence).")
    else: st.warning("No strategies were developed.")

# Map step names to rendering functions
INTERMEDIATE_RENDERERS = {
    STEP_SCREENING: render_screening_results, STEP_FUNDAMENTAL: render_fundamental_results,
    STEP_SENTIMENT: render_sentiment_results, STEP_TECHNICAL: render_technical_results,
    STEP_STRATEGY_DEV: render_strategy_dev_results,
}

# --- Main Job Status Page ---
def render_job_status():
    st.title("📊 View Analysis Jobs")
    username = st.session_state.logged_in_user
    user_jobs_dict = get_user_jobs(username)

    if not user_jobs_dict:
        st.info("You haven't started any analysis jobs yet.")
        st.button("➕ Start New Analysis", on_click=navigate_to, args=(PAGE_NEW_ANALYSIS,))
        return

    def parse_dt(dt_str): return datetime.fromisoformat(dt_str) if isinstance(dt_str, str) else datetime.min
    job_ids = list(user_jobs_dict.keys())
    job_ids.sort(key=lambda jid: parse_dt(user_jobs_dict[jid].get("submitted_at", "")), reverse=True)

    selected_job_id_state = st.session_state.get('selected_job_id')
    default_index = 0
    if selected_job_id_state and selected_job_id_state in job_ids:
        try: default_index = job_ids.index(selected_job_id_state)
        except ValueError: selected_job_id_state = None
    if not selected_job_id_state and job_ids:
         selected_job_id_state = job_ids[0]
         st.session_state.selected_job_id = selected_job_id_state

    def format_job_selector(jid):
        job = user_jobs_dict.get(jid, {})
        status = job.get('status', 'N/A')
        submitted_dt = parse_dt(job.get("submitted_at", ""))
        submitted_str = f"{submitted_dt:%Y-%m-%d %H:%M}" if submitted_dt != datetime.min else "N/A"
        return f"{jid} ({status} - {submitted_str})"

    selected_job_id = st.selectbox("Select Job ID:", job_ids, index=default_index, key="job_selector", format_func=format_job_selector)

    if selected_job_id != selected_job_id_state:
        st.session_state.selected_job_id = selected_job_id
        st.rerun()

    if not selected_job_id or selected_job_id not in user_jobs_dict:
        st.warning("Please select a valid job."); return

    _persistent_jobs_data = None # Clear local cache
    all_jobs = load_jobs_data() # Reload from file
    job_data = all_jobs.get(username, {}).get(selected_job_id)
    if not job_data: st.error(f"Job data for {selected_job_id} not found."); return

    original_status = job_data["status"]
    original_step = job_data.get("current_step")
    rerun_needed = False

    job_needs_processing = (original_status == STATUS_PENDING or original_status == STATUS_RUNNING)
    if job_needs_processing:
        with st.spinner(f"Simulating step: {job_data.get('current_step', 'Initialization')}..."):
            updated_job_data = run_next_job_step(job_data.copy())
        if updated_job_data["status"] != original_status or updated_job_data.get("current_step") != original_step:
            rerun_needed = True
        job_data = updated_job_data

    st.divider()
    st.header(f"Job Details: `{job_data['id']}`")
    submitted_dt = parse_dt(job_data.get("submitted_at"))
    started_dt = parse_dt(job_data.get("started_at"))
    completed_dt = parse_dt(job_data.get("completed_at"))
    info_cols = st.columns(3)
    info_cols[0].metric("Status", job_data["status"])
    info_cols[1].metric("Submitted", f"{submitted_dt:%Y-%m-%d %H:%M}" if submitted_dt != datetime.min else "N/A")
    if completed_dt != datetime.min: info_cols[2].metric("Completed", f"{completed_dt:%Y-%m-%d %H:%M}")
    elif started_dt != datetime.min: info_cols[2].metric("Started", f"{started_dt:%Y-%m-%d %H:%M}")
    else: info_cols[2].metric("Started", "Not Yet")

    st.subheader("Progress")
    current_step_name = job_data.get("current_step")
    current_status = job_data["status"]
    step_cols = st.columns(len(ANALYSIS_STEPS) -1)
    current_step_index = -1
    if current_step_name and current_step_name != STEP_COMPLETE:
        try: current_step_index = ANALYSIS_STEPS.index(current_step_name)
        except ValueError: pass
    for i, step_name in enumerate(ANALYSIS_STEPS[:-1]):
        with step_cols[i]:
            is_complete = current_status == STATUS_COMPLETED or (current_step_index != -1 and i < current_step_index)
            is_running = current_status == STATUS_RUNNING and i == current_step_index
            is_failed_here = current_status == STATUS_FAILED and i == current_step_index
            if is_complete: st.success(f"✓ {step_name}", icon="✅")
            elif is_running: st.info(f"⚙️ {step_name}", icon="⚙️")
            elif is_failed_here: st.error(f"❌ {step_name}", icon="❌")
            else: st.markdown(f"⚪ {step_name}")

    with st.expander("Show Detailed Progress Log"):
        log_reversed = job_data.get("progress_log", [])[::-1]
        st.code("\n".join(log_reversed), language="text")
    if job_data["error_message"]: st.error(f"Job Failed: {job_data['error_message']}")

    with st.expander("View Intermediate Analysis Results", expanded=False):
        has_intermediate_results = False
        results_dict = job_data.get("results", {})
        for step in ANALYSIS_STEPS:
            if step in INTERMEDIATE_RENDERERS and step in results_dict:
                render_func = INTERMEDIATE_RENDERERS[step]
                render_func(results_dict[step])
                st.markdown("---")
                has_intermediate_results = True
        if not has_intermediate_results: st.caption("No intermediate results available yet.")

    if job_data["status"] == STATUS_COMPLETED:
        st.subheader("✅ Final Portfolio Results")
        final_results_data = job_data.get("results", {}).get(STEP_FINAL_SELECTION, {})
        final_portfolio_list = final_results_data.get("final_portfolio", [])
        inputs = job_data.get("inputs", {})
        budget = inputs.get('budget', 10000)
        if not final_portfolio_list: st.warning("Analysis completed, but no final portfolio generated.")
        else:
            total_allocated_amount = 0.0
            for stock_info in final_portfolio_list:
                 with st.container(border=True):
                    alloc_percent = stock_info.get('Allocation (%)', 0.0)
                    amount = alloc_percent / 100.0 * budget
                    total_allocated_amount += amount
                    st.subheader(f"{stock_info.get('Ticker', 'N/A')} ({alloc_percent:.2f}%)")
                    st.markdown(f"**Strategy:** {stock_info.get('Chosen Strategy', 'N/A')}")
                    st.caption(f"{stock_info.get('Strategy Description', '')}")
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Allocation", f"{alloc_percent:.2f}%")
                    col2.metric("Amount", f"₹{amount:,.2f}")
                    col3.metric("Exp. Ann. Return", f"{stock_info.get('Annualized Return (%)', 0.0):.2f}%")
                    col4.metric("Exp. Sharpe Ratio", f"{stock_info.get('Sharpe Ratio', 0.0):.2f}")
            st.markdown("---")
            st.subheader("Portfolio Summary")
            summary_col1, summary_col2 = st.columns(2)
            summary_col1.metric("Target Budget", f"₹{budget:,.2f}")
            summary_col2.metric("Total Allocated", f"₹{total_allocated_amount:,.2f}")
            st.caption(f"Based on Risk Score: {inputs.get('risk_score', 'N/A')}/100")

            # --- Modified Paper Trade Button Action ---
            st.subheader("🚀 Paper Trading Action")
            if st.button("Prepare Portfolio for Paper Trading", type="primary"):
                # Prepare proposed trades and store in session state
                proposed = []
                for stock_info in final_portfolio_list:
                    alloc_percent = stock_info.get('Allocation (%)', 0.0)
                    target_amount = budget * (alloc_percent / 100.0)
                    if stock_info.get('Ticker') and target_amount > 0:
                        proposed.append({
                            "Ticker": stock_info['Ticker'],
                            "Target Amount": round(target_amount, 2),
                            # Add other info if needed, e.g., strategy
                            "Strategy": stock_info.get('Chosen Strategy', 'N/A')
                        })
                st.session_state.proposed_trades = proposed
                st.session_state.reviewed_trades = None # Clear any previous review
                st.success("Portfolio prepared. Navigate to the Paper Trading page to review and confirm.")
                time.sleep(1)
                navigate_to(PAGE_PAPER_TRADE) # Navigate automatically

    if rerun_needed: st.rerun()

def render_stock_details_popup(stock_data: dict):
    ticker = stock_data.get('Ticker', 'N/A')
    current_price = stock_data.get('Price', 0.0)
    # Use the 'Change' percentage directly from the API data
    day_change_pct = stock_data.get('Change', 0.0)

    st.markdown(f"#### {ticker} Overview")
    col1, col2 = st.columns(2)

    # Display Price from API data
    col1.metric("Current Price", f"₹{current_price:,.2f}") # Format as currency

    # Display Change % from API data
    # Determine color based on the sign of the change percentage
    delta_color = "off" # Default grey for 0% change
    if day_change_pct > 0:
        delta_color = "normal" # Streamlit's default green
    elif day_change_pct < 0:
        delta_color = "inverse" # Streamlit's default red

    col2.metric("Day's Change", f"{day_change_pct:+.2f}%", delta_color=delta_color)
    
    # Paper Trade Button
    st.subheader("Paper Trade Actions")
    username = st.session_state.logged_in_user

    # --- Move Radio Button OUTSIDE the form ---
    action = st.radio(
        "Action",
        ["Buy", "Sell"],
        horizontal=True,
        key=f"action_{ticker}_popup" # Key remains the same
    )

    # Fetch portfolio only if 'Sell' is selected, needed for validation later
    portfolio_for_validation = None
    if action == "Sell":
        portfolio_for_validation = get_paper_portfolio(username) # Backend basic fetch

    # --- Form now only contains the relevant input and button ---
    with st.form(key=f"trade_form_{ticker}_popup"): # Form key remains the same
        if action == "Buy":
            trade_qty = st.number_input(
                "Quantity to Buy", min_value=1, value=1, step=1,
                key=f"buy_qty_{ticker}_popup", # Key for input remains the same
                format="%d"
            )
        else: # Sell action selected
            holding = None
            if portfolio_for_validation and not portfolio_for_validation.get("error"):
                holding = next((h for h in portfolio_for_validation.get("holdings", []) if h["ticker"] == ticker), None)
            max_sell_qty = holding['quantity'] if holding else 0.0
            max_sell_qty_int = int(max_sell_qty) if max_sell_qty else 0

            trade_qty = st.number_input(
                f"Quantity to Sell (Max: {max_sell_qty_int})", min_value=0, max_value=max_sell_qty_int,
                value=0, step=1, key=f"sell_qty_{ticker}_popup", # Key for input remains the same
                format="%d"
            )

        trade_submitted = st.form_submit_button(f"Execute Paper {action}")

        if trade_submitted:
            try:
                final_trade_qty = int(trade_qty)
                # --- Validation ---
                if final_trade_qty <= 0 and action == "Buy":
                    st.warning("Buy quantity must be at least 1.")
                elif final_trade_qty < 0:
                    st.warning("Quantity cannot be negative.")
                # Fetch fresh portfolio data right before Sell validation inside submission logic
                elif action == "Sell":
                     portfolio_now = get_paper_portfolio(username) # Fetch fresh data
                     holding_now = next((h for h in portfolio_now.get("holdings", []) if h["ticker"] == ticker), None)
                     max_sell_now = int(holding_now['quantity']) if holding_now else 0
                     if final_trade_qty > max_sell_now:
                          st.warning(f"Cannot sell {final_trade_qty} shares. You now hold {max_sell_now}.")
                     else: # Quantity is valid for sell (or buy)
                          success, message = execute_paper_trade(username, action, ticker, quantity=final_trade_qty)
                          if success:
                              st.success(message)
                              st.rerun()
                          else:
                              st.error(message)
                else: # Buy action with valid quantity
                     success, message = execute_paper_trade(username, action, ticker, quantity=final_trade_qty)
                     if success:
                         st.success(message)
                         st.rerun()
                     else:
                         st.error(message)

            except (ValueError, TypeError):
                 st.error("Invalid quantity entered. Please enter a whole number.")

def render_home():
    st.title("📈 Market Overview")
 
    # --- Indices ---
    st.subheader("Indices")
    indices = get_live_indices_pricing()
    idx_cols = st.columns(len(indices))
    for i, idx in enumerate(indices):
        delta = f"{idx['Change']:+.2f} ({idx['Change %']:+.2f}%)"
        idx_cols[i].metric(label=idx["Name"], value=f"{idx['Value']:.2f}", delta=delta)

    st.divider()

    # --- Stock Search ---
    st.subheader("🔍 Stock Search")

    # --- CSS to adjust button alignment --- START ---
    # Adjust the margin-top value (e.g., 28px, 30px, 32px) as needed for perfect alignment
    button_margin_css = """
    <style>
        div[data-testid="stHorizontalBlock"] > div:nth-child(2) > div > div > div > button {
            margin-top: 28px;
        }
    </style>
    """
    st.markdown(button_margin_css, unsafe_allow_html=True)
    # --- CSS to adjust button alignment --- END ---


    search_col1, search_col2 = st.columns([3, 1])
    with search_col1:
        # Use label_visibility='collapsed' and rely on placeholder
        search_term = st.text_input(
            "Enter Ticker Symbol:",
            value=st.session_state.home_search_query,
            key="home_search_input",
            placeholder="Enter Ticker Symbol (e.g., AAPL, MSFT)",
            label_visibility='collapsed' # Collapse the label to potentially help alignment
        )
    with search_col2:
        # Button is now pushed down by the CSS margin
        if st.button("Search", key="home_search_button", use_container_width=True):
            st.session_state.home_search_query = search_term.strip().upper()
            # Rerun happens implicitly

    # --- Display Search Result ---
    if st.session_state.home_search_query: # Check if a search query exists
        query = st.session_state.home_search_query
        st.markdown("---") # Separator before search results
        st.markdown(f"#### Search Results for: \"{query}\"")

        # Call the search API
        search_results = search_tickertape_stocks(query, limit=5)

        if search_results is None:
            st.error("An error occurred while searching. Please try again.")
        elif not search_results: # Empty list means no results found
            st.info(f"No NSE stock results found matching \"{query}\".")
        else:
            # Display results in a list format
            for stock in search_results:
                # Determine color based on change percentage
                change_pct = stock.get('Change %', 0.0)
                color = "green" if change_pct > 0 else ("red" if change_pct < 0 else "grey")

                with st.container(border=True):
                    s_col1, s_col2 = st.columns([3, 1])
                    # Display Ticker and Name
                    s_col1.markdown(f"**{stock.get('Ticker', 'N/A')}**")
                    s_col1.caption(f"{stock.get('Name', 'Unknown Name')}")
                    # Format price as currency
                    s_col1.caption(f"Price: ₹{stock.get('Price', 0.0):,.2f}")
                    # Display percentage change
                    s_col2.markdown(f"<span style='color:{color}; font-weight:bold;'>{change_pct:+.2f}%</span>", unsafe_allow_html=True)
                    # Add expander for details/trade
                    with st.expander("Details / Trade"):
                        # It needs 'Price' and 'Change %' (which is 'Change' in its context)
                        # We don't have 'Cap' from search, so it will be omitted
                        popup_stock_data = {
                            "Ticker": stock.get('Ticker', 'N/A'),
                            "Name": stock.get('Name', 'Unknown Name'),
                            "Price": stock.get('Price', 0.0),
                            "Change": stock.get('Change %', 0.0) # Pass Change % as 'Change'
                        }
                        render_stock_details_popup(popup_stock_data)

        st.markdown("---") # Separator after search results

    # --- Movers Section ---
    st.subheader("Today's Movers (Simulated)")
    cap_options = ["LargeCap", "MidCap", "SmallCap"]
    default_cap_index = 0
    try:
        default_cap_index = cap_options.index(st.session_state.home_market_cap_filter)
    except ValueError:
        st.session_state.home_market_cap_filter = "LargeCap" # Default to LargeCap if not found

    selected_cap = st.radio(
        "Filter by Market Cap:",
        cap_options,
        index=default_cap_index,
        horizontal=True,
        key="home_cap_filter_radio"
    )

    if selected_cap != st.session_state.home_market_cap_filter:
        st.session_state.home_market_cap_filter = selected_cap
        st.rerun()
        
    gainers, losers = get_tickertape_movers(universe=st.session_state.home_market_cap_filter, count=5) # Fetch top 5
    # Display Gainers/Losers
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Top Gainers")
        if not gainers: st.caption(f"No gainers found for '{st.session_state.home_market_cap_filter}' filter.")
        for stock in gainers:
            with st.container(border=True):
                s_col1, s_col2 = st.columns([3, 1])
                s_col1.markdown(f"**{stock['Ticker']}** ({stock['Cap']})")
                s_col1.caption(f"Price: ₹{stock['Price']:.2f}")
                s_col2.markdown(f"<span style='color:green; font-weight:bold;'>+{stock['Change']:.1f}%</span>", unsafe_allow_html=True)
                with st.expander("Details / Trade"):
                     render_stock_details_popup(stock)
    with col2:
        st.markdown("#### Top Losers")
        if not losers: st.caption(f"No losers found for '{st.session_state.home_market_cap_filter}' filter.")
        for stock in losers:
             with st.container(border=True):
                s_col1, s_col2 = st.columns([3, 1])
                s_col1.markdown(f"**{stock['Ticker']}** ({stock['Cap']})")
                s_col1.caption(f"Price: ₹{stock['Price']:.2f}")
                s_col2.markdown(f"<span style='color:red; font-weight:bold;'>{stock['Change']:.1f}%</span>", unsafe_allow_html=True)
                with st.expander("Details / Trade"):
                     render_stock_details_popup(stock)

# --- Paper Trading Page Rendering ---
def render_paper_trade():
    st.title("📄 Paper Trading Portfolio")
    username = st.session_state.logged_in_user
    portfolio_details = get_detailed_paper_portfolio(username) # Use new function
    
    # Check for portfolio fetch error
    if portfolio_details.get("error"):
        st.error(f"Error loading portfolio: {portfolio_details['error']}")
        return # Stop rendering if portfolio fails

    # --- Add Funds Section ---
    with st.expander("💰 Add Funds"):
        with st.form("add_funds_form"):
            # Use '₹' symbol for currency
            amount_to_add = st.number_input("Amount (₹)", min_value=0.01, value=1000.0, step=100.0)
            add_funds_submitted = st.form_submit_button("Add Funds to Cash Balance")
            if add_funds_submitted:
                # Call the new backend function
                success, message = add_funds_to_portfolio(username, amount_to_add)
                if success:
                    st.success(message)
                    st.rerun() # Rerun to update displayed balances
                else:
                    st.error(message)

    # --- Proposed Trades Section (Logic remains similar, but uses execute_paper_trade from trading.py) ---
    if 'proposed_trades' in st.session_state and st.session_state.proposed_trades:
        st.subheader("📝 Review Proposed Trades from AI Analysis")
        st.caption("AI analysis suggests target amounts. Quantities are calculated based on current prices. Review and adjust quantities before execution.")

        # Initial calculation (no change needed here, still needs get_live_price)
        initial_proposed_trades_with_qty = []
        total_initial_cost = 0
        has_price_errors = False
        for trade in st.session_state.proposed_trades:
                ticker = trade["Ticker"]
                target_amount = trade["Target Amount"]
                # This part still needs a live price check
                live_price_info = get_live_price(ticker) # Keep this call here for this specific calculation
                current_price = live_price_info.get('ltp') if live_price_info else None

                if isinstance(current_price, (int, float)) and current_price > 0:
                    quantity = target_amount / current_price
                    cost = quantity * current_price
                    total_initial_cost += cost
                    initial_proposed_trades_with_qty.append({
                        "Ticker": ticker,
                        "Target Amount (₹)": target_amount, # Changed label ₹ -> ₹
                        "Live Price (₹)": current_price,    # Changed label
                        "Calculated Quantity": round(quantity, 4),
                        "Estimated Cost (₹)": round(cost, 2), # Changed label
                        "Strategy": trade.get("Strategy", "N/A")
                    })
                else:
                    st.warning(f"Could not get live price for {ticker} to calculate initial quantity. It will be excluded.")
                    has_price_errors = True
                    # You might want to exclude these completely or display them differently

        # Display only valid trades for editing
        valid_proposed_df = pd.DataFrame([t for t in initial_proposed_trades_with_qty if t["Calculated Quantity"] > 0])

        if not valid_proposed_df.empty:
            st.caption("Edit the 'Quantity to Buy' column below if needed.")
            edited_df = st.data_editor(
                valid_proposed_df,
                column_config={
                    "Ticker": st.column_config.TextColumn("Ticker", disabled=True),
                    "Target Amount (₹)": st.column_config.NumberColumn("Target Amt (Ref)", format="₹%.2f", disabled=True),
                    "Live Price (₹)": st.column_config.NumberColumn("Live Price", format="₹%.2f", disabled=True),
                    "Calculated Quantity": st.column_config.NumberColumn("Quantity to Buy", min_value=0.0, step=0.0001, format="%.4f", required=True),
                    "Estimated Cost (₹)": st.column_config.NumberColumn("Est. Cost", format="₹%.2f", disabled=True),
                    "Strategy": st.column_config.TextColumn("Strategy", disabled=True),
                },
                key="proposed_trades_editor_qty"
            )

            if st.button("🔍 Review & Confirm Trades"):
                # Review logic (calculating final cost based on potentially edited quantity)
                reviewed_trades_list = []
                total_final_cost = 0.0
                errors = []
                # Use the cash amount from the detailed portfolio fetched earlier
                current_cash = portfolio_details.get("cash", 0.0)

                for index, row in edited_df.iterrows():
                    ticker = row["Ticker"]
                    quantity_to_buy = row["Quantity to Buy"] # Use the edited quantity column name
                    live_price = row["Live Price (₹)"] # Use the price from the initial calculation

                    if not ticker or quantity_to_buy <= 0:
                        continue

                    if not isinstance(live_price, (int, float)) or live_price <= 0:
                            errors.append(f"Invalid price stored for {ticker}.")
                            continue

                    cost = quantity_to_buy * live_price
                    total_final_cost += cost
                    reviewed_trades_list.append({
                        "Ticker": ticker,
                        "Quantity": round(quantity_to_buy, 4),
                        "Live Price (₹)": live_price,
                        "Estimated Cost (₹)": round(cost, 2)
                    })

                st.session_state.reviewed_trades = {
                    "trades": reviewed_trades_list,
                    "total_cost": round(total_final_cost, 2),
                    "errors": errors,
                    "sufficient_cash": current_cash >= total_final_cost
                }
                st.rerun()
        else:
                st.info("No valid trades to propose after fetching initial prices.")


    # --- Confirmation Section (Calls execute_paper_trade from trading.py) ---
    if 'reviewed_trades' in st.session_state and st.session_state.reviewed_trades:
        review_data = st.session_state.reviewed_trades
        st.markdown("---")
        st.subheader("Confirm Execution")

        if review_data["errors"]:
            for error in review_data["errors"]: st.error(error)

        if review_data["trades"]:
            st.dataframe(pd.DataFrame(review_data["trades"]), hide_index=True,
                            column_config={
                                "Quantity": st.column_config.NumberColumn(format="%.4f"),
                                "Live Price (₹)": st.column_config.NumberColumn(format="₹%.2f"),
                                "Estimated Cost (₹)": st.column_config.NumberColumn(format="₹%.2f"),
                            })
            st.metric("Estimated Total Cost", f"₹{review_data['total_cost']:,.2f}")
            # Use cash from detailed portfolio
            st.metric("Available Cash", f"₹{portfolio_details.get('cash', 0.0):,.2f}")

            if not review_data["sufficient_cash"]:
                st.error("Insufficient cash to execute all reviewed trades.")
            else:
                if st.button("✅ Execute Confirmed Trades", type="primary"):
                    success_count = 0
                    fail_count = 0
                    for trade in review_data["trades"]:
                        # Call the CORRECT backend execute_paper_trade
                        success, msg = execute_paper_trade(
                            username, "Buy", trade["Ticker"], quantity=trade["Quantity"]
                        )
                        if success: success_count += 1
                        else: fail_count += 1; st.warning(f"Failed to buy {trade['Ticker']}: {msg}")

                    st.success(f"Attempted execution of {success_count} trades successfully.")
                    if fail_count > 0: st.error(f"{fail_count} trades failed.")
                    # Clear proposed and reviewed trades from state after execution attempt
                    st.session_state.proposed_trades = None
                    st.session_state.reviewed_trades = None
                    st.rerun() # Rerun to show updated portfolio
        else:
                if not review_data["errors"]:
                    st.warning("No valid trades reviewed for execution.")


    # --- Portfolio Summary ---
    st.divider()
    st.subheader("Portfolio Summary")
    # (Keep the Portfolio Summary logic using portfolio_details as is)
    calculated_totals = portfolio_details.get("calculated_totals", {})
    cash = portfolio_details.get("cash", 0.0)
    total_holdings_value = calculated_totals.get("total_holdings_value", 0.0)
    total_portfolio_value = calculated_totals.get("total_portfolio_value", 0.0)
    data_staleness = portfolio_details.get("data_staleness", {})

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Portfolio Value", f"₹{total_portfolio_value:,.2f}")
    if data_staleness.get("failed_prices", 0) > 0:
        col1.caption(f"({data_staleness['failed_prices']} prices stale)")
    col2.metric("Cash Balance", f"₹{cash:,.2f}")
    col3.metric("Holdings Value", f"₹{total_holdings_value:,.2f}")


    # --- Current Holdings ---
    st.subheader("Current Holdings")
    holdings = portfolio_details.get("holdings", [])

    if not holdings:
        st.info("You currently have no holdings.")
    else:
        # Display header row using columns
        header_cols = st.columns([2, 1, 2, 2, 2, 2]) # Adjust ratios as needed
        header_cols[0].markdown("**Ticker**")
        header_cols[1].markdown("**Quantity**")
        header_cols[2].markdown("**Avg Cost (₹)**")
        header_cols[3].markdown("**Mkt Price (₹)**")
        header_cols[4].markdown("**Mkt Value (₹)**")
        header_cols[5].markdown("**P/L (₹)** (%)")
        st.divider()

        # Iterate and display each holding with a trade form
        for i, h in enumerate(holdings):
            ticker = h["ticker"]
            quantity = int(h["quantity"])
            avg_cost = h["avg_cost"]
            current_price = h.get("current_price")
            current_value = h.get("current_value", 0.0)
            pnl = h.get("pnl", 0.0)
            pnl_pct = h.get("pnl_percentage", 0.0)
            is_stale = h.get("is_price_stale", True)

            data_cols = st.columns([2, 1, 2, 2, 2, 2])
            data_cols[0].markdown(f"**{ticker}**")
            data_cols[1].markdown(f"{quantity}")
            data_cols[2].markdown(f"₹{avg_cost:,.2f}")
            price_display = f"₹{current_price:,.2f}" if current_price is not None else "N/A"
            data_cols[3].markdown(price_display)
            data_cols[4].markdown(f"₹{current_value:,.2f}")
            pnl_color = "grey"
            if not is_stale:
                 if pnl > 0: pnl_color = "green"
                 elif pnl < 0: pnl_color = "red"
            data_cols[5].markdown(f"<span style='color:{pnl_color};'>₹{pnl:,.2f} ({pnl_pct:+.2f}%)</span>", unsafe_allow_html=True)


            # --- Trade Form Expander ---
            with st.expander(f"Trade {ticker}"):
                # --- Move Radio Button OUTSIDE the form ---
                trade_action = st.radio(
                    "Action",
                    ["Buy", "Sell"],
                    horizontal=True,
                    key=f"action_holding_{ticker}_{i}" # Unique key
                )

                # --- Form contains only the input and button ---
                with st.form(key=f"trade_holding_form_{ticker}_{i}"): # Unique form key
                    if trade_action == "Buy":
                        trade_qty = st.number_input(
                            "Quantity to Buy", min_value=1, value=1, step=1,
                            key=f"qty_buy_holding_{ticker}_{i}", # Unique input key
                            format="%d"
                        )
                    else: # Sell action selected
                        max_sell_qty = quantity # Use quantity from the loop
                        trade_qty = st.number_input(
                            f"Quantity to Sell (Max: {max_sell_qty})", min_value=0, max_value=max_sell_qty,
                            value=0, step=1, key=f"qty_sell_holding_{ticker}_{i}", # Unique input key
                            format="%d"
                        )

                    submitted = st.form_submit_button("Execute Trade")

                    if submitted:
                        try:
                            final_trade_qty = int(trade_qty)
                             # --- Validation ---
                            if final_trade_qty <= 0 and trade_action == "Buy":
                                st.warning("Buy quantity must be at least 1.")
                            elif final_trade_qty < 0:
                                st.warning("Quantity cannot be negative.")
                            elif trade_action == "Sell" and final_trade_qty > quantity:
                                # Re-check against current quantity in case it changed between render and submit
                                # (Though less likely without page reload, good practice)
                                current_portfolio_state = get_detailed_paper_portfolio(username)
                                current_holding_state = next((ch for ch in current_portfolio_state.get("holdings", []) if ch["ticker"] == ticker), None)
                                current_max_sell = int(current_holding_state['quantity']) if current_holding_state else 0
                                if final_trade_qty > current_max_sell:
                                     st.warning(f"Cannot sell {final_trade_qty} shares. You now hold {current_max_sell}.")
                                else: # Quantity is valid
                                     success, message = execute_paper_trade(username, trade_action, ticker, quantity=final_trade_qty)
                                     if success:
                                         st.success(message)
                                         st.rerun()
                                     else:
                                         st.error(message)
                            else: # Buy action or valid Sell action
                                success, message = execute_paper_trade(username, trade_action, ticker, quantity=final_trade_qty)
                                if success:
                                    st.success(message)
                                    st.rerun()
                                else:
                                    st.error(message)
                        except (ValueError, TypeError):
                            st.error("Invalid quantity entered. Please enter a whole number.")


            st.divider() # Separator between holdings

    # --- Trade History ---
    st.subheader("Trade History")
    # (Keep the Trade History display logic as is)
    transactions = get_paper_transactions(username, limit=25)
    if not transactions: st.caption("No trading history yet.")
    else:
        # ... (Existing history display logic using DataFrame) ...
        history_df_data = []
        for entry in transactions: # Already sorted
                ts = entry.get("timestamp")
                details = {
                    "price": entry.get("price"), "value": entry.get("cost_or_proceeds"),
                    "status": entry.get("status"), "msg": entry.get("message")
                }
                details_str = json.dumps({k: v for k, v in details.items() if v is not None})

                history_df_data.append({
                    "Timestamp": ts.strftime("%Y-%m-%d %H:%M:%S") if isinstance(ts, datetime) else "N/A",
                    "Action": entry.get("action", "N/A"),
                    "Ticker": entry.get("ticker", "--"),
                    "Quantity": int(entry["quantity"]) if entry.get("quantity") is not None else None,
                    "Details": details_str
                })
        history_df = pd.DataFrame(history_df_data)
        st.dataframe(history_df, hide_index=True, use_container_width=True,
                        column_config={
                        "Quantity": st.column_config.NumberColumn(format="%d"),
                        "Details": st.column_config.TextColumn(width="medium")
                        })


# --- Main App Router ---

if not check_login():
    st.stop()

display_sidebar()

page = st.session_state.current_page

if page == PAGE_HOME: render_home()
elif page == PAGE_DASHBOARD: render_dashboard()
elif page == PAGE_NEW_ANALYSIS: render_new_analysis()
elif page == PAGE_JOB_STATUS: render_job_status()
elif page == PAGE_PAPER_TRADE: render_paper_trade()
else:
    st.session_state.current_page = PAGE_HOME # Default to Home
    render_home()
