"""
EMA 9/21 crossover strategy — exact replication of the live bot.

This is the current live strategy. We backtest it to understand its behaviour
across timeframes. The live bot uses M1 bars; we'll test M1 through D1 to
show how timeframe selection affects performance.

STRATEGY LOGIC (matches src/strategy/moving_average.py exactly):

  Entry:
    BUY  if EMA9 crosses above EMA21
         AND RSI(7) is between 50 and 75 (momentum up, not overbought)
         AND price > EMA200 (in an uptrend)
         AND MACD histogram > 0 (momentum confirming)
         AND active session (07:00–21:00 UTC) [only for M1/M5/M15/H1]
         AND EMA gap >= 1 pip (not ranging)

    SELL if EMA9 crosses below EMA21
         AND RSI(7) is between 25 and 50 (momentum down, not oversold)
         AND price < EMA200 (in a downtrend)
         AND MACD histogram < 0
         AND active session
         AND EMA gap >= 1 pip

  Exit:
    Fixed SL = 20 pips, Fixed TP = 40 pips (2:1 RR)
    Trailing stop not replicated here (would require bar-by-bar state —
    added in a future iteration if needed).

  Parameters (matches live .env):
    short_period   = 9
    long_period    = 21
    trend_period   = 200
    rsi_period     = 7
    rsi_overbought = 75
    rsi_oversold   = 25
    sl_pips        = 20
    tp_pips        = 40
"""
from __future__ import annotations
import pandas as pd
import numpy as np
from backtest.strategies.base import Strategy, Signal


def _ema(series: pd.Series, span: int) -> pd.Series:
    """EMA using the same ewm(adjust=False) as the live bot."""
    return series.ewm(span=span, adjust=False).mean()


def _rsi(series: pd.Series, period: int = 7) -> float:
    """RSI using simple moving average of gains/losses (Wilder's method via rolling)."""
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.inf)
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not rsi.empty else 50.0


def _macd_histogram(series: pd.Series, fast=12, slow=26, signal=9) -> float:
    if len(series) < slow + signal:
        return 0.0
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return float((macd_line - signal_line).iloc[-1])


def _is_active_session(ts: pd.Timestamp) -> bool:
    """London + NY session: 07:00–21:00 UTC."""
    hour = ts.hour
    return 7 <= hour < 21


class EMACrossover(Strategy):
    """
    Exact replication of the live bot strategy for backtesting.

    Parameters
    ----------
    short_period : int, EMA fast period (default 9)
    long_period  : int, EMA slow period (default 21)
    trend_period : int, EMA trend filter period (default 200)
    rsi_period   : int (default 7)
    rsi_overbought : float (default 75)
    rsi_oversold   : float (default 25)
    sl_pips : float, stop loss in pips (default 20)
    tp_pips : float, take profit in pips (default 40)
    pip_size : float (default 0.0001 for EURUSD)
    use_session_filter : bool — disable for D1/H4 where session is irrelevant
    """

    def __init__(
        self,
        short_period: int = 9,
        long_period: int = 21,
        trend_period: int = 200,
        rsi_period: int = 7,
        rsi_overbought: float = 75.0,
        rsi_oversold: float = 25.0,
        sl_pips: float = 20.0,
        tp_pips: float = 40.0,
        pip_size: float = 0.0001,
        use_session_filter: bool = True,
    ):
        self.short_period = short_period
        self.long_period = long_period
        self.trend_period = trend_period
        self.rsi_period = rsi_period
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold
        self.sl_pips = sl_pips
        self.tp_pips = tp_pips
        self.pip_size = pip_size
        self.use_session_filter = use_session_filter

        # Track previous EMA values for crossover detection (stateful)
        self._prev_short: float | None = None
        self._prev_long:  float | None = None

    @property
    def warmup_bars(self) -> int:
        # Need at least trend_period bars for EMA200 to stabilise.
        # In practice EWM starts from bar 1 but the first 200 bars are unreliable.
        return self.trend_period + self.rsi_period + 30

    def generate_signal(self, bars: pd.DataFrame) -> tuple[Signal, float, float]:
        closes = bars["close"]

        if len(closes) < self.warmup_bars:
            return Signal.HOLD, self.sl_pips, self.tp_pips

        short_ma = float(_ema(closes, self.short_period).iloc[-1])
        long_ma  = float(_ema(closes, self.long_period).iloc[-1])
        trend_ma = float(_ema(closes, self.trend_period).iloc[-1])
        rsi      = _rsi(closes, self.rsi_period)
        macd_h   = _macd_histogram(closes)
        price    = float(closes.iloc[-1])
        ts       = bars.index[-1]

        signal = Signal.HOLD

        if self._prev_short is not None and self._prev_long is not None:
            crossover_up   = self._prev_short < self._prev_long and short_ma > long_ma
            crossover_down = self._prev_short > self._prev_long and short_ma < long_ma

            if crossover_up or crossover_down:
                ema_gap = abs(short_ma - long_ma)
                session_ok = (not self.use_session_filter) or _is_active_session(ts)

                if ema_gap >= self.pip_size and session_ok:
                    if crossover_up:
                        if 50 < rsi < self.rsi_overbought:
                            if price > trend_ma and macd_h > 0:
                                signal = Signal.BUY
                    elif crossover_down:
                        if self.rsi_oversold < rsi < 50:
                            if price < trend_ma and macd_h < 0:
                                signal = Signal.SELL

        # Update state AFTER computing signal so the crossover check uses
        # the previous tick's values, not the current ones.
        self._prev_short = short_ma
        self._prev_long  = long_ma

        return signal, self.sl_pips, self.tp_pips

    def reset(self) -> None:
        """Reset state between in-sample and out-of-sample runs."""
        self._prev_short = None
        self._prev_long  = None
