import streamlit as st
import pandas as pd
import numpy as np
import time
import random
import uuid # For generating unique job IDs
from datetime import datetime
import hashlib # For password hashing
import os # For salt generation
import json # For file I/O

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

# --- File Paths for Persistent Data ---
DATA_DIR = "data" # Store data in a sub-directory
USERS_FILE = os.path.join(DATA_DIR, "users.json")
JOBS_FILE = os.path.join(DATA_DIR, "jobs_data.json")
PAPER_PORTFOLIOS_FILE = os.path.join(DATA_DIR, "paper_portfolios.json") # New file

# --- Ensure Data Directory Exists ---
os.makedirs(DATA_DIR, exist_ok=True)

# --- Password Hashing Utilities ---
def hash_password(password, salt=None):
    """Hashes the password using SHA-256 with a salt."""
    if salt is None:
        salt = os.urandom(16) # Generate a new random salt
    hashed_password = hashlib.pbkdf2_hmac(
        'sha256', password.encode('utf-8'), salt, 100000 # 100k iterations
    )
    return salt, hashed_password

def verify_password(stored_salt, stored_hash, provided_password):
    """Verifies a provided password against the stored salt and hash."""
    try:
        salt = bytes.fromhex(stored_salt) # Convert hex string back to bytes
        stored_hash_bytes = bytes.fromhex(stored_hash) # Convert hex string back to bytes
    except (ValueError, TypeError):
        # Handle cases where salt/hash might not be valid hex (e.g., old data)
        return False
    _, hashed_provided_password = hash_password(provided_password, salt)
    return hashed_provided_password == stored_hash_bytes

# --- Persistent Data Loading/Saving ---

# Use st.cache_data for loading to avoid reloading files on every script run within a session
@st.cache_data(ttl=60) # Cache for 60 seconds
def load_users():
    """Loads user data from the JSON file."""
    try:
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

# Manage jobs and portfolios manually for modification
_persistent_jobs_data = None
_persistent_paper_portfolios = None

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

def save_users(users_data):
    """Saves user data to the JSON file."""
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump(users_data, f, indent=4)
    except IOError as e:
        st.error(f"Error saving user data: {e}")

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

def load_paper_portfolios():
    """Loads paper portfolio data from the JSON file."""
    global _persistent_paper_portfolios
    if _persistent_paper_portfolios is None:
        try:
            with open(PAPER_PORTFOLIOS_FILE, 'r') as f:
                _persistent_paper_portfolios = json.load(f)
                if not isinstance(_persistent_paper_portfolios, dict): _persistent_paper_portfolios = {}
        except (FileNotFoundError, json.JSONDecodeError):
            _persistent_paper_portfolios = {}
    return _persistent_paper_portfolios

def save_paper_portfolios():
    """Saves the current state of paper portfolios to the JSON file."""
    global _persistent_paper_portfolios
    if _persistent_paper_portfolios is None: return
    try:
        # Datetimes in history should already be ISO strings
        with open(PAPER_PORTFOLIOS_FILE, 'w') as f:
            json.dump(_persistent_paper_portfolios, f, indent=4)
    except IOError as e: st.error(f"Error saving paper portfolio data: {e}")

# --- Initialize Persistent Data on App Start ---
load_jobs_data()
load_paper_portfolios()

# --- Session State Initialization ---
# --- Session State Initialization ---
def initialize_session():
    """Initializes session state variables."""
    if 'logged_in_user' not in st.session_state:
        st.session_state.logged_in_user = None
    if 'current_page' not in st.session_state:
        st.session_state.current_page = PAGE_LOGIN
    if 'selected_job_id' not in st.session_state:
        st.session_state.selected_job_id = None
    if 'home_market_cap_filter' not in st.session_state:
        st.session_state.home_market_cap_filter = "All"
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

# --- Paper Portfolio Helper Functions ---

def get_paper_portfolio(username):
    """Gets the paper portfolio for a user, creating if it doesn't exist."""
    portfolios = load_paper_portfolios()
    if username not in portfolios:
        portfolios[username] = {
            "cash": 100000.00, "holdings": [], "history": [],
            "last_simulated_update": datetime.min.isoformat() # Start with min date
        }
        global _persistent_paper_portfolios
        _persistent_paper_portfolios = portfolios
        save_paper_portfolios()
    # Ensure essential keys exist even if loaded from file
    portfolio = portfolios[username]
    portfolio.setdefault("cash", 0.0)
    portfolio.setdefault("holdings", [])
    portfolio.setdefault("history", [])
    portfolio.setdefault("last_simulated_update", datetime.min.isoformat())
    return portfolio

def update_paper_portfolio(username, portfolio_data):
    """Updates and saves the paper portfolio for a user."""
    global _persistent_paper_portfolios
    if _persistent_paper_portfolios is None: _persistent_paper_portfolios = load_paper_portfolios()
    _persistent_paper_portfolios[username] = portfolio_data
    save_paper_portfolios()

# --- Simulation Functions ---
# Keep simulation functions simple for the demo

_simulated_prices = {} # Cache simulated prices within a run

def get_simulated_price(ticker):
    """Gets a simulated 'current' price for a ticker."""
    if ticker not in _simulated_prices:
        # Base price on ticker hash for some consistency, add randomness
        base = int(hashlib.sha1(ticker.encode()).hexdigest(), 16) % 500 + 10 # Base price 10-510
        _simulated_prices[ticker] = round(base * random.uniform(0.9, 1.1), 2)
    # Add slight fluctuation on subsequent calls within the same run
    _simulated_prices[ticker] *= random.uniform(0.998, 1.002)
    return round(max(0.01, _simulated_prices[ticker]), 2) # Ensure price is positive

def simulate_portfolio_performance(portfolio):
    """Very basic simulation of daily performance change."""
    try:
        last_update = datetime.fromisoformat(portfolio.get("last_simulated_update", datetime.min.isoformat()))
    except ValueError:
        last_update = datetime.min # Handle invalid format

    # Simulate only if enough time has passed (e.g., > 4 hours)
    if (datetime.now() - last_update).total_seconds() < 3600 * 4:
        return portfolio

    current_holdings_value = 0.0
    for holding in portfolio.get("holdings", []):
        current_price = get_simulated_price(holding['ticker']) # Use simulated price
        current_holdings_value += holding.get("quantity", 0) * current_price

    # Calculate old value based on *average cost* for comparison
    old_holdings_value = sum(h['quantity'] * h['avg_cost'] for h in portfolio.get("holdings", []))
    old_total_value = portfolio.get("cash", 0.0) + old_holdings_value

    # New total value based on *current simulated prices*
    new_total_value = portfolio.get("cash", 0.0) + current_holdings_value

    # Calculate the change and adjust cash (simple way to reflect value change)
    value_diff = new_total_value - old_total_value
    portfolio["cash"] = portfolio.get("cash", 0.0) + value_diff
    portfolio["last_simulated_update"] = datetime.now().isoformat()

    if abs(value_diff) > 0.01: # Log only if there's a noticeable change
        portfolio.setdefault("history", []).append({
            "timestamp": datetime.now().isoformat(),
            "action": "SIM_PERF",
            "details": {"simulated_value_change": round(value_diff, 2), "new_cash_value": round(portfolio["cash"], 2)}
        })

    return portfolio

# --- Authentication ---

def check_login():
    """Handles user login using hashed passwords from the persistent store."""
    if st.session_state.logged_in_user:
        return True

    st.title("🔒 AI Portfolio Manager Login")
    users_db = load_users()

    if not users_db:
        st.info("No users found. Please register the first admin user.")
        with st.form("register_form"):
            reg_username = st.text_input("Choose Admin Username").lower()
            reg_password = st.text_input("Choose Admin Password", type="password")
            reg_submitted = st.form_submit_button("Register Admin")
            if reg_submitted:
                if reg_username and reg_password:
                    if reg_username in users_db:
                         st.error("Username already exists.")
                    else:
                        salt, hashed_pw = hash_password(reg_password)
                        users_db[reg_username] = {"salt": salt.hex(), "hashed_password": hashed_pw.hex()}
                        save_users(users_db)
                        st.success(f"Admin user '{reg_username}' registered successfully! Please login.")
                        time.sleep(1)
                        st.rerun()
                else:
                    st.error("Username and password cannot be empty.")
        return False

    with st.form("login_form"):
        username = st.text_input("Username").lower()
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

        if submitted:
            user_data = users_db.get(username)
            if user_data and verify_password(user_data.get("salt",""), user_data.get("hashed_password",""), password):
                st.session_state.logged_in_user = username
                st.session_state.current_page = PAGE_HOME # Default to home after login
                # Clear any leftover proposed trades from previous sessions/users
                st.session_state.proposed_trades = None
                st.session_state.reviewed_trades = None
                st.rerun()
            else:
                st.error("Invalid username or password.")
    return False

# --- Navigation ---

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
    st.sidebar.markdown("---")
    st.sidebar.button("🚪 Logout", on_click=logout, use_container_width=True)

def logout():
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
        instructions = st.text_area("**Instructions:**", height=150, placeholder="e.g., Invest $50k...")
        with st.expander("Advanced Filters (Optional)"):
            budget = st.number_input("Budget ($)", min_value=1000, value=25000, step=1000, format="%d")
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
                    col2.metric("Amount", f"${amount:,.2f}")
                    col3.metric("Exp. Ann. Return", f"{stock_info.get('Annualized Return (%)', 0.0):.2f}%")
                    col4.metric("Exp. Sharpe Ratio", f"{stock_info.get('Sharpe Ratio', 0.0):.2f}")
            st.markdown("---")
            st.subheader("Portfolio Summary")
            summary_col1, summary_col2 = st.columns(2)
            summary_col1.metric("Target Budget", f"${budget:,.2f}")
            summary_col2.metric("Total Allocated", f"${total_allocated_amount:,.2f}")
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

# --- Home Page Rendering ---
def generate_dummy_market_data(cap_filter="All"):
    # Define the base data within the function or load from a source
    all_stocks = {
        "AAPL": {"Cap": "Large-Cap", "Price": 175.20, "Change": 1.5}, "MSFT": {"Cap": "Large-Cap", "Price": 305.50, "Change": -0.8},
        "GOOGL": {"Cap": "Large-Cap", "Price": 105.10, "Change": 2.1}, "AMZN": {"Cap": "Large-Cap", "Price": 102.80, "Change": -1.2},
        "TSLA": {"Cap": "Large-Cap", "Price": 190.60, "Change": 3.5}, "NVDA": {"Cap": "Large-Cap", "Price": 450.00, "Change": 4.1},
        "ETSY": {"Cap": "Mid-Cap", "Price": 115.30, "Change": 2.8}, "DOCN": {"Cap": "Mid-Cap", "Price": 35.70, "Change": -2.5},
        "PLTR": {"Cap": "Mid-Cap", "Price": 15.10, "Change": 5.5}, "RBLX": {"Cap": "Mid-Cap", "Price": 38.90, "Change": -1.9},
        "SAVA": {"Cap": "Small-Cap", "Price": 25.40, "Change": 10.2}, "GME": {"Cap": "Small-Cap", "Price": 18.60, "Change": -5.1},
        "AMC": {"Cap": "Small-Cap", "Price": 4.50, "Change": 7.3}, "BBBY": {"Cap": "Small-Cap", "Price": 0.20, "Change": -15.0}, # Note: BBBY is delisted, just for demo
    }

    # Simulate missing change data if needed (can be removed if data is complete)
    for ticker in all_stocks:
        if "Change" not in all_stocks[ticker]:
             all_stocks[ticker]["Change"] = round(random.uniform(-8.0, 8.0), 1)

    # Filter tickers based on market cap
    filtered_tickers = [t for t, info in all_stocks.items() if cap_filter == "All" or info["Cap"] == cap_filter]

    if not filtered_tickers:
        return [], [], all_stocks # Return empty lists and the full stock dict

    # Sort filtered tickers by change
    sorted_tickers = sorted(filtered_tickers, key=lambda t: all_stocks[t]["Change"], reverse=True)

    # Select top 5 gainers and losers from the *filtered* list
    gainers = [{"Ticker": t, **all_stocks[t]} for t in sorted_tickers if all_stocks[t]["Change"] > 0][:5]
    losers = [{"Ticker": t, **all_stocks[t]} for t in sorted_tickers if all_stocks[t]["Change"] < 0][::-1][:5] # Reverse losers list to show worst first

    return gainers, losers, all_stocks # <-- RETURN all_stocks

def generate_dummy_indices():
    return [
        {"Name": "S&P 500", "Value": 4350.25, "Change": 15.75, "Change %": 0.36},
        {"Name": "NASDAQ", "Value": 13580.10, "Change": 85.30, "Change %": 0.63},
        {"Name": "Dow Jones", "Value": 34050.60, "Change": -50.10, "Change %": -0.15},
    ]

def execute_paper_trade(username, action, ticker, quantity=None, amount=None):
    """Executes a buy or sell paper trade."""
    portfolio = get_paper_portfolio(username)
    current_price = get_simulated_price(ticker)
    if current_price <= 0: return False, "Invalid simulated price."

    if action == "Buy":
        if amount is None or amount <= 0: return False, "Invalid amount."
        if portfolio["cash"] < amount: return False, "Insufficient cash."
        quantity_to_buy = amount / current_price
        portfolio["cash"] -= amount
        existing_holding = next((h for h in portfolio["holdings"] if h["ticker"] == ticker), None)
        if existing_holding:
            new_total_qty = existing_holding["quantity"] + quantity_to_buy
            new_total_cost = (existing_holding["avg_cost"] * existing_holding["quantity"]) + amount
            existing_holding["avg_cost"] = new_total_cost / new_total_qty
            existing_holding["quantity"] = new_total_qty
        else:
            portfolio["holdings"].append({"ticker": ticker, "quantity": quantity_to_buy, "avg_cost": current_price})
        portfolio["history"].append({"timestamp": datetime.now().isoformat(), "action": "BUY", "details": {"ticker": ticker, "quantity": round(quantity_to_buy, 4), "price": current_price, "cost": round(amount, 2)}})
        update_paper_portfolio(username, portfolio)
        return True, f"Bought {quantity_to_buy:.4f} shares of {ticker}."

    elif action == "Sell":
        if quantity is None or quantity <= 0: return False, "Invalid quantity."
        holding = next((h for h in portfolio["holdings"] if h["ticker"] == ticker), None)
        if not holding: return False, f"No holdings found for {ticker}."
        if quantity > holding["quantity"]: return False, "Cannot sell more than held."
        proceeds = quantity * current_price
        portfolio["cash"] += proceeds
        holding["quantity"] -= quantity
        if holding["quantity"] < 0.0001: portfolio["holdings"] = [h for h in portfolio["holdings"] if h["ticker"] != ticker]
        portfolio["history"].append({"timestamp": datetime.now().isoformat(), "action": "SELL", "details": {"ticker": ticker, "quantity": round(quantity, 4), "price": current_price, "proceeds": round(proceeds, 2)}})
        update_paper_portfolio(username, portfolio)
        return True, f"Sold {quantity:.4f} shares of {ticker}."
    else:
        return False, "Invalid action."


def render_stock_details_popup(ticker):
    """Renders dummy stock details and Buy/Sell options."""
    st.markdown(f"#### {ticker} Overview (Simulated)")
    col1, col2 = st.columns(2)
    current_price = get_simulated_price(ticker)
    col1.metric("Current Price", f"${current_price:.2f}")
    # Simulate a day change based on current vs slightly older price
    day_change_pct = (current_price / (current_price / random.uniform(0.97, 1.03)) - 1) * 100
    col2.metric("Day's Change", f"{day_change_pct:.2f}%", delta_color=("inverse" if day_change_pct < 0 else "normal"))
    # Simple random walk for chart
    # price_history = (np.random.randn(20) * (current_price * 0.01)).cumsum() + current_price
    # st.line_chart(pd.DataFrame(price_history, columns=['Price']))
    # st.caption("Recent simulated performance.")
    # st.markdown("---")
    st.subheader("Paper Trade Actions")
    action = st.radio("Action", ["Buy", "Sell"], horizontal=True, key=f"action_{ticker}")

    username = st.session_state.logged_in_user
    portfolio = get_paper_portfolio(username) # Needed for sell validation

    with st.form(key=f"trade_form_{ticker}"):
        if action == "Buy":
            buy_amount = st.number_input("Amount to Invest ($)", min_value=1.0, value=100.0, step=10.0, key=f"buy_amount_{ticker}", help="Amount of cash to spend.")
            trade_qty = None # Quantity determined by amount/price
        else: # Sell
            holding = next((h for h in portfolio.get("holdings", []) if h["ticker"] == ticker), None)
            max_sell_qty = holding['quantity'] if holding else 0.0
            trade_qty = st.number_input(f"Quantity to Sell (Max: {max_sell_qty:.4f})", min_value=0.0, max_value=max_sell_qty, value=0.0, step=0.0001, key=f"sell_qty_{ticker}", format="%.4f")
            buy_amount = None # Amount determined by qty*price

        trade_submitted = st.form_submit_button(f"Execute Paper {action}")

        if trade_submitted:
            success, message = execute_paper_trade(username, action, ticker, quantity=trade_qty, amount=buy_amount)
            if success:
                st.success(message)
                # Clear price cache to get potentially new price on rerun
                global _simulated_prices
                if ticker in _simulated_prices: del _simulated_prices[ticker]
                st.rerun()
            else:
                st.error(message)

def render_home():
    st.title("📈 Market Overview")

    # --- Indices ---
    st.subheader("Major Indices (Simulated)")
    indices = generate_dummy_indices()
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

    # --- Get Market Data (Gainers/Losers/All Stocks) ---
    # (Rest of the function remains the same as the previous corrected version)
    gainers, losers, all_stocks_data = generate_dummy_market_data(st.session_state.home_market_cap_filter)

    # --- Display Search Result ---
    if st.session_state.home_search_query:
        search_ticker = st.session_state.home_search_query
        stock_info = all_stocks_data.get(search_ticker)
        st.markdown("---") # Separator for search result
        if stock_info:
            st.markdown(f"#### Search Result: {search_ticker}")
            with st.container(border=True):
                s_col1, s_col2 = st.columns([3, 1])
                change_pct = stock_info.get('Change', 0.0)
                price = stock_info.get('Price', 0.0)
                cap = stock_info.get('Cap', 'N/A')
                color = "green" if change_pct > 0 else ("red" if change_pct < 0 else "grey")

                s_col1.markdown(f"**{search_ticker}** ({cap})")
                s_col1.caption(f"Price: ${price:.2f}")
                s_col2.markdown(f"<span style='color:{color}; font-weight:bold;'>{change_pct:+.1f}%</span>", unsafe_allow_html=True)
                with st.expander("Details / Trade"):
                    render_stock_details_popup(search_ticker)
        else:
            st.warning(f"Ticker '{search_ticker}' not found in simulated data.")
        st.markdown("---") # Separator after search result

    # --- Movers Section ---
    st.subheader("Today's Movers (Simulated)")
    cap_options = ["All", "Large-Cap", "Mid-Cap", "Small-Cap"]
    default_cap_index = 0
    try:
        default_cap_index = cap_options.index(st.session_state.home_market_cap_filter)
    except ValueError:
        st.session_state.home_market_cap_filter = "All"

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

    # Display Gainers/Losers
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Top Gainers")
        if not gainers: st.caption(f"No gainers found for '{st.session_state.home_market_cap_filter}' filter.")
        for stock in gainers:
            with st.container(border=True):
                s_col1, s_col2 = st.columns([3, 1])
                s_col1.markdown(f"**{stock['Ticker']}** ({stock['Cap']})")
                s_col1.caption(f"Price: ${stock['Price']:.2f}")
                s_col2.markdown(f"<span style='color:green; font-weight:bold;'>+{stock['Change']:.1f}%</span>", unsafe_allow_html=True)
                with st.expander("Details / Trade"):
                     render_stock_details_popup(stock['Ticker'])
    with col2:
        st.markdown("#### Top Losers")
        if not losers: st.caption(f"No losers found for '{st.session_state.home_market_cap_filter}' filter.")
        for stock in losers:
             with st.container(border=True):
                s_col1, s_col2 = st.columns([3, 1])
                s_col1.markdown(f"**{stock['Ticker']}** ({stock['Cap']})")
                s_col1.caption(f"Price: ${stock['Price']:.2f}")
                s_col2.markdown(f"<span style='color:red; font-weight:bold;'>{stock['Change']:.1f}%</span>", unsafe_allow_html=True)
                with st.expander("Details / Trade"):
                     render_stock_details_popup(stock['Ticker'])

# --- Paper Trading Page Rendering ---
def render_paper_trade():
    st.title("📄 Paper Trading Portfolio")
    username = st.session_state.logged_in_user
    portfolio = get_paper_portfolio(username)

    # Simulate performance update on page load
    portfolio = simulate_portfolio_performance(portfolio)
    update_paper_portfolio(username, portfolio) # Save potential simulation changes

    # --- Add Funds Section ---
    with st.expander("💰 Add Funds"):
        with st.form("add_funds_form"):
            amount_to_add = st.number_input("Amount ($)", min_value=0.01, value=1000.0, step=100.0)
            add_funds_submitted = st.form_submit_button("Add Funds to Cash Balance")
            if add_funds_submitted:
                portfolio["cash"] += amount_to_add
                portfolio["history"].append({
                    "timestamp": datetime.now().isoformat(),
                    "action": "ADD_FUNDS",
                    "details": {"amount": round(amount_to_add, 2)}
                })
                update_paper_portfolio(username, portfolio)
                st.success(f"Successfully added ${amount_to_add:,.2f} to cash balance.")
                st.rerun() # Rerun to update displayed balances

    # --- Proposed Trades Section (if applicable) ---
    if 'proposed_trades' in st.session_state and st.session_state.proposed_trades:
        st.subheader("📝 Review Proposed Trades from AI Analysis")
        st.caption("Review and adjust the target amounts for the portfolio suggested by the AI analysis. The system will calculate quantities based on simulated current prices.")

        proposed_df = pd.DataFrame(st.session_state.proposed_trades)

        # Use st.data_editor for editing target amounts
        edited_df = st.data_editor(
            proposed_df,
            column_config={
                "Ticker": st.column_config.TextColumn("Ticker", disabled=True),
                "Target Amount": st.column_config.NumberColumn("Target Amount ($)", min_value=0.0, step=10.0, format="$%.2f"),
                "Strategy": st.column_config.TextColumn("Strategy", disabled=True),
            },
            num_rows="dynamic", # Allow removing rows
            key="proposed_trades_editor"
        )

        if st.button("🔍 Review & Calculate Trades"):
            reviewed_trades_list = []
            total_cost = 0.0
            errors = []
            current_cash = portfolio.get("cash", 0.0)

            for index, row in edited_df.iterrows():
                ticker = row["Ticker"]
                target_amount = row["Target Amount"]
                if not ticker or target_amount <= 0:
                    continue # Skip removed or zero amount rows

                current_price = get_simulated_price(ticker)
                if current_price <= 0:
                    errors.append(f"Could not get valid price for {ticker}.")
                    continue

                quantity = target_amount / current_price
                cost = quantity * current_price # Should be very close to target_amount
                total_cost += cost
                reviewed_trades_list.append({
                    "Ticker": ticker,
                    "Quantity": round(quantity, 4),
                    "Simulated Price ($)": current_price,
                    "Estimated Cost ($)": round(cost, 2)
                })

            st.session_state.reviewed_trades = {
                "trades": reviewed_trades_list,
                "total_cost": round(total_cost, 2),
                "errors": errors,
                "sufficient_cash": current_cash >= total_cost
            }
            st.rerun() # Rerun to show the confirmation section

        # --- Confirmation Section ---
        if 'reviewed_trades' in st.session_state and st.session_state.reviewed_trades:
            review_data = st.session_state.reviewed_trades
            st.markdown("---")
            st.subheader("Confirm Execution")

            if review_data["errors"]:
                for error in review_data["errors"]: st.error(error)

            if review_data["trades"]:
                st.dataframe(pd.DataFrame(review_data["trades"]), hide_index=True)
                st.metric("Estimated Total Cost", f"${review_data['total_cost']:,.2f}")
                st.metric("Available Cash", f"${portfolio.get('cash', 0.0):,.2f}")

                if not review_data["sufficient_cash"]:
                    st.error("Insufficient cash to execute all reviewed trades.")
                else:
                    if st.button("✅ Execute Confirmed Trades", type="primary"):
                        success_count = 0
                        fail_count = 0
                        # Get fresh portfolio data before executing multiple trades
                        current_portfolio = get_paper_portfolio(username)
                        for trade in review_data["trades"]:
                            # Use the calculated quantity and amount (cost) for execution
                            success, msg = execute_paper_trade(username, "Buy", trade["Ticker"], amount=trade["Estimated Cost ($)"])
                            if success: success_count += 1
                            else: fail_count += 1; st.warning(f"Failed to buy {trade['Ticker']}: {msg}")

                        st.success(f"Executed {success_count} trades successfully.")
                        if fail_count > 0: st.error(f"{fail_count} trades failed.")
                        # Clear proposed and reviewed trades from state after execution
                        st.session_state.proposed_trades = None
                        st.session_state.reviewed_trades = None
                        st.rerun() # Rerun to show updated portfolio
            else:
                st.warning("No valid trades calculated for execution.")


    # --- Portfolio Summary ---
    st.divider()
    st.subheader("Portfolio Summary")
    holdings = portfolio.get("holdings", [])
    cash = portfolio.get("cash", 0.0)
    holdings_value = 0.0
    for holding in holdings:
        current_price = get_simulated_price(holding['ticker']) # Use simulated price for current value
        holdings_value += holding.get("quantity", 0) * current_price
    total_value = cash + holdings_value

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Portfolio Value", f"${total_value:,.2f}")
    col2.metric("Cash Balance", f"${cash:,.2f}")
    col3.metric("Holdings Value", f"${holdings_value:,.2f}")

    # --- Current Holdings ---
    st.subheader("Current Holdings")
    if not holdings: st.info("You currently have no holdings.")
    else:
        holdings_df_data = []
        for h in holdings:
            current_price = get_simulated_price(h['ticker'])
            current_holding_value = h.get("quantity", 0) * current_price
            pnl = current_holding_value - (h.get("quantity", 0) * h.get("avg_cost", 0))
            pnl_pct = (pnl / (h.get("quantity", 0) * h.get("avg_cost", 0)) * 100) if h.get("quantity", 0) * h.get("avg_cost", 0) != 0 else 0
            holdings_df_data.append({
                "Ticker": h["ticker"], "Quantity": h["quantity"], "Average Cost ($)": h["avg_cost"],
                "Current Price ($)": current_price, "Current Value ($)": current_holding_value,
                "P/L ($)": pnl, "P/L (%)": pnl_pct
            })
        holdings_df = pd.DataFrame(holdings_df_data)
        st.dataframe(
            holdings_df, hide_index=True, use_container_width=True,
            column_config={
                "Quantity": st.column_config.NumberColumn(format="%.4f"),
                "Average Cost ($)": st.column_config.NumberColumn(format="$%.2f"),
                "Current Price ($)": st.column_config.NumberColumn(format="$%.2f"),
                "Current Value ($)": st.column_config.NumberColumn(format="$%.2f"),
                "P/L ($)": st.column_config.NumberColumn(format="$%.2f"),
                "P/L (%)": st.column_config.NumberColumn(format="%.2f%%"),
            }
        )

    # --- Trade History ---
    st.subheader("Trade History")
    history = portfolio.get("history", [])
    if not history: st.caption("No trading history yet.")
    else:
        history_df_data = []
        for entry in sorted(history, key=lambda x: x.get("timestamp", ""), reverse=True)[:20]:
             ts_str = entry.get("timestamp", "")
             ts = datetime.fromisoformat(ts_str) if ts_str else datetime.min
             details_str = json.dumps(entry.get("details", {}))
             history_df_data.append({
                 "Timestamp": ts.strftime("%Y-%m-%d %H:%M:%S") if ts != datetime.min else "N/A",
                 "Action": entry.get("action", "N/A"),
                 "Details": details_str
             })
        history_df = pd.DataFrame(history_df_data)
        st.dataframe(history_df, hide_index=True, use_container_width=True)


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
