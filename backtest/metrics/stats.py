"""
Performance metrics.

METRIC GUIDE:
  Win rate        — % of trades that made money. Means nothing alone.
  Profit factor   — Gross profit / Gross loss. PF > 1 = profitable.
  Sharpe ratio    — Risk-adjusted return on trade PnL series (annualized).
  Sortino ratio   — Like Sharpe but only penalizes losing trades.
                    COMPUTED ON TRADE PnL SERIES, not bar-by-bar equity curve.
                    Bar-by-bar equity is flat between trades → near-zero std →
                    garbage Sortino. Trade PnL series is the correct denominator.
  Max drawdown    — Largest peak-to-trough decline in equity.
  Expectancy      — Average profit per trade in dollars.
  T-statistic     — t = mean_pnl / (std_pnl / sqrt(n)).
                    t < 2.0 → cannot reject H0 that edge = 0.
  Trades per year — n_trades / years_covered. < 30/yr = too few to be reliable.
  Calmar ratio    — Annual return / Max drawdown %.
"""
from __future__ import annotations
import math
import numpy as np
import pandas as pd
from backtest.engine.broker import SimBroker, Trade


def compute(broker: SimBroker, periods_per_year: int = 252,
            years_covered: float | None = None) -> dict:
    """
    Compute all performance metrics from a completed backtest.

    Parameters
    ----------
    broker : SimBroker after running the backtest
    periods_per_year : trading periods per year for Sharpe annualisation.
    years_covered : length of the period in years (used for trades/yr).
        If None, estimated from the equity_curve timestamps.
    """
    trades = broker.trades
    initial = broker.initial_equity
    final = broker.equity

    if not trades:
        return _empty_metrics()

    pnls = np.array([t.net_pnl for t in trades])
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]

    n_trades = len(pnls)
    win_rate = len(wins) / n_trades
    avg_win = float(np.mean(wins)) if len(wins) else 0.0
    avg_loss = float(abs(np.mean(losses))) if len(losses) else 0.0
    expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

    gross_profit = float(wins.sum()) if len(wins) else 0.0
    gross_loss = float(abs(losses.sum())) if len(losses) else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    net_return_pct = (final - initial) / initial * 100

    # ── Equity curve for drawdown only ──────────────────────────────────
    equity_vals = [eq for _, eq in broker.equity_curve]
    equity_series = pd.Series(equity_vals)
    max_dd, max_dd_pct = _max_drawdown(equity_series)

    # ── Sharpe / Sortino on TRADE PnL series (not bar-by-bar equity) ────
    # Bar-by-bar equity is flat between trades so its std is inflated by zeros,
    # making Sortino nonsensically large. Use trade-level PnL as the return series.
    sharpe = _sharpe_from_pnl(pnls, periods_per_year)
    sortino = _sortino_from_pnl(pnls, periods_per_year)

    # ── T-statistic on mean trade PnL ───────────────────────────────────
    # H0: mean trade PnL = 0 (no edge). t < 2 → fail to reject H0.
    pnl_std = float(np.std(pnls, ddof=1))
    if pnl_std > 0 and n_trades >= 2:
        t_stat = float(np.mean(pnls)) / (pnl_std / math.sqrt(n_trades))
    else:
        t_stat = 0.0

    # ── Trades per year ──────────────────────────────────────────────────
    if years_covered is None and len(broker.equity_curve) >= 2:
        t0 = broker.equity_curve[0][0]
        t1 = broker.equity_curve[-1][0]
        years_covered = (t1 - t0).total_seconds() / (365.25 * 86400)
    trades_per_year = n_trades / years_covered if (years_covered and years_covered > 0) else 0.0

    calmar = (net_return_pct / 100) / (max_dd_pct / 100) if max_dd_pct > 0 else float("inf")

    return {
        "n_trades":        n_trades,
        "win_rate":        round(win_rate * 100, 1),
        "avg_win":         round(avg_win, 4),
        "avg_loss":        round(avg_loss, 4),
        "expectancy":      round(expectancy, 4),
        "profit_factor":   round(profit_factor, 3),
        "gross_profit":    round(gross_profit, 4),
        "gross_loss":      round(gross_loss, 4),
        "net_return_pct":  round(net_return_pct, 2),
        "final_equity":    round(final, 4),
        "sharpe":          round(sharpe, 3),
        "sortino":         round(sortino, 3),
        "t_stat":          round(t_stat, 2),
        "trades_per_year": round(trades_per_year, 1),
        "max_dd_usd":      round(max_dd, 4),
        "max_dd_pct":      round(max_dd_pct, 2),
        "calmar":          round(calmar, 3),
        "pct_tp":          round(sum(1 for t in trades if t.exit_reason == "TP") / n_trades * 100, 1),
        "pct_sl":          round(sum(1 for t in trades if t.exit_reason == "SL") / n_trades * 100, 1),
    }


def _sharpe_from_pnl(pnls: np.ndarray, periods_per_year: int) -> float:
    """Sharpe computed on per-trade PnL series, annualized by periods_per_year."""
    if len(pnls) < 2:
        return 0.0
    std = float(np.std(pnls, ddof=1))
    if std == 0:
        return 0.0
    return float((np.mean(pnls) / std) * math.sqrt(periods_per_year))


def _sortino_from_pnl(pnls: np.ndarray, periods_per_year: int) -> float:
    """Sortino computed on per-trade PnL series. Denominator = std of losing trades only."""
    losses = pnls[pnls < 0]
    if len(losses) < 2:
        return 0.0
    downside_std = float(np.std(losses, ddof=1))
    if downside_std == 0:
        return 0.0
    return float((np.mean(pnls) / downside_std) * math.sqrt(periods_per_year))


def _max_drawdown(equity: pd.Series) -> tuple[float, float]:
    """Returns (max_drawdown_in_dollars, max_drawdown_as_pct_of_peak)."""
    peak = equity.cummax()
    drawdown = equity - peak
    max_dd_usd = abs(float(drawdown.min()))
    max_dd_pct = abs(float((drawdown / peak).min())) * 100
    return max_dd_usd, max_dd_pct


def _empty_metrics() -> dict:
    return {k: 0 for k in [
        "n_trades", "win_rate", "avg_win", "avg_loss", "expectancy",
        "profit_factor", "gross_profit", "gross_loss", "net_return_pct",
        "final_equity", "sharpe", "sortino", "t_stat", "trades_per_year",
        "max_dd_usd", "max_dd_pct", "calmar", "pct_tp", "pct_sl",
    ]}


def print_report(metrics: dict, label: str = "", years_covered: float = 0.0) -> None:
    """Print a formatted performance report."""
    header = f"  {label}  " if label else ""
    n = metrics["n_trades"]
    inconclusive = n < 30

    print(f"\n{'═'*55}")
    print(f"  BACKTEST RESULTS {header}")
    if inconclusive:
        print(f"  *** INCONCLUSIVE — only {n} trades (need ≥30) ***")
    print(f"{'═'*55}")
    print(f"  Trades:         {n}  ({metrics['trades_per_year']}/yr)")
    print(f"  Win rate:       {metrics['win_rate']}%")
    print(f"  Avg win:        ${metrics['avg_win']:.4f}")
    print(f"  Avg loss:       ${metrics['avg_loss']:.4f}")
    print(f"  Expectancy:     ${metrics['expectancy']:.4f} / trade")
    print(f"  Profit factor:  {metrics['profit_factor']}")
    print(f"  Net return:     {metrics['net_return_pct']}%")
    print(f"  Sharpe ratio:   {metrics['sharpe']}")
    print(f"  Sortino ratio:  {metrics['sortino']}")
    t = metrics["t_stat"]
    t_flag = "  ← FAIL: no detectable edge" if abs(t) < 2.0 else "  ← edge detectable"
    print(f"  T-statistic:    {t:.2f}{t_flag}")
    print(f"  Max drawdown:   {metrics['max_dd_pct']}%  (${metrics['max_dd_usd']:.4f})")
    print(f"  Calmar ratio:   {metrics['calmar']}")
    print(f"  TP exits:       {metrics['pct_tp']}%  |  SL exits: {metrics['pct_sl']}%")
    print(f"{'═'*55}\n")
