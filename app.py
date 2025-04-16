import streamlit as st

# --- Page Setup (Should be first Streamlit command) ---
st.set_page_config(layout='wide', page_title="AI Hedge Fund", page_icon=":moneybag:")
import install_talib

# --- Core Imports ---
import time
import os

import warnings
warnings.filterwarnings("ignore")

# --- Cookie Manager ---
from streamlit_cookies_manager import EncryptedCookieManager

# --- Authentication & Core Routers ---
from src.routers.auth import authenticate_user

# --- Data Sources Needed by Core App (e.g., Home Page) ---
from src.data_source.apis_2 import get_live_indices_pricing
from src.data_source.apis_3 import get_tickertape_movers, search_tickertape_stocks

# --- Page Rendering Modules ---
from page.analysis import render_dashboard, render_job_status, render_new_analysis
from page.paper_trading import initialize_paper_trading_session, render_paper_trade # Import render function
from page.stock_research import initialize_stock_research_session, render_stock_research # Import init and render
from page.reuse_component import render_stock_details_popup

# --- Constants ---
PAGE_LOGIN = "login"
PAGE_HOME = "home"
PAGE_NEW_ANALYSIS = "new_analysis"
PAGE_JOB_STATUS = "job_status"
# PAGE_DASHBOARD = "dashboard"
PAGE_PAPER_TRADE = "paper_trade"
PAGE_STOCK_RESEARCH = "stock_research"
LOGIN_COOKIE_NAME = "ai_hedge_fund_user_session"
COOKIE_EXPIRY_DAYS = 7

# --- Initialize Cookie Manager ---
cookie_password = os.environ.get("STREAMLIT_COOKIE_PASSWORD", "admin")
cookies = EncryptedCookieManager(
    password=cookie_password,
    prefix="ai_hedge_fund/",
)
# Wait for cookies
if not cookies.ready():
    st.spinner("Loading session...")
    st.stop()

# --- Initialize Persistent Data & Session States --

# Central session state initialization
def initialize_session():
    """Initializes core session state variables."""
    # User Login State (driven by cookie)
    if 'logged_in_user' not in st.session_state:
        user_from_cookie = cookies.get(LOGIN_COOKIE_NAME)
        if user_from_cookie is not None and user_from_cookie != "logout":
            st.session_state.logged_in_user = user_from_cookie
        else:
            st.session_state.logged_in_user = None

    # Navigation State
    if 'current_page' not in st.session_state:
        # Set initial page based on login status
        st.session_state.current_page = PAGE_HOME if st.session_state.logged_in_user else PAGE_LOGIN

    # Analysis Job State (if needed globally)
    if 'selected_job_id' not in st.session_state:
        st.session_state.selected_job_id = None

    # Home Page Specific State
    if 'home_market_cap_filter' not in st.session_state:
        st.session_state.home_market_cap_filter = "LargeCap"
    if 'home_search_query' not in st.session_state:
        st.session_state.home_search_query = ""

initialize_session()
initialize_stock_research_session()
initialize_paper_trading_session()


# --- Authentication Logic ---
def check_login():
    """Handles user login form and checks authentication status."""
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
                st.session_state.current_page = PAGE_HOME # Default to home
                # Clear potentially sensitive trading states on new login
                st.session_state.proposed_trades = None
                st.session_state.reviewed_trades = None
                # Set login cookie
                cookies[LOGIN_COOKIE_NAME] = username
                cookies.save()
                st.success(f"Welcome, {username}!")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("Invalid username or password.")
    return False

# --- Navigation ---
def navigate_to(page_name, job_id=None, clear_proposed=False):
    """Updates session state to navigate to a different page."""
    st.session_state.current_page = page_name
    st.session_state.selected_job_id = job_id
    if clear_proposed:
        st.session_state.proposed_trades = None
        st.session_state.reviewed_trades = None
    st.rerun()

# --- Logout ---
def logout():
    """Logs the user out, clears relevant session state and cookie."""
    # Clear cookie by setting to 'logout' or deleting
    cookies[LOGIN_COOKIE_NAME] = "logout" # Or del cookies[LOGIN_COOKIE_NAME]
    cookies.save()

    # Clear sensitive session state keys
    keys_to_clear = [
        'logged_in_user', 'selected_job_id', 'proposed_trades', 'reviewed_trades',
        'stock_research_query', 'stock_search_results', 'selected_stock_for_analysis',
        'stock_analysis_results', 'analyze_button_clicked' # Clear research state too
    ]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]

    # Reset to login page and re-initialize basic state
    st.session_state.current_page = PAGE_LOGIN
    initialize_session() # Re-initialize core session state (which will set user to None)
    initialize_stock_research_session() # Re-initialize research state
    st.rerun()

# --- Sidebar ---
def display_sidebar():
    """Renders the sidebar navigation."""
    if not st.session_state.logged_in_user: return # Don't show sidebar if not logged in

    st.sidebar.header(f"Welcome, {st.session_state.logged_in_user}!")

    # Navigation Buttons
    pages = {
        "🏠 Home": PAGE_HOME,
        "🔍 Stock Research": PAGE_STOCK_RESEARCH,
        # "⚙️ AI Analysis Dashboard": PAGE_DASHBOARD,
        "➕ Start New Analysis": PAGE_NEW_ANALYSIS,
        "📊 View Analysis Jobs": PAGE_JOB_STATUS,
        "📄 Paper Trading": PAGE_PAPER_TRADE,
    }

    for label, page_key in pages.items():
        # Determine if proposed trades should be cleared (True for all except Paper Trading)
        clear_proposed = (page_key != PAGE_PAPER_TRADE)
        # Set button type based on current page
        button_type = "primary" if st.session_state.current_page == page_key else "secondary"
        st.sidebar.button(label, on_click=navigate_to, args=(page_key, None, clear_proposed),
                          use_container_width=True, type=button_type)

    st.sidebar.markdown("---")
    # Refresh Button
    if st.sidebar.button("🔄 Refresh Data", use_container_width=True, key="manual_refresh"):
        # Add any specific cache clearing logic here if needed before rerun
        st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.button("🚪 Logout", on_click=logout, use_container_width=True)

# --- Home Page Rendering (Keep in app.py for now) ---
def render_home():
    """Renders the Home page content."""
    st.title("📈 Market Overview")

    # Indices
    st.subheader("Indices")
    try:
        indices = get_live_indices_pricing()
        if indices:
            idx_cols = st.columns(len(indices))
            for i, idx in enumerate(indices):
                delta = f"{idx['Change']:+.2f} ({idx['Change %']:+.2f}%)"
                idx_cols[i].metric(label=idx["Name"], value=f"{idx['Value']:.2f}", delta=delta)
        else:
            st.warning("Could not fetch live index data.")
    except Exception as e:
        st.error(f"Error loading indices: {e}")

    st.divider()

    # Stock Search on Home Page
    st.subheader("🔍 Stock Search")
    # CSS to align search button (optional, adjust px value as needed)
    st.markdown("""<style> div[data-testid="stHorizontalBlock"] > div:nth-child(2) > div > div > div > button { margin-top: 28px; } </style>""", unsafe_allow_html=True)

    search_col1, search_col2 = st.columns([3, 1])
    with search_col1:
        search_term = st.text_input(
            "Enter Ticker Symbol:", value=st.session_state.home_search_query,
            key="home_search_input", placeholder="Enter Ticker Symbol (e.g., RELIANCE, INFY)",
            label_visibility='collapsed'
        )
    with search_col2:
        if st.button("Search", key="home_search_button", use_container_width=True):
            st.session_state.home_search_query = search_term.strip().upper()
            st.rerun() # Rerun to display results

    # Display Home Search Result
    if st.session_state.home_search_query:
        query = st.session_state.home_search_query
        st.markdown("---")
        st.markdown(f"#### Search Results for: \"{query}\"")
        with st.spinner(f"Searching for {query}..."):
            search_results = search_tickertape_stocks(query, limit=5)

        if search_results is None: st.error("An error occurred while searching.")
        elif not search_results: st.info(f"No NSE stock results found matching \"{query}\".")
        else:
            for stock in search_results:
                change_pct = stock.get('Change %', 0.0)
                color = "green" if change_pct > 0 else ("red" if change_pct < 0 else "grey")
                with st.container(border=True):
                    s_col1, s_col2 = st.columns([3, 1])
                    s_col1.markdown(f"**{stock.get('Ticker', 'N/A')}**")
                    s_col1.caption(f"{stock.get('Name', 'Unknown Name')}")
                    s_col1.caption(f"Price: ₹{stock.get('Price', 0.0):,.2f}")
                    s_col2.markdown(f"<span style='color:{color}; font-weight:bold;'>{change_pct:+.2f}%</span>", unsafe_allow_html=True)
                    with st.expander("Details / Trade"):
                        # Prepare data for the popup function
                        popup_stock_data = {
                            "Ticker": stock.get('Ticker', 'N/A'),
                            "Name": stock.get('Name', 'Unknown Name'),
                            "Price": stock.get('Price', 0.0),
                            "Change": stock.get('Change %', 0.0) # Pass Change % as 'Change'
                        }
                        render_stock_details_popup(popup_stock_data) # Call the popup renderer
        st.markdown("---")

    # Movers Section
    st.subheader("Today's Movers (Simulated)")
    cap_options = ["LargeCap", "MidCap", "SmallCap"]
    # Use session state for persistence
    selected_cap = st.radio(
        "Filter by Market Cap:", cap_options,
        index=cap_options.index(st.session_state.home_market_cap_filter) if st.session_state.home_market_cap_filter in cap_options else 0,
        horizontal=True, key="home_cap_filter_radio"
    )
    # Update session state and rerun if selection changes
    if selected_cap != st.session_state.home_market_cap_filter:
        st.session_state.home_market_cap_filter = selected_cap
        st.rerun()

    with st.spinner(f"Fetching {selected_cap} movers..."):
        gainers, losers = get_tickertape_movers(universe=selected_cap, count=5)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Top Gainers")
        if gainers is None: st.error("Error fetching gainers.")
        elif not gainers: st.caption(f"No gainers found for '{selected_cap}'.")
        else:
            for stock in gainers:
                with st.container(border=True):
                    s_col1, s_col2 = st.columns([3, 1])
                    s_col1.markdown(f"**{stock['Ticker']}** ({stock['Cap']})")
                    s_col1.caption(f"Price: ₹{stock['Price']:.2f}")
                    s_col2.markdown(f"<span style='color:green; font-weight:bold;'>+{stock['Change']:.1f}%</span>", unsafe_allow_html=True)
                    with st.expander("Details / Trade"): render_stock_details_popup(stock)
    with col2:
        st.markdown("#### Top Losers")
        if losers is None: st.error("Error fetching losers.")
        elif not losers: st.caption(f"No losers found for '{selected_cap}'.")
        else:
             for stock in losers:
                 with st.container(border=True):
                    s_col1, s_col2 = st.columns([3, 1])
                    s_col1.markdown(f"**{stock['Ticker']}** ({stock['Cap']})")
                    s_col1.caption(f"Price: ₹{stock['Price']:.2f}")
                    s_col2.markdown(f"<span style='color:red; font-weight:bold;'>{stock['Change']:.1f}%</span>", unsafe_allow_html=True)
                    with st.expander("Details / Trade"): render_stock_details_popup(stock)

# --- Main Application Flow ---
if __name__ == "__main__":
    # Check Login Status
    if not check_login():
        st.stop() # Stop execution if login fails or form is displayed

    # Display Sidebar
    display_sidebar()

    # --- Page Router ---
    page = st.session_state.current_page

    if page == PAGE_HOME:
        render_home()
    # elif page == PAGE_DASHBOARD:
    #     render_dashboard()
    elif page == PAGE_NEW_ANALYSIS:
        render_new_analysis()
    elif page == PAGE_JOB_STATUS:
        render_job_status()
    elif page == PAGE_PAPER_TRADE:
        render_paper_trade() # Call function from imported module
    elif page == PAGE_STOCK_RESEARCH:
        render_stock_research() # Call function from imported module
    else:
        # Default to home page if current_page is invalid
        st.session_state.current_page = PAGE_HOME
        render_home()