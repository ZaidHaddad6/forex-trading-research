"""
Data fetcher: downloads EURUSD OHLCV data from Yahoo Finance and caches it.

WHY YAHOO FINANCE?
  Free, no API key, good quality for forex. The ticker "EURUSD=X" is the
  mid-price composite from several interbank sources. It's not tick data but
  it's good enough for strategy research.

KNOWN LIMITATIONS (be honest about these):
  - Daily data: goes back to the early 2000s. Excellent for D1 testing.
  - Hourly data: max ~730 days (~2 years). Covers 2022–2024 but NOT 2020 COVID.
  - M5 data:    max ~60 days. Not useful for multi-year backtests.
  - M1 data:    max ~7 days. Essentially useless for backtesting.

  For M1/M5, a proper backtest would need Dukascopy or HistData.com tick data.
  We'll be explicit when a timeframe lacks sufficient history.

  The prices are MID prices. In live trading you pay the ASK to buy and receive
  the BID to sell. The spread cost is modeled separately in the broker.
"""

import os
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")

# Yahoo Finance interval → max lookback period we can request
_MAX_PERIOD = {
    "1m":  "7d",
    "5m":  "60d",
    "15m": "60d",
    "1h":  "730d",
    "1d":  "10y",
}

# Map our human-readable names to yfinance interval strings
TIMEFRAME_MAP = {
    "M1":  "1m",
    "M5":  "5m",
    "M15": "15m",
    "H1":  "1h",
    "H4":  "1h",   # fetched as H1, resampled to H4
    "D1":  "1d",
}

# Minimum bars we consider "enough" for a meaningful backtest
MIN_BARS = {
    "M1":  500,
    "M5":  2000,
    "M15": 2000,
    "H1":  5000,
    "H4":  1000,
    "D1":  500,
}


def fetch(timeframe: str = "H1", ticker: str = "EURUSD=X", force_refresh: bool = False) -> pd.DataFrame:
    """
    Return a clean OHLCV DataFrame for the requested timeframe.

    Columns: open, high, low, close, volume
    Index:   DatetimeIndex in UTC

    If H4 is requested, we download H1 and resample — Yahoo doesn't
    offer H4 natively.

    Results are cached as CSV so repeated runs don't hit the network.
    """
    if timeframe not in TIMEFRAME_MAP:
        raise ValueError(f"Unknown timeframe '{timeframe}'. Choose from {list(TIMEFRAME_MAP)}")

    cache_path = os.path.join(CACHE_DIR, f"{ticker.replace('=','_')}_{timeframe}.csv")

    if not force_refresh and os.path.exists(cache_path):
        df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True)
        print(f"[data] Loaded {timeframe} from cache: {len(df)} bars "
              f"({df.index[0].date()} → {df.index[-1].date()})")
        return df

    yf_interval = TIMEFRAME_MAP[timeframe]
    period = _MAX_PERIOD[yf_interval]

    print(f"[data] Downloading {ticker} {timeframe} (yfinance interval={yf_interval}, period={period})...")

    raw = yf.download(
        ticker,
        period=period,
        interval=yf_interval,
        auto_adjust=True,
        progress=False,
    )

    if raw.empty:
        raise RuntimeError(f"No data returned for {ticker} {timeframe}")

    # Flatten multi-level columns if present (yfinance sometimes returns them)
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [col[0].lower() for col in raw.columns]
    else:
        raw.columns = [c.lower() for c in raw.columns]

    df = raw[["open", "high", "low", "close", "volume"]].copy()
    df.index = pd.to_datetime(df.index, utc=True)
    df = df.dropna()

    # H4: resample from H1
    if timeframe == "H4":
        df = _resample_to_h4(df)

    # Warn if data is thin
    n = len(df)
    min_bars = MIN_BARS.get(timeframe, 100)
    if n < min_bars:
        print(f"[data] WARNING: Only {n} bars for {timeframe}. "
              f"Need {min_bars}+ for a meaningful backtest. "
              f"Consider using D1 or H1 instead.")
    else:
        print(f"[data] {timeframe}: {n} bars "
              f"({df.index[0].date()} → {df.index[-1].date()})")

    df.to_csv(cache_path)
    return df


def _resample_to_h4(df: pd.DataFrame) -> pd.DataFrame:
    """
    Resample H1 OHLCV to H4 bars.

    OHLC resampling rules:
      open  = first bar's open
      high  = max of 4 bars
      low   = min of 4 bars
      close = last bar's close
      volume = sum

    We use closed='left', label='left' so the H4 bar timestamp is the
    OPEN time of the first H1 bar — consistent with how brokers display them.
    """
    return df.resample("4h", closed="left", label="left").agg({
        "open":   "first",
        "high":   "max",
        "low":    "min",
        "close":  "last",
        "volume": "sum",
    }).dropna()


def split_train_test(df: pd.DataFrame, train_pct: float = 0.70) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Split into in-sample (train) and out-of-sample (test) by TIME, not randomly.

    WHY TIME-BASED SPLIT?
      Random splits leak future data into training. If a model trains on data
      from 2023 and also has some 2023 test points, it has implicitly seen the
      future market regime. Time-based split ensures OOS data is strictly
      later than all IS data — the only valid evaluation approach for time series.

    We never tune parameters on the OOS set. It exists only for final evaluation.
    """
    cutoff = int(len(df) * train_pct)
    train = df.iloc[:cutoff].copy()
    test  = df.iloc[cutoff:].copy()
    print(f"[data] Train: {len(train)} bars ({train.index[0].date()} → {train.index[-1].date()})")
    print(f"[data] Test:  {len(test)} bars  ({test.index[0].date()} → {test.index[-1].date()})")
    return train, test
