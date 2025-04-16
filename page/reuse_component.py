import streamlit as st
from src.routers.trading import execute_paper_trade, get_paper_portfolio

# --- Reusable UI Components (if needed by multiple pages rendered from app.py) ---
def render_stock_details_popup(stock_data: dict):
    """Renders the popup for stock details and simple trading (used on Home page)."""
    ticker = stock_data.get('Ticker', 'N/A')
    current_price = stock_data.get('Price', 0.0)
    day_change_pct = stock_data.get('Change', 0.0) # Assumes 'Change' holds pct

    st.markdown(f"#### {ticker} Overview")
    col1, col2 = st.columns(2)
    col1.metric("Current Price", f"₹{current_price:,.2f}")

    delta_color = "off"
    if day_change_pct > 0: delta_color = "normal"
    elif day_change_pct < 0: delta_color = "inverse"
    col2.metric("Day's Change", f"{day_change_pct:+.2f}%", delta_color=delta_color)

    # --- Simple Trade Form ---
    st.subheader("Paper Trade Actions")
    username = st.session_state.logged_in_user

    action = st.radio("Action", ["Buy", "Sell"], horizontal=True, key=f"action_{ticker}_popup")

    portfolio_for_validation = None
    if action == "Sell":
        # Quick check using basic portfolio info is sufficient here
        portfolio_for_validation = get_paper_portfolio(username)

    with st.form(key=f"trade_form_{ticker}_popup"):
        if action == "Buy":
            trade_qty = st.number_input("Quantity to Buy", min_value=1, value=1, step=1, key=f"buy_qty_{ticker}_popup", format="%d")
        else: # Sell
            holding = None
            if portfolio_for_validation and not portfolio_for_validation.get("error"):
                holding = next((h for h in portfolio_for_validation.get("holdings", []) if h["ticker"] == ticker), None)
            max_sell_qty_int = int(holding['quantity']) if holding else 0
            trade_qty = st.number_input(f"Quantity to Sell (Max: {max_sell_qty_int})", min_value=0, max_value=max_sell_qty_int, value=0, step=1, key=f"sell_qty_{ticker}_popup", format="%d")

        trade_submitted = st.form_submit_button(f"Execute Paper {action}")

        if trade_submitted:
            try:
                final_trade_qty = int(trade_qty)
                if final_trade_qty <= 0:
                    st.warning("Quantity must be greater than zero.")
                elif action == "Sell":
                    # Re-validate against potentially changed portfolio right before execution
                    portfolio_now = get_paper_portfolio(username)
                    holding_now = next((h for h in portfolio_now.get("holdings", []) if h["ticker"] == ticker), None)
                    max_sell_now = int(holding_now['quantity']) if holding_now else 0
                    if final_trade_qty > max_sell_now:
                         st.warning(f"Cannot sell {final_trade_qty} shares. You now hold {max_sell_now}.")
                    else: # Valid Sell
                         success, message = execute_paper_trade(username, action, ticker, quantity=final_trade_qty)
                         if success: st.success(message); st.rerun()
                         else: st.error(message)
                else: # Valid Buy
                     success, message = execute_paper_trade(username, action, ticker, quantity=final_trade_qty)
                     if success: st.success(message); st.rerun()
                     else: st.error(message)
            except (ValueError, TypeError):
                 st.error("Invalid quantity entered. Please enter a whole number.")