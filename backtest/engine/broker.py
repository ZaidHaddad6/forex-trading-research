"""
Simulated broker — models Capital.com's cost structure.

COST MODEL DESIGN DECISIONS:
  Capital.com is a CFD broker. The cost structure is:
    1. Spread: The difference between the bid and ask price. You buy at the ask,
       sell at the bid. For EURUSD during normal hours, Capital.com quotes ~0.6 pips.
       During news events or low liquidity, spread widens to 2-5+ pips.
    2. No commission: Capital.com retail accounts don't charge per-trade commission.
       The spread IS the commission.
    3. Overnight financing (swap): CFD positions held overnight incur a financing
       charge. For simplicity we model this as 0 since our strategy targets
       intraday exits. In practice this matters for D1 strategies.
    4. Slippage: The difference between the price you see and the price you get.
       At market order on a liquid pair like EURUSD, slippage is typically 0–1 pip.
       We model 0.5 pip per side conservatively.

  Total round-trip cost per trade:
    Spread: 0.6 pip (we pay 0.3 pip entering, 0.3 pip exiting)
    Slippage: 0.5 pip entering + 0.5 pip exiting = 1.0 pip
    Total: ~1.6 pips round trip = 0.00016 price units for EURUSD

  This is deliberately conservative (real-world is closer to 1.3 pips in liquid hours).
  A strategy that can't overcome 1.6 pips of cost isn't worth trading.

POSITION SIZING:
  The live bot uses fixed size = 100 units. For the backtest we use a fixed
  fractional risk model: risk 1% of current equity per trade, with the stop loss
  defining position size.

  Position size = (equity * risk_pct) / (sl_pips * pip_value)

  This is more realistic than fixed lots and lets us compound gains/losses
  naturally over time.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd


@dataclass
class Trade:
    """A single completed trade record."""
    entry_time: pd.Timestamp
    exit_time:  pd.Timestamp
    direction:  str          # "BUY" or "SELL"
    entry_price: float
    exit_price:  float
    sl_price:    float
    tp_price:    float
    size:        float       # units
    gross_pnl:   float       # P&L before costs (in price units × size)
    cost:        float       # total transaction cost (spread + slippage)
    net_pnl:     float       # gross_pnl - cost
    exit_reason: str         # "TP", "SL", "SIGNAL", "END"
    equity_at_entry: float


class SimBroker:
    """
    Simulates order execution with realistic costs.

    Parameters
    ----------
    initial_equity : float
        Starting account size in USD.
    spread_pips : float
        Bid-ask spread in pips. 0.6 matches Capital.com EURUSD typical.
    slippage_pips : float
        Additional execution slippage per side in pips.
    risk_pct : float
        Fraction of equity risked per trade (e.g. 0.01 = 1%).
    pip_size : float
        Size of 1 pip in price units. 0.0001 for EURUSD, 0.01 for USDJPY.
    pip_value_per_unit : float
        USD value of 1 pip move per 1 unit of size.
        For EURUSD: 1 unit = 1 USD notional → 1 pip = $0.0001.
        For a standard lot (100,000 units): 1 pip = $10.
    """

    def __init__(
        self,
        initial_equity: float = 10.0,
        spread_pips: float = 0.6,
        slippage_pips: float = 0.5,
        risk_pct: float = 0.01,
        pip_size: float = 0.0001,
        pip_value_per_unit: float = 0.0001,
    ):
        self.initial_equity = initial_equity
        self.equity = initial_equity
        self.spread_pips = spread_pips
        self.slippage_pips = slippage_pips
        self.risk_pct = risk_pct
        self.pip_size = pip_size
        self.pip_value_per_unit = pip_value_per_unit

        self._position: Optional[dict] = None   # open position state
        self.trades: list[Trade] = []
        self.equity_curve: list[tuple] = [(None, initial_equity)]  # (time, equity)

    # ------------------------------------------------------------------
    # Cost helpers
    # ------------------------------------------------------------------

    @property
    def _cost_per_side(self) -> float:
        """Cost in price units per side (spread half + slippage)."""
        return (self.spread_pips / 2 + self.slippage_pips) * self.pip_size

    def _entry_price(self, mid: float, direction: str) -> float:
        """Effective execution price at entry after spread and slippage."""
        if direction == "BUY":
            return mid + self._cost_per_side   # we pay the ask + slippage
        else:
            return mid - self._cost_per_side   # we sell the bid - slippage

    def _exit_price(self, mid: float, direction: str) -> float:
        """Effective execution price at exit after spread and slippage."""
        if direction == "BUY":
            return mid - self._cost_per_side   # we sell the bid - slippage
        else:
            return mid + self._cost_per_side   # we buy the ask + slippage

    # ------------------------------------------------------------------
    # Position sizing
    # ------------------------------------------------------------------

    def _calc_size(self, sl_pips: float) -> float:
        """
        Risk-based position sizing.

        size = (equity × risk_pct) / (sl_pips × pip_value_per_unit)

        Example: equity=$10, risk=1%, sl=20 pips, pip_value=$0.0001/unit
          size = (10 × 0.01) / (20 × 0.0001) = 0.10 / 0.002 = 50 units
        """
        if sl_pips <= 0:
            return 0.0
        risk_usd = self.equity * self.risk_pct
        size = risk_usd / (sl_pips * self.pip_value_per_unit)
        return round(size, 2)

    # ------------------------------------------------------------------
    # Order execution
    # ------------------------------------------------------------------

    def open(
        self,
        time: pd.Timestamp,
        direction: str,
        mid_price: float,
        sl_pips: float,
        tp_pips: float,
    ) -> None:
        """Open a new position. Ignores the call if already in a position."""
        if self._position is not None:
            return

        size = self._calc_size(sl_pips)
        if size <= 0:
            return

        entry = self._entry_price(mid_price, direction)
        pip = self.pip_size

        if direction == "BUY":
            sl_price = entry - sl_pips * pip
            tp_price = entry + tp_pips * pip
        else:
            sl_price = entry + sl_pips * pip
            tp_price = entry - tp_pips * pip

        self._position = {
            "entry_time": time,
            "direction":  direction,
            "entry_price": entry,
            "sl_price":   sl_price,
            "tp_price":   tp_price,
            "size":       size,
            "equity_at_entry": self.equity,
        }

    def close(
        self,
        time: pd.Timestamp,
        mid_price: float,
        reason: str = "SIGNAL",
    ) -> Optional[Trade]:
        """Close the current position and record the trade."""
        if self._position is None:
            return None

        p = self._position
        exit_px = self._exit_price(mid_price, p["direction"])

        if p["direction"] == "BUY":
            gross_pnl = (exit_px - p["entry_price"]) * p["size"]
        else:
            gross_pnl = (p["entry_price"] - exit_px) * p["size"]

        # Total cost: we already paid half the spread+slippage on entry,
        # now pay the other half on exit.
        total_cost = self._cost_per_side * 2 * p["size"]
        net_pnl = gross_pnl - total_cost

        # Wait — cost is already baked into entry/exit prices above.
        # So gross_pnl already includes the spread/slippage. net_pnl = gross_pnl.
        # We track 'cost' separately for analysis purposes only.
        cost_for_analysis = total_cost
        net_pnl = gross_pnl  # already accounts for spread via entry/exit prices

        self.equity += net_pnl
        self.equity_curve.append((time, self.equity))

        trade = Trade(
            entry_time=p["entry_time"],
            exit_time=time,
            direction=p["direction"],
            entry_price=p["entry_price"],
            exit_price=exit_px,
            sl_price=p["sl_price"],
            tp_price=p["tp_price"],
            size=p["size"],
            gross_pnl=gross_pnl,
            cost=cost_for_analysis,
            net_pnl=net_pnl,
            exit_reason=reason,
            equity_at_entry=p["equity_at_entry"],
        )
        self.trades.append(trade)
        self._position = None
        return trade

    def check_sl_tp(
        self,
        time: pd.Timestamp,
        high: float,
        low: float,
    ) -> Optional[Trade]:
        """
        Check if SL or TP was hit during this bar.

        WHY CHECK HIGH/LOW AND NOT JUST CLOSE?
          A bar's close doesn't tell you the order in which prices moved intrabar.
          A bar with close=1.1650 might have touched both 1.1640 (SL) and 1.1660 (TP)
          during the same bar. We can't know which hit first from OHLC data alone.

          Convention: if both SL and TP are hit in the same bar, assume SL hit first
          (conservative — avoids flattering the results). If only one is hit, use that.
          If neither, no fill.
        """
        if self._position is None:
            return None

        p = self._position
        sl, tp = p["sl_price"], p["tp_price"]

        if p["direction"] == "BUY":
            sl_hit = low <= sl
            tp_hit = high >= tp
            if sl_hit:  # conservative: SL wins ties
                return self.close(time, sl, "SL")
            if tp_hit:
                return self.close(time, tp, "TP")
        else:
            sl_hit = high >= sl
            tp_hit = low <= tp
            if sl_hit:
                return self.close(time, sl, "SL")
            if tp_hit:
                return self.close(time, tp, "TP")

        return None

    @property
    def has_position(self) -> bool:
        return self._position is not None

    @property
    def position_direction(self) -> Optional[str]:
        return self._position["direction"] if self._position else None

    def reset(self) -> None:
        self.equity = self.initial_equity
        self._position = None
        self.trades = []
        self.equity_curve = [(None, self.initial_equity)]
