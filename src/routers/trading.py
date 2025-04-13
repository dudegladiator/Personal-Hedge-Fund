import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple, List
from utils.app_logger import setup_logger
from utils.config import get_sync_database
from src.data_source.apis_1 import get_live_price # Assuming get_live_price is here

logger = setup_logger("src.routers.trading")
db = get_sync_database()
portfolios_collection = db.paper_portfolios
transactions_collection = db.paper_trading_transactions

DEFAULT_CASH = 0.00 # Increased default cash

# --- Portfolio Management ---

def get_paper_portfolio(username: str) -> Dict[str, Any]:
    """
    Retrieves the basic paper portfolio data (holdings, cash) for a user from MongoDB.
    Creates a default portfolio if one doesn't exist. Ensures required fields are present.
    Internal use mostly, prefer get_detailed_paper_portfolio for UI.
    """
    username = username.lower()
    portfolio = portfolios_collection.find_one({"username": username})

    if portfolio is None:
        logger.info(f"No portfolio found for {username}. Creating default.")
        default_portfolio = {
            "username": username,
            "cash": DEFAULT_CASH,
            "holdings": [], # List of {"ticker": str, "quantity": float, "avg_cost": float}
            "created_at": datetime.now(timezone.utc),
            "last_updated": datetime.now(timezone.utc),
        }
        try:
            portfolios_collection.insert_one(default_portfolio.copy()) # Insert a copy
            # Return the structure without DB ID
            newly_created = default_portfolio.copy()
            newly_created.pop('_id', None)
            return newly_created
        except Exception as e:
            logger.exception(f"Failed to create default portfolio for {username}: {e}")
            return {"error": "Failed to create portfolio", "username": username}
    else:
        # Ensure essential keys exist and provide defaults if missing on load
        portfolio.setdefault("cash", 0.0)
        portfolio.setdefault("holdings", [])
        portfolio.setdefault("created_at", datetime.now(timezone.utc)) # Add if missing
        portfolio.setdefault("last_updated", datetime.now(timezone.utc))
        portfolio.pop('_id', None) # Remove internal ID before returning
        return portfolio

def get_detailed_paper_portfolio(username: str) -> Dict[str, Any]:
    username = username.lower()
    base_portfolio = get_paper_portfolio(username)

    if "error" in base_portfolio:
        return base_portfolio # Return error if base fetching failed

    detailed_holdings = []
    total_holdings_value = 0.0
    total_cost_basis = 0.0
    successful_prices = 0
    failed_prices = 0

    for holding in base_portfolio.get("holdings", []):
        ticker = holding.get('ticker')
        quantity = holding.get('quantity', 0.0)
        avg_cost = holding.get('avg_cost', 0.0)

        if not ticker or quantity <= 0 or avg_cost <= 0:
             logger.warning(f"Skipping invalid holding data for user {username}: {holding}")
             continue # Skip malformed holdings

        cost_basis = quantity * avg_cost
        total_cost_basis += cost_basis

        # Fetch live price
        live_price_info = get_live_price(ticker)
        current_price = None
        is_price_stale = True

        if live_price_info and isinstance(live_price_info.get('ltp'), (int, float)) and live_price_info['ltp'] > 0:
            current_price = float(live_price_info['ltp'])
            is_price_stale = False
            successful_prices += 1
        else:
            logger.warning(f"Could not fetch valid live price for {ticker} for user {username}. Using avg_cost for value.")
            failed_prices += 1
            # Fallback: use average cost for current price/value if live fails
            # This means P/L will be calculated as 0 for this holding in the UI
            current_price = avg_cost # Or set to None if preferred for display logic

        current_value = quantity * current_price # Will use avg_cost if live price failed
        pnl = current_value - cost_basis
        pnl_percentage = (pnl / cost_basis * 100) if cost_basis != 0 else 0.0

        detailed_holdings.append({
            **holding, # Include original ticker, quantity, avg_cost
            "current_price": current_price if not is_price_stale else None, # Show None if price is stale
            "current_value": current_value,
            "cost_basis": cost_basis,
            "pnl": pnl,
            "pnl_percentage": pnl_percentage,
            "is_price_stale": is_price_stale
        })
        total_holdings_value += current_value

    # Calculate overall totals
    cash = base_portfolio.get("cash", 0.0)
    total_portfolio_value = cash + total_holdings_value
    total_pnl = total_holdings_value - total_cost_basis
    # Calculate overall P/L percentage based on initial cash + total cost basis if available
    initial_total_value_basis = DEFAULT_CASH # Or track invested capital separately
    overall_pnl_percentage = ((total_portfolio_value - initial_total_value_basis) / initial_total_value_basis * 100) if initial_total_value_basis else 0.0


    return {
        "username": base_portfolio.get("username"),
        "cash": cash,
        "holdings": detailed_holdings,
        "calculated_totals": {
            "total_holdings_value": total_holdings_value,
            "total_portfolio_value": total_portfolio_value,
            "total_pnl": total_pnl,
            "total_cost_basis": total_cost_basis, # Added for reference
            "overall_pnl_percentage": overall_pnl_percentage, # Example calculation
        },
        "created_at": base_portfolio.get("created_at"),
        "last_updated": base_portfolio.get("last_updated"),
        "data_staleness": {
            "successful_prices": successful_prices,
            "failed_prices": failed_prices,
            "timestamp": datetime.now(timezone.utc)
        }
    }


def add_funds_to_portfolio(username: str, amount: float) -> Tuple[bool, str]:
    """
    Adds funds to the user's paper trading cash balance.

    Args:
        username (str): The user receiving the funds.
        amount (float): The amount of cash to add.

    Returns:
        Tuple[bool, str]: (success_status, message)
    """
    username = username.lower()
    if not isinstance(amount, (int, float)) or amount <= 0:
        logger.warning(f"Invalid amount '{amount}' for adding funds attempt by {username}.")
        return False, "Amount must be a positive number."

    try:
        # Get current portfolio to ensure it exists and get current cash
        portfolio = get_paper_portfolio(username)
        if "error" in portfolio:
            return False, portfolio["error"]

        current_cash = portfolio.get("cash", 0.0)
        new_cash = current_cash + amount

        # Update the portfolio document
        update_result = portfolios_collection.update_one(
            {"username": username},
            {"$set": {
                "cash": new_cash,
                "last_updated": datetime.now(timezone.utc)}
            },
            upsert=False # Portfolio must exist
        )

        if update_result.matched_count == 0:
             raise Exception("Portfolio document not found during funds update.")
        # modified_count could be 0 if amount is 0, which is already checked

        # Log the transaction
        transaction = {
            "transaction_id": f"txn_{uuid.uuid4().hex[:12]}",
            "username": username, "timestamp": datetime.now(timezone.utc),
            "action": "ADD_FUNDS", "ticker": None, "quantity": None, "price": None,
            "cost_or_proceeds": amount, "status": "COMPLETED", "message": "Funds added successfully."
        }
        transactions_collection.insert_one(transaction)

        success_msg = f"Successfully added ₹{amount:,.2f} to cash balance."
        logger.info(f"Funds added for {username}: {success_msg}")
        return True, success_msg

    except Exception as e:
        logger.exception(f"Critical error adding funds for {username}: {e}")
        return False, f"An unexpected error occurred while adding funds: {e}"


def execute_paper_trade(username: str, action: str, ticker: str, quantity: int) -> Tuple[bool, str]: # Changed quantity type hint to int
    """
    Executes a paper trade (Buy or Sell) using INTEGER quantity, updating the portfolio
    and logging the transaction ONLY on success.
    """
    username = username.lower()
    action = action.upper()
    ticker = ticker.upper()

    # --- Input Validation ---
    if action not in ["BUY", "SELL"]:
        logger.warning(f"Invalid action '{action}' attempt by {username}.")
        return False, "Invalid action. Must be 'Buy' or 'Sell'."
    if not ticker:
        logger.warning(f"Empty ticker attempt by {username}.")
        return False, "Ticker symbol cannot be empty."

    # --- INTEGER QUANTITY VALIDATION ---
    if not isinstance(quantity, int) or quantity <= 0:
        logger.warning(f"Invalid quantity '{quantity}' (must be positive integer) for {ticker} attempt by {username}.")
        return False, "Quantity must be a positive whole number."
    # --- End INTEGER QUANTITY VALIDATION ---

    # --- Get Live Price ---
    live_price_data = get_live_price(symbol=ticker, exchange="NSE") # Use correct import
    if live_price_data is None or 'ltp' not in live_price_data:
        err_msg = f"Could not fetch live price for {ticker}. Market might be closed or API error."
        logger.warning(f"Trade failed for {username} ({action} {ticker}): {err_msg}")
        return False, err_msg

    try:
        live_price = float(live_price_data['ltp'])
        if live_price <= 0:
            raise ValueError("Price must be positive")
    except (ValueError, TypeError) as e:
        err_msg = f"Invalid live price received for {ticker}: {live_price_data.get('ltp')} ({e})"
        logger.error(f"Trade failed for {username} ({action} {ticker}): {err_msg}")
        return False, err_msg

    # --- Get Current Portfolio ---
    portfolio = get_paper_portfolio(username)
    if "error" in portfolio:
         return False, portfolio["error"]

    current_cash = portfolio.get("cash", 0.0)
    holdings = portfolio.get("holdings", [])

    # --- Execute Trade Logic ---
    cost_or_proceeds = float(quantity) * live_price # Calculate cost using float quantity
    new_holdings = holdings.copy()
    new_cash = current_cash
    existing_holding_index = -1
    found_holding = None

    for i, h in enumerate(new_holdings):
        if h.get("ticker") == ticker:
            existing_holding_index = i
            found_holding = h
            break

    try:
        # --- Buy Logic ---
        if action == "BUY":
            if current_cash < cost_or_proceeds:
                err_msg = f"Insufficient cash. Need ₹{cost_or_proceeds:.2f}, have ₹{current_cash:.2f}."
                logger.warning(f"Trade failed for {username} ({action} {ticker}): {err_msg}")
                return False, err_msg

            new_cash -= cost_or_proceeds

            if found_holding:
                # Update existing holding - Quantity must be integer
                old_qty = int(found_holding.get("quantity", 0))
                old_avg_cost = found_holding.get("avg_cost", 0.0)

                if old_qty < 0 or old_avg_cost < 0:
                     raise ValueError(f"Invalid existing holding state for {ticker}: Qty={old_qty}, AvgCost={old_avg_cost}")

                new_total_qty = old_qty + quantity
                if new_total_qty <= 0: # Should not happen if old_qty >= 0 and quantity > 0
                    raise ValueError("Invalid total quantity calculation during buy.")

                # Calculate new average cost
                new_avg_cost = ((old_avg_cost * float(old_qty)) + cost_or_proceeds) / float(new_total_qty)

                new_holdings[existing_holding_index]["quantity"] = new_total_qty # Store as integer
                new_holdings[existing_holding_index]["avg_cost"] = new_avg_cost
            else:
                # Add new holding - quantity is integer
                new_holding_data = {"ticker": ticker, "quantity": quantity, "avg_cost": live_price}
                new_holdings.append(new_holding_data)

        # --- Sell Logic ---
        elif action == "SELL":
            if not found_holding:
                err_msg = f"No holdings found for {ticker} to sell."
                logger.warning(f"Trade failed for {username} ({action} {ticker}): {err_msg}")
                return False, err_msg

            # Held quantity is integer
            held_quantity = int(found_holding.get("quantity", 0))
            if quantity > held_quantity: # Simple integer comparison
                err_msg = f"Cannot sell {quantity} shares. Only hold {held_quantity} shares of {ticker}."
                logger.warning(f"Trade failed for {username} ({action} {ticker}): {err_msg}")
                return False, err_msg

            new_cash += cost_or_proceeds
            new_holdings[existing_holding_index]["quantity"] -= quantity # Integer subtraction

            # Remove holding if quantity is exactly zero
            if new_holdings[existing_holding_index]["quantity"] == 0:
                logger.info(f"Removing zero-quantity holding for {ticker} for user {username}.")
                del new_holdings[existing_holding_index]

        # --- Commit Changes to Database ---
        portfolio_update_data = {
            "cash": round(new_cash, 2), # Round cash
            "holdings": new_holdings, # Contains integer quantities
            "last_updated": datetime.now(timezone.utc)
        }

        update_result = portfolios_collection.update_one(
            {"username": username},
            {"$set": portfolio_update_data},
            upsert=False
        )

        if update_result.matched_count == 0:
            raise Exception(f"Portfolio document for {username} not found during update.")

        # --- Log Successful Transaction (Quantity is integer) ---
        transaction = {
            "transaction_id": f"txn_{uuid.uuid4().hex[:12]}",
            "username": username, "timestamp": datetime.now(timezone.utc),
            "action": action, "ticker": ticker, "quantity": quantity, # Store integer quantity
            "price": live_price, "cost_or_proceeds": round(cost_or_proceeds, 2),
            "status": "COMPLETED", "message": None
        }
        transactions_collection.insert_one(transaction)

        success_msg = f"Successfully {action.lower()} {quantity} shares of {ticker} @ ₹{live_price:.2f}."
        logger.info(f"Trade successful for {username}: {success_msg}")
        return True, success_msg

    except Exception as e:
        logger.exception(f"Critical error during paper trade for {username} ({action} {ticker}): {e}")
        return False, f"An unexpected error occurred during the trade: {e}"


# --- Transaction Retrieval ---

def get_paper_transactions(username: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Retrieves the most recent paper trading transactions (COMPLETED only) for a user."""
    username = username.lower()
    try:
        transactions_cursor = transactions_collection.find(
            {"username": username} # Fetch all statuses by default now
        ).sort("timestamp", -1).limit(limit) # Sort newest first

        transactions = []
        for txn in transactions_cursor:
             # Ensure datetime is timezone-aware UTC for consistency if needed
             if isinstance(txn.get("timestamp"), datetime) and txn["timestamp"].tzinfo is None:
                  txn["timestamp"] = txn["timestamp"].replace(tzinfo=timezone.utc)
             txn.pop('_id', None) # Remove internal ID
             transactions.append(txn)
        return transactions
    except Exception as e:
        logger.exception(f"Failed to retrieve transactions for {username}: {e}")
        return [] # Return empty list on error