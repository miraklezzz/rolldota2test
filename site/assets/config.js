/* Адрес локального движка по умолчанию.
   Переопределяется параметром ?api=https://... (его подставляет бот),
   либо вручную через localStorage: localStorage.setItem("dotarandom.api", "https://...") */
window.DOTA_RANDOM_CONFIG = {
  api: "http://127.0.0.1:8765",
};
