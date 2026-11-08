(() => {
  "use strict";

  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  if (tg) {
    try {
      tg.ready();
      tg.expand();
      tg.setHeaderColor?.("#08090a");
      tg.setBackgroundColor?.("#08090a");
      tg.disableVerticalSwipes?.();
    } catch (error) {
      /* Telegram WebApp может быть недоступен — работаем как обычный сайт */
    }
  }

  const CONFIG = window.DOTA_RANDOM_CONFIG || {};
  const API = resolveApi();
  const BLOCKS = 4;          // копии ленты для бесконечной карусели
  const MIN_DISTANCE = 0.55; // минимальный «пробег» в героях

  const state = {
    heroes: [],
    N: 0,
    cardW: 0,
    step: 0,
    pad: 0,
    trackX: 0,
    centerIndex: 0,
    spinning: false,
    online: false,
    total: 0,
    history: [],
    cooldownUntil: 0,
    activeEl: null,
    raf: 0,
    demoTipShown: false,
    inTelegram: Boolean(tg && tg.initData),
  };

  const els = {};
  const prefersReduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

  /* ── Утилиты ─────────────────────────────────────────────── */

  function resolveApi() {
    const fromQuery = new URLSearchParams(location.search).get("api");
    let saved = null;
    try {
      saved = localStorage.getItem("dotarandom.api");
    } catch (error) {
      saved = null;
    }
    const raw = (fromQuery || saved || CONFIG.api || "http://127.0.0.1:8765").trim();
    return raw.replace(/\/+$/, "");
  }

  function plural(n, one, few, many) {
    const mod100 = n % 100;
    if (mod100 >= 11 && mod100 <= 14) return many;
    switch (n % 10) {
      case 1: return one;
      case 2:
      case 3:
      case 4: return few;
      default: return many;
    }
  }

  async function request(url, options = {}, timeout = 6000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      return await fetch(url, { ...options, signal: controller.signal });
    } finally {
      clearTimeout(timer);
    }
  }

  async function getJson(url, timeout = 6000) {
    const response = await request(url, { cache: "no-cache" }, timeout);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  function formatTime(value) {
    const date = value ? new Date(value) : new Date();
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  }

  let toastTimer = 0;
  function toast(message) {
    if (!els.toast) return;
    els.toast.textContent = message;
    els.toast.classList.add("is-visible");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => els.toast.classList.remove("is-visible"), 2600);
  }

  function setStatus(kind, text) {
    if (!els.status) return;
    els.status.dataset.state = kind;
    els.statusText.textContent = text;
    els.status.title =
      kind === "online"
        ? "Локальный движок доступен"
        : "Движок на компьютере недоступен — спины идут в демо-режиме";
  }

  function setGreeting() {
    const user = tg && tg.initDataUnsafe ? tg.initDataUnsafe.user : null;
    if (user && user.first_name) {
      els.greeting.textContent = `привет, ${user.first_name} · рулетка героев`;
    }
  }

  /* ── Карусель ────────────────────────────────────────────── */

  function buildTrack() {
    const fragment = document.createDocumentFragment();
    for (let block = 0; block < BLOCKS; block += 1) {
      for (const hero of state.heroes) {
        const card = document.createElement("article");
        card.className = "card";
        card.dataset.slug = hero.slug;

        const frame = document.createElement("div");
        frame.className = "card__frame";

        const img = document.createElement("img");
        img.src = hero.img;
        img.alt = hero.name;
        img.draggable = false;
        img.decoding = "async";
        img.loading = "eager";
        img.width = 256;
        img.height = 144;

        const name = document.createElement("span");
        name.className = "card__name";
        name.textContent = hero.name;

        frame.appendChild(img);
        card.append(frame, name);
        fragment.appendChild(card);
      }
    }
    els.track.replaceChildren(fragment);
  }

  function measure() {
    const cards = els.track.children;
    if (!cards.length) return;
    const first = cards[0].getBoundingClientRect();
    const second = cards[1] ? cards[1].getBoundingClientRect() : null;
    state.cardW = first.width;
    state.step = second ? second.left - first.left : first.width + 14;
    state.pad = Math.max(0, (els.viewport.clientWidth - state.cardW) / 2);
    els.track.style.setProperty("--pad", `${state.pad}px`);
  }

  function centerFor(index) {
    return (
      els.viewport.clientWidth / 2 -
      state.pad -
      index * state.step -
      state.cardW / 2
    );
  }

  function applyPosition() {
    els.track.style.transform = `translate3d(${state.trackX}px, 0, 0)`;
  }

  function centerOn(index, { animate = false } = {}) {
    state.centerIndex = index;
    const target = centerFor(index);
    if (!animate || prefersReduced) {
      state.trackX = target;
      applyPosition();
      return;
    }
    const from = state.trackX;
    const start = performance.now();
    const duration = 450;
    const tick = (now) => {
      const p = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      state.trackX = from + (target - from) * eased;
      applyPosition();
      if (p < 1) state.raf = requestAnimationFrame(tick);
    };
    state.raf = requestAnimationFrame(tick);
  }

  function layout() {
    const active = state.centerIndex;
    measure();
    if (state.spinning) return;
    centerOn(Math.min(active, state.N * BLOCKS - 1));
  }

  function markActive(index) {
    if (state.activeEl) state.activeEl.classList.remove("is-active");
    const el = els.track.children[index];
    if (el) {
      el.classList.add("is-active");
      state.activeEl = el;
    }
  }

  function spinTo(index) {
    return new Promise((resolve) => {
      const N = state.N;
      const startIndex = state.centerIndex;

      let targetIndex = 2 * N + index;
      if (targetIndex - startIndex < N * MIN_DISTANCE) {
        targetIndex = 3 * N + index;
      }

      const jitter = (Math.random() * 0.3 - 0.15) * state.step;
      const targetX = centerFor(targetIndex) + jitter;
      const fromX = state.trackX;
      const distance = Math.abs(targetX - fromX);
      const duration = prefersReduced
        ? 900
        : Math.min(6600, 4400 + distance * 0.026 + Math.random() * 400);
      const started = performance.now();

      const easeOut = (t) => 1 - Math.pow(1 - t, 5);

      const tick = (now) => {
        const p = Math.min(1, (now - started) / duration);
        const eased = easeOut(p);
        state.trackX = fromX + (targetX - fromX) * eased;
        applyPosition();
        if (p < 1) {
          state.raf = requestAnimationFrame(tick);
        } else {
          const activeIndex = targetIndex - N;
          state.centerIndex = activeIndex;
          state.trackX = centerFor(activeIndex) + jitter;
          applyPosition();
          markActive(activeIndex);
          state.raf = 0;
          resolve();
        }
      };

      state.raf = requestAnimationFrame(tick);
    });
  }

  /* ── Спин ────────────────────────────────────────────────── */

  async function spin() {
    if (state.spinning || !state.N) return;

    const now = Date.now();
    if (now < state.cooldownUntil) {
      toast(`Пауза ${Math.ceil((state.cooldownUntil - now) / 1000)} с`);
      return;
    }

    state.spinning = true;
    els.spinBtn.disabled = true;
    els.spinBtn.classList.add("is-busy");
    els.spinBtn.querySelector(".btn__label").textContent = "Крутим…";

    let hero = null;
    let meta = null;
    let demo = false;

    try {
      const response = await request(
        `${API}/api/spin`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            initData: tg && tg.initData ? tg.initData : "",
            user: tg && tg.initDataUnsafe ? tg.initDataUnsafe.user : null,
          }),
        },
        8000
      );

      if (response.status === 429) {
        const data = await response.json().catch(() => ({}));
        const wait = Math.ceil(Number(data.retry_after) || 3);
        state.cooldownUntil = Date.now() + wait * 1000;
        throw Object.assign(new Error("cooldown"), { cooldown: wait });
      }

      if (response.status === 401) {
        throw Object.assign(new Error("auth"), { noFallback: true });
      }

      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const data = await response.json();
      const index = state.heroes.findIndex((item) => item.slug === data.hero.slug);
      if (index < 0) throw new Error("hero not found");

      hero = state.heroes[index];
      meta = data;
      state.online = true;
      state.total = Number(data.total_spins) || state.total + 1;
      state.cooldownUntil = Date.now() + (Number(data.cooldown_seconds) || 3) * 1000;
      setStatus("online", "движок онлайн");
    } catch (error) {
      if (error.cooldown) {
        toast(`Пауза ${error.cooldown} с`);
        finishSpin();
        return;
      }
      if (error.noFallback) {
        toast("Откройте рулетку через Telegram");
        finishSpin();
        return;
      }

      // Движок на компьютере недоступен — демо-режим, чтобы кнопка работала всегда.
      demo = true;
      state.online = false;
      state.total += 1;
      state.cooldownUntil = Date.now() + 1500;
      setStatus("offline", "демо-режим");
      hero = state.heroes[Math.floor(Math.random() * state.N)];
      meta = {
        spin_id: state.total,
        total_spins: state.total,
        created_at: new Date().toISOString(),
      };
      if (!state.demoTipShown) {
        state.demoTipShown = true;
        toast("Движок недоступен — демо-режим");
      }
    }

    const index = state.heroes.indexOf(hero);
    await spinTo(index);
    showResult(hero, meta, demo);

    if (demo) {
      state.history.unshift({
        id: meta.spin_id,
        hero,
        created_at: meta.created_at,
        source: "demo",
      });
      state.history = state.history.slice(0, 10);
      renderHistory();
    } else {
      loadHistory();
    }
    updateCounters();

    try {
      tg?.HapticFeedback?.notificationOccurred("success");
    } catch (error) {
      /* без вибрации */
    }

    finishSpin();
  }

  function finishSpin() {
    state.spinning = false;
    els.spinBtn.disabled = false;
    els.spinBtn.classList.remove("is-busy");
    els.spinBtn.querySelector(".btn__label").textContent = "Крутить";
  }

  function showResult(hero, meta, demo) {
    els.resultName.textContent = hero.name;
    const number = meta && (meta.spin_id ?? meta.total_spins);
    const stamp = formatTime(meta && meta.created_at);
    els.resultMeta.textContent = `${demo ? "демо-режим · " : ""}спин #${number ?? "—"} · ${stamp}`;

    els.verdict.classList.remove("is-revealing");
    void els.verdict.offsetWidth;
    els.verdict.classList.add("is-revealing");
  }

  /* ── История ─────────────────────────────────────────────── */

  async function loadHistory() {
    if (!state.online) {
      renderHistory();
      return;
    }
    try {
      const data = await getJson(`${API}/api/history?limit=10`, 4500);
      state.history = Array.isArray(data.items) ? data.items : [];
      state.total = Number(data.total_spins) || state.total;
      renderHistory();
      updateCounters();
    } catch (error) {
      renderHistory();
    }
  }

  function renderHistory() {
    const list = els.historyList;
    list.replaceChildren();
    if (!state.history.length) {
      const empty = document.createElement("p");
      empty.className = "chip__name";
      empty.style.width = "auto";
      empty.textContent = "пока пусто";
      list.appendChild(empty);
      return;
    }
    for (const item of state.history.slice(0, 10)) {
      const chip = document.createElement("div");
      chip.className = "chip";

      const frame = document.createElement("div");
      frame.className = "chip__img";

      const img = document.createElement("img");
      img.src = item.hero.img;
      img.alt = item.hero.name;
      img.loading = "lazy";
      frame.appendChild(img);

      const name = document.createElement("p");
      name.className = "chip__name";
      name.textContent = item.hero.name;

      chip.append(frame, name);
      list.appendChild(chip);
    }
  }

  function updateCounters() {
    els.historyCount.textContent = String(state.total);
    els.totalSpins.textContent = `${state.total} всего`;
  }

  function toggleHistory() {
    const isHidden = els.history.hidden;
    els.history.hidden = !isHidden;
    els.historyBtn.setAttribute("aria-expanded", String(isHidden));
    if (isHidden) {
      els.history.scrollIntoView({ behavior: "smooth", block: "nearest" });
      loadHistory();
    }
  }

  /* ── Движок ──────────────────────────────────────────────── */

  async function ping({ silent = true } = {}) {
    try {
      const data = await getJson(`${API}/api/health`, 3000);
      state.online = true;
      state.total = Number(data.total_spins) || 0;
      setStatus("online", "движок онлайн");
      if (data.heroes_total) {
        els.heroCount.textContent = `${data.heroes_total} ${plural(
          data.heroes_total, "герой", "героя", "героев"
        )}`;
      }
      updateCounters();
      return true;
    } catch (error) {
      state.online = false;
      setStatus("offline", "демо-режим");
      if (!silent) toast("Локальный движок недоступен");
      return false;
    }
  }

  /* ── Инициализация ───────────────────────────────────────── */

  function bindEvents() {
    els.spinBtn.addEventListener("click", spin);
    els.historyBtn.addEventListener("click", toggleHistory);

    document.addEventListener("keydown", (event) => {
      if (event.code !== "Space" && event.key !== " ") return;
      const tag = (document.activeElement?.tagName || "").toLowerCase();
      if (["input", "textarea", "button", "a", "select"].includes(tag)) return;
      event.preventDefault();
      spin();
    });

    let resizeTimer = 0;
    window.addEventListener("resize", () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(layout, 160);
    });

    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible" && !state.spinning) ping();
    });

    setInterval(() => {
      if (!state.spinning && document.visibilityState === "visible") ping();
    }, 30000);
  }

  async function init() {
    [
      "greeting", "status", "statusText", "track", "viewport", "stage",
      "verdict", "resultName", "resultMeta", "spinBtn", "historyBtn",
      "history", "historyList", "historyCount", "totalSpins", "heroCount", "toast",
    ].forEach((id) => {
      els[id] = document.getElementById(id);
    });

    setGreeting();
    bindEvents();

    try {
      const data = await getJson("heroes.json", 8000);
      if (!data || !Array.isArray(data.heroes) || data.heroes.length < 2) {
        throw new Error("bad manifest");
      }
      state.heroes = data.heroes;
      state.N = data.heroes.length;
      els.heroCount.textContent = `${state.N} ${plural(
        state.N, "герой", "героя", "героев"
      )}`;
      buildTrack();
      requestAnimationFrame(() => {
        measure();
        const start = state.N + Math.floor(Math.random() * state.N);
        centerOn(start);
      });
    } catch (error) {
      els.resultName.textContent = "Нет данных";
      els.resultMeta.textContent = "не удалось загрузить heroes.json";
      setStatus("offline", "нет данных");
      return;
    }

    await ping();
    loadHistory();
  }

  init();
})();
