import json
import logging
import os
import time
from collections import deque
from datetime import datetime
from typing import Optional

from src.api.capital_client import CapitalClient, CapitalAPIError
from src.news.economic_calendar import get_blocks
from src.notifications.telegram import log_trade_close, log_trade_open, log_trade_skipped
from src.strategy.moving_average import Signal, compute_signal

logger = logging.getLogger(__name__)

SIGNAL_ICON = {Signal.BUY: "▲ BUY", Signal.SELL: "▼ SELL", Signal.HOLD: "— HOLD"}
DIR_ICON = {"BUY": "▲ LONG", "SELL": "▼ SHORT"}


class Trader:
    """Fetches live prices and executes MA crossover trades."""

    def __init__(
        self,
        client: CapitalClient,
        epic: str,
        trade_size: float,
        short_period: int,
        long_period: int,
        resolution: str = "MINUTE",
        stop_loss_pips: int = 20,
        take_profit_pips: int = 40,
        profit_target: float = 150.0,
        max_loss: float = 30.0,
        rsi_period: int = 7,
        rsi_overbought: float = 75.0,
        rsi_oversold: float = 25.0,
        trailing_stop_pips: int = 5,
    ):
        self.client = client
        self.epic = epic
        self.trade_size = trade_size
        self.short_period = short_period
        self.long_period = long_period
        self.resolution = resolution
        self.stop_loss_pips = stop_loss_pips
        self.take_profit_pips = take_profit_pips
        self.profit_target = profit_target
        self.max_loss = max_loss
        self.rsi_period = rsi_period
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold
        self.trailing_stop_pips = trailing_stop_pips
        self.trend_period = 200

        self._open_deal_id: Optional[str] = None
        self._open_direction: Optional[str] = None
        self._open_stop: Optional[float] = None
        self._open_tp: Optional[float] = None
        self._open_entry: Optional[float] = None
        self._prev_short_ma: Optional[float] = None
        self._prev_long_ma: Optional[float] = None
        self._signal_history: deque = deque(maxlen=8)
        self._tick_count: int = 0
        self._realized_pnl: float = 0.0
        self._last_trade_close_time: Optional[float] = None
        self._trade_cooldown_seconds: int = 300  # 5 min — prevents flip-flopping
        self._last_price: float = 0.0

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def tick(self) -> None:
        self._tick_count += 1
        prices = self._fetch_close_prices()
        if not prices:
            logger.warning("No price data returned for %s.", self.epic)
            return

        result = compute_signal(
            prices,
            self.short_period,
            self.long_period,
            self._prev_short_ma,
            self._prev_long_ma,
            rsi_period=self.rsi_period,
            rsi_overbought=self.rsi_overbought,
            rsi_oversold=self.rsi_oversold,
            trend_period=self.trend_period,
            epic=self.epic,
        )

        self._signal_history.append((datetime.now(), result.signal))
        self._prev_short_ma = result.short_ma
        self._prev_long_ma = result.long_ma
        self._last_price = result.price

        pnl = self._fetch_open_pnl()
        total_pnl = self._realized_pnl + (pnl or 0.0)
        self._print_status(result, pnl, total_pnl)

        tags = []
        if result.rsi_filtered:    tags.append("RSI")
        if result.trend_filtered:  tags.append("TREND")
        if result.macd_filtered:   tags.append("MACD")
        if result.session_filtered: tags.append("SESSION")
        if result.ranging_filtered: tags.append("RANGING")
        filter_tag = (" [" + "+".join(tags) + " BLOCKED]") if tags else ""

        if tags:
            intended = "BUY" if result.short_ma > result.long_ma else "SELL"
            log_trade_skipped(self.epic, intended, result.price, " + ".join(tags) + " filter blocked crossover")

        logger.info(
            "[%s] price=%.5f  MA%d=%.5f  MA%d=%.5f  MA%d=%.5f  RSI=%.1f  MACD_H=%+.5f  signal=%s%s  unrealized=%s  total_pnl=%+.2f",
            self.epic, result.price,
            self.short_period, result.short_ma,
            self.long_period, result.long_ma,
            self.trend_period, result.trend_ma,
            result.rsi, result.macd_histogram,
            result.signal.value, filter_tag,
            f"{pnl:+.2f}" if pnl is not None else "n/a",
            total_pnl,
        )

        if self._check_limits(total_pnl):
            return

        # Trailing stop — update SL to trail the long EMA on every tick
        if self._open_deal_id and result.long_ma > 0:
            self._update_trailing_stop(result.price, result.long_ma)

        # On first tick: enter immediately if a clear trend exists (session filter still applies)
        if self._tick_count == 1 and not self._open_deal_id:
            from src.strategy.moving_average import is_active_session
            if not is_active_session():
                logger.info("Startup: outside active session — waiting.")
                return
            above_trend = result.trend_ma == 0.0 or result.price > result.trend_ma
            below_trend = result.trend_ma == 0.0 or result.price < result.trend_ma
            if result.short_ma > result.long_ma and above_trend and result.macd_histogram > 0 and result.rsi > 50:
                logger.info("Startup: bullish alignment confirmed — entering BUY.")
                self._alert(Signal.BUY, result.price)
                self._handle_buy(result.price)
            elif result.short_ma < result.long_ma and below_trend and result.macd_histogram < 0 and result.rsi < 50:
                logger.info("Startup: bearish alignment confirmed — entering SELL.")
                self._alert(Signal.SELL, result.price)
                self._handle_sell(result.price)
            else:
                logger.info("Startup: filters not aligned — waiting for clean signal.")
            return

        if result.signal in (Signal.BUY, Signal.SELL):
            self._alert(result.signal, result.price)

        if result.signal == Signal.BUY:
            self._handle_buy(result.price)
        elif result.signal == Signal.SELL:
            self._handle_sell(result.price)

    # ------------------------------------------------------------------
    # Profit / loss limits
    # ------------------------------------------------------------------

    def _check_limits(self, total_pnl: float) -> bool:
        """Return True and shut down if a limit is hit."""
        if total_pnl >= self.profit_target:
            self._limit_alert(
                f"PROFIT TARGET HIT: +${total_pnl:.2f}",
                f"Profit target of ${self.profit_target:.0f} reached. Bot stopping.",
                "green",
            )
            self._shutdown()
            return True
        if total_pnl <= -self.max_loss:
            self._limit_alert(
                f"MAX LOSS HIT: -${abs(total_pnl):.2f}",
                f"Max loss of ${self.max_loss:.0f} reached. Bot stopping.",
                "red",
            )
            self._shutdown()
            return True
        return False

    def _limit_alert(self, headline: str, detail: str, color: str) -> None:
        code = "\033[92m" if color == "green" else "\033[91m"
        reset = "\033[0m"
        banner = f"""
{code}
╔══════════════════════════════════════════════╗
║                                              ║
║   *** {headline:<40} *** ║
║   {detail:<44}  ║
║                                              ║
╚══════════════════════════════════════════════╝
{reset}"""
        print(banner)
        logger.info("LIMIT ALERT — %s | %s", headline, detail)

    def _shutdown(self) -> None:
        if self._open_deal_id:
            logger.info("Closing open position before shutdown…")
            self._close_open_position()
        raise SystemExit(0)

    def run(self, interval_seconds: int = 60) -> None:
        import requests as _requests
        logger.info(
            "Bot started — epic=%s  short=%d  long=%d  interval=%ds  target=+$%.0f  maxloss=-$%.0f",
            self.epic, self.short_period, self.long_period, interval_seconds,
            self.profit_target, self.max_loss,
        )
        try:
            while True:
                try:
                    self.tick()
                except CapitalAPIError as exc:
                    if "invalid.session.token" in str(exc) or "401" in str(exc):
                        logger.warning("Session expired — re-authenticating…")
                        print("\n  [!] Session expired, re-authenticating…\n")
                        try:
                            self.client.create_session()
                            logger.info("Re-authentication successful.")
                        except CapitalAPIError as auth_exc:
                            logger.error("Re-authentication failed: %s", auth_exc)
                    else:
                        logger.warning("API error — will retry next tick: %s", exc)
                        print(f"\n  [!] API error, retrying in {interval_seconds}s…\n")
                except (_requests.exceptions.ConnectionError,
                        _requests.exceptions.Timeout,
                        _requests.exceptions.RequestException) as exc:
                    logger.warning("Network error — will retry next tick: %s", exc)
                    print(f"\n  [!] Connection error, retrying in {interval_seconds}s…\n")
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user.")
            if self._open_deal_id:
                logger.info("Closing open position before exit…")
                self._close_open_position()

    # ------------------------------------------------------------------
    # Status display
    # ------------------------------------------------------------------

    def _print_status(self, result, pnl: Optional[float], total_pnl: float) -> None:
        from src.strategy.moving_average import StrategyResult, is_active_session
        price, short_ma, long_ma = result.price, result.short_ma, result.long_ma
        signal, rsi, trend_ma = result.signal, result.rsi, result.trend_ma

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        w = 50

        ma_arrow = "▲" if short_ma > long_ma else "▼" if short_ma < long_ma else "="
        session_tag = "🟢 ACTIVE" if is_active_session() else "🔴 CLOSED"

        if trend_ma > 0:
            trend_dir = "▲ uptrend" if price > trend_ma else "▼ downtrend"
            trend_line = f"│  EMA{self.trend_period:<3}      {trend_ma:.5f}  {trend_dir}".ljust(w + 1) + "│"
        else:
            trend_line = f"│  EMA{self.trend_period:<3}      (building…)".ljust(w + 1) + "│"

        if self._open_deal_id and self._open_direction:
            pos_str = DIR_ICON[self._open_direction]
            pnl_str = f"  P&L: {pnl:+.2f}" if pnl is not None else ""
            sl_str = f"  SL:{self._open_stop}" if self._open_stop else ""
            tp_str = f"  TP:{self._open_tp}" if self._open_tp else ""
            position_line = f"{pos_str}{pnl_str}{sl_str}{tp_str}"
        else:
            position_line = "No open position"

        history_icons = " ".join(
            "▲" if s == Signal.BUY else "▼" if s == Signal.SELL else "·"
            for _, s in self._signal_history
        )

        filters = []
        if result.rsi_filtered:     filters.append("RSI")
        if result.trend_filtered:   filters.append("TREND")
        if result.macd_filtered:    filters.append("MACD")
        if result.session_filtered: filters.append("SESSION")
        if result.ranging_filtered: filters.append("RANGING")
        filter_note = ("  [" + "+".join(filters) + "]") if filters else ""

        macd_dir = "▲" if result.macd_histogram > 0 else "▼" if result.macd_histogram < 0 else "="
        pnl_color = "\033[92m" if total_pnl >= 0 else "\033[91m"
        reset = "\033[0m"
        total_pnl_str = f"{pnl_color}{total_pnl:+.2f}{reset}"
        limits_str = f"target +${self.profit_target:.0f}  limit -${self.max_loss:.0f}"

        lines = [
            "┌" + "─" * w + "┐",
            f"│  {self.epic} Bot — tick #{self._tick_count:<4}  {now}  {session_tag}  │",
            "├" + "─" * w + "┤",
            f"│  Price       {price:.5f}".ljust(w + 1) + "│",
            f"│  EMA{self.short_period:<2}        {short_ma:.5f}".ljust(w + 1) + "│",
            f"│  EMA{self.long_period:<2}        {long_ma:.5f}  {ma_arrow}".ljust(w + 1) + "│",
            trend_line,
            f"│  RSI({self.rsi_period})      {rsi:.1f}  {'⚠ overbought' if rsi >= self.rsi_overbought else '⚠ oversold' if rsi <= self.rsi_oversold else 'neutral'}".ljust(w + 1) + "│",
            f"│  MACD Hist   {result.macd_histogram:+.5f}  {macd_dir}".ljust(w + 1) + "│",
            "├" + "─" * w + "┤",
            f"│  Signal      {SIGNAL_ICON[signal]}{filter_note}".ljust(w + 1) + "│",
            f"│  Position    {position_line}".ljust(w + 1) + "│",
            f"│  Session P&L {total_pnl_str}   {limits_str}".ljust(w + 1 + len(pnl_color) + len(reset)) + "│",
            "├" + "─" * w + "┤",
            f"│  History     {history_icons}".ljust(w + 1) + "│",
            "└" + "─" * w + "┘",
        ]
        print("\n" + "\n".join(lines))

    # ------------------------------------------------------------------
    # Trailing stop
    # ------------------------------------------------------------------

    def _update_trailing_stop(self, price: float, long_ma: float) -> None:
        """Trail the stop loss behind the EMA21. Only moves in the profitable direction."""
        if not self._open_deal_id or not self._open_direction or not self._open_stop:
            return

        real_deal_id = self._lookup_real_deal_id()
        if real_deal_id is None:
            # Position was already closed by SL/TP
            self._open_deal_id = None
            self._open_direction = None
            self._open_stop = None
            self._open_tp = None
            self._open_entry = None
            return

        pip = 0.01 if "JPY" in self.epic else 0.0001
        buffer = self.trailing_stop_pips * pip

        if self._open_direction == "BUY":
            new_stop = round(long_ma - buffer, 5)
            # Only tighten — never widen the stop
            if new_stop > self._open_stop:
                try:
                    self.client.update_position_stop(real_deal_id, new_stop)
                    logger.info("Trailing stop moved UP to %.5f (EMA21=%.5f)", new_stop, long_ma)
                    self._open_stop = new_stop
                except CapitalAPIError as exc:
                    logger.warning("Could not update trailing stop: %s", exc)

        elif self._open_direction == "SELL":
            new_stop = round(long_ma + buffer, 5)
            # Only tighten — never widen the stop
            if new_stop < self._open_stop:
                try:
                    self.client.update_position_stop(real_deal_id, new_stop)
                    logger.info("Trailing stop moved DOWN to %.5f (EMA21=%.5f)", new_stop, long_ma)
                    self._open_stop = new_stop
                except CapitalAPIError as exc:
                    logger.warning("Could not update trailing stop: %s", exc)

    # ------------------------------------------------------------------
    # Alert
    # ------------------------------------------------------------------

    def _alert(self, signal: Signal, price: float) -> None:
        label = "BUY  ▲" if signal == Signal.BUY else "SELL ▼"
        color = "\033[92m" if signal == Signal.BUY else "\033[91m"
        reset = "\033[0m"
        banner = f"""
{color}
╔══════════════════════════════════════════════╗
║                                              ║
║   *** SIGNAL FIRED: {label} ***           ║
║   Instrument : {self.epic:<28}  ║
║   Price      : {price:<28.5f}  ║
║                                              ║
╚══════════════════════════════════════════════╝
{reset}"""
        print(banner)
        logger.info("ALERT — %s signal fired at %.5f", signal.value, price)

    # ------------------------------------------------------------------
    # Trade execution
    # ------------------------------------------------------------------

    def _in_cooldown(self) -> bool:
        if self._last_trade_close_time is None:
            return False
        elapsed = time.time() - self._last_trade_close_time
        if elapsed < self._trade_cooldown_seconds:
            logger.info("Cooldown active — %ds remaining before next trade.", int(self._trade_cooldown_seconds - elapsed))
            return True
        return False

    def _handle_buy(self, price: float) -> None:
        if self._open_direction == "BUY":
            return
        if self._in_cooldown():
            log_trade_skipped(self.epic, "BUY", price, "Cooldown — 5 min between trades")
            return
        blocks = get_blocks(self.epic)
        if blocks:
            logger.info("NEWS BLOCK — skipping BUY on %s: %s", self.epic, " | ".join(blocks))
            log_trade_skipped(self.epic, "BUY", price, "News blackout: " + " | ".join(blocks))
            return
        if self._open_deal_id:
            self._close_open_position()
        self._open_position("BUY", price)

    def _handle_sell(self, price: float) -> None:
        if self._open_direction == "SELL":
            return
        if self._in_cooldown():
            log_trade_skipped(self.epic, "SELL", price, "Cooldown — 5 min between trades")
            return
        blocks = get_blocks(self.epic)
        if blocks:
            logger.info("NEWS BLOCK — skipping SELL on %s: %s", self.epic, " | ".join(blocks))
            log_trade_skipped(self.epic, "SELL", price, "News blackout: " + " | ".join(blocks))
            return
        if self._open_deal_id:
            self._close_open_position()
        self._open_position("SELL", price)

    def _open_position(self, direction: str, price: Optional[float] = None) -> None:
        pip = 0.01 if "JPY" in self.epic else 0.0001
        stop_loss = take_profit = None
        if price and self.stop_loss_pips:
            if direction == "BUY":
                stop_loss = round(price - self.stop_loss_pips * pip, 5)
                take_profit = round(price + self.take_profit_pips * pip, 5)
            else:
                stop_loss = round(price + self.stop_loss_pips * pip, 5)
                take_profit = round(price - self.take_profit_pips * pip, 5)
        try:
            response = self.client.open_position(
                self.epic, direction, self.trade_size,
                stop_loss=stop_loss, take_profit=take_profit,
            )
            deal_id = response.get("dealId") or response.get("dealReference")
            self._open_deal_id = deal_id
            self._open_direction = direction
            self._open_stop = stop_loss
            self._open_tp = take_profit
            self._open_entry = price
            logger.info(
                "Opened %s @ %.5f — SL: %s  TP: %s  dealId: %s",
                direction, price or 0, stop_loss, take_profit, deal_id,
            )
            log_trade_open(self.epic, direction, price or 0, stop_loss, take_profit)
        except CapitalAPIError as exc:
            logger.error("Failed to open %s position: %s", direction, exc)

    def _close_open_position(self) -> None:
        if not self._open_deal_id:
            return
        real_deal_id = self._lookup_real_deal_id()
        direction = self._open_direction
        if real_deal_id is None:
            # Already closed by SL/TP — just clear local state
            logger.info("Position for %s not found in open positions — already closed by SL/TP.", self.epic)
            self._open_deal_id = None
            self._open_direction = None
            self._open_stop = None
            self._open_tp = None
            return
        last_pnl = self._fetch_open_pnl() or 0.0
        try:
            self.client.close_position(real_deal_id)
            self._realized_pnl += last_pnl
            self._last_trade_close_time = time.time()
            logger.info("Closed position %s — realized: %+.2f  total: %+.2f",
                        real_deal_id, last_pnl, self._realized_pnl)
            log_trade_close(self.epic, direction or "", self._open_entry, self._last_price, last_pnl)
            self._write_trade_log(direction, last_pnl)
        except CapitalAPIError as exc:
            logger.error("Failed to close position %s: %s", real_deal_id, exc)
        finally:
            self._open_deal_id = None
            self._open_direction = None
            self._open_stop = None
            self._open_tp = None
            self._open_entry = None

    def _write_trade_log(self, direction: Optional[str], pnl: float) -> None:
        log_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "../../logs/trades.json"))
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        try:
            trades = []
            if os.path.exists(log_path):
                with open(log_path) as f:
                    trades = json.load(f)
        except (json.JSONDecodeError, OSError):
            trades = []
        trades.append({
            "id": int(datetime.now().timestamp() * 1000),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "time": datetime.now().strftime("%H:%M:%S"),
            "pair": self.epic,
            "side": "Long" if direction == "BUY" else "Short",
            "pnl": round(pnl, 2),
        })
        with open(log_path, "w") as f:
            json.dump(trades, f, indent=2)

    def _lookup_real_deal_id(self) -> Optional[str]:
        try:
            data = self.client.get_positions()
            for pos in data.get("positions", []):
                if pos.get("market", {}).get("epic") == self.epic:
                    return pos["position"]["dealId"]
        except CapitalAPIError:
            pass
        return None

    # ------------------------------------------------------------------
    # Data fetching
    # ------------------------------------------------------------------

    def _fetch_close_prices(self) -> list[float]:
        needed = max(self.trend_period + 5, self.long_period + 5)
        try:
            data = self.client.get_prices(self.epic, self.resolution, max_bars=needed)
            candles = data.get("prices", [])
            return [
                float(c["closePrice"]["bid"])
                for c in candles
                if c.get("closePrice") and c["closePrice"].get("bid") is not None
            ]
        except CapitalAPIError as exc:
            if "invalid.session.token" in str(exc):
                raise  # let run() handle re-auth
            logger.error("Price fetch failed: %s", exc)
            return []

    def _fetch_open_pnl(self) -> Optional[float]:
        if not self._open_deal_id:
            return None
        try:
            data = self.client.get_positions()
            for pos in data.get("positions", []):
                if pos.get("market", {}).get("epic") == self.epic:
                    return float(pos["position"].get("upl", 0))
        except CapitalAPIError:
            pass
        return None
