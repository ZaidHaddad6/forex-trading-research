# Strategy Analysis Report

**Asset:** EURUSD  
**Data source:** Yahoo Finance (mid prices, cached)  
**Cost model:** 0.6 pip spread + 0.5 pip slippage per side = 1.6 pips round-trip  
**Risk per trade:** 1% of equity (risk-based position sizing)  
**Evaluation split:** 70% in-sample (IS) / 30% out-of-sample (OOS), time-ordered  
**Edge threshold:** |t-statistic| ≥ 2.0 (95% confidence)  
**Inconclusive threshold:** OOS trade count < 30  

---

## Data Availability

Yahoo Finance provides the following history for EURUSD:

| Timeframe | Max History | Bars Available | Suitable for Backtesting? |
|-----------|-------------|----------------|--------------------------|
| D1 | 10 years | 2,601 | Yes — best coverage |
| H1 | 730 days | 17,252 | Marginal — one regime |
| H4 | 730 days (resampled from H1) | 4,440 | Marginal |
| M5 | 60 days | 16,733 | No — too short |
| M1 | 7 days | 8,989 | No — effectively useless |

The M1 and M5 results are included for completeness but carry a data warning. Any M5 or M1 "result" is a snapshot of 60 or 7 days of one recent market regime, not a strategy evaluation.

---

## Strategy 1: EMA 9/21 Crossover (Live Bot Replication)

**Logic:** Buy when EMA(9) crosses above EMA(21), RSI(7) between 50–75, price above EMA(200), MACD histogram positive. Sell on mirror conditions. Fixed 20-pip SL, 40-pip TP.

**Parameters:** Exact production values from the live bot — no tuning.

### Full Results

| Split | TF | Trades | Trades/yr | Win% | PF | Sharpe | t-stat | MaxDD% | Net% |
|---|---|---|---|---|---|---|---|---|---|
| IS | D1 | 9 | 1.3 | 22.2 | 0.52 | -4.72 | -0.89 | 6.1 | -3.4 |
| **OOS** | **D1** | **3** | **1.0** | **66.7** | **3.71** | **8.71** | **0.95** | **1.0** | **+2.9** |
| IS | H4 | 11 | 5.6 | 45.5 | 1.55 | 3.93 | 0.67 | 3.2 | +3.5 |
| **OOS** | **H4** | **4** | **4.8** | **25.0** | **0.62** | **-3.87** | **-0.40** | **2.1** | **-1.2** |
| IS | H1 | 33 | 16.9 | 36.4 | 1.06 | 1.07 | 0.16 | 13.7 | +1.4 |
| **OOS** | **H1** | **6** | **7.1** | **33.3** | **0.93** | **-1.26** | **-0.08** | **2.1** | **-0.3** |
| IS | M5 | 2 | 12.7 | 100.0 | ∞ | — | — | 0.0 | +4.0 |
| **OOS** | **M5** | **1** | **14.1** | **0.0** | **0.00** | **—** | **—** | **1.0** | **-1.0** |
| IS | M1 | 0 | — | — | — | — | — | — | — |
| **OOS** | **M1** | **0** | **—** | **—** | **—** | **—** | **—** | **—** | **—** |

### Interpretation

**The fundamental problem is signal frequency.** The EMA crossover fires 1–7 times per year at H1 and above. To detect a genuine edge with 95% confidence, you need a t-statistic ≥ 2.0. With 6 OOS trades (H1), you'd need a win rate above ~80% to achieve this — which would itself be suspicious.

The D1 OOS shows +2.9% and a PF of 3.71 on 3 trades. This looks impressive. It is not. Three trades is smaller than the margin of error — three heads in a row does not prove a coin is biased.

The H1 in-sample result (33 trades, t=0.16) is the only statistically credible observation. A t-statistic of 0.16 means the results are 84% of the way toward being indistinguishable from random chance. There is no detectable edge.

**Verdict: INCONCLUSIVE at all timeframes.** The strategy does not generate enough trades to be fairly evaluated. This is itself a finding — a strategy that fires once per year per timeframe cannot be tested and therefore cannot be trusted.

---

## Strategy 2: Mean Reversion — RSI(2) + Bollinger Bands (H1)

**Logic:** Buy when RSI(2) < 10 AND price touches or crosses the lower Bollinger Band (20, 2σ). Sell on mirror conditions. SL = 1.5× ATR(14), TP = 1:1 SL distance.

**Rationale:** RSI(2) is a short-term overbought/oversold oscillator. Combined with a Bollinger Band touch, it identifies statistically extreme moves expected to revert.

### Full Results

| Split | Trades | Trades/yr | Win% | PF | Sharpe | t-stat | MaxDD% | Net% |
|---|---|---|---|---|---|---|---|---|
| IS | 483 | 247.0 | 50.5 | 0.90 | -2.06 | -1.17 | 40.7 | -19.7 |
| **OOS** | **208** | **247.3** | **51.4** | **0.96** | **-0.83** | **-0.31** | **15.3** | **-4.3** |

### Interpretation

This is the most statistically meaningful result in the study — 208 OOS trades is a large enough sample to draw conclusions.

**The conclusion is: this strategy loses money on EURUSD H1, 2025–2026.** Profit factor of 0.96 means for every $1 in gross losses, the strategy earns $0.96. After 208 trades the cumulative cost drag (-4.3%) is clear and consistent with the IS result (-19.7%). The directional bias is stable: this strategy underperforms.

**Why does it fail?** The EURUSD 2023–2026 period was characterized by strong directional moves driven by central bank policy divergence (Fed, ECB, BOE). Mean reversion strategies perform well in quiet, range-bound regimes and catastrophically in trending regimes — you keep buying into falling markets and selling into rising ones. The 40.7% IS max drawdown reflects this.

A 51.4% win rate sounds promising but is irrelevant: the strategy loses more per loss than it wins per win (avg win < avg loss), making positive expectancy impossible.

**Verdict: FAIL — conclusively unprofitable in this test period.**

---

## Strategy 3: Donchian Channel Breakout (H4)

**Logic:** Buy when close breaks above the 20-period Donchian high (prior 20 bars' highest high). Sell on break below. SL = 1.5× ATR(14), TP = 3.0× ATR(14).

**Rationale:** Price breaking out of a 20-bar channel (80 hours) represents a significant level breach. The 2:1 RR (TP at 3× ATR vs SL at 1.5× ATR) means the strategy can be profitable below 40% win rate.

### Full Results

| Split | Trades | Trades/yr | Win% | PF | Sharpe | t-stat | MaxDD% | Net% |
|---|---|---|---|---|---|---|---|---|
| IS | 153 | 78.3 | 28.1 | 0.75 | -2.62 | -1.67 | 25.7 | -23.3 |
| **OOS** | **66** | **78.5** | **27.3** | **0.73** | **-2.85** | **-1.19** | **15.1** | **-11.8** |

### Interpretation

66 OOS trades is a credible sample. Both IS and OOS are clearly negative, with consistent profit factors (0.75 and 0.73). This is the most consistent result in the study — consistently losing.

**Why does it fail?** Breakout strategies need sustained directional moves after the breakout. On H4 EURUSD, the 20-bar channel (~80 hours) is wide enough that by the time price breaks it, the move has often largely occurred. Price then frequently reverses, hitting the SL. The 28% win rate is far below the 33% minimum needed to be profitable with 2:1 RR. The SL is being hit 68% of the time.

The IS t-statistic is -1.67, approaching the 2.0 threshold from below — this result is approaching statistical confidence that the strategy *loses*, not that it's just noisy.

**Verdict: FAIL — consistently and conclusively unprofitable.**

---

## Strategy 4: Trend Following — Donchian Midline + ADX (D1)

**Logic:** Buy when price crosses above the midline of the 50-period Donchian channel and ADX(14) > 20. Sell on mirror conditions. SL = 2× ATR(14), TP = 4× ATR(14).

**Rationale:** The Donchian midline crossover is a classic trend entry signal. ADX > 20 filters out sideways regimes where trend-following fails most often.

### Full Results

| Split | Trades | Trades/yr | Win% | PF | Sharpe | t-stat | MaxDD% | Net% |
|---|---|---|---|---|---|---|---|---|
| IS | 80 | 11.5 | 31.2 | 0.60 | -3.06 | -1.73 | 13.4 | -11.8 |
| **OOS** | **27** | **9.0** | **29.6** | **0.92** | **-0.47** | **-0.15** | **4.6** | **-0.8** |

### Interpretation

The OOS result of 27 trades is just below the 30-trade threshold — technically inconclusive, but the IS result (80 trades, t=-1.73) is statistically meaningful. The IS shows consistent underperformance with a trend t-stat approaching significance in the negative direction.

The OOS looks much better (-0.8% vs -11.8% IS). This is likely regime-specific: the D1 IS period (2016–2023) includes several high-volatility regimes where trend-following gets whipsawed. The OOS period (2023–2026) may have been more directionally consistent. But with 27 trades, we cannot distinguish "better strategy" from "three years of favorable coin flips."

**Verdict: INCONCLUSIVE (OOS) / FAIL (IS). Does not clear the t ≥ 2.0 bar at any split.**

---

## Master Summary

| Strategy | TF | OOS N | OOS PF | OOS Net% | t-stat | Final Verdict |
|---|---|---|---|---|---|---|
| EMA Crossover | D1 | 3 | 3.71 | +2.9% | 0.95 | **INCONCLUSIVE** |
| EMA Crossover | H4 | 4 | 0.62 | -1.2% | -0.40 | **INCONCLUSIVE** |
| EMA Crossover | H1 | 6 | 0.93 | -0.3% | -0.08 | **INCONCLUSIVE** |
| Mean Reversion | H1 | 208 | 0.96 | -4.3% | -0.31 | **FAIL** |
| Donchian Breakout | H4 | 66 | 0.73 | -11.8% | -1.19 | **FAIL** |
| Trend Following | D1 | 27 | 0.92 | -0.8% | -0.15 | **INCONCLUSIVE** |

**No strategy produced a t-statistic ≥ 2.0 on the out-of-sample period.** The null hypothesis — that these strategies have no edge over random trading — cannot be rejected at any reasonable confidence level.

---

## Lessons Learned

### 1. Most retail technical strategies don't have a verifiable edge

The strategies tested here — EMA crossovers, RSI extremes, Bollinger Bands, Donchian channels — are in every trading book written in the last 40 years. Millions of retail traders run variants of them. If they worked consistently, the edge would be arbitraged away. More importantly, when you apply a proper statistical test (t-statistic), most "profitable" backtests reveal their results to be within normal random variation.

This doesn't mean all technical strategies fail. It means the bar for claiming a strategy "works" is higher than most retail content implies. A PF > 1 on a 3-month backtest is not evidence of an edge.

### 2. Overfitting is invisible from the inside

Overfitting is when a strategy's parameters are tuned — consciously or unconsciously — to produce good results on historical data. It's nearly impossible to detect from within a single backtest because every overfit strategy looks profitable in-sample by definition.

Signs you might be overfitting:
- You tested multiple parameter combinations and kept the best one
- Your best results are on a specific date range (because you looked at dates while tuning)
- Your strategy has many simultaneous conditions that all need to be true
- In-sample performance is dramatically better than OOS (this project: EMA H4 IS +3.5% → OOS -1.2%)

The correct response to these signs is not to keep testing. It's to stop, report the honest result, and treat the strategy as unproven.

### 3. Why t-statistics matter

A profit factor of 3.71 sounds excellent. The EMA crossover on D1 OOS achieved this. It was on 3 trades. With 3 trades, you need to win all 3 at 3:1 RR — which happens by chance 12.5% of the time even for a coin-flip strategy. You cannot distinguish "genuine edge" from "got lucky" with 3 observations.

The t-statistic operationalizes this intuition:

```
t = mean_trade_PnL / (std_trade_PnL / sqrt(n))
```

It asks: "How many standard errors away from zero is my mean return?" If t < 2.0, the answer is "not far enough to be confident it isn't zero." Every OOS result in this study had |t| < 2.0.

For common trading frequencies:
- 1 trade/year on D1 → you need 25+ years to achieve t ≥ 2.0 even with a genuine edge
- 10 trades/year on H1 → you need 10+ years  
- 50 trades/year → you need 2–3 years of clean data

The EMA crossover, firing 1–7 times per year, is mathematically untestable on the data lengths available.

### 4. Transaction costs are not a rounding error

At 1.6 pips round-trip, the EMA crossover with 20-pip SL has a built-in cost of 8% of its risk per trade before the market moves at all. For the strategy to break even at 50% win rate with 2:1 RR, it needs the market to move 40 pips before the 20-pip SL triggers — but the 1.6-pip cost means the effective SL is only 18.4 pips and the effective TP is 41.6 pips. This shifts the breakeven win rate upward.

For strategies that trade frequently (Mean Reversion: 247 trades/year), costs dominate. The mean reversion strategy lost 19.7% IS — close to all of it is the cost of 483 round-trips at 1.6 pips each.

### 5. The live bot taught me more than any book

Running a real bot — even on $10 — forced me to handle: API authentication failures, rate limiting, session token expiry, timezone bugs in pip detection, race conditions across three simultaneous bots, process persistence, and the psychological experience of watching losses in real time.

None of this appears in backtesting tutorials. Building both sides of the system — live execution and historical simulation — made the limitations of each obvious.

---

## What a Genuine Edge Would Require

A strategy worth trading would need to demonstrate:

1. **OOS t-statistic ≥ 2.0** on a test set that was never seen during development
2. **Consistent IS → OOS degradation** that is small and explainable (not 90% deterioration)
3. **Enough trades** to achieve statistical power (≥ 30 OOS trades is the minimum; 100+ is better)
4. **Performance across multiple asset pairs** — if it only works on EURUSD, it's probably fit to that pair's regime history
5. **An explainable reason why the edge exists** — what market inefficiency is being captured, and why hasn't it been arbitraged away?

None of the strategies tested here met criteria 1–3, let alone 4–5.

---

## Next Steps (If Continuing)

If this project were to continue with the same rigor:

1. **Acquire better intraday data.** Dukascopy and HistData.com provide free tick-level data going back 10+ years. This enables M5/M15 testing with statistical power.

2. **Walk-forward validation.** Instead of one IS/OOS split, roll a 1-year training window forward in 3-month steps and check whether OOS performance is consistent across windows. Inconsistency = regime dependence.

3. **Test fundamentally different strategy types.** Statistical arbitrage (pairs trading), options-based strategies, or machine-learning approaches on structured fundamental data rather than price alone.

4. **Multiple assets simultaneously.** A strategy that works on 10 uncorrelated instruments at t ≥ 2.0 each is far more credible than one working on EURUSD alone.
