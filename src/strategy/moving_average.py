import pandas as pd
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Signal(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class StrategyResult:
    signal: Signal
    short_ma: float
    long_ma: float
    price: float
    rsi: float = 0.0
    rsi_filtered: bool = False
    trend_ma: float = 0.0
    trend_filtered: bool = False
    macd_histogram: float = 0.0
    macd_filtered: bool = False
    session_filtered: bool = False
    ranging_filtered: bool = False


def compute_rsi(prices: list[float], period: int = 7) -> float:
    if len(prices) < period + 1:
        return 50.0
    series = pd.Series(prices)
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, float("inf"))
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])


def compute_macd(prices: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[float, float, float]:
    """Returns (macd_line, signal_line, histogram)."""
    if len(prices) < slow + signal:
        return 0.0, 0.0, 0.0
    series = pd.Series(prices)
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return float(macd_line.iloc[-1]), float(signal_line.iloc[-1]), float(histogram.iloc[-1])


def is_active_session() -> bool:
    """True during London + NY sessions (07:00-21:00 UTC). Skip Asian dead hours."""
    from datetime import datetime, timezone
    hour = datetime.now(timezone.utc).hour
    return 7 <= hour < 21


def compute_signal(
    prices: list[float],
    short_period: int,
    long_period: int,
    previous_short_ma: Optional[float] = None,
    previous_long_ma: Optional[float] = None,
    rsi_period: int = 7,
    rsi_overbought: float = 75.0,
    rsi_oversold: float = 25.0,
    trend_period: int = 200,
    check_session: bool = True,
    epic: str = "",
) -> StrategyResult:
    """EMA crossover with MACD, RSI direction, MA200 trend, session, and ranging filters.

    Entry rules:
      BUY : EMA9 crosses above EMA21 AND RSI>50 AND RSI<overbought AND price>EMA200
            AND MACD histogram>0 AND active session AND EMAs not flat
      SELL: EMA9 crosses below EMA21 AND RSI<50 AND RSI>oversold AND price<EMA200
            AND MACD histogram<0 AND active session AND EMAs not flat
    """
    if len(prices) < long_period:
        return StrategyResult(
            signal=Signal.HOLD,
            short_ma=0.0,
            long_ma=0.0,
            price=prices[-1] if prices else 0.0,
        )

    series = pd.Series(prices)
    short_ma = float(series.ewm(span=short_period, adjust=False).mean().iloc[-1])
    long_ma = float(series.ewm(span=long_period, adjust=False).mean().iloc[-1])
    price = prices[-1]
    rsi = compute_rsi(prices, rsi_period)
    _, _, macd_histogram = compute_macd(prices)

    trend_ma = 0.0
    has_trend = len(prices) >= trend_period
    if has_trend:
        trend_ma = float(series.ewm(span=trend_period, adjust=False).mean().iloc[-1])

    signal = Signal.HOLD
    rsi_filtered = False
    trend_filtered = False
    macd_filtered = False
    session_filtered = False
    ranging_filtered = False

    if previous_short_ma is not None and previous_long_ma is not None:
        was_below = previous_short_ma < previous_long_ma
        is_above = short_ma > long_ma
        was_above = previous_short_ma > previous_long_ma
        is_below = short_ma < long_ma

        crossover_up = was_below and is_above
        crossover_down = was_above and is_below

        if crossover_up or crossover_down:
            # Session filter
            if check_session and not is_active_session():
                session_filtered = True
            else:
                pip = 0.01 if "JPY" in epic else 0.0001
                ema_gap = abs(short_ma - long_ma)
                # Ranging filter: EMAs must be separated by at least 1 pip
                if ema_gap < pip:
                    ranging_filtered = True
                elif crossover_up:
                    if rsi >= rsi_overbought:
                        rsi_filtered = True
                    elif rsi < 50:  # RSI must confirm upward momentum
                        rsi_filtered = True
                    elif has_trend and price < trend_ma:
                        trend_filtered = True
                    elif macd_histogram < 0:
                        macd_filtered = True
                    else:
                        signal = Signal.BUY
                elif crossover_down:
                    if rsi <= rsi_oversold:
                        rsi_filtered = True
                    elif rsi > 50:  # RSI must confirm downward momentum
                        rsi_filtered = True
                    elif has_trend and price > trend_ma:
                        trend_filtered = True
                    elif macd_histogram > 0:
                        macd_filtered = True
                    else:
                        signal = Signal.SELL

    return StrategyResult(
        signal=signal,
        short_ma=short_ma,
        long_ma=long_ma,
        price=price,
        rsi=rsi,
        rsi_filtered=rsi_filtered,
        trend_ma=trend_ma,
        trend_filtered=trend_filtered,
        macd_histogram=macd_histogram,
        macd_filtered=macd_filtered,
        session_filtered=session_filtered,
        ranging_filtered=ranging_filtered,
    )
