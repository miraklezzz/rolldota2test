"""Настройки проекта. Значения читаются из .env (без внешних зависимостей)."""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SITE_DIR = BASE_DIR / "site"
DATA_DIR = BASE_DIR / "data"
PORTRAIT_DIR = BASE_DIR / "hero_portrait"
DB_PATH = DATA_DIR / "roulette.db"


def load_dotenv(path: Path | None = None) -> None:
    """Минимальная загрузка .env: KEY=VALUE, комментарии через #."""
    env_path = path or (BASE_DIR / ".env")
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


load_dotenv()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()
# Адрес страницы на GitHub Pages, например:
# https://username.github.io/dotarandom_bot/
PAGES_URL: str = os.getenv("PAGES_URL", "").strip()
# Публичный HTTPS-адрес локального API (например, cloudflared-туннель).
# Нужен, если открывать мини-приложение с телефона.
PUBLIC_API_URL: str = os.getenv("PUBLIC_API_URL", "").strip()

HOST: str = os.getenv("HOST", "127.0.0.1").strip() or "127.0.0.1"
PORT: int = _env_int("PORT", 8765)
COOLDOWN_SECONDS: int = max(0, _env_int("COOLDOWN_SECONDS", 3))
NOTIFY_ON_SPIN: bool = _env_bool("NOTIFY_ON_SPIN", True)
STRICT_INITDATA: bool = _env_bool("STRICT_INITDATA", False)

LOCAL_API_URL: str = f"http://{HOST}:{PORT}"
