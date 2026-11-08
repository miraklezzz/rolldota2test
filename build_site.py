"""Сборка статической части мини-приложения.

Копирует портреты из hero_portrait/ в site/heroes/ и генерирует
site/heroes.json — единый источник данных для сайта и сервера.

Запуск:  python build_site.py
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SOURCE_DIR = BASE_DIR / "hero_portrait"
SITE_DIR = BASE_DIR / "site"
TARGET_DIR = SITE_DIR / "heroes"

# slug (имя файла без .png) -> отображаемое имя
HERO_NAMES: dict[str, str] = {
    "abaddon": "Abaddon",
    "abyssal_underlord": "Underlord",
    "alchemist": "Alchemist",
    "ancient_apparition": "Ancient Apparition",
    "antimage": "Anti-Mage",
    "arc_warden": "Arc Warden",
    "axe": "Axe",
    "bane": "Bane",
    "batrider": "Batrider",
    "beastmaster": "Beastmaster",
    "bloodseeker": "Bloodseeker",
    "bounty_hunter": "Bounty Hunter",
    "brewmaster": "Brewmaster",
    "bristleback": "Bristleback",
    "broodmother": "Broodmother",
    "centaur": "Centaur Warrunner",
    "chaos_knight": "Chaos Knight",
    "chen": "Chen",
    "clinkz": "Clinkz",
    "crystal_maiden": "Crystal Maiden",
    "dark_seer": "Dark Seer",
    "dark_willow": "Dark Willow",
    "dawnbreaker": "Dawnbreaker",
    "dazzle": "Dazzle",
    "death_prophet": "Death Prophet",
    "disruptor": "Disruptor",
    "doom_bringer": "Doom",
    "dragon_knight": "Dragon Knight",
    "drow_ranger": "Drow Ranger",
    "earthshaker": "Earthshaker",
    "earth_spirit": "Earth Spirit",
    "elder_titan": "Elder Titan",
    "ember_spirit": "Ember Spirit",
    "enchantress": "Enchantress",
    "enigma": "Enigma",
    "faceless_void": "Faceless Void",
    "furion": "Nature's Prophet",
    "grimstroke": "Grimstroke",
    "gyrocopter": "Gyrocopter",
    "hoodwink": "Hoodwink",
    "huskar": "Huskar",
    "invoker": "Invoker",
    "jakiro": "Jakiro",
    "juggernaut": "Juggernaut",
    "keeper_of_the_light": "Keeper of the Light",
    "kez": "Kez",
    "kunkka": "Kunkka",
    "largo": "Largo",
    "legion_commander": "Legion Commander",
    "leshrac": "Leshrac",
    "lich": "Lich",
    "life_stealer": "Lifestealer",
    "lina": "Lina",
    "lion": "Lion",
    "lone_druid": "Lone Druid",
    "luna": "Luna",
    "lycan": "Lycan",
    "magnataur": "Magnus",
    "marci": "Marci",
    "mars": "Mars",
    "medusa": "Medusa",
    "meepo": "Meepo",
    "mirana": "Mirana",
    "monkey_king": "Monkey King",
    "morphling": "Morphling",
    "muerta": "Muerta",
    "naga_siren": "Naga Siren",
    "necrolyte": "Necrophos",
    "nevermore": "Shadow Fiend",
    "night_stalker": "Night Stalker",
    "nyx_assassin": "Nyx Assassin",
    "obsidian_destroyer": "Outworld Destroyer",
    "ogre_magi": "Ogre Magi",
    "omniknight": "Omniknight",
    "oracle": "Oracle",
    "pangolier": "Pangolier",
    "phantom_assassin": "Phantom Assassin",
    "phantom_lancer": "Phantom Lancer",
    "phoenix": "Phoenix",
    "primal_beast": "Primal Beast",
    "puck": "Puck",
    "pudge": "Pudge",
    "pugna": "Pugna",
    "queenofpain": "Queen of Pain",
    "rattletrap": "Clockwerk",
    "razor": "Razor",
    "riki": "Riki",
    "ringmaster": "Ringmaster",
    "rubick": "Rubick",
    "sand_king": "Sand King",
    "shadow_demon": "Shadow Demon",
    "shadow_shaman": "Shadow Shaman",
    "shredder": "Timbersaw",
    "silencer": "Silencer",
    "skeleton_king": "Wraith King",
    "skywrath_mage": "Skywrath Mage",
    "slardar": "Slardar",
    "slark": "Slark",
    "snapfire": "Snapfire",
    "sniper": "Sniper",
    "spectre": "Spectre",
    "spirit_breaker": "Spirit Breaker",
    "storm_spirit": "Storm Spirit",
    "sven": "Sven",
    "techies": "Techies",
    "templar_assassin": "Templar Assassin",
    "terrorblade": "Terrorblade",
    "tidehunter": "Tidehunter",
    "tinker": "Tinker",
    "tiny": "Tiny",
    "treant": "Treant Protector",
    "troll_warlord": "Troll Warlord",
    "tusk": "Tusk",
    "undying": "Undying",
    "ursa": "Ursa",
    "vengefulspirit": "Vengeful Spirit",
    "venomancer": "Venomancer",
    "viper": "Viper",
    "visage": "Visage",
    "void_spirit": "Void Spirit",
    "warlock": "Warlock",
    "weaver": "Weaver",
    "windrunner": "Windranger",
    "winter_wyvern": "Winter Wyvern",
    "wisp": "Io",
    "witch_doctor": "Witch Doctor",
    "zuus": "Zeus",
}


def main() -> int:
    if not SOURCE_DIR.is_dir():
        print(f"[!] Не найдена папка с портретами: {SOURCE_DIR}")
        return 1

    files = sorted(SOURCE_DIR.glob("*.png"))
    if not files:
        print(f"[!] В {SOURCE_DIR} нет PNG-файлов")
        return 1

    slugs = [f.stem for f in files]
    missing = [s for s in slugs if s not in HERO_NAMES]
    if missing:
        print("[!] Нет отображаемых имён для: " + ", ".join(missing))
        return 2

    TARGET_DIR.mkdir(parents=True, exist_ok=True)

    heroes = []
    for slug in sorted(slugs, key=lambda s: HERO_NAMES[s].lower()):
        source = SOURCE_DIR / f"{slug}.png"
        target = TARGET_DIR / f"{slug}.png"
        if not target.exists() or target.stat().st_size != source.stat().st_size:
            shutil.copy2(source, target)
        heroes.append(
            {
                "slug": slug,
                "name": HERO_NAMES[slug],
                "img": f"heroes/{slug}.png",
            }
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total": len(heroes),
        "heroes": heroes,
    }
    site_json = SITE_DIR / "heroes.json"
    site_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # GitHub Pages: отключаем Jekyll
    (SITE_DIR / ".nojekyll").write_text("", encoding="utf-8")

    print(f"[+] Героев: {len(heroes)}")
    print(f"[+] Данные: {site_json}")
    print(f"[+] Портреты: {TARGET_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
