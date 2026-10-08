/* Read-only cabinet mounting does not require an administrative WebSocket. */
(() => {
  let loaded = false;
  function mount() {
    const routes = {"/driver": ["driver-app", "/driver-app.js"], "/loader": ["loader-app", "/loader-app.js"]};
    const config = routes[window.location.pathname.replace(/\/$/, "")];
    if (!config || loaded) return;
    const root = document.getElementById(config[0]);
    if (!root) return;
    loaded = true;
    observer.disconnect();
    const script = document.createElement("script");
    script.src = config[1];
    script.onerror = () => {
      root.textContent = "Не удалось загрузить рабочее место. Проверьте подключение и обновите страницу.";
      root.setAttribute("role", "alert");
    };
    document.body.appendChild(script);
  }
  const observer = new MutationObserver(mount);
  observer.observe(document.documentElement, {childList: true, subtree: true});
  document.addEventListener("DOMContentLoaded", mount, {once: true});
  mount();
})();
