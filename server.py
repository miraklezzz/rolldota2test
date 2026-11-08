"""Локальный движок рулетки.

Flask-приложение:
  GET  /api/health   — состояние движка
  GET  /api/heroes   — список героев (тот же, что на сайте)
  POST /api/spin     — серверный выбор героя + запись в SQLite
  GET  /api/history  — последние спины
  GET  /             — статическая страница (локальный режим)

Запуск отдельно:  python server.py
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import random
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl

import requests
from flask import Flask, jsonify, request, send_from_directory

import settings

log = logging.getLogger("dotarandom")

VERSION = "1.0.0"
SCHEMA = """
CREATE TABLE IF NOT EXISTS spins (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT,
    username   TEXT,
    hero_slug  TEXT NOT NULL,
    source     TEXT NOT NULL DEFAULT 'web',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_spins_created ON spins (created_at DESC);
"""

_rng = random.SystemRandom()
_cooldowns: dict[str, float] = {}
_cooldown_lock = threading.Lock()


def load_heroes() -> list[dict]:
    manifest = settings.SITE_DIR / "heroes.json"
    if not manifest.is_file():
        log.warning("heroes.json не найден, выполните: python build_site.py")
        return []
    data = json.loads(manifest.read_text(encoding="utf-8"))
    return data.get("heroes", [])


HEROES: list[dict] = load_heroes()
HERO_BY_SLUG: dict[str, dict] = {h["slug"]: h for h in HEROES}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def total_spins() -> int:
    with connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM spins").fetchone()
    return int(row["c"]) if row else 0


def record_spin(
    hero_slug: str,
    *,
    user_id: str | None = None,
    username: str | None = None,
    source: str = "web",
) -> tuple[int, str]:
    created_at = utc_now()
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO spins (user_id, username, hero_slug, source, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (user_id, username, hero_slug, source, created_at),
        )
        spin_id = int(cur.lastrowid)
    return spin_id, created_at


def random_hero() -> dict:
    return _rng.choice(HEROES)


def recent_spins(limit: int = 10) -> tuple[list[dict], int]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, user_id, username, hero_slug, source, created_at"
            " FROM spins ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) AS c FROM spins").fetchone()["c"]
    items = []
    for row in rows:
        hero = HERO_BY_SLUG.get(row["hero_slug"], {
            "slug": row["hero_slug"],
            "name": row["hero_slug"].replace("_", " ").title(),
            "img": f"heroes/{row['hero_slug']}.png",
        })
        items.append(
            {
                "id": row["id"],
                "hero": hero,
                "source": row["source"],
                "username": row["username"],
                "created_at": row["created_at"],
            }
        )
    return items, int(total)


def stats() -> dict:
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total, COUNT(DISTINCT hero_slug) AS uniq FROM spins"
        ).fetchone()
    return {"total_spins": int(row["total"]), "unique_heroes": int(row["uniq"]),
            "heroes_total": len(HEROES)}


def verify_init_data(init_data: str, max_age: int = 86400) -> dict | None:
    """Проверка подписи Telegram WebApp initData (HMAC-SHA256)."""
    if not init_data or not settings.BOT_TOKEN:
        return None
    try:
        pairs = dict(parse_qsl(init_data, strict_parsing=True))
        received_hash = pairs.pop("hash", None)
        if not received_hash:
            return None
        check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
        secret = hmac.new(
            b"WebAppData", settings.BOT_TOKEN.encode("utf-8"), hashlib.sha256
        ).digest()
        calculated = hmac.new(
            secret, check_string.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(calculated, received_hash):
            return None
        auth_date = int(pairs.get("auth_date", "0") or 0)
        if max_age and (time.time() - auth_date) > max_age:
            return None
        return json.loads(pairs.get("user") or "{}")
    except Exception:  # noqa: BLE001 — некорректный initData не должен ломать запрос
        return None


def _notify_telegram(user: dict, hero: dict, spin_id: int) -> None:
    """Отправляет результат в чат. Только для подписанного initData."""
    if not settings.BOT_TOKEN or not settings.NOTIFY_ON_SPIN:
        return
    chat_id = user.get("id") if user else None
    if not chat_id:
        return
    portrait = settings.PORTRAIT_DIR / f"{hero['slug']}.png"
    caption = f"🎰 <b>{hero['name']}</b>\nспин #{spin_id}"
    try:
        if portrait.is_file():
            with portrait.open("rb") as file:
                requests.post(
                    f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendPhoto",
                    data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
                    files={"photo": (portrait.name, file, "image/png")},
                    timeout=10,
                )
        else:
            requests.post(
                f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage",
                data={"chat_id": chat_id, "text": caption, "parse_mode": "HTML"},
                timeout=10,
            )
    except Exception as exc:  # noqa: BLE001 — уведомление не должно ломать спин
        log.warning("Не удалось отправить результат в Telegram: %s", exc)


def _cooldown_left(key: str) -> float:
    with _cooldown_lock:
        until = _cooldowns.get(key, 0.0)
    return max(0.0, until - time.monotonic())


def _set_cooldown(key: str) -> None:
    with _cooldown_lock:
        _cooldowns[key] = time.monotonic() + settings.COOLDOWN_SECONDS
        # небольшая уборка старых записей
        if len(_cooldowns) > 2000:
            now = time.monotonic()
            for k, until in list(_cooldowns.items()):
                if until < now:
                    _cooldowns.pop(k, None)


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)
    init_db()

    @app.after_request
    def cors(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Private-Network"] = "true"
        response.headers["Access-Control-Max-Age"] = "86400"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = response.headers.get(
            "Cache-Control", "no-store" if request.path.startswith("/api/") else "no-cache"
        )
        return response

    @app.get("/api/health")
    def health():
        return jsonify(
            {
                "ok": True,
                "version": VERSION,
                "heroes_total": len(HEROES),
                "total_spins": total_spins(),
                "cooldown_seconds": settings.COOLDOWN_SECONDS,
            }
        )

    @app.get("/api/heroes")
    def heroes():
        return jsonify({"total": len(HEROES), "heroes": HEROES})

    @app.post("/api/spin")
    def spin():
        body = request.get_json(silent=True) or {}
        init_data = str(body.get("initData") or "")
        verified_user = verify_init_data(init_data)

        if settings.STRICT_INITDATA and settings.BOT_TOKEN and not verified_user:
            return jsonify({"error": "invalid_init_data"}), 401

        client_user = body.get("user") if isinstance(body.get("user"), dict) else None
        user = verified_user or client_user or {}
        user_id = str(user.get("id") or "").strip() or None
        username = (user.get("username") or user.get("first_name") or "")[:64] or None

        key = f"u:{user_id}" if user_id else f"ip:{request.remote_addr}"
        left = _cooldown_left(key)
        if left > 0:
            return jsonify({"error": "cooldown", "retry_after": round(left, 2)}), 429

        if not HEROES:
            return jsonify({"error": "heroes_not_built"}), 503

        hero = random_hero()
        index = HEROES.index(hero)
        spin_id, created_at = record_spin(
            hero["slug"], user_id=user_id, username=username, source="web"
        )
        _set_cooldown(key)

        if verified_user:
            threading.Thread(
                target=_notify_telegram,
                args=(verified_user, hero, spin_id),
                daemon=True,
            ).start()

        return jsonify(
            {
                "spin_id": spin_id,
                "index": index,
                "hero": hero,
                "heroes_total": len(HEROES),
                "total_spins": total_spins(),
                "cooldown_seconds": settings.COOLDOWN_SECONDS,
                "created_at": created_at,
                "source": "engine",
            }
        )

    @app.get("/api/history")
    def history():
        try:
            limit = int(request.args.get("limit", 10))
        except ValueError:
            limit = 10
        limit = max(1, min(limit, 30))
        items, total = recent_spins(limit)
        return jsonify({"items": items, "total_spins": total})

    @app.errorhandler(404)
    def not_found(_error):
        if request.path.startswith("/api/"):
            return jsonify({"error": "not_found"}), 404
        if Path(request.path).suffix:
            return jsonify({"error": "not_found"}), 404
        return send_from_directory(settings.SITE_DIR, "index.html"), 200

    @app.get("/")
    def index():
        return send_from_directory(settings.SITE_DIR, "index.html")

    @app.get("/<path:path>")
    def static_files(path: str):
        target = (settings.SITE_DIR / path).resolve()
        try:
            target.relative_to(settings.SITE_DIR.resolve())
        except ValueError:
            return jsonify({"error": "forbidden"}), 403
        if not target.is_file():
            return jsonify({"error": "not_found"}), 404
        response = send_from_directory(settings.SITE_DIR, path)
        if path.startswith("heroes/"):
            response.headers["Cache-Control"] = "public, max-age=86400"
        return response

    return app


app = create_app()


def main() -> None:
    log.info("Локальный движок: http://%s:%s", settings.HOST, settings.PORT)
    log.info("Героев в рулетке: %s", len(HEROES))
    app.run(
        host=settings.HOST,
        port=settings.PORT,
        threaded=True,
        debug=False,
        use_reloader=False,
    )


_background_thread: threading.Thread | None = None


def start_background_server() -> threading.Thread:
    """Поднимает Flask в фоновом потоке (для запуска вместе с ботом)."""
    global _background_thread
    if _background_thread and _background_thread.is_alive():
        return _background_thread
    _background_thread = threading.Thread(
        target=main, name="roulette-engine", daemon=True
    )
    _background_thread.start()
    return _background_thread


if __name__ == "__main__":
    main()
