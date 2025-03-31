import ast
import importlib
import tempfile
from pydantic import BaseModel, Field, field_validator
from typing import Dict, List, Optional, Tuple, Union
from datetime import datetime
import pandas as pd
import numpy as np
import talib as ta

from enum import Enum
from src.backtesting.data_loader import DataLoader
from utils.app_logger import setup_logger

logger = setup_logger("src/backtesting/backtesting_engine.py")

class PositionType(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"

class TimeFrame(str, Enum):
    DAILY = "1D"
    HOURLY = "1H"
    MINUTE_15 = "15M"
    MINUTE_5 = "5M"
    MINUTE_1 = "1M"

class TaxStructure(BaseModel):
    stt: float = Field(default=0.001, description="Securities Transaction Tax")
    gst: float = Field(default=0.18, description="GST on brokerage")
    stamp_duty: float = Field(default=0.00015, description="Stamp duty")

class TradingHours(BaseModel):
    start: str = Field(default="09:15", description="Trading start time")
    end: str = Field(default="15:30", description="Trading end time")

class BacktestParameters(BaseModel):
    # Basic Parameters
    symbol: str
    strategy_code: str
    start_date: datetime
    end_date: datetime
    initial_capital: float = Field(default=100000.0)
    
    # Trading Parameters
    position_type: PositionType = Field(default=PositionType.LONG)
    position_size: Union[int, float] = Field(default=0)
    
    # Risk Management
    stop_loss: float = Field(default=0.0)
    take_profit: float = Field(default=0.0)
    max_drawdown: float = Field(default=0.0)
    
    # Cost & Taxes
    brokerage: float = Field(default=0.0)
    slippage: float = Field(default=0.0)
    taxes: TaxStructure = Field(default_factory=TaxStructure)
    
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
    position_type: PositionType
    quantity: int
    pnl: Optional[float] = None
    costs: float
    status: str = "OPEN"

class BacktestResult(BaseModel):
    initial_capital: float
    final_capital: float
    total_profit_loss: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    profit_factor: float
    avg_profit_per_trade: float
    avg_loss_per_trade: float
    risk_reward_ratio: float
    max_consecutive_wins: int
    max_consecutive_losses: int
    longest_winning_streak: int
    longest_losing_streak: int
    total_trading_days: int
    position_holding_time: float
    transaction_costs: float
    trades_history: List[Trade]
    equity_curve: List[float]
    monthly_returns: Dict[str, float]
    yearly_returns: Dict[str, float]


def process_strategy_code(strategy_code: str) -> callable:
    """
    Process and validate strategy code from LLM
    """
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

def calculate_position_size(capital: float, price: float, params: BacktestParameters) -> int:
    """
    Calculate position size based on available capital
    """
    price = float(price.iloc[0] if isinstance(price, pd.Series) else price)
    
    if params.position_size > 0:
        return min(
            int(params.position_size),
            int(capital / price)
        )
    else:
        # Default to 100% of available capital
        return int(capital / price)

def calculate_transaction_costs(price: float, quantity: int, params: BacktestParameters) -> float:
    """
    Calculate total transaction costs including brokerage, taxes, and slippage
    """
    # Convert to float to ensure we're working with single values
    price = float(price)
    quantity = int(quantity)
    
    transaction_value = price * quantity
    
    # Brokerage
    brokerage = min(float(transaction_value * params.brokerage), 20.0)  # Cap at ₹20
    
    # Securities Transaction Tax (STT)
    stt = float(transaction_value * params.taxes.stt)
    
    # GST on brokerage
    gst = float(brokerage * params.taxes.gst)
    
    # Stamp duty
    stamp_duty = float(transaction_value * params.taxes.stamp_duty)
    
    # Slippage
    slippage = float(transaction_value * params.slippage)
    
    return brokerage + stt + gst + stamp_duty + slippage

def simulate_trades(
    data: pd.DataFrame,
    signals: pd.DataFrame,
    params: BacktestParameters
) -> Tuple[List[Trade], List[float]]:
    """
    Simulate trades based on signals and parameters
    """
    trades: List[Trade] = []
    available_capital = params.initial_capital
    current_position = None
    equity_curve = [params.initial_capital]
    
    for timestamp, row in data.iterrows():
        current_signal = signals.loc[timestamp]
        
        # Skip if no signal
        if float(current_signal['Signal'].iloc[0] if isinstance(current_signal['Signal'], pd.Series) else current_signal['Signal']) == 0:
            continue
            
        current_price = float(row['Close'].iloc[0] if isinstance(row['Close'], pd.Series) else row['Close'])
        
        # Check if we need to close existing position
        if current_position is not None:
            # Check stop loss and take profit
            if params.position_type == PositionType.LONG:
                stop_hit = current_price <= current_position.entry_price * (1 - params.stop_loss)
                profit_hit = current_price >= current_position.entry_price * (1 + params.take_profit)
            else:
                stop_hit = current_price >= current_position.entry_price * (1 + params.stop_loss)
                profit_hit = current_price <= current_position.entry_price * (1 - params.take_profit)
                
            signal_value = float(current_signal['Signal'].iloc[0] if isinstance(current_signal['Signal'], pd.Series) else current_signal['Signal'])
            if stop_hit or profit_hit or signal_value == -1:
                # Close position
                costs = calculate_transaction_costs(
                    current_price,
                    current_position.quantity,
                    params
                )
                
                pnl = (
                    (current_price - current_position.entry_price)
                    * current_position.quantity
                    * (1 if params.position_type == PositionType.LONG else -1)
                ) - costs
                
                current_position.exit_date = timestamp
                current_position.exit_price = current_price
                current_position.pnl = pnl
                current_position.status = "CLOSED"
                
                available_capital += (current_price * current_position.quantity) - costs
                trades.append(current_position)
                current_position = None
                equity_curve.append(available_capital)
        
        # Open new position if we have signal and no current position
        signal_value = float(current_signal['Signal'].iloc[0] if isinstance(current_signal['Signal'], pd.Series) else current_signal['Signal'])
        if current_position is None and signal_value == 1:
            quantity = calculate_position_size(available_capital, current_price, params)
            
            if quantity > 0:
                costs = calculate_transaction_costs(current_price, quantity, params)
                
                current_position = Trade(
                    entry_date=timestamp,
                    entry_price=current_price,
                    position_type=params.position_type,
                    quantity=quantity,
                    costs=costs
                )
                
                available_capital -= (current_price * quantity + costs)
                equity_curve.append(available_capital)
    
    # Close any remaining position at the end
    if current_position is not None:
        last_price = float(data.iloc[-1]['Close'].iloc[0] if isinstance(data.iloc[-1]['Close'], pd.Series) else data.iloc[-1]['Close'])
        costs = calculate_transaction_costs(
            last_price,
            current_position.quantity,
            params
        )
        
        pnl = (
            (last_price - current_position.entry_price)
            * current_position.quantity
            * (1 if params.position_type == PositionType.LONG else -1)
        ) - costs
        
        current_position.exit_date = data.index[-1]
        current_position.exit_price = last_price
        current_position.pnl = pnl
        current_position.status = "CLOSED"
        trades.append(current_position)
        equity_curve.append(available_capital + (last_price * current_position.quantity) - costs)
    
    return trades, equity_curve

def calculate_metrics(
    trades: List[Trade],
    equity_curve: List[float],
    params: BacktestParameters
) -> BacktestResult:
    """
    Calculate performance metrics from trades
    """
    if not trades:
        return BacktestResult(
            initial_capital=params.initial_capital,
            final_capital=params.initial_capital,  # Unchanged capital
            total_profit_loss=0.0,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            max_drawdown=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            profit_factor=0.0,
            avg_profit_per_trade=0.0,
            avg_loss_per_trade=0.0,
            risk_reward_ratio=0.0,
            max_consecutive_wins=0,
            max_consecutive_losses=0,
            longest_winning_streak=0,
            longest_losing_streak=0,
            total_trading_days=0,
            position_holding_time=0.0,
            transaction_costs=0.0,
            trades_history=[],
            equity_curve=[params.initial_capital],  # Single point equity curve
            monthly_returns={},
            yearly_returns={}
        )
        
    # Basic metrics
    total_trades = len(trades)
    winning_trades = len([t for t in trades if t.pnl > 0])
    losing_trades = len([t for t in trades if t.pnl < 0])
    
    total_pnl = sum(t.pnl for t in trades)
    total_costs = sum(t.costs for t in trades)
    
    # Calculate streaks
    current_streak = 0
    max_win_streak = 0
    max_loss_streak = 0
    
    for trade in trades:
        if trade.pnl > 0:
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
    
    # Calculate returns
    returns = np.diff(equity_curve) / equity_curve[:-1]
    
    # Calculate monthly and yearly returns
    monthly_returns = {}
    yearly_returns = {}
    
    for trade in trades:
        month_key = trade.exit_date.strftime("%Y-%m")
        year_key = trade.exit_date.strftime("%Y")
        
        monthly_returns[month_key] = monthly_returns.get(month_key, 0) + trade.pnl
        yearly_returns[year_key] = yearly_returns.get(year_key, 0) + trade.pnl
    
    return BacktestResult(
        initial_capital=params.initial_capital,
        final_capital=equity_curve[-1],
        total_profit_loss=total_pnl,
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        win_rate=winning_trades / total_trades if total_trades > 0 else 0,
        max_drawdown=calculate_max_drawdown(equity_curve),
        sharpe_ratio=calculate_sharpe_ratio(returns),
        sortino_ratio=calculate_sortino_ratio(returns),
        profit_factor=calculate_profit_factor(trades),
        avg_profit_per_trade=np.mean([t.pnl for t in trades if t.pnl > 0]) if winning_trades > 0 else 0,
        avg_loss_per_trade=np.mean([t.pnl for t in trades if t.pnl < 0]) if losing_trades > 0 else 0,
        risk_reward_ratio=calculate_risk_reward_ratio(trades),
        max_consecutive_wins=max_win_streak,
        max_consecutive_losses=abs(max_loss_streak),
        longest_winning_streak=max_win_streak,
        longest_losing_streak=abs(max_loss_streak),
        total_trading_days=len(set(t.entry_date.date() for t in trades)),
        position_holding_time=calculate_avg_holding_time(trades),
        transaction_costs=total_costs,
        trades_history=trades,
        equity_curve=equity_curve,
        monthly_returns=monthly_returns,
        yearly_returns=yearly_returns
    )

def calculate_max_drawdown(equity_curve: List[float]) -> float:
    """Calculate maximum drawdown from equity curve"""
    peak = equity_curve[0]
    max_dd = 0
    
    for value in equity_curve:
        if value > peak:
            peak = value
        dd = (peak - value) / peak
        max_dd = max(max_dd, dd)
    
    return max_dd

def calculate_sharpe_ratio(returns: np.ndarray, risk_free_rate: float = 0.05) -> float:
    """Calculate Sharpe ratio"""
    if len(returns) < 2:
        return 0
    excess_returns = returns - risk_free_rate/252  # Daily risk-free rate
    return np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252)

def calculate_sortino_ratio(returns: np.ndarray, risk_free_rate: float = 0.05) -> float:
    """Calculate Sortino ratio"""
    if len(returns) < 2:
        return 0
    excess_returns = returns - risk_free_rate/252
    downside_returns = np.where(returns < 0, returns, 0)
    return np.mean(excess_returns) / np.std(downside_returns) * np.sqrt(252)

def calculate_profit_factor(trades: List[Trade]) -> float:
    """Calculate profit factor"""
    gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
    gross_loss = abs(sum(t.pnl for t in trades if t.pnl < 0))
    return gross_profit / gross_loss if gross_loss != 0 else float('inf')

def calculate_risk_reward_ratio(trades: List[Trade]) -> float:
    """Calculate risk/reward ratio"""
    avg_profit = np.mean([t.pnl for t in trades if t.pnl > 0]) if any(t.pnl > 0 for t in trades) else 0
    avg_loss = abs(np.mean([t.pnl for t in trades if t.pnl < 0])) if any(t.pnl < 0 for t in trades) else float('inf')
    return avg_profit / avg_loss if avg_loss != 0 else float('inf')

def calculate_avg_holding_time(trades: List[Trade]) -> float:
    """Calculate average holding time in days"""
    holding_times = [(t.exit_date - t.entry_date).total_seconds() / (24*3600) for t in trades]
    return np.mean(holding_times) if holding_times else 0

def execute_backtesting(params: BacktestParameters) -> BacktestResult:
    """Main backtesting function"""
    try:
        # Initialize data loader
        data_loader = DataLoader()
        
        # Load historical data
        data = data_loader.load_data(symbol=params.symbol, start_date=params.start_date, end_date=params.end_date, timeframe=params.timeframe.value)
        
        # Process strategy code
        strategy = process_strategy_code(params.strategy_code)
        
        # Execute strategy to get signals
        signals = strategy(data)
        # Validate signals DataFrame
        required_columns = ['Signal']
        if not all(col in signals.columns for col in required_columns):
            raise ValueError(f"Strategy must return DataFrame with columns: {required_columns}")
        
        # Run simulation
        trades, equity_curve = simulate_trades(data, signals, params)
        
        # Calculate metrics
        result = calculate_metrics(trades, equity_curve, params)
        
        return result
        
    except Exception as e:
        raise Exception(f"Backtesting failed: {str(e)}")
    
if __name__ == "__main__":
    # Example usage
    
    your_strategy_code1 = """
    import pandas as pd
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
        end_date=datetime(2023, 12, 31),
        initial_capital=100000,
        position_type=PositionType.LONG,
        stop_loss=0.02,  # 2%
        take_profit=0.05,  # 5%
    )

    result = execute_backtesting(params)
    print(result.model_dump_json())