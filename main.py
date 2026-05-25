import logging
import sys

from src.api.capital_client import CapitalClient, CapitalAPIError
from src.bot.trader import Trader

from config import settings as _settings_for_log
from config import settings
_log_file = f"logs/bot_{_settings_for_log.TRADE_EPIC}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def main() -> None:
    if not all([settings.CAPITAL_API_KEY, settings.CAPITAL_EMAIL, settings.CAPITAL_PASSWORD]):
        logger.error("Missing credentials. Copy .env.example → .env and fill in your details.")
        sys.exit(1)

    client = CapitalClient(
        base_url=settings.BASE_URL,
        api_key=settings.CAPITAL_API_KEY,
        email=settings.CAPITAL_EMAIL,
        password=settings.CAPITAL_PASSWORD,
    )

    try:
        client.create_session()
    except CapitalAPIError as exc:
        logger.error("Authentication failed: %s", exc)
        sys.exit(1)

    trader = Trader(
        client=client,
        epic=settings.TRADE_EPIC,
        trade_size=settings.TRADE_SIZE,
        short_period=settings.SHORT_MA_PERIOD,
        long_period=settings.LONG_MA_PERIOD,
        resolution=settings.PRICE_RESOLUTION,
        stop_loss_pips=settings.STOP_LOSS_PIPS,
        take_profit_pips=settings.TAKE_PROFIT_PIPS,
        profit_target=settings.PROFIT_TARGET,
        max_loss=settings.MAX_LOSS,
        rsi_period=settings.RSI_PERIOD,
        rsi_overbought=settings.RSI_OVERBOUGHT,
        rsi_oversold=settings.RSI_OVERSOLD,
        trailing_stop_pips=settings.TRAILING_STOP_PIPS,
    )

    try:
        trader.run(interval_seconds=60)
    finally:
        client.close_session()


if __name__ == "__main__":
    main()
