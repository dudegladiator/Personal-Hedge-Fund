import ast
import importlib
import tempfile
from pydantic import BaseModel, Field, field_validator
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import pandas as pd
import numpy as np
import talib as ta
from enum import Enum
from src.backtesting.data_loader import DataLoader
from utils.app_logger import setup_logger

logger = setup_logger("src/backtesting/backtesting_engine.py")

class TimeFrame(str, Enum):
    DAILY = "1D"
    HOURLY = "1H"
    MINUTE_15 = "15M"
    MINUTE_5 = "5M"
    MINUTE_1 = "1M"

class TradingHours(BaseModel):
    start: str = Field(default="09:15", description="Trading start time")
    end: str = Field(default="15:30", description="Trading end time")

class BacktestParameters(BaseModel):
    # Basic Parameters
    symbol: str
    strategy_code: str
    start_date: datetime
    end_date: datetime
    
    # Risk Management
    stop_loss: float = Field(default=0.0)  # In percentage
    take_profit: float = Field(default=0.0)  # In percentage
    
    # Data Parameters
    timeframe: TimeFrame = Field(default=TimeFrame.DAILY)
    
    # Constraints
    trading_hours: TradingHours = Field(default_factory=TradingHours)
    trading_days: List[str] = Field(
        default=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    )
    holidays: List[datetime] = Field(default_factory=list)

    @field_validator('end_date')
    def end_date_must_be_after_start_date(cls, v, info):
        if info.data.get('start_date') and v <= info.data.get('start_date'):
            raise ValueError('end_date must be after start_date')
        return v

class Trade(BaseModel):
    entry_date: datetime
    entry_price: float
    exit_date: Optional[datetime] = None
    exit_price: Optional[float] = None
    returns: Optional[float] = None  # Percentage returns
    status: str = "OPEN"

class BacktestResult(BaseModel):
    total_returns: float  # Total percentage returns
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    profit_factor: float
    avg_return_per_trade: float
    avg_winning_trade: float
    avg_losing_trade: float
    risk_reward_ratio: float
    max_consecutive_wins: int
    max_consecutive_losses: int
    longest_winning_streak: int
    longest_losing_streak: int
    total_trading_days: int
    avg_holding_time: float
    trades_history: List[Trade]
    equity_curve: List[float]  # Normalized to start at 100
    monthly_returns: Dict[str, float]
    yearly_returns: Dict[str, float]
    
def process_strategy_code(strategy_code: str) -> callable:
    """Process and validate strategy code from LLM"""
    try:
        # Security check
        tree = ast.parse(strategy_code)
        
        # Check for unsafe operations
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                allowed_modules = {'pandas', 'numpy', 'ta', 'talib'}
                for name in node.names:
                    if name.name.split('.')[0] not in allowed_modules:
                        raise ValueError(f"Unauthorized import: {name.name}")
                        
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                banned_functions = {'eval', 'exec', 'system', 'open', 'write'}
                if node.func.attr in banned_functions:
                    raise ValueError(f"Unauthorized function: {node.func.attr}")

        # Create temporary module
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(strategy_code)
            temp_path = f.name

        # Import strategy
        spec = importlib.util.spec_from_file_location("strategy_module", temp_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if not hasattr(module, 'generate_signals'):
            raise ValueError("Strategy must contain 'generate_signals' function")

        return module.generate_signals

    except Exception as e:
        raise ValueError(f"Strategy code processing failed: {str(e)}")

def simulate_trades(
    data: pd.DataFrame,
    signals: pd.DataFrame,
    params: BacktestParameters
) -> Tuple[List[Trade], List[float]]:
    """Simulate trades based on signals and parameters"""
    trades: List[Trade] = []
    equity_curve = [100.0]  # Start at 100%
    current_position = None
    current_equity = 100.0
    
    for timestamp, row in data.iterrows():
        current_signal = signals.loc[timestamp]
        current_price = float(row['Close'].iloc[0] if isinstance(row['Close'], pd.Series) else row['Close'])
        signal_value = float(current_signal['Signal'].iloc[0] if isinstance(current_signal['Signal'], pd.Series) else current_signal['Signal'])
        
        # Handle existing position
        if current_position is not None:
            # Calculate current returns
            current_return = (current_price - current_position.entry_price) / current_position.entry_price * 100
            
            # Check stop loss and take profit
            stop_hit = current_return <= -params.stop_loss if params.stop_loss > 0 else False
            profit_hit = current_return >= params.take_profit if params.take_profit > 0 else False
            
            # Close position if: stop loss hit, take profit hit, or sell signal
            if stop_hit or profit_hit or signal_value == -1:
                current_position.exit_date = timestamp
                current_position.exit_price = current_price
                current_position.returns = current_return
                current_position.status = "CLOSED"
                
                # Update equity
                current_equity *= (1 + current_return/100)
                trades.append(current_position)
                current_position = None
                equity_curve.append(current_equity)
        
        # Open new position if we have buy signal and no current position
        elif signal_value == 1:
            current_position = Trade(
                entry_date=timestamp,
                entry_price=current_price
            )
            equity_curve.append(current_equity)
    
    # Close any remaining position at the end
    if current_position is not None:
        last_price = float(data.iloc[-1]['Close'].iloc[0] if isinstance(data.iloc[-1]['Close'], pd.Series) else data.iloc[-1]['Close'])
        final_return = (last_price - current_position.entry_price) / current_position.entry_price * 100
        
        current_position.exit_date = data.index[-1]
        current_position.exit_price = last_price
        current_position.returns = final_return
        current_position.status = "CLOSED"
        
        current_equity *= (1 + final_return/100)
        trades.append(current_position)
        equity_curve.append(current_equity)
    
    return trades, equity_curve


def calculate_metrics(
    trades: List[Trade],
    equity_curve: List[float],
    params: BacktestParameters
) -> BacktestResult:
    """Calculate performance metrics from trades"""
    try:
        if not trades:
            return BacktestResult(
                total_returns=0.0,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                max_drawdown=0.0,
                sharpe_ratio=0.0,
                sortino_ratio=0.0,
                profit_factor=0.0,
                avg_return_per_trade=0.0,
                avg_winning_trade=0.0,
                avg_losing_trade=0.0,
                risk_reward_ratio=0.0,
                max_consecutive_wins=0,
                max_consecutive_losses=0,
                longest_winning_streak=0,
                longest_losing_streak=0,
                total_trading_days=0,
                avg_holding_time=0.0,
                trades_history=[],
                equity_curve=[100.0],
                monthly_returns={},
                yearly_returns={}
            )
            
        # Basic metrics
        total_trades = len(trades)
        winning_trades = len([t for t in trades if t.returns > 0])
        losing_trades = len([t for t in trades if t.returns < 0])
        
        try:
            total_returns = ((equity_curve[-1] - equity_curve[0]) / equity_curve[0]) * 100
        except:
            total_returns = 0.0
        
        try:
            win_rate = winning_trades / total_trades if total_trades > 0 else 0.0
        except:
            win_rate = 0.0
            
        # Calculate streaks safely
        try:
            current_streak = 0
            max_win_streak = 0
            max_loss_streak = 0
            
            for trade in trades:
                if trade.returns > 0:
                    if current_streak > 0:
                        current_streak += 1
                    else:
                        current_streak = 1
                else:
                    if current_streak < 0:
                        current_streak -= 1
                    else:
                        current_streak = -1
                        
                max_win_streak = max(max_win_streak, current_streak if current_streak > 0 else 0)
                max_loss_streak = min(max_loss_streak, current_streak if current_streak < 0 else 0)
        except:
            max_win_streak = 0
            max_loss_streak = 0
        
        # Calculate returns series safely
        try:
            returns = np.diff(equity_curve) / equity_curve[:-1]
        except:
            returns = np.array([0.0])
        
        # Calculate monthly and yearly returns safely
        try:
            monthly_returns = {}
            yearly_returns = {}
            
            for trade in trades:
                month_key = trade.exit_date.strftime("%Y-%m")
                year_key = trade.exit_date.strftime("%Y")
                
                monthly_returns[month_key] = monthly_returns.get(month_key, 0) + trade.returns
                yearly_returns[year_key] = yearly_returns.get(year_key, 0) + trade.returns
        except:
            monthly_returns = {}
            yearly_returns = {}
        
        # Calculate metrics with error handling
        try:
            avg_return_per_trade = np.mean([t.returns for t in trades])
        except:
            avg_return_per_trade = 0.0
            
        try:
            avg_winning_trade = np.mean([t.returns for t in trades if t.returns > 0]) if winning_trades > 0 else 0.0
        except:
            avg_winning_trade = 0.0
            
        try:
            avg_losing_trade = np.mean([t.returns for t in trades if t.returns < 0]) if losing_trades > 0 else 0.0
        except:
            avg_losing_trade = 0.0
        
        return BacktestResult(
            total_returns=total_returns,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            max_drawdown=calculate_max_drawdown(equity_curve),
            sharpe_ratio=calculate_sharpe_ratio(returns),
            sortino_ratio=calculate_sortino_ratio(returns),
            profit_factor=calculate_profit_factor(trades),
            avg_return_per_trade=avg_return_per_trade,
            avg_winning_trade=avg_winning_trade,
            avg_losing_trade=avg_losing_trade,
            risk_reward_ratio=calculate_risk_reward_ratio(trades),
            max_consecutive_wins=max_win_streak,
            max_consecutive_losses=abs(max_loss_streak),
            longest_winning_streak=max_win_streak,
            longest_losing_streak=abs(max_loss_streak),
            total_trading_days=len(set(t.entry_date.date() for t in trades)),
            avg_holding_time=calculate_avg_holding_time(trades),
            trades_history=trades,
            equity_curve=equity_curve,
            monthly_returns=monthly_returns,
            yearly_returns=yearly_returns
        )
    except Exception as e:
        logger.error(f"Error calculating metrics: {str(e)}")
        return BacktestResult(
            total_returns=0.0,
            total_trades=len(trades) if trades else 0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            max_drawdown=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            profit_factor=0.0,
            avg_return_per_trade=0.0,
            avg_winning_trade=0.0,
            avg_losing_trade=0.0,
            risk_reward_ratio=0.0,
            max_consecutive_wins=0,
            max_consecutive_losses=0,
            longest_winning_streak=0,
            longest_losing_streak=0,
            total_trading_days=0,
            avg_holding_time=0.0,
            trades_history=trades if trades else [],
            equity_curve=equity_curve if equity_curve else [100.0],
            monthly_returns={},
            yearly_returns={}
        )

def calculate_max_drawdown(equity_curve: List[float]) -> float:
    """Calculate maximum drawdown from equity curve"""
    try:
        peak = equity_curve[0]
        max_dd = 0
        
        for value in equity_curve:
            if value > peak:
                peak = value
            dd = (peak - value) / peak * 100
            max_dd = max(max_dd, dd)
        
        return max_dd
    except:
        return 0.0

def calculate_sharpe_ratio(returns: np.ndarray, risk_free_rate: float = 0.05) -> float:
    """Calculate Sharpe ratio"""
    try:
        if len(returns) < 2:
            return 0.0
        excess_returns = returns - risk_free_rate/252
        return np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252)
    except:
        return 0.0

def calculate_sortino_ratio(returns: np.ndarray, risk_free_rate: float = 0.05) -> float:
    """Calculate Sortino ratio"""
    try:
        if len(returns) < 2:
            return 0.0
        excess_returns = returns - risk_free_rate/252
        downside_returns = np.where(returns < 0, returns, 0)
        if np.std(downside_returns) == 0:
            return 0.0
        return np.mean(excess_returns) / np.std(downside_returns) * np.sqrt(252)
    except:
        return 0.0

def calculate_profit_factor(trades: List[Trade]) -> float:
    """Calculate profit factor"""
    try:
        total_gains = sum(t.returns for t in trades if t.returns > 0)
        total_losses = abs(sum(t.returns for t in trades if t.returns < 0))
        return total_gains / total_losses if total_losses != 0 else 0.0
    except:
        return 0.0

def calculate_risk_reward_ratio(trades: List[Trade]) -> float:
    """Calculate risk/reward ratio"""
    try:
        avg_gain = np.mean([t.returns for t in trades if t.returns > 0]) if any(t.returns > 0 for t in trades) else 0
        avg_loss = abs(np.mean([t.returns for t in trades if t.returns < 0])) if any(t.returns < 0 for t in trades) else 0
        return avg_gain / avg_loss if avg_loss != 0 else 0.0
    except:
        return 0.0

def calculate_avg_holding_time(trades: List[Trade]) -> float:
    """Calculate average holding time in days"""
    try:
        holding_times = [(t.exit_date - t.entry_date).total_seconds() / (24*3600) for t in trades]
        return np.mean(holding_times) if holding_times else 0.0
    except:
        return 0.0


def execute_backtesting(params: BacktestParameters) -> BacktestResult:
    """Main backtesting function"""
    try:
        # Initialize data loader
        data_loader = DataLoader()
        
        # Load historical data
        data = data_loader.load_data(
            symbol=params.symbol, 
            start_date=params.start_date, 
            end_date=params.end_date, 
            timeframe=params.timeframe.value
        )
        
        if data.empty:
            raise ValueError("No historical data found for backtesting")
        
        # Process strategy code
        strategy = process_strategy_code(params.strategy_code)
        
        # Execute strategy to get signals
        signals = strategy(data)         
        
        # Check if the output is a DataFrame
        if not isinstance(signals, pd.DataFrame):
            # This error means the strategy code itself is fundamentally broken
            # or didn't return a DataFrame as required.
            raise TypeError(f"Strategy '{strategy.__name__}' did not return a pandas DataFrame.") # Assuming strategy has a __name__

        # Check if the mandatory 'Signal' column exists
        if 'Signal' not in signals.columns:
            raise ValueError(f"Strategy '{strategy.__name__}' must return DataFrame with 'Signal' column")

        # Check if the mandatory 'Error' column exists (as per the latest prompt)
        if 'Error' not in signals.columns:
            raise ValueError(f"Strategy '{strategy.__name__}' must return DataFrame with 'Error' column")

        # --- Validation 2: Check for Reported Errors from Strategy ---

        # Check if any non-NaN value exists in the 'Error' column.
        # The strategy's internal try-except block should populate this with an error message string if it failed.
        # .notna() returns True for non-NaN values (like error strings).
        # .any() checks if at least one True exists in the resulting boolean Series.
        if signals['Error'].notna().any():
            # An error occurred *inside* the strategy's execution logic.
            # Extract the first reported error message for logging/reporting.
            first_error_message = signals['Error'].dropna().iloc[0]
            # Raise a specific error indicating the strategy logic failed.
            raise RuntimeError(f"Strategy '{strategy.__name__}' reported an internal execution error: {first_error_message}")
        
        # Run simulation
        trades, equity_curve = simulate_trades(data, signals, params)
        
        # Calculate metrics
        result = calculate_metrics(trades, equity_curve, params)
        
        return result
        
    except Exception as e:
        logger.error(f"Backtesting failed: {str(e)}")
        raise Exception(f"Backtesting failed: {str(e)}")
    
if __name__ == "__main__":
    # Example usage
    
    your_strategy_code1 = """import pandas as pd
import numpy as np
import talib as ta

def generate_signals(data: pd.DataFrame) -> pd.DataFrame:
    signals = pd.DataFrame(index=data.index)
    signals['Signal'] = 0
    
    # Ensure 1D array for TA-Lib
    close_prices = data['Close'].iloc[:, 0].values.astype(np.float64)
    
    # Calculate RSI
    data['RSI'] = ta.RSI(close_prices, timeperiod=14)
    
    # Generate signals based on overbought/oversold conditions
    signals['Signal'] = np.where(data['RSI'] < 30, 1, 0)  # Buy when RSI below 30 (oversold)
    signals['Signal'] = np.where(data['RSI'] > 70, -1, signals['Signal'])  # Sell when RSI above 70 (overbought)
    
    return signals
    """

    # Corrected strategy_code2 (Bollinger Bands)
    your_strategy_code2 = """
import pandas as pd
import numpy as np
import talib as ta

def generate_signals(data: pd.DataFrame) -> pd.DataFrame:
    signals = pd.DataFrame(index=data.index)
    signals['Signal'] = 0
    
    # Ensure we're working with single column Series
    close_prices = data['Close'].iloc[:, 0].values.astype(np.float64)
    
    # Calculate Bollinger Bands
    upper, middle, lower = ta.BBANDS(
        close_prices, 
        timeperiod=20, 
        nbdevup=2, 
        nbdevdn=2, 
        matype=0
    )
    
    # Create signals using numpy arrays
    close_array = close_prices
    signals.loc[:, 'Signal'] = 0
    
    # Generate signals using numpy where
    signals.loc[close_array <= lower, 'Signal'] = 1
    signals.loc[close_array >= upper, 'Signal'] = -1
    
    # Forward fill NaN values with 0
    signals['Signal'] = signals['Signal'].fillna(0)
    
    return signals
    """

    # Corrected strategy_code3 (Multiple Indicators)
    your_strategy_code3 = """
import pandas as pd
import numpy as np
import talib as ta

def generate_signals(data: pd.DataFrame) -> pd.DataFrame:
    signals = pd.DataFrame(index=data.index)
    signals['Signal'] = 0
    
    # Ensure we're working with single column Series
    close_prices = data['Close'].iloc[:, 0].values.astype(np.float64)
    high_prices = data['High'].iloc[:, 0].values.astype(np.float64)
    low_prices = data['Low'].iloc[:, 0].values.astype(np.float64)
    
    # Calculate indicators
    sma_200 = ta.SMA(close_prices, timeperiod=200)
    rsi = ta.RSI(close_prices, timeperiod=14)
    sma_20 = ta.SMA(close_prices, timeperiod=20)
    sma_50 = ta.SMA(close_prices, timeperiod=50)
    
    # Convert to pandas Series
    data_dict = {
        'Close': close_prices,
        'SMA_200': sma_200,
        'RSI': rsi,
        'SMA_20': sma_20,
        'SMA_50': sma_50
    }
    
    # Create DataFrame for calculations
    indicator_df = pd.DataFrame(data_dict, index=data.index)
    
    # Generate signals using vectorized operations
    buy_condition = (
        (indicator_df['Close'] > indicator_df['SMA_200']) & 
        (indicator_df['SMA_20'] > indicator_df['SMA_50']) & 
        (indicator_df['RSI'] > 50)
    )
    
    sell_condition = (
        (indicator_df['Close'] < indicator_df['SMA_200']) & 
        (indicator_df['SMA_20'] < indicator_df['SMA_50']) & 
        (indicator_df['RSI'] < 50)
    )
    
    # Apply conditions
    signals.loc[buy_condition, 'Signal'] = 1
    signals.loc[sell_condition, 'Signal'] = -1
    
    # Forward fill NaN values with 0
    signals['Signal'] = signals['Signal'].fillna(0)
    
    return signals
    """
        
    params = BacktestParameters(
        symbol="RELIANCE",
        strategy_code=your_strategy_code1,  # LLM generated code as string
        start_date=datetime(2022, 1, 1),
        end_date=datetime(2025, 3, 31),
        stop_loss=0.03,  # 2%
        take_profit=0.05,  # 5%
    )

    result = execute_backtesting(params)
    print(result.model_dump_json())