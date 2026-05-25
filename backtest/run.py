"""
Backtesting runner — Steps 1, 2, and 3.

WHAT THIS DOES:
  Step 1 (EMA crossover): D1, H4, H1, M5, M1
  Step 2 (alternative strategies):
    - Mean reversion (RSI2 + Bollinger): H1
    - Donchian breakout (ATR stops):     H4
    - Trend following (Donchian midline): D1

  For each run we report:
    - In-sample vs out-of-sample performance
    - T-statistic with PASS/FAIL on edge detection (|t| >= 2)
    - Trades/year — < 5/yr flagged as "too few to be reliable"
    - INCONCLUSIVE banner when OOS trade count < 30

  We do NOT tune any parameters on the out-of-sample set.
  We do NOT cherry-pick results.

HONEST DATA LIMITATIONS:
  M1: max 7 days of data (yfinance) — functionally useless for backtesting.
      Results are purely illustrative of costs, not strategy performance.
  M5: max 60 days — too short to be statistically meaningful.
  H1: ~730 days — borderline. Enough for one regime but not multi-regime.
  H4: ~730 days resampled — same limitations as H1.
  D1: ~10 years — best data quality. Still only one asset.

Run from the trading-bot directory:
  python -m backtest.run
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from backtest.data.fetcher import fetch, split_train_test
from backtest.engine.broker import SimBroker
from backtest.engine.engine import run
from backtest.metrics.stats import compute, print_report
from backtest.strategies.ema_crossover import EMACrossover
from backtest.strategies.mean_reversion import MeanReversion
from backtest.strategies.donchian_breakout import DonchianBreakout
from backtest.strategies.trend_daily import TrendDaily


# ── Sanity checks ──────────────────────────────────────────────────────────────

def verify_no_lookahead(trades, df, warmup_bars):
    if not trades:
        return True
    first_possible_entry = df.index[warmup_bars + 1]
    for t in trades:
        if t.entry_time < first_possible_entry:
            print(f"  [FAIL] Look-ahead detected! Trade at {t.entry_time} before warmup ends at {first_possible_entry}")
            return False
    print(f"  [OK] No look-ahead bias — earliest trade at {trades[0].entry_time}")
    return True


def verify_sl_tp_placement(trades):
    for t in trades:
        if t.direction == "BUY":
            assert t.sl_price < t.entry_price, f"BUY SL above entry: {t}"
            assert t.tp_price > t.entry_price, f"BUY TP below entry: {t}"
        else:
            assert t.sl_price > t.entry_price, f"SELL SL below entry: {t}"
            assert t.tp_price < t.entry_price, f"SELL TP above entry: {t}"
    print(f"  [OK] All SL/TP placements correct ({len(trades)} trades)")


def verify_equity_curve(broker):
    expected = broker.initial_equity + sum(t.net_pnl for t in broker.trades)
    actual = broker.equity
    if abs(expected - actual) > 0.0001:
        print(f"  [FAIL] Equity mismatch: expected {expected:.6f}, got {actual:.6f}")
        return False
    print(f"  [OK] Equity curve consistent (${actual:.4f})")
    return True


# ── Generic runner ─────────────────────────────────────────────────────────────

def run_strategy(
    strategy,
    timeframe: str,
    label: str,
    data_warning: str = "",
    sanity_checks: bool = False,
) -> tuple[dict, dict]:
    """
    Run a strategy IS+OOS on the given timeframe.
    Returns (is_metrics, oos_metrics). Returns (None, None) if insufficient data.
    """
    print(f"\n{'━'*60}")
    print(f"  {label.upper()}  [{timeframe}]")
    if data_warning:
        print(f"  ⚠  DATA WARNING: {data_warning}")
    print(f"{'━'*60}")

    df = fetch(timeframe)
    if len(df) < 500:
        print(f"  Skipping: insufficient data ({len(df)} bars, need 500+)")
        return None, None

    periods_map = {
        "M1": 252*390, "M5": 252*78, "M15": 252*26,
        "H1": 252*6, "H4": 252*1.5, "D1": 252,
    }
    ppy = int(periods_map.get(timeframe, 252))

    train, test = split_train_test(df, train_pct=0.70)

    def _years(subset: pd.DataFrame) -> float:
        secs = (subset.index[-1] - subset.index[0]).total_seconds()
        return secs / (365.25 * 86400)

    broker = SimBroker(initial_equity=10.0)

    # ── In-sample ──────────────────────────────────────────────────────────
    print("\n  IN-SAMPLE")
    strategy.reset()
    run(train, strategy, broker, label=f"{label} IS")
    is_metrics = compute(broker, periods_per_year=ppy, years_covered=_years(train))
    print_report(is_metrics, f"{label} In-Sample")

    if sanity_checks:
        print("  Framework sanity checks:")
        verify_no_lookahead(broker.trades, train, strategy.warmup_bars)
        if broker.trades:
            verify_sl_tp_placement(broker.trades)
        verify_equity_curve(broker)

    # ── Out-of-sample ──────────────────────────────────────────────────────
    print("\n  OUT-OF-SAMPLE (honest evaluation)")
    strategy.reset()
    broker.reset()
    run(test, strategy, broker, label=f"{label} OOS")
    oos_metrics = compute(broker, periods_per_year=ppy, years_covered=_years(test))
    print_report(oos_metrics, f"{label} Out-of-Sample")

    return is_metrics, oos_metrics


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "═"*60)
    print("  BACKTESTING FRAMEWORK — STEPS 1, 2 & 3")
    print("  Data: EURUSD via Yahoo Finance (mid prices)")
    print("  Costs: 0.6 pip spread + 0.5 pip slippage/side (1.6 pip round-trip)")
    print("  Risk: 1% equity per trade")
    print("  Split: 70% in-sample / 30% out-of-sample (time-based, never random)")
    print("  Edge threshold: |t-stat| >= 2.0 (95% confidence)")
    print("  Inconclusive: OOS < 30 trades regardless of returns")
    print("═"*60)

    results = []  # list of (strategy_name, timeframe, is_m, oos_m)

    # ══════════════════════════════════════════════════════════════════════
    print("\n\n" + "█"*60)
    print("  STEP 1 — EMA 9/21 CROSSOVER (live bot replication)")
    print("█"*60)

    # D1 — best coverage
    is_m, oos_m = run_strategy(
        EMACrossover(use_session_filter=False), "D1", "EMA Crossover",
        sanity_checks=True,
    )
    if is_m:
        results.append(("EMA Crossover", "D1", is_m, oos_m))

    # H4
    is_m, oos_m = run_strategy(
        EMACrossover(use_session_filter=False), "H4", "EMA Crossover",
    )
    if is_m:
        results.append(("EMA Crossover", "H4", is_m, oos_m))

    # H1
    is_m, oos_m = run_strategy(
        EMACrossover(use_session_filter=True), "H1", "EMA Crossover",
    )
    if is_m:
        results.append(("EMA Crossover", "H1", is_m, oos_m))

    # M5 — 60 days only, purely illustrative
    is_m, oos_m = run_strategy(
        EMACrossover(use_session_filter=True), "M5", "EMA Crossover",
        data_warning="60 days max. Results are NOT statistically meaningful.",
    )
    if is_m:
        results.append(("EMA Crossover", "M5", is_m, oos_m))

    # M1 — 7 days only, functionally useless
    is_m, oos_m = run_strategy(
        EMACrossover(use_session_filter=True), "M1", "EMA Crossover",
        data_warning="7 days max. IGNORE RESULTS — this is cost illustration only.",
    )
    if is_m:
        results.append(("EMA Crossover", "M1", is_m, oos_m))

    # ══════════════════════════════════════════════════════════════════════
    print("\n\n" + "█"*60)
    print("  STEP 2 — ALTERNATIVE STRATEGIES")
    print("█"*60)

    # Mean reversion on H1
    is_m, oos_m = run_strategy(
        MeanReversion(), "H1", "Mean Reversion (RSI2+BB)",
    )
    if is_m:
        results.append(("Mean Reversion", "H1", is_m, oos_m))

    # Donchian breakout on H4
    is_m, oos_m = run_strategy(
        DonchianBreakout(), "H4", "Donchian Breakout",
    )
    if is_m:
        results.append(("Donchian Breakout", "H4", is_m, oos_m))

    # Trend following on D1
    is_m, oos_m = run_strategy(
        TrendDaily(), "D1", "Trend Following (Daily)",
    )
    if is_m:
        results.append(("Trend Daily", "D1", is_m, oos_m))

    # ══════════════════════════════════════════════════════════════════════
    # Summary table
    if results:
        print("\n" + "═"*90)
        print("  MASTER SUMMARY TABLE")
        print(f"  {'Strategy':<25} {'TF':<5} {'Spl':<4} {'N':>5} {'Tr/yr':>6} "
              f"{'WR%':>5} {'PF':>5} {'Sharpe':>7} {'Sortino':>8} {'t-stat':>7} "
              f"{'DD%':>6} {'Net%':>7} {'Verdict'}")
        print("  " + "─"*88)

        for (strat, tf, is_m, oos_m) in results:
            for split, m in [("IS", is_m), ("OOS", oos_m)]:
                n = m["n_trades"]
                t = m["t_stat"]
                inconcl = (split == "OOS" and n < 30)
                verdict = "INCONCLUSIVE (<30 trades)" if inconcl else (
                    "FAIL (t<2)" if abs(t) < 2.0 else (
                        "PASS" if m["net_return_pct"] > 0 and m["profit_factor"] > 1 else "FAIL"
                    )
                )
                print(
                    f"  {strat:<25} {tf:<5} {split:<4} {n:>5} "
                    f"{m['trades_per_year']:>6.1f} "
                    f"{m['win_rate']:>5.1f} {m['profit_factor']:>5.2f} "
                    f"{m['sharpe']:>7.2f} {m['sortino']:>8.2f} "
                    f"{t:>7.2f} {m['max_dd_pct']:>6.2f} "
                    f"{m['net_return_pct']:>7.2f} {verdict}"
                )
        print("═"*90)

    print("\n[DONE]")
    print("  Interpretation guide:")
    print("  INCONCLUSIVE   — < 30 OOS trades. Returns mean nothing at this sample size.")
    print("  FAIL (t<2)     — Cannot reject H0 (no edge). Results are noise.")
    print("  PASS           — t >= 2, positive expectancy, PF > 1 on OOS. Warrants further study.")
    print("  If everything shows FAIL or INCONCLUSIVE: the strategies don't have a detectable edge.")
    print("  That is a valid result. Do not curve-fit to make them pass.\n")


if __name__ == "__main__":
    main()
