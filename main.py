"""Единая точка запуска: локальный движок + Telegram-бот.

    python main.py              # движок + бот (long polling)
    python main.py --web-only   # только движок, страница локально
    python main.py --open       # открыть страницу в браузере при старте
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
import webbrowser

import settings

log = logging.getLogger("dotarandom")


def ensure_site() -> None:
    if (settings.SITE_DIR / "heroes.json").is_file():
        return
    log.info("Сборка статической части…")
    import build_site

    if build_site.main() != 0:
        raise SystemExit("Не удалось собрать site/. Проверьте hero_portrait/.")


def open_browser_later(url: str, delay: float = 1.2) -> None:
    threading.Timer(delay, lambda: webbrowser.open(url)).start()


def main() -> int:
    parser = argparse.ArgumentParser(description="Dota Random — рулетка героев Dota 2")
    parser.add_argument("--web-only", action="store_true", help="только локальный движок")
    parser.add_argument("--open", action="store_true", help="открыть страницу в браузере")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s"
    )

    ensure_site()

    import server  # после ensure_site: нужен heroes.json

    if not server.HEROES:
        log.error("Список героев пуст. Запустите: python build_site.py")
        return 1

    page_url = f"{settings.LOCAL_API_URL}/"
    log.info("Героев: %s", len(server.HEROES))
    log.info("Локальная страница: %s", page_url)
    log.info("API: %s/api/health", settings.LOCAL_API_URL)
    if settings.PAGES_URL:
        log.info("GitHub Pages: %s", settings.PAGES_URL)
    if settings.PUBLIC_API_URL:
        log.info("Публичный API: %s", settings.PUBLIC_API_URL)

    if args.open:
        open_browser_later(page_url)

    if args.web_only or not settings.BOT_TOKEN:
        if not settings.BOT_TOKEN:
            log.warning(
                "BOT_TOKEN не задан — запускаю только движок. "
                "Добавьте токен в .env, чтобы включить бота."
            )
        server.main()
        return 0

    server.start_background_server()
    import bot

    try:
        bot.run_bot()
    except (KeyboardInterrupt, SystemExit) as exc:
        log.info("Остановка: %s", exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
