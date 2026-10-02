const DB_NAME = "logistics-driver";
const DB_VERSION = 3;
const ORDER_STORE = "orders";
const SESSION_STORE = "session";
const QUEUE_STORE = "queue";
const MILEAGE_QUEUE_STORE = "mileage_queue";
let csrfToken = "";
let driverId = "";
let assignment = null;
let mileage = null;
let selectedStoreId = "";
let view = "login";
let online = navigator.onLine;
let theme = (() => {
  try { return localStorage.getItem("driver-theme") === "dark" ? "dark" : "light"; } catch (_) { return "light"; }
})();

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
      if (!db.objectStoreNames.contains(MILEAGE_QUEUE_STORE)) db.createObjectStore(MILEAGE_QUEUE_STORE);
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

async function saveSession() {
  if (driverId) await dbPut(SESSION_STORE, "current", {driver_id: driverId, mileage});
}

async function clearOfflineData() {
  const db = await openDb();
  await new Promise((resolve, reject) => {
    const tx = db.transaction([ORDER_STORE, SESSION_STORE, QUEUE_STORE, MILEAGE_QUEUE_STORE], "readwrite");
    tx.objectStore(ORDER_STORE).clear();
    tx.objectStore(SESSION_STORE).clear();
    tx.objectStore(QUEUE_STORE).clear();
    tx.objectStore(MILEAGE_QUEUE_STORE).clear();
    tx.oncomplete = resolve;
    tx.onerror = () => reject(tx.error);
  });
  assignment = null;
  mileage = null;
  driverId = "";
  csrfToken = "";
  navigator.serviceWorker?.controller?.postMessage({type: "CLEAR_DRIVER_DATA"});
}

function root() {
  return document.getElementById("driver-app");
}

function logoMark() {
  return `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6.5h11v9H3zM14 10h3.5l2.5 2.5v3H14zM7 18.5a1.75 1.75 0 1 0 0-3.5 1.75 1.75 0 0 0 0 3.5Zm10 0a1.75 1.75 0 1 0 0-3.5 1.75 1.75 0 0 0 0 3.5Z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>`;
}

function themeIcon() {
  return theme === "dark"
    ? `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 2.5v2M12 19.5v2M21.5 12h-2M4.5 12h-2M18.72 5.28l-1.42 1.42M6.7 17.3l-1.42 1.42M18.72 18.72 17.3 17.3M6.7 6.7 5.28 5.28" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>`
    : `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.5 15.2A8.5 8.5 0 0 1 8.8 3.5 8.5 8.5 0 1 0 20.5 15.2Z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>`;
}

function appHeader(showLogout = false) {
  return `<header class="driver-app-header">
    <a class="driver-brand" href="/driver" aria-label="Dostavo.online">
      <span class="driver-brand-mark">${logoMark()}</span><strong>dostavo.online</strong><span class="driver-brand-subtitle">Кабинет водителя</span>
    </a>
    <div class="driver-header-actions">
      <button class="driver-icon-button" data-theme-toggle type="button" aria-label="${theme === "dark" ? "Включить светлую тему" : "Включить тёмную тему"}">${themeIcon()}</button>
      ${showLogout ? '<button class="driver-logout" data-logout type="button">Выйти</button>' : ""}
    </div>
  </header>`;
}

function applyTheme() {
  root()?.querySelector(".driver-app-frame")?.setAttribute("data-theme", theme);
  try { localStorage.setItem("driver-theme", theme); } catch (_) {}
}

function bindFrameActions() {
  applyTheme();
  root().querySelector("[data-theme-toggle]")?.addEventListener("click", () => {
    theme = theme === "dark" ? "light" : "dark";
    applyTheme();
    render();
  });
  root().querySelector("[data-logout]")?.addEventListener("click", logout);
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
  else if (mileage?.required) renderMileage();
  else if (view === "store") renderStore();
  else renderOrder();
}

function renderLogin() {
  root().innerHTML = `
    <div class="driver-app-frame">
      ${appHeader()}
      <main class="driver-login-shell">
        <section class="driver-panel driver-login-panel">
          <h1>Рабочее место водителя</h1>
          <p class="driver-muted">Войдите по коду водителя и PIN-коду</p>
          <form data-login-form class="driver-form">
            <label>Код водителя<input name="driver_id" autocomplete="username" required maxlength="128"></label>
            <label>PIN-код<input name="pin" type="password" inputmode="numeric" autocomplete="current-password" required minlength="4" maxlength="12"></label>
            <button class="driver-primary" type="submit">Войти</button>
          </form>
          <p data-message class="driver-message"></p>
        </section>
        <p class="driver-offline-note ${online ? "driver-online" : "driver-offline"}"><span aria-hidden="true"></span>${online ? "Подключение к серверу доступно" : "Нет подключения к серверу"}</p>
      </main>
    </div>`;
  bindFrameActions();
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
      mileage = data.mileage || null;
      await saveSession();
      if (mileage?.required) {
        view = "order";
        render();
      } else {
        await loadOrder();
      }
    } catch (error) {
      setMessage(error.message || "Ошибка входа", true);
      button.disabled = false;
    }
  });
}

function renderMileage() {
  const vehicle = mileage?.vehicle || {};
  const isAvailable = mileage?.available;
  const vehicleLabel = [vehicle.name, vehicle.plate].filter(Boolean).join(" · ") || "Назначенный автомобиль";
  root().innerHTML = `
    <div class="driver-app-frame">
      ${appHeader(true)}
      <main class="driver-shell">
        <div class="driver-modal-backdrop">
          <section class="driver-modal" role="dialog" aria-modal="true" aria-labelledby="mileage-title">
            <h1 id="mileage-title">Укажите пробег</h1>
            <p class="driver-muted">Перед началом работы зафиксируйте показание одометра.</p>
            <p class="driver-mileage-vehicle">${esc(vehicleLabel)}</p>
            ${isAvailable ? `<form data-mileage-form class="driver-form">
              <label>Пробег, км<input name="odometer_km" type="number" inputmode="numeric" min="0" max="9999999" step="1" required autofocus></label>
              <button class="driver-primary" type="submit">Сохранить пробег</button>
            </form>` : ""}
            <p data-message class="${isAvailable ? "driver-message" : "driver-message driver-message-error"}">${esc(isAvailable ? (mileage?.pending ? "Показание ожидает отправки после восстановления связи." : "") : (mileage?.error || "Проверьте активное назначение."))}</p>
          </section>
        </div>
      </main>
    </div>`;
  bindFrameActions();
  const form = root().querySelector("[data-mileage-form]");
  if (form) form.addEventListener("submit", submitMileage);
}

function summaryRows() {
  return (assignment?.summary || []).map((line) => `
    <tr><td>${esc(line.name)}</td><td>${esc(line.unit)}</td><td>${numberText(line.planned)}</td><td>${numberText(line.necessary)}</td><td>${numberText(line.completed)}</td></tr>
  `).join("");
}

function driverInitials() {
  return esc((assignment?.driver_name || "Водитель").split(/\s+/).filter(Boolean).map((part) => part[0]).join("").slice(0, 2).toUpperCase());
}

function storeCards(stores, offset = 0) {
  return stores.map((store, index) => {
    const completed = store.status === "completed";
    return `<button class="driver-store ${completed ? "driver-store-done" : ""}" data-store-id="${esc(store.store_id)}" ${completed ? "disabled" : ""}>
      <span class="driver-store-index">${offset + index + 1}</span>
      <span class="driver-store-name">${esc(store.name)}</span>
      <strong>${completed ? "Выполнено" : "Открыть"}</strong>
    </button>`;
  }).join("");
}

function storesPanel(stores, offset = 0, className = "") {
  return `<section class="driver-panel driver-stores-panel ${className}">
    <div class="driver-panel-heading"><div><h2>Магазины</h2><p class="driver-muted">Откройте магазин, чтобы начать работу с заказом</p></div><span class="driver-count">${assignment?.store_count || 0}</span></div>
    <div class="driver-store-list">${stores.length ? storeCards(stores, offset) : '<p class="driver-muted">Магазины не назначены</p>'}</div>
  </section>`;
}

function renderOrder() {
  const completed = assignment?.completed_stores || 0;
  const total = assignment?.store_count || 0;
  const stores = assignment?.stores || [];
  const progress = total ? Math.round((completed / total) * 100) : 0;
  root().innerHTML = `
    <div class="driver-app-frame">
      ${appHeader(true)}
      <main class="driver-shell driver-order-shell">
        <p class="driver-breadcrumb">Назначенный заказ</p>
        <div class="driver-route-title"><h1>${esc(assignment?.route_label || "Назначенный заказ")}</h1><span>${online ? "Онлайн" : "Офлайн"}</span></div>
        <section class="driver-overview">
          <div class="driver-overview-card"><span class="driver-avatar">${driverInitials()}</span><div><small>Водитель</small><strong>${esc(assignment?.driver_name || "Не назначен")}</strong></div></div>
          <div class="driver-overview-card driver-progress-card"><div><small>${completed} из ${total} магазинов</small><strong>${progress}%</strong></div><div class="driver-progress"><span style="width:${progress}%"></span></div></div>
        </section>
        <p data-message class="driver-message"></p>
        <div class="driver-workspace">
          <section class="driver-panel driver-order-panel">
            <div class="driver-panel-heading"><div><h2>Весь заказ</h2><p class="driver-muted">Общий объём товаров по маршруту. Данные обновляются при синхронизации.</p></div><span class="driver-products-count">${(assignment?.summary || []).length} товаров</span></div>
            <div class="driver-table-wrap"><table class="driver-table"><thead><tr><th>Товар</th><th>Ед.</th><th>Заказ на маршрут</th><th>Необходимо на маршрут</th><th>Выполнено</th></tr></thead><tbody>${summaryRows()}</tbody></table></div>
            <p class="driver-table-note">Для подтверждения магазина заполните фактическое количество каждой позиции.</p>
          </section>
          ${storesPanel(stores)}
        </div>
        <footer class="driver-footer"><span class="${online ? "driver-online" : "driver-offline"}"><i aria-hidden="true"></i>${online ? "Онлайн" : "Офлайн"}<small>${online ? "Данные синхронизированы с сервером" : "Изменения будут отправлены после восстановления связи"}</small></span><button data-sync class="driver-primary driver-sync" type="button">Синхронизировать</button></footer>
      </main>
    </div>`;
  bindFrameActions();
  root().querySelectorAll("[data-store-id]").forEach((button) => button.addEventListener("click", () => {
    selectedStoreId = button.dataset.storeId;
    view = "store";
    render();
  }));
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
    <div class="driver-app-frame">
      ${appHeader(true)}
      <main class="driver-shell driver-store-shell">
        <p class="driver-breadcrumb">${esc(assignment?.route_label || "Назначенный заказ")}</p>
        <header class="driver-header"><button data-back class="driver-secondary" type="button">Назад</button><div><h1>${esc(store.name)}</h1><p class="driver-muted">${completed ? "Магазин выполнен" : "Введите фактическое количество"}</p></div></header>
        <section class="driver-panel driver-store-detail"><div class="driver-lines">${lines}</div>${completed ? "" : '<button data-complete class="driver-primary" type="button">Подтвердить магазин</button>'}<p data-message class="driver-message"></p></section>
      </main>
    </div>`;
  bindFrameActions();
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
    error.mileage = data.mileage;
    throw error;
  }
  return response.json();
}

function mileageQueueKey(payload) {
  return `${driverId}:${payload.assignment_id}:${payload.vehicle_id}:${payload.date}`;
}

async function submitMileage(event) {
  event.preventDefault();
  if (!mileage?.available) return;
  const form = new FormData(event.currentTarget);
  const odometer = String(form.get("odometer_km") || "").trim();
  if (!/^\d+$/.test(odometer)) {
    setMessage("Пробег должен быть целым неотрицательным числом", true);
    return;
  }
  const button = event.currentTarget.querySelector("button");
  button.disabled = true;
  const payload = {
    odometer_km: odometer,
    vehicle_id: mileage.vehicle.id,
    date: mileage.date,
    assignment_id: mileage.assignment_id
  };
  try {
    const data = await api("/api/driver/mileage", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
    mileage = data.mileage || null;
    await saveSession();
    await loadOrder();
  } catch (error) {
    button.disabled = false;
    if (!error.status) {
      mileage = {...mileage, pending: true};
      await dbPut(MILEAGE_QUEUE_STORE, mileageQueueKey(payload), {driver_id: driverId, payload});
      await saveSession();
      setMessage("Показание сохранено на устройстве и будет отправлено после восстановления связи.", true);
    } else if (error.status === 409 && error.mileage) {
      mileage = error.mileage;
      await saveSession();
      if (mileage.required) render();
      else await loadOrder();
    } else {
      setMessage(error.message || "Не удалось сохранить пробег", true);
    }
  }
}

async function flushMileageQueue() {
  if (!csrfToken || !online) return false;
  const queued = await dbAll(MILEAGE_QUEUE_STORE).catch(() => []);
  for (const operation of queued.filter((item) => item.driver_id === driverId)) {
    try {
      const data = await api("/api/driver/mileage", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(operation.payload)
      });
      mileage = data.mileage || null;
      await dbDelete(MILEAGE_QUEUE_STORE, mileageQueueKey(operation.payload));
      await saveSession();
    } catch (error) {
      if (error.status === 409 && error.mileage) {
        mileage = error.mileage;
        await saveSession();
        continue;
      }
      return false;
    }
  }
  return !mileage?.required;
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
    if (error.status === 409 && error.mileage) {
      mileage = error.mileage;
      await saveSession();
      view = "order";
      render();
      return;
    }
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
    if (!await flushMileageQueue()) {
      if (mileage?.required) {
        view = "order";
        render();
        setMessage("Показание ожидает отправки. Повторите синхронизацию после восстановления связи.", true);
      }
      return;
    }
    await flushQueue();
    const data = await api("/api/driver/sync", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"});
    assignment = data.assignment;
    if (assignment) await dbPut(ORDER_STORE, driverId, assignment);
    render();
    setMessage("Данные синхронизированы");
  } catch (error) {
    if (error.status === 409 && error.mileage) {
      mileage = error.mileage;
      await saveSession();
      view = "order";
      render();
    }
    setMessage(error.message || "Синхронизация недоступна", true);
  }
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
    mileage = data.mileage || null;
    assignment = data.assignment;
    await saveSession();
    if (assignment) await dbPut(ORDER_STORE, driverId, assignment);
    if (mileage?.required) {
      view = "order";
      render();
    } else if (assignment) {
      view = "order";
      render();
    } else {
      view = "login";
      render();
      setMessage("Для водителя нет активного назначения", true);
    }
  } catch (_) {
    driverId = saved.driver_id;
    mileage = saved.mileage || {required: true, available: false, error: "Подключитесь к серверу, чтобы проверить обязательный пробег."};
    assignment = await dbGet(ORDER_STORE, driverId).catch(() => null);
    if (mileage.required) {
      view = "order";
      render();
    } else if (assignment) {
      view = "order";
      render();
      setMessage("Офлайн-копия заказа", true);
    } else {
      render();
    }
  }
}

window.addEventListener("online", async () => {
  online = true;
  if (driverId && !csrfToken) await restoreSession();
  if (driverId && csrfToken) syncOrder();
});
window.addEventListener("offline", () => { online = false; if (view !== "login") render(); });
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/service-worker.js").catch(() => {});
applyTheme();
restoreSession();
