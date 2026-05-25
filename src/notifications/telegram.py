"""Telegram notifications for trade events."""
import logging
import os
import requests
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_PARSE_MODE = "Markdown"
_TIMEOUT = 10


def send_telegram(message: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": _PARSE_MODE},
            timeout=_TIMEOUT,
        )
        if not resp.ok:
            logger.warning("Telegram rejected message (HTTP %d): %s", resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.warning("Telegram send failed: %s", exc)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def log_trade_open(
    pair: str,
    direction: str,
    entry: float,
    sl: float | None,
    tp: float | None,
) -> None:
    arrow = "🟢 BUY" if direction == "BUY" else "🔴 SELL"
    sl_str = f"`{sl}`" if sl else "—"
    tp_str = f"`{tp}`" if tp else "—"
    send_telegram(
        f"🟡 *Trade Opened*\n"
        f"Pair: `{pair}` {arrow}\n"
        f"Entry: `{entry}`\n"
        f"SL: {sl_str}  |  TP: {tp_str}\n"
        f"🕐 {_utc_now()}"
    )


def log_trade_close(
    pair: str,
    direction: str,
    entry: float | None,
    close_price: float,
    pnl: float,
) -> None:
    emoji = "✅" if pnl >= 0 else "❌"
    result = "Profit" if pnl >= 0 else "Loss"
    arrow = "🟢 BUY" if direction == "BUY" else "🔴 SELL"
    entry_str = f"`{entry}`" if entry else "—"
    send_telegram(
        f"{emoji} *Trade Closed — {result}*\n"
        f"Pair: `{pair}` {arrow}\n"
        f"Entry: {entry_str}  →  Close: `{close_price}`\n"
        f"P&L: `{pnl:+.2f} USD`\n"
        f"🕐 {_utc_now()}"
    )


def log_trade_skipped(
    pair: str,
    direction: str,
    price: float,
    reason: str,
) -> None:
    arrow = "BUY ▲" if direction == "BUY" else "SELL ▼"
    send_telegram(
        f"⏭️ *Trade Skipped*\n"
        f"Pair: `{pair}` {arrow}\n"
        f"Price: `{price}`\n"
        f"Reason: _{reason}_\n"
        f"🕐 {_utc_now()}"
    )
