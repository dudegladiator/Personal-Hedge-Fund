import time
import streamlit as st
import pandas as pd
import json
from datetime import datetime

# --- Imports required specifically for Paper Trading ---
from src.data_source.apis_1 import get_live_price # Needed for proposed trades calculation
from src.routers.trading import (
    add_funds_to_portfolio,
    execute_paper_trade,
    get_detailed_paper_portfolio,
    get_paper_transactions,
    get_paper_portfolio # Still needed for quick check in popup/trade form
)

def initialize_paper_trading_session():
    defaults = {
        'proposed_trades': None,
        'reviewed_trades': None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

# --- Main Paper Trading Rendering Function ---
def render_paper_trade():
    """Renders the entire Paper Trading page UI and logic."""
    st.title("📄 Paper Trading Portfolio")

    # Ensure user is logged in (although app.py should handle this route guarding)
    if 'logged_in_user' not in st.session_state or not st.session_state.logged_in_user:
        st.warning("Please log in to view the paper trading portfolio.")
        return # Avoid running if not logged in

    username = st.session_state.logged_in_user
    # Fetch fresh portfolio details each time the page renders
    portfolio_details = get_detailed_paper_portfolio(username)

    # Check for portfolio fetch error
    if portfolio_details.get("error"):
        st.error(f"Error loading portfolio: {portfolio_details['error']}")
        # Attempt to show add funds anyway? Or just return? Let's return for now.
        return

    # --- Add Funds Section ---
    with st.expander("💰 Add Funds"):
        with st.form("add_funds_form"):
            amount_to_add = st.number_input("Amount (₹)", min_value=0.01, value=1000.0, step=100.0, key="add_funds_input")
            add_funds_submitted = st.form_submit_button("Add Funds to Cash Balance")
            if add_funds_submitted:
                success, message = add_funds_to_portfolio(username, amount_to_add)
                if success:
                    st.success(message)
                    st.rerun() # Rerun to update displayed balances immediately
                else:
                    st.error(message)

    # --- Proposed Trades Section ---
    if 'proposed_trades' in st.session_state and st.session_state.proposed_trades:
        st.subheader("📝 Review Proposed Trades from AI Analysis")
        st.caption("AI analysis suggests target amounts. Quantities are calculated based on current prices. Review and adjust quantities before execution.")

        initial_proposed_trades_with_qty = []
        total_initial_cost = 0
        has_price_errors = False

        # Create a copy to avoid modifying the original proposed_trades in session state directly during iteration
        proposed_trades_list = list(st.session_state.proposed_trades)

        with st.spinner("Fetching live prices for proposed trades..."):
            for trade in proposed_trades_list:
                    ticker = trade.get("Ticker")
                    target_amount = trade.get("Target Amount")

                    if not ticker or not isinstance(target_amount, (int, float)):
                        st.warning(f"Skipping invalid proposed trade data: {trade}")
                        continue

                    # Fetch live price
                    live_price_info = get_live_price(ticker) # API call
                    current_price = live_price_info.get('ltp') if live_price_info else None

                    if isinstance(current_price, (int, float)) and current_price > 0:
                        quantity = target_amount / current_price
                        cost = quantity * current_price
                        total_initial_cost += cost
                        initial_proposed_trades_with_qty.append({
                            "Ticker": ticker,
                            "Target Amount (₹)": target_amount,
                            "Live Price (₹)": current_price,
                            "Calculated Quantity": round(quantity, 4),
                            "Estimated Cost (₹)": round(cost, 2),
                            "Strategy": trade.get("Strategy", "N/A")
                        })
                    else:
                        st.warning(f"Could not get valid live price for {ticker}. It will be excluded from review.")
                        has_price_errors = True

        # Display only valid trades for editing
        valid_proposed_df = pd.DataFrame([t for t in initial_proposed_trades_with_qty if t.get("Calculated Quantity", 0) > 0])

        if not valid_proposed_df.empty:
            st.caption("Edit the 'Quantity to Buy' column below if needed.")
            # Use a unique key for the editor
            edited_df = st.data_editor(
                valid_proposed_df,
                column_config={
                    "Ticker": st.column_config.TextColumn("Ticker", disabled=True),
                    "Target Amount (₹)": st.column_config.NumberColumn("Target Amt (Ref)", format="₹%.2f", disabled=True),
                    "Live Price (₹)": st.column_config.NumberColumn("Live Price", format="₹%.2f", disabled=True),
                    # IMPORTANT: Changed column name for editing
                    "Calculated Quantity": st.column_config.NumberColumn("Quantity to Buy", min_value=0.0, step=0.0001, format="%.4f", required=True),
                    "Estimated Cost (₹)": st.column_config.NumberColumn("Est. Cost", format="₹%.2f", disabled=True),
                    "Strategy": st.column_config.TextColumn("Strategy", disabled=True),
                },
                key="proposed_trades_editor_qty", # Unique key
                hide_index=True,
                use_container_width=True
            )

            if st.button("🔍 Review & Confirm Trades", key="review_proposed_trades_btn"):
                reviewed_trades_list = []
                total_final_cost = 0.0
                errors = []
                # Use the cash amount from the detailed portfolio fetched at the start of the function
                current_cash = portfolio_details.get("cash", 0.0)

                for index, row in edited_df.iterrows():
                    ticker = row["Ticker"]
                    # Use the potentially edited quantity
                    quantity_to_buy = row["Quantity to Buy"] # Corrected column name from editor config
                    live_price = row["Live Price (₹)"] # Use price fetched initially

                    if not ticker or not isinstance(quantity_to_buy, (int, float)) or quantity_to_buy <= 0:
                        continue # Skip invalid rows (e.g., quantity edited to 0)

                    if not isinstance(live_price, (int, float)) or live_price <= 0:
                            errors.append(f"Invalid price ({live_price}) stored for {ticker}.")
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
                # Don't clear proposed trades yet, only after execution or cancellation
                st.rerun() # Rerun to show the confirmation section
        elif has_price_errors:
             st.info("No valid trades to propose after attempting to fetch live prices.")
        else:
             # This case might happen if proposed_trades was empty or all target amounts were <= 0 initially
             st.info("No trades were proposed or eligible for review.")


    # --- Confirmation Section ---
    if 'reviewed_trades' in st.session_state and st.session_state.reviewed_trades:
        review_data = st.session_state.reviewed_trades
        st.markdown("---")
        st.subheader("Confirm Execution")

        if review_data["errors"]:
            for error in review_data["errors"]: st.error(error)

        if review_data["trades"]:
            st.dataframe(pd.DataFrame(review_data["trades"]), hide_index=True, use_container_width=True,
                            column_config={
                                "Quantity": st.column_config.NumberColumn(format="%.4f"),
                                "Live Price (₹)": st.column_config.NumberColumn(format="₹%.2f"),
                                "Estimated Cost (₹)": st.column_config.NumberColumn(format="₹%.2f"),
                            })
            st.metric("Estimated Total Cost", f"₹{review_data['total_cost']:,.2f}")
            # Use cash from detailed portfolio fetched at start
            st.metric("Available Cash", f"₹{portfolio_details.get('cash', 0.0):,.2f}")

            col_confirm, col_cancel = st.columns(2)
            with col_confirm:
                execute_disabled = not review_data["sufficient_cash"] or not review_data["trades"]
                if st.button("✅ Execute Confirmed Trades", type="primary", disabled=execute_disabled, use_container_width=True, key="execute_reviewed_trades_btn"):
                    success_count = 0
                    fail_count = 0
                    results_messages = []
                    with st.spinner("Executing trades..."):
                        for trade in review_data["trades"]:
                            success, msg = execute_paper_trade(
                                username, "Buy", trade["Ticker"], quantity=trade["Quantity"]
                            )
                            if success:
                                success_count += 1
                                results_messages.append(st.success(f"Bought {trade['Quantity']} {trade['Ticker']}: {msg}", icon="✅"))
                            else:
                                fail_count += 1
                                results_messages.append(st.error(f"Failed to buy {trade['Ticker']}: {msg}", icon="❌"))

                    # Display summary after loop
                    if success_count > 0: st.info(f"Successfully executed {success_count} trades.")
                    if fail_count > 0: st.warning(f"{fail_count} trades failed.")

                    # Clear proposed and reviewed trades from state after execution attempt
                    st.session_state.proposed_trades = None
                    st.session_state.reviewed_trades = None
                    time.sleep(2) # Allow user to see results
                    st.rerun() # Rerun to show updated portfolio

            with col_cancel:
                if st.button("❌ Cancel Trades", use_container_width=True, key="cancel_reviewed_trades_btn"):
                    st.session_state.proposed_trades = None # Clear both on cancel
                    st.session_state.reviewed_trades = None
                    st.info("Proposed trades cancelled.")
                    time.sleep(1)
                    st.rerun()

            if not review_data["sufficient_cash"]:
                st.error("Insufficient cash to execute all reviewed trades.")

        else: # No trades in the review_data list
                if not review_data["errors"]: # Only show if no errors were reported
                    st.warning("No valid trades were reviewed for execution.")
                # Add cancel button even if no trades, to clear the state
                if st.button("❌ Clear Review", key="clear_empty_review_btn"):
                    st.session_state.reviewed_trades = None
                    st.rerun()


    # --- Portfolio Summary ---
    st.divider()
    st.subheader("Portfolio Summary")
    calculated_totals = portfolio_details.get("calculated_totals", {})
    cash = portfolio_details.get("cash", 0.0)
    total_holdings_value = calculated_totals.get("total_holdings_value", 0.0)
    total_portfolio_value = calculated_totals.get("total_portfolio_value", 0.0)
    data_staleness = portfolio_details.get("data_staleness", {})

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Portfolio Value", f"₹{total_portfolio_value:,.2f}")
    # Display staleness warning more prominently if present
    failed_prices = data_staleness.get("failed_prices", 0)
    if failed_prices > 0:
        col1.warning(f"{failed_prices} holding price(s) are stale. Total value might be inaccurate.")
    col2.metric("Cash Balance", f"₹{cash:,.2f}")
    col3.metric("Holdings Value", f"₹{total_holdings_value:,.2f}")
    # Display timestamp of last price update if available
    last_updated_str = data_staleness.get("last_update_time_utc")
    if last_updated_str:
        try:
            last_updated_dt = datetime.fromisoformat(last_updated_str.replace('Z', '+00:00'))
            st.caption(f"Holding prices last updated: {last_updated_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        except:
            st.caption(f"Holding prices last updated: {last_updated_str}")


    # --- Current Holdings ---
    st.divider()
    st.subheader("Current Holdings")
    holdings = portfolio_details.get("holdings", [])

    if not holdings:
        st.info("You currently have no holdings.")
    else:
        # Display header row using columns for better alignment
        header_cols = st.columns([2, 1, 2, 2, 2, 2]) # Adjust ratios if needed
        header_cols[0].markdown("**Ticker**")
        header_cols[1].markdown("**Quantity**")
        header_cols[2].markdown("**Avg Cost (₹)**")
        header_cols[3].markdown("**Mkt Price (₹)**")
        header_cols[4].markdown("**Mkt Value (₹)**")
        header_cols[5].markdown("**P/L (₹)** (%)")
        st.divider()

        # Iterate and display each holding with its own trade form inside an expander
        for i, h in enumerate(holdings):
            ticker = h.get("ticker", "N/A")
            quantity_float = h.get("quantity", 0.0)
            quantity = int(quantity_float) # Use integer for display/max sell
            avg_cost = h.get("avg_cost", 0.0)
            current_price = h.get("current_price") # Might be None
            current_value = h.get("current_value", 0.0)
            pnl = h.get("pnl", 0.0)
            pnl_pct = h.get("pnl_percentage", 0.0)
            is_stale = h.get("is_price_stale", False)

            data_cols = st.columns([2, 1, 2, 2, 2, 2])
            data_cols[0].markdown(f"**{ticker}**")
            data_cols[1].markdown(f"{quantity}") # Display integer quantity
            data_cols[2].markdown(f"₹{avg_cost:,.2f}")

            price_display = f"₹{current_price:,.2f}" if current_price is not None else "N/A"
            if is_stale and current_price is not None:
                 price_display += " (Stale)"
                 data_cols[3].markdown(f"<span style='color:orange;'>{price_display}</span>", unsafe_allow_html=True)
            elif is_stale:
                 data_cols[3].markdown(f"<span style='color:orange;'>N/A (Stale)</span>", unsafe_allow_html=True)
            else:
                 data_cols[3].markdown(price_display)


            data_cols[4].markdown(f"₹{current_value:,.2f}")

            # Color P/L based on value, but grey out if price is stale
            pnl_color = "grey"
            if not is_stale:
                 if pnl > 0: pnl_color = "green"
                 elif pnl < 0: pnl_color = "red"
            data_cols[5].markdown(f"<span style='color:{pnl_color};'>₹{pnl:,.2f} ({pnl_pct:+.2f}%)</span>", unsafe_allow_html=True)

            # --- Trade Form Expander ---
            with st.expander(f"Trade {ticker}"):
                # Radio button OUTSIDE the form for action selection
                trade_action = st.radio(
                    "Action", ["Buy", "Sell"], horizontal=True,
                    key=f"action_holding_{ticker}_{i}" # Unique key per holding
                )

                # Form contains only the input and button
                with st.form(key=f"trade_holding_form_{ticker}_{i}"): # Unique form key
                    if trade_action == "Buy":
                        trade_qty = st.number_input(
                            "Quantity to Buy", min_value=1, value=1, step=1,
                            key=f"qty_buy_holding_{ticker}_{i}", # Unique input key
                            format="%d" # Ensure integer input for buy
                        )
                    else: # Sell action
                        # Use the integer quantity for max sell
                        max_sell_qty = quantity
                        trade_qty = st.number_input(
                            f"Quantity to Sell (Max: {max_sell_qty})", min_value=0, max_value=max_sell_qty,
                            value=0, step=1,
                            key=f"qty_sell_holding_{ticker}_{i}", # Unique input key
                            format="%d" # Ensure integer input for sell
                        )

                    submitted = st.form_submit_button(f"Execute {trade_action}")

                    if submitted:
                        try:
                            final_trade_qty = int(trade_qty) # Ensure integer

                            # --- Validation within submission ---
                            if final_trade_qty <= 0:
                                st.warning("Quantity must be greater than zero.")
                            elif trade_action == "Sell":
                                # Re-fetch basic portfolio info JUST before sell execution for validation
                                current_portfolio_basic = get_paper_portfolio(username)
                                current_holding_info = next((ch for ch in current_portfolio_basic.get("holdings", []) if ch["ticker"] == ticker), None)
                                current_max_sell = int(current_holding_info['quantity']) if current_holding_info else 0

                                if final_trade_qty > current_max_sell:
                                     st.error(f"Cannot sell {final_trade_qty} shares. You currently hold {current_max_sell}.")
                                else: # Quantity is valid for sell
                                     success, message = execute_paper_trade(username, trade_action, ticker, quantity=final_trade_qty)
                                     if success:
                                         st.success(message)
                                         st.rerun() # Rerun on success
                                     else:
                                         st.error(message) # Show error but don't necessarily rerun immediately
                            else: # Buy action (quantity > 0 checked already)
                                success, message = execute_paper_trade(username, trade_action, ticker, quantity=final_trade_qty)
                                if success:
                                    st.success(message)
                                    st.rerun() # Rerun on success
                                else:
                                    st.error(message) # Show error
                        except (ValueError, TypeError):
                            st.error("Invalid quantity entered. Please enter a whole number.")
            st.divider() # Separator between holdings

    # --- Trade History ---
    st.divider()
    st.subheader("Trade History")
    with st.spinner("Loading trade history..."):
        transactions = get_paper_transactions(username, limit=25) # Fetch history

    if transactions is None: # Check for API error
        st.error("Could not load trade history.")
    elif not transactions:
        st.caption("No trading history yet.")
    else:
        history_df_data = []
        for entry in transactions: # Already sorted by backend hopefully
                ts = entry.get("timestamp") # Assumes backend returns datetime object or serializable string
                # Ensure timestamp is datetime object for formatting
                if isinstance(ts, str):
                    try: ts = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    except ValueError: ts = None # Handle unexpected string formats
                elif not isinstance(ts, datetime):
                    ts = None # Handle other non-datetime types

                # Simplify details display
                details = {
                    "Price": f"₹{entry.get('price'):,.2f}" if entry.get('price') is not None else "N/A",
                    "Value": f"₹{entry.get('cost_or_proceeds'):,.2f}" if entry.get('cost_or_proceeds') is not None else "N/A",
                    "Status": entry.get("status", "N/A"),
                }
                if entry.get("message"): # Include message only if present
                    details["Msg"] = entry.get("message")

                history_df_data.append({
                    "Timestamp": ts.strftime("%Y-%m-%d %H:%M") if ts else "N/A", # Shorter format
                    "Action": entry.get("action", "N/A"),
                    "Ticker": entry.get("ticker", "--"),
                    "Quantity": int(entry["quantity"]) if entry.get("quantity") is not None else "N/A",
                    "Details": json.dumps(details) # Keep details compact
                })
        history_df = pd.DataFrame(history_df_data)
        st.dataframe(history_df, hide_index=True, use_container_width=True,
                        column_config={
                            "Timestamp": st.column_config.TextColumn(width="small"),
                            "Action": st.column_config.TextColumn(width="small"),
                            "Ticker": st.column_config.TextColumn(width="small"),
                            "Quantity": st.column_config.NumberColumn(format="%d", width="small"),
                            "Details": st.column_config.TextColumn(width="large") # Allow more space for details
                        })