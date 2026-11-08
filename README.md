# Dota Random

Рулетка-карусель со всеми героями Dota 2 в виде Telegram Mini App.
Страница лежит на GitHub Pages (HTTPS, бесплатно), а **все процессы** —
бот, случайный выбор, кулдаун, история спинов — работают на вашем компьютере.

```
Telegram  ──►  mini app (GitHub Pages: HTML/CSS/JS)
                    │  POST /api/spin  (127 портретов крутит карусель)
                    ▼
              Flask :8765 на вашем ПК  ──►  SQLite (data/roulette.db)
                    ▲
                    │ long polling
              aiogram-бот (@BotFather)
```

- Серверный `SystemRandom` — результат нельзя «подкрутить» в браузере.
- Портреты берутся из `hero_portrait/` и копируются в `site/heroes/`.
- Если движок выключен, кнопка всё равно работает в **демо-режиме**
  (честно помечен в интерфейсе), чтобы страница на Pages не была мёртвой.

## Быстрый старт

```powershell
# 1. зависимости (уже установлены в этой среде)
pip install -r requirements.txt

# 2. заполните .env
#    BOT_TOKEN=...   (от @BotFather)
#    PAGES_URL=https://<username>.github.io/dotarandom_bot/

# 3. соберите статику (127 героев)
python build_site.py

# 4. запуск: движок + бот
python main.py
```

Проверка только страницы, без Telegram:

```powershell
python main.py --web-only --open
```

Откроется `http://127.0.0.1:8765/` — кнопка «Крутить», история и статус движка
работают локально.

## Публикация страницы на GitHub Pages

1. Создайте репозиторий на GitHub (например `dotarandom_bot`).
2. Из папки проекта:

   ```powershell
   git init
   git add .
   git commit -m "Dota Random mini app"
   git branch -M main
   git remote add origin https://github.com/<username>/dotarandom_bot.git
   git push -u origin main
   ```

3. В репозитории: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
   Workflow `.github/workflows/pages.yml` опубликует папку `site/`.
4. Через минуту страница будет доступна:
   `https://<username>.github.io/dotarandom_bot/`
5. Впишите этот адрес в `.env` → `PAGES_URL` (обязательно со слешем в конце)
   и перезапустите бота.

Кнопка «Открыть рулетку» в боте откроет Pages-страницу, добавив адрес
локального API: `?api=http://127.0.0.1:8765`.

## Важно про телефон и HTTPS

GitHub Pages — HTTPS. Браузеры Chromium (Telegram Desktop, Android) разрешают
запросы с HTTPS-страницы на `http://127.0.0.1` (localhost считается
доверенным). На **телефоне** `127.0.0.1` — это сам телефон, поэтому нужен
туннель до вашего ПК:

```powershell
cloudflared tunnel --url http://127.0.0.1:8765
```

Полученный `https://...trycloudflare.com` впишите в `.env` → `PUBLIC_API_URL`.
Бот сам подставит его в ссылку мини-приложения. Адрес бесплатного туннеля
меняется при перезапуске — просто перезапустите бота (страницу
пересобирать не нужно).

Если `PAGES_URL` не задан, но `PUBLIC_API_URL` есть, бот откроет страницу
прямо с туннеля: Flask отдаёт `site/` и API на одном адресе.

## API

| Метод | Адрес | Назначение |
|---|---|---|
| GET | `/api/health` | статус, число героев, всего спинов |
| GET | `/api/heroes` | список героев |
| POST | `/api/spin` | серверный выбор героя + запись в SQLite |
| GET | `/api/history?limit=10` | последние спины |

`POST /api/spin` принимает `initData` из Telegram WebApp. Если задан
`BOT_TOKEN`, подпись проверяется по HMAC-SHA256; результат спина
отправляется в чат (можно отключить: `NOTIFY_ON_SPIN=0`).

## Структура

```
hero_portrait/           исходные портреты (127 PNG)
site/                    статика для GitHub Pages
  index.html
  assets/styles.css      minimal dark UI: графит + золото
  assets/app.js          карусель, спин, история, демо-режим
  assets/config.js       адрес API по умолчанию
  heroes.json            генерируется build_site.py
  heroes/                копии портретов
build_site.py            сборка heroes.json + копирование картинок
settings.py              чтение .env
server.py                Flask API + SQLite + проверка initData
bot.py                   aiogram 2.x: /start, /spin, /stats, /help
main.py                  единая точка запуска
run.bat / run-web.bat    запуск на Windows
```

## Команды бота

- `/start` или `/app` — приветствие и кнопка мини-приложения
- `/spin` — случайный герой с портретом прямо в чате
- `/stats` — всего спинов и уникальных героев
- `/help` — справка

## Настройки `.env`

| Переменная | По умолчанию | Описание |
|---|---|---|
| `BOT_TOKEN` | — | токен от @BotFather |
| `PAGES_URL` | — | адрес GitHub Pages |
| `PUBLIC_API_URL` | — | публичный HTTPS-туннель к API |
| `HOST` / `PORT` | `127.0.0.1` / `8765` | локальный сервер |
| `COOLDOWN_SECONDS` | `3` | пауза между спинами |
| `NOTIFY_ON_SPIN` | `1` | дублировать результат в чат |
| `STRICT_INITDATA` | `0` | требовать валидную подпись Telegram |

## Если что-то не работает

- **Статус «демо-режим»** — движок выключен или страница не видит
  `127.0.0.1:8765`. Запустите `python main.py`, проверьте
  `http://127.0.0.1:8765/api/health`.
- **Кнопка WebApp не появилась** — не задан `PAGES_URL`, либо чат не личный.
- **Порт занят** — измените `PORT` в `.env` (тогда обновите и `?api=`:
  бот подставит новый автоматически).
- **Pages отдаёт 404** — проверьте, что workflow завершился, а Source
  в настройках Pages = GitHub Actions.
- **Телефон не крутит** — нужен `PUBLIC_API_URL` (туннель), см. выше.
- **Строгая проверка** — при `STRICT_INITDATA=1` спины из обычного браузера
  будут отклонены: открывайте только через Telegram.
