# Algorithmic Forex Trading — Research & Backtesting

A personal project to learn quantitative trading through building, deploying, and rigorously testing a live forex bot. The project concludes honestly: **none of the four strategies tested showed a statistically detectable edge** on EURUSD after transaction costs.

The value here is the methodology — not a fake-profitable result.

---

## What I Built

### 1. Live Trading Bot (`src/`)

A Python bot that traded EURUSD live on a Capital.com CFD account using a real $10 balance.

- **Strategy:** EMA 9/21 crossover with RSI(7), MACD, and EMA(200) trend filters
- **Infrastructure:** Capital.com REST API, PM2 process manager for persistence, Telegram notifications for every trade
- **Risk management:** 1% equity risk per trade, fixed 20-pip SL / 40-pip TP (2:1 RR), 5-minute post-trade cooldown, economic calendar blackout (FOMC, ECB, NFP)
- **Multi-pair:** Ran simultaneously on EURUSD, GBPUSD, USDJPY with staggered startup and rate-limit backoff

### 2. Backtesting Framework (`backtest/`)

A from-scratch bar-by-bar backtesting engine built to learn what a rigorous test actually requires.

- **No look-ahead bias:** Signal fires at close of bar N; execution at open of bar N+1
- **Realistic costs:** 0.6-pip spread + 0.5-pip slippage per side (1.6 pips round-trip)
- **Risk-based sizing:** Position size derived from 1% equity risk and the specific SL distance, not fixed lots
- **Proper evaluation:** Time-based 70/30 train/test split (never random), t-statistic edge detection, trades-per-year, max drawdown
- **Four strategies tested:** EMA crossover, RSI2+Bollinger mean reversion, Donchian channel breakout, Donchian midline trend following

---

## Project Structure

```
trading-bot/
├── src/                          # Live bot
│   ├── api/capital_client.py     # Capital.com REST client (auth, orders, prices)
│   ├── bot/trader.py             # Main trading loop
│   ├── strategy/moving_average.py # EMA crossover signal logic
│   ├── news/economic_calendar.py  # High-impact event blackout filter
│   └── notifications/telegram.py  # Telegram trade alerts
│
├── backtest/                     # Backtesting framework
│   ├── data/fetcher.py           # Yahoo Finance downloader + H4 resampler + cache
│   ├── engine/
│   │   ├── engine.py             # Event loop (causal bar-by-bar execution)
│   │   └── broker.py             # SimBroker: costs, sizing, SL/TP, equity curve
│   ├── metrics/stats.py          # Sharpe, Sortino, max DD, t-stat, trades/yr
│   ├── strategies/
│   │   ├── base.py               # Abstract Strategy interface
│   │   ├── ema_crossover.py      # Live bot replication
│   │   ├── mean_reversion.py     # RSI(2) + Bollinger Bands
│   │   ├── donchian_breakout.py  # Donchian channel with ATR stops
│   │   └── trend_daily.py        # Donchian midline + ADX filter
│   └── run.py                    # Master runner: all strategies, all timeframes
│
├── main.py                       # Bot entry point
├── run_all.py                    # Multi-pair launcher
└── requirements.txt
```

---

## How to Run the Backtest

```bash
# Install dependencies
pip install pandas numpy yfinance

# Run all strategies across all timeframes
python -m backtest.run
```

The runner downloads EURUSD data from Yahoo Finance (free, no API key), caches it locally, and produces a full results table with statistical verdicts.

---

## Results Summary

Full results with interpretation: [`ANALYSIS.md`](ANALYSIS.md)

| Strategy | TF | OOS Trades | OOS PF | OOS Net% | t-stat | Verdict |
|---|---|---|---|---|---|---|
| EMA Crossover | D1 | 3 | 3.71 | +2.9% | 0.95 | INCONCLUSIVE |
| EMA Crossover | H4 | 4 | 0.62 | -1.2% | -0.40 | INCONCLUSIVE |
| EMA Crossover | H1 | 6 | 0.93 | -0.3% | -0.08 | INCONCLUSIVE |
| Mean Reversion | H1 | 208 | 0.96 | -4.3% | -0.31 | FAIL |
| Donchian Breakout | H4 | 66 | 0.73 | -11.8% | -1.19 | FAIL |
| Trend Following | D1 | 27 | 0.92 | -0.8% | -0.15 | INCONCLUSIVE |

**No strategy passed the t ≥ 2.0 threshold for edge detection.** The EMA crossover generates too few signals to be conclusive at any testable timeframe. The three alternative strategies are conclusively unprofitable on the test period.

---

## Key Technical Decisions

**Why time-based train/test split?**
Random splits leak future market regimes into training. A model trained on mixed 2022/2024 data has implicitly "seen" how 2022 resolved. The only honest split is chronological — train on everything before date X, test on everything after.

**Why t-statistic instead of profit factor?**
Profit factor can look good on 5 lucky trades. A t-statistic of 0.95 on 3 OOS trades means the result is within normal random variation — you cannot distinguish it from a coin flip. t ≥ 2.0 means you'd see this result by chance less than 5% of the time.

**Why not tune parameters until they work?**
That's overfitting. Any parameter set that happens to be profitable on 5–10 trades found by searching is capturing random noise, not market structure. The parameters tested here are the live bot's production values, untouched.

**Why the conservative SL-wins-ties rule?**
When both SL and TP are touched in the same bar (we can't know order from OHLC data), assume SL hit first. This prevents the engine from flattering results in ambiguous cases.

---

## Lessons Learned

See [`ANALYSIS.md`](ANALYSIS.md) for the full write-up, including why retail technical strategies typically fail, what curve-fitting looks like, and what a proper edge test requires.

---

## What I Would Do Differently

1. **Start with statistics, not code.** Before writing a single line, I'd calculate how many trades a strategy generates per year on my target timeframe. Less than 50/year means you need 5+ years of data to say anything meaningful.

2. **Use tick data or proper intraday data.** Yahoo Finance's M1 limit of 7 days makes sub-hourly testing functionally impossible without paid data (Dukascopy, HistData).

3. **Test on multiple currency pairs.** A strategy that only works on EURUSD has likely fit that pair's specific volatility regime, not a real market inefficiency.

4. **Regime analysis first.** EURUSD 2020–2024 cycled through: low-vol range (2021), explosive trending (2022 rate hikes), mean-reverting chop (2023–2024). A strategy that works in one regime will fail in others. Identifying regimes before testing prevents the false hope of regime-specific backtests.
