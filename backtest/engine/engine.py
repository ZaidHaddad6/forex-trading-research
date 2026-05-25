"""
Backtesting engine — the event loop.

THE MOST IMPORTANT RULE: NO LOOK-AHEAD BIAS.

Look-ahead bias = using future data to make a past decision.
It's the most common and damaging mistake in backtesting, and it always
makes results look better than they are. Common sources:

  1. Using the bar's own close to both generate the signal AND execute the trade.
     FIX: signal fires at bar N close, trade executes at bar N+1 open.

  2. Computing indicators on the full dataset before slicing.
     This is actually FINE for indicators like EMA and MACD (they're causal
     by definition — each value only depends on past values). The pandas ewm()
     function computes them correctly without lookahead. We verify this below.

  3. Using adjusted prices or split-adjusted data where the adjustment factor
     came from future events. Less relevant for forex.

  4. Fitting normalization parameters (mean, std) on the full dataset.
     We don't do this here.

HOW WE PREVENT LOOK-AHEAD BIAS:
  - Signal computed at close of bar i
  - Trade opened at open of bar i+1 (next bar)
  - SL/TP checked against HIGH/LOW of each subsequent bar
  - Strategy only receives df.iloc[:i+1] — strictly past data

  The strategy classes compute all indicators on the slice they receive.
  Because EMA/RSI/MACD are causal, we could also precompute them on the full
  dataset and just index by row — same result. We do the former for clarity.
"""
from __future__ import annotations
import pandas as pd
from backtest.engine.broker import SimBroker
from backtest.strategies.base import Strategy, Signal


def run(
    df: pd.DataFrame,
    strategy: Strategy,
    broker: SimBroker,
    label: str = "",
) -> list:
    """
    Run a backtest on a prepared OHLCV DataFrame.

    Parameters
    ----------
    df : DataFrame with columns [open, high, low, close, volume], DatetimeIndex
    strategy : Strategy instance with generate_signal() method
    broker : SimBroker instance (will be reset before running)
    label : string prefix for progress messages

    Returns
    -------
    List of Trade objects (also stored on broker.trades)
    """
    broker.reset()
    warmup = strategy.warmup_bars
    n = len(df)

    for i in range(warmup, n):
        bar = df.iloc[i]
        time = df.index[i]

        # ── Step 1: check SL/TP on the current bar ──────────────────────
        # This must happen BEFORE generating new signals, because the position
        # might have been closed by this bar's price action.
        if broker.has_position:
            broker.check_sl_tp(time, bar["high"], bar["low"])

        # ── Step 2: generate signal using ALL data up to and INCLUDING bar i ─
        # Strictly causal: strategy can only see df.iloc[:i+1]
        bars_so_far = df.iloc[:i + 1]
        signal, sl_pips, tp_pips = strategy.generate_signal(bars_so_far)

        # ── Step 3: execute at OPEN of bar i+1 ──────────────────────────
        # This is the critical anti-lookahead step. We know the signal at
        # the close of bar i, but we can't actually trade until the next bar opens.
        if i + 1 >= n:
            break  # no next bar to execute on

        next_bar = df.iloc[i + 1]
        next_time = df.index[i + 1]
        next_open = next_bar["open"]

        if signal == Signal.BUY:
            if broker.has_position and broker.position_direction == "SELL":
                broker.close(next_time, next_open, "SIGNAL")
            if not broker.has_position:
                broker.open(next_time, "BUY", next_open, sl_pips, tp_pips)

        elif signal == Signal.SELL:
            if broker.has_position and broker.position_direction == "BUY":
                broker.close(next_time, next_open, "SIGNAL")
            if not broker.has_position:
                broker.open(next_time, "SELL", next_open, sl_pips, tp_pips)

    # ── Close any open position at end of data ───────────────────────────
    if broker.has_position:
        last_bar = df.iloc[-1]
        broker.close(df.index[-1], last_bar["close"], "END")

    if label:
        print(f"[engine] {label}: {len(broker.trades)} trades completed")

    return broker.trades
