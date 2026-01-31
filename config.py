import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///hrzn.db")

    # Couleurs
    COLOR_PRIMARY = 0x5865F2
    COLOR_SUCCESS = 0x57F287
    COLOR_ERROR = 0xED4245
    COLOR_WARNING = 0xFEE75C

    # Délais par défaut
    DEFAULT_REMINDER_MINUTES = [30, 10, 5]

    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN non définie dans le .env")
