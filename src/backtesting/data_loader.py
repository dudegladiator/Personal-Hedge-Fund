from requests_ratelimiter import LimiterSession, RequestRate, Limiter, Duration
import pandas as pd
import yfinance as yf


class DataLoader:
    def __init__(self):
        history_rate = RequestRate(1, Duration.SECOND)
        limiter = Limiter(history_rate)
        self.session = LimiterSession(limiter=limiter)
        self.session.headers['User-agent'] = 'tickerpicker/1.0'

    def load_data(self, symbol, start_date, end_date, timeframe = "1D") -> pd.DataFrame:
        """Load historical data for backtesting"""
        try:
            # Format ticker based on exchange
            ticker = f"{symbol}.NS"
            
            # Download data
            data = yf.download(
                ticker,
                start=start_date,
                end=end_date,
                interval=timeframe,
                progress=False,
                session=self.session
            )
            
            if data.empty or len(data) < 2:
                raise ValueError(f"Insufficient data for {symbol}")
            
            return data
            
        except Exception as e:
            raise Exception(f"Error loading data for {symbol}: {str(e)}")