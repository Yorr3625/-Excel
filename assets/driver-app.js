const DB_NAME = "logistics-driver";
const DB_VERSION = 2;
const ORDER_STORE = "orders";
const SESSION_STORE = "session";
const QUEUE_STORE = "queue";
let csrfToken = "";
let driverId = "";
let assignment = null;
let selectedStoreId = "";
let view = "login";
let online = navigator.onLine;

const apiBasePromise = (async () => {
  try {
    const response = await fetch("/env.json", {credentials: "same-origin"});
    if (!response.ok) return window.location.origin;
    const environment = await response.json();
    const endpoint = new URL(environment.PING, window.location.origin);
    if (["localhost", "0.0.0.0", "::", "0:0:0:0:0:0:0:0"].includes(endpoint.hostname)) {
      endpoint.hostname = window.location.hostname;
      if (window.location.protocol === "https:") {
        endpoint.protocol = "https:";
        endpoint.port = "";
      }
    }
    return endpoint.origin;
  } catch (_) {
    return window.location.origin;
  }
})();

async function apiUrl(path) {
  return `${await apiBasePromise}${path}`;
}

function openDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(ORDER_STORE)) db.createObjectStore(ORDER_STORE);
      if (!db.objectStoreNames.contains(SESSION_STORE)) db.createObjectStore(SESSION_STORE);
      if (!db.objectStoreNames.contains(QUEUE_STORE)) db.createObjectStore(QUEUE_STORE);
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function dbPut(store, key, value) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, "readwrite");
    tx.objectStore(store).put(value, key);
    tx.oncomplete = resolve;
    tx.onerror = () => reject(tx.error);
  });
}

async function dbGet(store, key) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const request = db.transaction(store).objectStore(store).get(key);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function dbAll(store) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const request = db.transaction(store).objectStore(store).getAll();
    request.onsuccess = () => resolve(request.result || []);
    request.onerror = () => reject(request.error);
  });
}

async function dbDelete(store, key) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, "readwrite");
    tx.objectStore(store).delete(key);
    tx.oncomplete = resolve;
    tx.onerror = () => reject(tx.error);
  });
}

async function clearOfflineData() {
  const db = await openDb();
  await new Promise((resolve, reject) => {
    const tx = db.transaction([ORDER_STORE, SESSION_STORE, QUEUE_STORE], "readwrite");
    tx.objectStore(ORDER_STORE).clear();
    tx.objectStore(SESSION_STORE).clear();
    tx.objectStore(QUEUE_STORE).clear();
    tx.oncomplete = resolve;
    tx.onerror = () => reject(tx.error);
  });
  assignment = null;
  driverId = "";
  csrfToken = "";
  navigator.serviceWorker?.controller?.postMessage({type: "CLEAR_DRIVER_DATA"});
}

function root() {
  return document.getElementById("driver-app");
}

function esc(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
  }[character]));
}

function numberText(value) {
  return String(value ?? "0");
}

function setMessage(message, error = false) {
  const element = root().querySelector("[data-message]");
  if (element) {
    element.textContent = message || "";
    element.className = error ? "driver-message driver-message-error" : "driver-message";
  }
}

function render() {
  if (!root()) return;
  if (view === "login") renderLogin();
  else if (view === "store") renderStore();
  else renderOrder();
}

function renderLogin() {
  root().innerHTML = `
    <main class="driver-shell driver-login-shell">
      <section class="driver-panel driver-login-panel">
        <img class="driver-logo" src="/icon-192.svg" alt="Логистика">
        <h1>Рабочее место водителя</h1>
        <p class="driver-muted">Войдите по коду водителя и PIN-коду</p>
        <form data-login-form class="driver-form">
          <label>Код водителя<input name="driver_id" autocomplete="username" required maxlength="128"></label>
          <label>PIN-код<input name="pin" type="password" inputmode="numeric" autocomplete="current-password" required minlength="4" maxlength="12"></label>
          <button class="driver-primary" type="submit">Войти</button>
        </form>
        <p data-message class="driver-message"></p>
        <p class="driver-offline-note">${online ? "Подключение к серверу доступно" : "Нет подключения к серверу"}</p>
      </section>
    </main>`;
  root().querySelector("[data-login-form]").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const button = event.currentTarget.querySelector("button");
    button.disabled = true;
    setMessage("Проверяем данные…");
    try {
      const response = await fetch(await apiUrl("/api/driver/login"), {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        credentials: "include",
        body: JSON.stringify({driver_id: form.get("driver_id"), pin: form.get("pin")})
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Не удалось войти");
      driverId = data.driver.id;
      csrfToken = data.csrf_token;
      await dbPut(SESSION_STORE, "current", {driver_id: driverId});
      await loadOrder();
    } catch (error) {
      setMessage(error.message || "Ошибка входа", true);
      button.disabled = false;
    }
  });
}

function summaryRows() {
  return (assignment?.summary || []).map((line) => `
    <tr><td>${esc(line.name)}</td><td>${esc(line.unit)}</td><td>${numberText(line.planned)}</td><td>${numberText(line.necessary)}</td><td>${numberText(line.completed)}</td></tr>
  `).join("");
}

function storeCards() {
  return (assignment?.stores || []).map((store) => {
    const completed = store.status === "completed";
    return `<button class="driver-store ${completed ? "driver-store-done" : ""}" data-store-id="${esc(store.store_id)}" ${completed ? "disabled" : ""}>
      <span>${esc(store.name)}</span><strong>${completed ? "Выполнено" : "Открыть"}</strong>
    </button>`;
  }).join("");
}

function renderOrder() {
  const completed = assignment?.completed_stores || 0;
  const total = assignment?.store_count || 0;
  root().innerHTML = `
    <main class="driver-shell">
      <header class="driver-header"><div><h1>${esc(assignment?.route_label || "Назначенный заказ")}</h1><p class="driver-muted">${esc(assignment?.driver_name || "")} · ${completed} из ${total} магазинов</p></div><button data-logout class="driver-secondary">Выйти</button></header>
      <p data-message class="driver-message"></p>
      <section class="driver-panel"><h2>Весь заказ</h2><div class="driver-table-wrap"><table class="driver-table"><thead><tr><th>Товар</th><th>Ед.</th><th>План</th><th>Необходимо</th><th>Выполнено</th></tr></thead><tbody>${summaryRows()}</tbody></table></div></section>
      <section class="driver-panel"><h2>Магазины</h2><div class="driver-store-list">${storeCards() || "<p class=\"driver-muted\">Магазины не назначены</p>"}</div></section>
      <footer class="driver-footer"><span>${online ? "Онлайн" : "Офлайн"}</span><button data-sync class="driver-secondary">Синхронизировать</button></footer>
    </main>`;
  root().querySelectorAll("[data-store-id]").forEach((button) => button.addEventListener("click", () => {
    selectedStoreId = button.dataset.storeId;
    view = "store";
    render();
  }));
  root().querySelector("[data-logout]").addEventListener("click", logout);
  root().querySelector("[data-sync]").addEventListener("click", syncOrder);
}

function selectedStore() {
  return (assignment?.stores || []).find((store) => store.store_id === selectedStoreId);
}

function renderStore() {
  const store = selectedStore();
  if (!store) { view = "order"; render(); return; }
  const completed = store.status === "completed";
  const lines = (store.lines || []).map((line) => `
    <label class="driver-line"><span>${esc(line.name)} <small>${esc(line.unit)}</small><em>План: ${numberText(line.required_qty)}</em></span>
    <input data-line-id="${esc(line.line_id)}" type="number" inputmode="decimal" min="0" step="any" value="${completed ? numberText(line.actual_qty) : ""}" ${completed ? "disabled" : "required"}>
    </label>`).join("");
  root().innerHTML = `
    <main class="driver-shell"><header class="driver-header"><button data-back class="driver-secondary">Назад</button><div><h1>${esc(store.name)}</h1><p class="driver-muted">${completed ? "Магазин выполнен" : "Введите фактическое количество"}</p></div></header>
      <section class="driver-panel"><div class="driver-lines">${lines}</div>${completed ? "" : "<button data-complete class=\"driver-primary\">Подтвердить магазин</button>"}<p data-message class="driver-message"></p></section>
    </main>`;
  root().querySelector("[data-back]").addEventListener("click", () => { view = "order"; render(); });
  const complete = root().querySelector("[data-complete]");
  if (complete) complete.addEventListener("click", completeStore);
}

async function api(path, options = {}) {
  const headers = {...(options.headers || {})};
  if (options.method && options.method !== "GET") headers["X-Driver-CSRF"] = csrfToken;
  const response = await fetch(await apiUrl(path), {...options, headers, credentials: "include"});
  if (!response.ok) {
    let data = {};
    try { data = await response.json(); } catch (_) {}
    const error = new Error(data.error || `HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

async function flushQueue() {
  if (!csrfToken || !online) return true;
  const queued = await dbAll(QUEUE_STORE).catch(() => []);
  let clean = true;
  for (const operation of queued.filter((item) => item.driver_id === driverId)) {
    try {
      const data = await api(`/api/driver/order/stores/${encodeURIComponent(operation.store_id)}/complete`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(operation.payload)
      });
      assignment = data.assignment;
      await dbPut(ORDER_STORE, driverId, assignment);
      await dbDelete(QUEUE_STORE, operation.payload.operation_id);
    } catch (error) {
      if (error.status === 409) {
        await dbDelete(QUEUE_STORE, operation.payload.operation_id);
        clean = false;
        setMessage("Одну из офлайн-операций нельзя применить: заказ изменён на сервере.", true);
      } else {
        clean = false;
        break;
      }
    }
  }
  return clean;
}

async function loadOrder() {
  try {
    const data = await api("/api/driver/order");
    assignment = data.assignment;
    if (!assignment) throw new Error("Для водителя нет активного назначения");
    await dbPut(ORDER_STORE, driverId, assignment);
    view = "order";
    render();
  } catch (error) {
    const cached = driverId ? await dbGet(ORDER_STORE, driverId).catch(() => null) : null;
    if (cached) {
      assignment = cached;
      view = "order";
      render();
      setMessage("Показана сохранённая копия. Для подтверждения нужен сервер.", true);
    } else {
      view = "login";
      render();
      setMessage(error.message || "Не удалось загрузить заказ", true);
    }
  }
}

async function completeStore() {
  const store = selectedStore();
  if (!store) return;
  const quantities = {};
  let invalid = false;
  root().querySelectorAll("[data-line-id]").forEach((input) => {
    if (input.value === "" || Number(input.value) < 0 || !Number.isFinite(Number(input.value))) invalid = true;
    quantities[input.dataset.lineId] = input.value;
  });
  if (invalid) { setMessage("Заполните каждую строку неотрицательным числом", true); return; }
  const operationId = crypto.randomUUID();
  const payload = {quantities, operation_id: operationId, base_revision: assignment.revision};
  const button = root().querySelector("[data-complete]");
  button.disabled = true;
  try {
    const data = await api(`/api/driver/order/stores/${encodeURIComponent(store.store_id)}/complete`, {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)
    });
    assignment = data.assignment;
    await dbPut(ORDER_STORE, driverId, assignment);
    view = "order";
    render();
  } catch (error) {
    button.disabled = false;
    if (!error.status && !online) {
      await dbPut(QUEUE_STORE, operationId, {
        driver_id: driverId,
        store_id: store.store_id,
        payload
      });
      applyLocalCompletion(store, quantities);
      await dbPut(ORDER_STORE, driverId, assignment);
      view = "order";
      render();
      setMessage("Сохранено на устройстве и будет отправлено после восстановления связи.", true);
    } else if (error.status === 409) {
      setMessage("Заказ изменён на другом устройстве. Синхронизируйте данные.", true);
    } else {
      setMessage(error.message || "Не удалось сохранить магазин", true);
    }
  }
}

function applyLocalCompletion(store, quantities) {
  store.status = "completed";
  store.completed_at = new Date().toISOString();
  for (const line of store.lines) line.actual_qty = String(quantities[line.line_id]);
  assignment.revision += 1;
  for (const line of assignment.summary) {
    const matching = store.lines.find((item) => item.name === line.name);
    if (matching) {
      line.completed = String(Number(line.completed) + Number(matching.actual_qty));
      line.necessary = String(Math.max(Number(line.necessary) - Number(matching.required_qty), 0));
    }
  }
  assignment.completed_stores += 1;
}

async function syncOrder() {
  try {
    await flushQueue();
    const data = await api("/api/driver/sync", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"});
    assignment = data.assignment;
    if (assignment) await dbPut(ORDER_STORE, driverId, assignment);
    render();
    setMessage("Данные синхронизированы");
  } catch (error) { setMessage(error.message || "Синхронизация недоступна", true); }
}

async function logout() {
  try { await api("/api/driver/logout", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"}); } catch (_) {}
  await clearOfflineData();
  view = "login";
  render();
}

async function restoreSession() {
  const saved = await dbGet(SESSION_STORE, "current").catch(() => null);
  if (!saved) { render(); return; }
  try {
    const data = await api("/api/driver/me");
    driverId = data.driver.id;
    csrfToken = data.csrf_token || "";
    assignment = data.assignment;
    if (assignment) await dbPut(ORDER_STORE, driverId, assignment);
    if (assignment) { view = "order"; render(); } else { view = "login"; render(); setMessage("Для водителя нет активного назначения", true); }
  } catch (_) {
    driverId = saved.driver_id;
    assignment = await dbGet(ORDER_STORE, driverId).catch(() => null);
    if (assignment) { view = "order"; render(); setMessage("Офлайн-копия заказа", true); } else render();
  }
}

window.addEventListener("online", () => { online = true; if (assignment) syncOrder(); });
window.addEventListener("offline", () => { online = false; if (view === "order") render(); });
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/service-worker.js").catch(() => {});
restoreSession();
