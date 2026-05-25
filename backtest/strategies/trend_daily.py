"""
Daily Trend Following — Donchian midline with ATR trailing stop, D1.

STRATEGY LOGIC:
  BUY  when close crosses above the midline of the 50-period Donchian channel
       AND ADX(14) > 20 (confirming trend, not ranging)
  SELL when close crosses below the midline
       AND ADX(14) > 20

  Midline = (highest_high_50 + lowest_low_50) / 2
  (equivalent to the midline of a Donchian channel — a simple trend proxy)

  SL  = 2.0 × ATR(14) from entry
  TP  = 4.0 × ATR(14) from entry (2:1 RR)

  On D1 we don't use a session filter (irrelevant for daily bars).

RATIONALE:
  Daily trend following is the oldest quantitative strategy. The Donchian
  midline crossover is a gentler entry than a full channel breakout — you
  enter when price reclaims the "center of gravity" of the last 50 days.
  ADX > 20 filters out sideways noise.

HONEST ASSESSMENT:
  D1 EURUSD with Yahoo Finance gives us ~10 years of data but the EMA200
  warmup plus train/test split leaves us with limited IS bars and very few
  OOS trades. Expect inconclusive results due to trade count.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from backtest.strategies.base import Strategy, Signal


class TrendDaily(Strategy):
    """
    Donchian midline crossover with ADX filter, D1.
    """

    def __init__(
        self,
        channel_period: int = 50,
        adx_period: int = 14,
        adx_threshold: float = 20.0,
        atr_period: int = 14,
        atr_sl_mult: float = 2.0,
        atr_tp_mult: float = 4.0,
        pip_size: float = 0.0001,
    ):
        self.channel_period = channel_period
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold
        self.atr_period = atr_period
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult
        self.pip_size = pip_size

        self._prev_above_mid: bool | None = None

    @property
    def warmup_bars(self) -> int:
        return self.channel_period + self.adx_period + 10

    def generate_signal(self, bars: pd.DataFrame) -> tuple[Signal, float, float]:
        if len(bars) < self.warmup_bars:
            self._prev_above_mid = None
            return Signal.HOLD, 40.0, 80.0

        closes = bars["close"]
        highs  = bars["high"]
        lows   = bars["low"]

        ch_high  = float(highs.rolling(self.channel_period).max().iloc[-1])
        ch_low   = float(lows.rolling(self.channel_period).min().iloc[-1])
        midline  = (ch_high + ch_low) / 2.0
        price    = float(closes.iloc[-1])

        adx = _adx(highs, lows, closes, self.adx_period)
        atr_pips = _atr(highs, lows, closes, self.atr_period) / self.pip_size
        sl_pips = max(20.0, round(self.atr_sl_mult * atr_pips, 1))
        tp_pips = max(40.0, round(self.atr_tp_mult * atr_pips, 1))

        above_mid = price > midline
        signal = Signal.HOLD

        if self._prev_above_mid is not None and adx > self.adx_threshold:
            if not self._prev_above_mid and above_mid:
                signal = Signal.BUY
            elif self._prev_above_mid and not above_mid:
                signal = Signal.SELL

        self._prev_above_mid = above_mid
        return signal, sl_pips, tp_pips

    def reset(self) -> None:
        self._prev_above_mid = None


def _atr(highs: pd.Series, lows: pd.Series, closes: pd.Series, period: int) -> float:
    prev_close = closes.shift(1)
    tr = pd.concat([
        highs - lows,
        (highs - prev_close).abs(),
        (lows  - prev_close).abs(),
    ], axis=1).max(axis=1)
    val = tr.rolling(period).mean().iloc[-1]
    return float(val) if not np.isnan(val) else 0.0020


def _adx(highs: pd.Series, lows: pd.Series, closes: pd.Series, period: int) -> float:
    """Wilder's ADX. Returns ADX value for the last bar."""
    prev_high  = highs.shift(1)
    prev_low   = lows.shift(1)
    prev_close = closes.shift(1)

    # True Range
    tr = pd.concat([
        highs - lows,
        (highs - prev_close).abs(),
        (lows  - prev_close).abs(),
    ], axis=1).max(axis=1)

    # Directional moves
    up_move   = highs - prev_high
    down_move = prev_low - lows

    dm_plus  = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    dm_minus = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    dm_plus_s  = pd.Series(dm_plus,  index=closes.index).rolling(period).mean()
    dm_minus_s = pd.Series(dm_minus, index=closes.index).rolling(period).mean()
    atr_s      = tr.rolling(period).mean()

    di_plus  = 100 * dm_plus_s  / atr_s.replace(0, np.nan)
    di_minus = 100 * dm_minus_s / atr_s.replace(0, np.nan)

    dx = 100 * (di_plus - di_minus).abs() / (di_plus + di_minus).replace(0, np.nan)
    adx = dx.rolling(period).mean()

    val = adx.iloc[-1]
    return float(val) if not np.isnan(val) else 0.0
