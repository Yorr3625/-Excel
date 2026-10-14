/* Mount standalone cabinets only after Reflex hydrates the server-rendered page. */
(() => {
  const routes = {"/driver": ["driver-app", "/driver-app.js"], "/crew": ["driver-app", "/driver-app.js"], "/loader": ["loader-app", "/loader-app.js"]};
  const config = routes[window.location.pathname.replace(/\/$/, "")];
  if (!config || window.__logisticsCabinetBootstrap) return;
  window.__logisticsCabinetBootstrap = true;

  let started = false;
  let scheduled = false;
  let scriptState = "idle";

  function mount() {
    const root = document.getElementById(config[0]);
    if (!root) return;
    if (scriptState === "idle") {
      scriptState = "loading";
      const script = document.createElement("script");
      script.src = config[1];
      script.onload = () => { scriptState = "ready"; schedule(); };
      script.onerror = () => {
        scriptState = "failed";
        root.textContent = "Не удалось загрузить рабочее место. Проверьте подключение и обновите страницу.";
        root.setAttribute("role", "alert");
      };
      document.body.appendChild(script);
    } else if (scriptState === "ready" && !root.firstElementChild && !root.textContent.trim()) {
      // A late Reflex hydration can replace the cabinet root after its script ran.
      // Restore the view without loading the script or re-sending operations.
      window.render?.();
    }
  }

  function schedule() {
    if (!started || scheduled) return;
    scheduled = true;
    window.setTimeout(() => { scheduled = false; mount(); }, 50);
  }

  new MutationObserver(schedule).observe(document.documentElement, {childList: true, subtree: true});
  function start() {
    if (started) return;
    started = true;
    window.setTimeout(mount, 200);
  }
  if (document.readyState === "complete") start();
  else window.addEventListener("load", start, {once: true});
})();
