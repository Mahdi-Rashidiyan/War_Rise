import os

from dotenv import load_dotenv


load_dotenv()


def required_env(name):
    value = os.getenv(name, "").strip()
    if not value or value.startswith("your_"):
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


TELEGRAM_MAINBOT_API = required_env("TELEGRAM_MAINBOT_API")
TELEGRAM_BOT_ADMIN_API = required_env("TELEGRAM_BOT_ADMIN_API")
TELEGRAM_BOT_INV_API = required_env("TELEGRAM_BOT_INV_API")
TELEGRAM_BOT_DIP_API = required_env("TELEGRAM_BOT_DIP_API")
TELEGRAM_BOT_SPY_API = required_env("TELEGRAM_BOT_SPY_API")
TELEGRAM_BOT_WAR_API = required_env("TELEGRAM_BOT_WAR_API")

ADMIN_IDS = frozenset(
    int(value.strip())
    for value in required_env("ADMIN_IDS").split(",")
    if value.strip()
)
CHANNEL_ID = os.getenv("CHANNEL_ID", "@war_rise_unitednations").strip()
NEWS_CHANNEL_ID = os.getenv("NEWS_CHANNEL_ID", "@war_rise_news").strip()