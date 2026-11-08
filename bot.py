"""Telegram-бот Dota Random.

Запускается через main.py (вместе с локальным движком) либо отдельно:
    python bot.py
"""

from __future__ import annotations

import logging
from urllib.parse import quote

from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, WebAppInfo
from aiogram.utils import executor

import server
import settings

log = logging.getLogger("dotarandom.bot")


def webapp_url() -> str | None:
    """Ссылка на страницу мини-приложения + адрес локального API."""
    page = settings.PAGES_URL.strip() or settings.PUBLIC_API_URL.strip()
    if not page:
        return None
    if not page.endswith("/"):
        page += "/"
    api = (settings.PUBLIC_API_URL or settings.LOCAL_API_URL).rstrip("/")
    separator = "&" if "?" in page else "?"
    return f"{page}{separator}api={quote(api, safe='')}"


def main_keyboard() -> InlineKeyboardMarkup | None:
    url = webapp_url()
    if not url:
        return None
    return (
        InlineKeyboardMarkup()
        .add(InlineKeyboardButton(text="🎰 Открыть рулетку", web_app=WebAppInfo(url=url)))
        .add(InlineKeyboardButton(text="🎲 Случайный герой", callback_data="roll"))
    )


def help_text() -> str:
    return (
        "<b>Dota Random</b>\n"
        "<i>Рулетка всех героев Dota 2</i>\n\n"
        "Мини-приложение открывается кнопкой ниже. Движок, случайный выбор "
        "и история спинов работают на вашем компьютере.\n\n"
        "/app — открыть рулетку\n"
        "/spin — случайный герой прямо в чате\n"
        "/stats — статистика\n"
        "/help — эта справка"
    )


def build_dispatcher(bot: Bot) -> Dispatcher:
    dp = Dispatcher(bot)

    @dp.message_handler(commands=["start", "app"])
    async def cmd_start(message: types.Message):
        keyboard = main_keyboard()
        if message.chat.type != "private":
            await message.answer(
                help_text() + "\n\nМини-приложение доступно в личном чате с ботом."
            )
            return
        if keyboard:
            await message.answer(help_text(), reply_markup=keyboard)
        else:
            await message.answer(
                help_text()
                + "\n\n⚠️ В <code>.env</code> не задан <code>PAGES_URL</code> — "
                "кнопка мини-приложения скрыта."
            )

    @dp.message_handler(commands=["help"])
    async def cmd_help(message: types.Message):
        await message.answer(help_text())

    @dp.message_handler(commands=["stats"])
    async def cmd_stats(message: types.Message):
        data = server.stats()
        await message.answer(
            "<b>Статистика</b>\n"
            f"Спинов: <b>{data['total_spins']}</b>\n"
            f"Уникальных героев: <b>{data['unique_heroes']}</b> из {data['heroes_total']}"
        )

    async def send_roll(chat: types.Message, user: types.User):
        if not server.HEROES:
            await chat.answer("Список героев не собран. Запустите build_site.py.")
            return
        hero = server.random_hero()
        spin_id, _ = server.record_spin(
            hero["slug"],
            user_id=str(user.id),
            username=user.username or user.first_name,
            source="bot",
        )
        caption = f"🎰 <b>{hero['name']}</b>\nспин #{spin_id}"
        portrait = settings.PORTRAIT_DIR / f"{hero['slug']}.png"
        if portrait.is_file():
            await chat.answer_photo(
                InputFile(portrait, filename=portrait.name), caption=caption
            )
        else:
            await chat.answer(caption)

    @dp.message_handler(commands=["spin", "roll"])
    async def cmd_spin(message: types.Message):
        await send_roll(message, message.from_user)

    @dp.callback_query_handler(lambda call: call.data == "roll")
    async def cb_roll(call: types.CallbackQuery):
        await call.answer("Крутим…")
        if call.message:
            await send_roll(call.message, call.from_user)

    return dp


def run_bot() -> None:
    if not settings.BOT_TOKEN:
        raise SystemExit(
            "BOT_TOKEN не задан. Укажите токен в .env — его выдаёт @BotFather."
        )

    bot = Bot(token=settings.BOT_TOKEN, parse_mode="HTML")
    dp = build_dispatcher(bot)

    async def on_startup():
        try:
            me = await bot.get_me()
            log.info("Бот запущен: @%s", me.username)
        except Exception as exc:  # noqa: BLE001
            log.error("Не удалось подключиться к Telegram: %s", exc)
            raise
        log.info("Локальный движок: %s", settings.LOCAL_API_URL)
        url = webapp_url()
        if url:
            log.info("Мини-приложение: %s", url)
        else:
            log.warning(
                "PAGES_URL не задан — мини-приложение недоступно. "
                "Укажите адрес GitHub Pages в .env."
            )

    log.info("Запуск long polling…")
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s"
    )
    server.start_background_server()
    run_bot()
