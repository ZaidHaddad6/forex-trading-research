"""
Mean Reversion — RSI(2) extremes + Bollinger Band touch, H1.

STRATEGY LOGIC:
  BUY  when RSI(2) < 10 AND close <= lower Bollinger Band (20, 2.0)
       → price is stretched far below average, bet on snap-back
       Exit: close >= middle band (SMA20) OR fixed SL

  SELL when RSI(2) > 90 AND close >= upper Bollinger Band (20, 2.0)
       → price is stretched far above average, bet on snap-back
       Exit: close <= middle band (SMA20) OR fixed SL

  SL = 1.5 × ATR(14) pips (adaptive, not fixed)
  TP = touch of middle Bollinger Band (SMA20 close) → but we use a
       fixed 1:1 TP here since the engine uses fixed pip targets.
       We set TP = SL so we get 1:1 RR. Mean reversion historically
       has high win rate with 1:1 or even 0.8:1 RR.

  No session filter — mean reversion works across all hours.
  No trend filter — mean reversion is counter-trend by design.

HONEST ASSESSMENT:
  This strategy relies on RSI(2) which is extremely sensitive and whipsaw-prone.
  It works well in range-bound markets and fails badly in trending markets.
  On H1 EURUSD the regime mix is unknown — results will tell.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from backtest.strategies.base import Strategy, Signal


class MeanReversion(Strategy):
    """
    RSI(2) + Bollinger Band mean reversion on H1.
    """

    def __init__(
        self,
        rsi_period: int = 2,
        rsi_oversold: float = 10.0,
        rsi_overbought: float = 90.0,
        bb_period: int = 20,
        bb_std: float = 2.0,
        atr_period: int = 14,
        atr_sl_mult: float = 1.5,
        pip_size: float = 0.0001,
    ):
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.atr_period = atr_period
        self.atr_sl_mult = atr_sl_mult
        self.pip_size = pip_size

    @property
    def warmup_bars(self) -> int:
        return max(self.bb_period, self.atr_period) + self.rsi_period + 10

    def generate_signal(self, bars: pd.DataFrame) -> tuple[Signal, float, float]:
        if len(bars) < self.warmup_bars:
            return Signal.HOLD, 20.0, 20.0

        closes = bars["close"]
        highs  = bars["high"]
        lows   = bars["low"]

        rsi = _rsi(closes, self.rsi_period)

        sma = closes.rolling(self.bb_period).mean()
        std = closes.rolling(self.bb_period).std(ddof=0)
        upper_band = float((sma + self.bb_std * std).iloc[-1])
        lower_band = float((sma - self.bb_std * std).iloc[-1])

        price = float(closes.iloc[-1])
        atr_pips = _atr(highs, lows, closes, self.atr_period) / self.pip_size
        sl_pips = max(10.0, round(self.atr_sl_mult * atr_pips, 1))
        tp_pips = sl_pips  # 1:1 RR

        if rsi < self.rsi_oversold and price <= lower_band:
            return Signal.BUY, sl_pips, tp_pips
        if rsi > self.rsi_overbought and price >= upper_band:
            return Signal.SELL, sl_pips, tp_pips

        return Signal.HOLD, sl_pips, tp_pips

    def reset(self) -> None:
        pass  # stateless


def _rsi(series: pd.Series, period: int) -> float:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.inf)
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return float(val) if not np.isnan(val) else 50.0


def _atr(highs: pd.Series, lows: pd.Series, closes: pd.Series, period: int) -> float:
    prev_close = closes.shift(1)
    tr = pd.concat([
        highs - lows,
        (highs - prev_close).abs(),
        (lows  - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    val = atr.iloc[-1]
    return float(val) if not np.isnan(val) else 0.0002
