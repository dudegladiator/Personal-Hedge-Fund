from typing import Dict
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import talib as ta
from src.backtesting.data_loader import DataLoader
from pydantic import BaseModel
from utils.app_logger import setup_logger

logger = setup_logger("src/backtesting/technical_indicators.py")

class TechnicalAnalysisValues(BaseModel):
    # Trend Indicators
    sma_values: Dict[str, float]  # Current SMA values and slopes
    ema_values: Dict[str, float]  # Current EMA values and slopes
    macd_values: Dict[str, float]  # MACD line, signal line, histogram
    trend_metrics: Dict[str, float]  # Trend-related metrics

    # Momentum Indicators
    rsi_values: Dict[str, float]  # RSI value and slope
    stoch_values: Dict[str, float]  # SlowK, SlowD values
    cci_values: Dict[str, float]  # CCI value and slope

    # Volume Indicators
    obv_values: Dict[str, float]  # OBV value and slope
    adl_values: Dict[str, float]  # ADL value and slope

    # Volatility Indicators
    bollinger_values: Dict[str, float]  # BB upper, middle, lower, bandwidth
    atr_values: Dict[str, float]  # ATR value and as % of price

def analyze_trend_indicators(data: pd.DataFrame) -> Dict:
    """Return key trend indicator values"""
    close = data['Close'].iloc[:, 0].values.astype(np.float64)
    
    # Calculate SMAs
    sma20 = ta.SMA(close, timeperiod=20)
    sma50 = ta.SMA(close, timeperiod=50)
    sma200 = ta.SMA(close, timeperiod=200)
    
    # Calculate EMAs
    ema20 = ta.EMA(close, timeperiod=20)
    ema50 = ta.EMA(close, timeperiod=50)
    
    # Calculate MACD
    macd, signal, hist = ta.MACD(close)
    
    # Current values and slopes (using last 20 periods where applicable)
    current_price = close[-1] if len(close) > 0 else np.nan
    
    sma_values = {
        "sma20": sma20[-1] if len(sma20) > 0 else np.nan,
        "sma50": sma50[-1] if len(sma50) > 0 else np.nan,
        "sma200": sma200[-1] if len(sma200) > 0 else np.nan,
        "sma200_slope": ((sma200[-1] - sma200[-20]) / sma200[-20] * 100 
                        if len(sma200) >= 20 else np.nan)
    }
    
    ema_values = {
        "ema20": ema20[-1] if len(ema20) > 0 else np.nan,
        "ema50": ema50[-1] if len(ema50) > 0 else np.nan,
        "ema20_slope": ((ema20[-1] - ema20[-20]) / ema20[-20] * 100 
                       if len(ema20) >= 20 else np.nan)
    }
    
    macd_values = {
        "macd": macd[-1] if len(macd) > 0 else np.nan,
        "signal": signal[-1] if len(signal) > 0 else np.nan,
        "histogram": hist[-1] if len(hist) > 0 else np.nan
    }
    
    trend_metrics = {
        "price_to_sma200": ((current_price - sma200[-1]) / sma200[-1] * 100 
                          if len(sma200) > 0 else np.nan),
        "sma20_50_spread": ((sma20[-1] - sma50[-1]) / sma50[-1] * 100 
                          if len(sma20) > 0 and len(sma50) > 0 else np.nan)
    }
    
    return {
        "sma_values": sma_values,
        "ema_values": ema_values,
        "macd_values": macd_values,
        "trend_metrics": trend_metrics
    }

def analyze_momentum_indicators(data: pd.DataFrame) -> Dict:
    """Return key momentum indicator values"""
    close = data['Close'].iloc[:, 0].values.astype(np.float64)
    high = data['High'].iloc[:, 0].values.astype(np.float64)
    low = data['Low'].iloc[:, 0].values.astype(np.float64)
    
    rsi = ta.RSI(close)
    slowk, slowd = ta.STOCH(high, low, close)
    cci = ta.CCI(high, low, close)
    
    rsi_values = {
        "rsi": rsi[-1] if len(rsi) > 0 else np.nan,
        "rsi_slope": ((rsi[-1] - rsi[-20]) / rsi[-20] * 100 
                     if len(rsi) >= 20 else np.nan)
    }
    
    stoch_values = {
        "slowk": slowk[-1] if len(slowk) > 0 else np.nan,
        "slowd": slowd[-1] if len(slowd) > 0 else np.nan,
        "k_d_spread": (slowk[-1] - slowd[-1] 
                      if len(slowk) > 0 and len(slowd) > 0 else np.nan)
    }
    
    cci_values = {
        "cci": cci[-1] if len(cci) > 0 else np.nan,
        "cci_slope": ((cci[-1] - cci[-20]) / cci[-20] * 100 
                     if len(cci) >= 20 else np.nan)
    }
    
    return {
        "rsi_values": rsi_values,
        "stoch_values": stoch_values,
        "cci_values": cci_values
    }

def analyze_volume_indicators(data: pd.DataFrame) -> Dict:
    """Return key volume indicator values"""
    close = data['Close'].iloc[:, 0].values.astype(np.float64)
    volume = data['Volume'].iloc[:, 0].values.astype(np.float64)
    high = data['High'].iloc[:, 0].values.astype(np.float64)
    low = data['Low'].iloc[:, 0].values.astype(np.float64)
    
    obv = ta.OBV(close, volume)
    adl = ta.AD(high, low, close, volume)
    
    obv_values = {
        "obv": obv[-1] if len(obv) > 0 else np.nan,
        "obv_slope": ((obv[-1] - obv[-20]) / obv[-20] * 100 
                     if len(obv) >= 20 else np.nan)
    }
    
    adl_values = {
        "adl": adl[-1] if len(adl) > 0 else np.nan,
        "adl_slope": ((adl[-1] - adl[-20]) / adl[-20] * 100 
                     if len(adl) >= 20 else np.nan)
    }
    
    return {
        "obv_values": obv_values,
        "adl_values": adl_values
    }

def analyze_volatility_indicators(data: pd.DataFrame) -> Dict:
    """Return key volatility indicator values"""
    close = data['Close'].iloc[:, 0].values.astype(np.float64)
    high = data['High'].iloc[:, 0].values.astype(np.float64)
    low = data['Low'].iloc[:, 0].values.astype(np.float64)
    
    upper, middle, lower = ta.BBANDS(close)
    atr = ta.ATR(high, low, close)
    
    current_price = close[-1] if len(close) > 0 else np.nan
    
    bollinger_values = {
        "upper": upper[-1] if len(upper) > 0 else np.nan,
        "middle": middle[-1] if len(middle) > 0 else np.nan,
        "lower": lower[-1] if len(lower) > 0 else np.nan,
        "bandwidth": ((upper[-1] - lower[-1]) / middle[-1] * 100 
                     if len(upper) > 0 and len(lower) > 0 and len(middle) > 0 else np.nan),
        "price_to_middle": ((current_price - middle[-1]) / middle[-1] * 100 
                          if len(middle) > 0 else np.nan)
    }
    
    atr_values = {
        "atr": atr[-1] if len(atr) > 0 else np.nan,
        "atr_percent": (atr[-1] / current_price * 100 
                       if len(atr) > 0 and current_price != 0 else np.nan)
    }
    
    return {
        "bollinger_values": bollinger_values,
        "atr_values": atr_values
    }

def get_basic_technical_indicators(
    symbol: str,
    start_date: datetime = datetime.now() - timedelta(days=365),
    end_date: datetime = datetime.now(),
    interval: str = "1D"
) -> TechnicalAnalysisValues:
    logger.info(f"Analyzing basic technical indicators for {symbol}")
    try:
        # Initialize data loader
        data_loader = DataLoader()
        # Load historical data
        data = data_loader.load_data(symbol, start_date, end_date, interval)

        # Analyze all indicator groups
        trend_analysis = analyze_trend_indicators(data)
        momentum_analysis = analyze_momentum_indicators(data)
        volume_analysis = analyze_volume_indicators(data)
        volatility_analysis = analyze_volatility_indicators(data)
        
        logger.info(f"Successfully analyzed basic technical indicators for {symbol}")
        return TechnicalAnalysisValues(
            **trend_analysis,
            **momentum_analysis,
            **volume_analysis,
            **volatility_analysis
        )

    except Exception as e:
        raise Exception(f"Error analyzing technical indicators: {str(e)}")

# Example usage
if __name__ == "__main__":
    analysis = get_basic_technical_indicators(
        symbol="RELIANCE"
    )
    
    print(analysis)
    
    print("\nTechnical Indicator Values:")
    print("\nTrend Indicators:")
    print(f"SMA Values: {analysis.sma_values}")
    print(f"EMA Values: {analysis.ema_values}")
    print(f"MACD Values: {analysis.macd_values}")
    print(f"Trend Metrics: {analysis.trend_metrics}")
    
    print("\nMomentum Indicators:")
    print(f"RSI Values: {analysis.rsi_values}")
    print(f"Stochastic Values: {analysis.stoch_values}")
    print(f"CCI Values: {analysis.cci_values}")
    
    print("\nVolume Indicators:")
    print(f"OBV Values: {analysis.obv_values}")
    print(f"ADL Values: {analysis.adl_values}")
    
    print("\nVolatility Indicators:")
    print(f"Bollinger Values: {analysis.bollinger_values}")
    print(f"ATR Values: {analysis.atr_values}")