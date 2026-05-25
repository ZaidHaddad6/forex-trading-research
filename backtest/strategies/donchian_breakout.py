"""
Donchian Channel Breakout — H4.

STRATEGY LOGIC:
  BUY  when close breaks ABOVE the 20-period Donchian high
       (highest high of the previous 20 bars, excluding current bar)
  SELL when close breaks BELOW the 20-period Donchian low
       (lowest low of the previous 20 bars, excluding current bar)

  SL  = 1.5 × ATR(14) from entry (adaptive)
  TP  = 3.0 × ATR(14) from entry (2:1 RR)

  One position at a time. Reverse on opposite signal.

RATIONALE:
  Donchian breakouts capture the start of new trends. They work best when
  markets have strong directional moves. H4 gives enough bar resolution
  to catch multi-day trends without the noise of H1.

  Known weakness: whipsaw in sideways markets. The 20-bar lookback means
  we only trade breakouts of ~80 hours of consolidation — meaningful levels.

HONEST ASSESSMENT:
  Breakout strategies have low win rates (30-45%) but large winners.
  On EURUSD they've historically worked during rate-hike/risk-off regimes
  and failed badly in the low-volatility range-bound periods of 2021-2022.
  We don't know which regime the test period hits — results will tell.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from backtest.strategies.base import Strategy, Signal


class DonchianBreakout(Strategy):
    """
    Donchian channel breakout on H4 with ATR-based stops.
    """

    def __init__(
        self,
        channel_period: int = 20,
        atr_period: int = 14,
        atr_sl_mult: float = 1.5,
        atr_tp_mult: float = 3.0,
        pip_size: float = 0.0001,
    ):
        self.channel_period = channel_period
        self.atr_period = atr_period
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult
        self.pip_size = pip_size

    @property
    def warmup_bars(self) -> int:
        return self.channel_period + self.atr_period + 5

    def generate_signal(self, bars: pd.DataFrame) -> tuple[Signal, float, float]:
        if len(bars) < self.warmup_bars:
            return Signal.HOLD, 20.0, 40.0

        closes = bars["close"]
        highs  = bars["high"]
        lows   = bars["low"]

        # Use bars up to (but NOT including) the current bar for channel levels.
        # This prevents current bar's own high/low from being part of the breakout level.
        prev_bars = bars.iloc[:-1]
        channel_high = float(prev_bars["high"].rolling(self.channel_period).max().iloc[-1])
        channel_low  = float(prev_bars["low"].rolling(self.channel_period).min().iloc[-1])

        price = float(closes.iloc[-1])
        atr_pips = _atr(highs, lows, closes, self.atr_period) / self.pip_size
        sl_pips = max(10.0, round(self.atr_sl_mult * atr_pips, 1))
        tp_pips = max(20.0, round(self.atr_tp_mult * atr_pips, 1))

        if price > channel_high:
            return Signal.BUY, sl_pips, tp_pips
        if price < channel_low:
            return Signal.SELL, sl_pips, tp_pips

        return Signal.HOLD, sl_pips, tp_pips

    def reset(self) -> None:
        pass  # stateless


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
