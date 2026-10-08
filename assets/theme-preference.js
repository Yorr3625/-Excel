/* Shared presentation preference. No form, session or queue state belongs here. */
(() => {
  if (window.LogisticsTheme) return;
  const KEY = "logistics-theme";
  const allowed = ["system", "light", "dark"];
  const media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  let preference = "system";
  try {
    const stored = localStorage.getItem(KEY);
    const legacy = localStorage.getItem("driver-theme");
    preference = allowed.includes(stored) ? stored : ["light", "dark"].includes(legacy) ? legacy : "system";
  } catch (_) { /* Storage may be unavailable in private contexts. */ }
  function effective() { return preference === "system" ? media?.matches ? "dark" : "light" : preference; }
  function syncControls() {
    document.querySelectorAll(".radix-themes").forEach(container => {
      container.classList.toggle("dark", effective() === "dark");
      container.classList.toggle("light", effective() === "light");
    });
    document.querySelectorAll("[data-theme-select]").forEach(select => { select.value = preference; });
  }
  function apply() {
    const theme = effective();
    const html = document.documentElement;
    html.dataset.theme = theme;
    html.style.colorScheme = theme;
    html.classList.toggle("dark", theme === "dark");
    html.classList.toggle("light", theme === "light");
    document.querySelectorAll('meta[name="theme-color"]').forEach(meta => {
      meta.setAttribute("content", theme === "dark" ? "#171a18" : "#ffffff");
    });
    syncControls();
    window.dispatchEvent(new CustomEvent("logistics-theme-change", {detail: {preference, theme}}));
  }
  function setPreference(value) {
    if (!allowed.includes(value)) return;
    preference = value;
    try { localStorage.setItem(KEY, value); } catch (_) {}
    apply();
  }
  window.LogisticsTheme = {getPreference: () => preference, getTheme: effective, setPreference};
  document.addEventListener("change", event => {
    if (event.target.matches?.("[data-theme-select]")) setPreference(event.target.value);
  });
  window.addEventListener("storage", event => {
    if (event.key !== KEY) return;
    preference = allowed.includes(event.newValue) ? event.newValue : "system";
    apply();
  });
  const onSystemChange = () => { if (preference === "system") apply(); };
  if (media?.addEventListener) media.addEventListener("change", onSystemChange);
  else media?.addListener?.(onSystemChange);
  apply();
  document.addEventListener("DOMContentLoaded", apply, {once: true});
  new MutationObserver(syncControls).observe(document.documentElement, {childList: true, subtree: true});
})();
