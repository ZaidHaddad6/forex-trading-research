import os
from dotenv import load_dotenv

load_dotenv()

CAPITAL_API_KEY = os.getenv("CAPITAL_API_KEY", "")
CAPITAL_EMAIL = os.getenv("CAPITAL_EMAIL", "")
CAPITAL_PASSWORD = os.getenv("CAPITAL_PASSWORD", "")
CAPITAL_ENV = os.getenv("CAPITAL_ENV", "demo")

TRADE_EPIC = os.getenv("TRADE_EPIC", "EURUSD")
TRADE_SIZE = float(os.getenv("TRADE_SIZE", "1"))
SHORT_MA_PERIOD = int(os.getenv("SHORT_MA_PERIOD", "9"))
LONG_MA_PERIOD = int(os.getenv("LONG_MA_PERIOD", "21"))
PRICE_RESOLUTION = os.getenv("PRICE_RESOLUTION", "MINUTE")
STOP_LOSS_PIPS = int(os.getenv("STOP_LOSS_PIPS", "20"))
TAKE_PROFIT_PIPS = int(os.getenv("TAKE_PROFIT_PIPS", "40"))
PROFIT_TARGET = float(os.getenv("PROFIT_TARGET", "150"))
MAX_LOSS = float(os.getenv("MAX_LOSS", "30"))
RSI_PERIOD = int(os.getenv("RSI_PERIOD", "7"))
RSI_OVERBOUGHT = float(os.getenv("RSI_OVERBOUGHT", "75"))
RSI_OVERSOLD = float(os.getenv("RSI_OVERSOLD", "25"))
TRAILING_STOP_PIPS = int(os.getenv("TRAILING_STOP_PIPS", "5"))

BASE_URLS = {
    "demo": "https://demo-api-capital.backend-capital.com/api/v1",
    "live": "https://api-capital.backend-capital.com/api/v1",
}

BASE_URL = BASE_URLS[CAPITAL_ENV]
