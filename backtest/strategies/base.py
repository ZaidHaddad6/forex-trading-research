"""
Abstract base class for all strategies.

Every strategy must implement:
  generate_signal(bars) → (Signal, sl_pips, tp_pips)
  warmup_bars            → int (minimum bars needed before first signal)

The engine calls generate_signal() with ALL bars up to the current bar.
The strategy must only use data from that slice — the engine enforces this
by only passing df.iloc[:i+1].

DESIGN PRINCIPLE:
  Strategies are stateless functions of their input bars. This makes them
  easy to test, easy to reason about, and impossible to accidentally leak
  state between the in-sample and out-of-sample runs.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from enum import Enum
import pandas as pd


class Signal(Enum):
    BUY  = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class Strategy(ABC):

    @property
    @abstractmethod
    def warmup_bars(self) -> int:
        """Number of bars to skip at the start before the strategy can produce signals.
        Typically = max indicator period. The engine never calls generate_signal()
        for the first warmup_bars bars.
        """

    @abstractmethod
    def generate_signal(self, bars: pd.DataFrame) -> tuple[Signal, float, float]:
        """
        Parameters
        ----------
        bars : DataFrame of ALL bars up to and including the current bar.
               Columns: open, high, low, close, volume
               The strategy should only use bars.iloc[-N:] or indicators
               computed from this slice.

        Returns
        -------
        (signal, sl_pips, tp_pips)
          signal   : Signal.BUY, SELL, or HOLD
          sl_pips  : stop loss distance in pips (always positive)
          tp_pips  : take profit distance in pips (always positive)
        """
