const DB_NAME = "logistics-driver";
const DB_VERSION = 4;
const ORDER_STORE = "orders";
const SESSION_STORE = "session";
const QUEUE_STORE = "queue";
const MILEAGE_QUEUE_STORE = "mileage_queue";
const RETURN_CACHE_STORE = "return_cache";
const RETURN_DRAFT_STORE = "return_drafts";
const RETURN_QUEUE_STORE = "return_queue";
let returnIndex = {returns: [], assignments: []};
let returnContext = null;
let returnDraft = null;
let returnOperation = null;
let returnSave = Promise.resolve();
let syncing = false;
let loggingOut = false;
let syncFinished = Promise.resolve();
let csrfToken = "";
let driverId = "";
let assignment = null;
let mileage = null;
let selectedStoreId = "";
let view = "login";
let online = navigator.onLine;
const themePreference = () => window.LogisticsTheme?.getPreference?.() || "system";

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
      if (!db.objectStoreNames.contains(RETURN_CACHE_STORE)) db.createObjectStore(RETURN_CACHE_STORE);
      if (!db.objectStoreNames.contains(RETURN_DRAFT_STORE)) db.createObjectStore(RETURN_DRAFT_STORE);
      if (!db.objectStoreNames.contains(RETURN_QUEUE_STORE)) db.createObjectStore(RETURN_QUEUE_STORE);
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
  await returnSave.catch(() => {});
  const db = await openDb();
  await new Promise((resolve, reject) => {
    const tx = db.transaction([ORDER_STORE, SESSION_STORE, QUEUE_STORE, MILEAGE_QUEUE_STORE, RETURN_CACHE_STORE, RETURN_DRAFT_STORE, RETURN_QUEUE_STORE], "readwrite");
    tx.objectStore(ORDER_STORE).clear();
    tx.objectStore(SESSION_STORE).clear();
    tx.objectStore(QUEUE_STORE).clear();
    tx.objectStore(MILEAGE_QUEUE_STORE).clear();
    tx.objectStore(RETURN_CACHE_STORE).clear();
    tx.objectStore(RETURN_DRAFT_STORE).clear();
    tx.objectStore(RETURN_QUEUE_STORE).clear();
    tx.oncomplete = resolve;
    tx.onerror = () => reject(tx.error);
  });
  assignment = null;
  returnContext = returnDraft = returnOperation = null;
  returnIndex = {returns: [], assignments: []};
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

function appHeader(showLogout = false) {
  return `<header class="driver-app-header">
    <a class="driver-brand" href="/driver" aria-label="Dostavo.online">
      <span class="driver-brand-mark">${logoMark()}</span><strong>dostavo.online</strong><span class="driver-brand-subtitle">Кабинет водителя</span>
    </a>
    <div class="driver-header-actions">
      <label class="driver-theme-control">Тема<select data-theme-select aria-label="Тема оформления">
        <option value="system" ${themePreference() === "system" ? "selected" : ""}>Системная</option>
        <option value="light" ${themePreference() === "light" ? "selected" : ""}>Светлая</option>
        <option value="dark" ${themePreference() === "dark" ? "selected" : ""}>Тёмная</option>
      </select></label>
      ${showLogout ? '<button class="driver-logout" data-returns type="button">Возвраты</button><button class="driver-logout" data-logout type="button">Выйти</button>' : ""}
    </div>
  </header>`;
}

function bindFrameActions() {
  // Theme changes are handled by the shared LogisticsTheme controller. Do not
  // render here: replacing the root would discard unsaved measurement fields.
  root().querySelector("[data-logout]")?.addEventListener("click", logout);
  root().querySelector("[data-returns]")?.addEventListener("click", openReturns);
}

function esc(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
  }[character]));
}

function numberText(value) {
  return String(value ?? "0");
}

function measurementNet(measurement) {
  const boxes = Number(measurement?.box_count);
  const tare = Number(measurement?.tare_weight_per_box_kg);
  const gross = Number(measurement?.gross_weight_kg);
  if (!Number.isInteger(boxes) || boxes < 0 || !Number.isFinite(tare) || tare < 0 || !Number.isFinite(gross) || gross < 0) return "";
  const net = gross - boxes * tare;
  return net >= 0 ? String(net) : "";
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
  else if (view === "returns") renderReturns();
  else if (view === "return") renderReturn();
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
            <button data-return-history class="driver-secondary" type="button">История возвратов</button>
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
  root().querySelector("[data-return-history]").addEventListener("click", openReturns);
  const form = root().querySelector("[data-mileage-form]");
  if (form) form.addEventListener("submit", submitMileage);
}

function summaryRows() {
  return (assignment?.summary || []).map((line) => `
    <tr><td data-label="Товар">${esc(line.name)}</td><td data-label="Ед.">${esc(line.unit)}</td><td data-label="Заказ на маршрут">${numberText(line.planned)}</td><td data-label="Необходимо на маршрут">${numberText(line.necessary)}</td><td data-label="Выполнено">${numberText(line.completed)}</td></tr>
  `).join("");
}

function driverInitials() {
  return esc((assignment?.driver_name || "Водитель").split(/\s+/).filter(Boolean).map((part) => part[0]).join("").slice(0, 2).toUpperCase());
}

function storeCards(stores, offset = 0) {
  const waitingForLoading = assignment?.loading_status === "waiting_loading";
  return stores.map((store, index) => {
    const completed = store.status === "completed";
    const blocked = completed || waitingForLoading;
    return `<button class="driver-store ${completed ? "driver-store-done" : ""}" data-store-id="${esc(store.store_id)}" ${blocked ? "disabled" : ""}>
      <span class="driver-store-index">${offset + index + 1}</span>
      <span class="driver-store-name">${esc(store.name)}</span>
      <strong>${completed ? "Выполнено" : (waitingForLoading ? "Ожидает загрузки" : "Открыть")}</strong>
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
        <p data-message class="driver-message">${assignment?.loading_status === "waiting_loading" ? "Склад ещё не подтвердил загрузку. Отгрузка будет доступна после подтверждения." : ""}</p>
        <button data-route-return class="driver-secondary" type="button">Возврат остатка / история</button>
        <div class="driver-workspace">
          <section class="driver-panel driver-order-panel">
            <div class="driver-panel-heading"><div><h2>Весь заказ</h2><p class="driver-muted">Общий объём товаров по маршруту. Данные обновляются при синхронизации.</p></div><span class="driver-products-count">${(assignment?.summary || []).length} товаров</span></div>
            <div class="driver-table-wrap"><table class="driver-table"><thead><tr><th>Товар</th><th>Ед.</th><th>Заказ на маршрут</th><th>Необходимо на маршрут</th><th>Выполнено</th></tr></thead><tbody>${summaryRows()}</tbody></table></div>
            <p class="driver-table-note">Для отгрузки магазина укажите ящики, тару одного ящика и грязный вес по каждой позиции.</p>
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
  root().querySelector("[data-route-return]").addEventListener("click", () => assignment?.assignment_id ? openReturn(assignment.assignment_id) : openReturns());
}

function selectedStore() {
  return (assignment?.stores || []).find((store) => store.store_id === selectedStoreId);
}

function refreshNetPreviews() {
  const measurements = {};
  root().querySelectorAll("[data-measurement-input]").forEach((input) => {
    const lineId = input.dataset.lineId;
    measurements[lineId] ||= {};
    measurements[lineId][input.dataset.field] = input.value;
  });
  root().querySelectorAll("[data-net-line-id]").forEach((output) => {
    const net = measurementNet(measurements[output.dataset.netLineId]);
    output.textContent = net === "" ? "—" : `${net} кг`;
  });
}

function renderStore() {
  const store = selectedStore();
  if (!store) { view = "order"; render(); return; }
  const completed = store.status === "completed";
  const waitingForLoading = assignment?.loading_status === "waiting_loading";
  const lines = (store.lines || []).map((line) => {
    const measurement = line.shipment_measurement || {};
    const saved = completed;
    const savedDetails = measurement.legacy_net_weight_kg
      ? `<span class="driver-line-net">Нетто: ${esc(numberText(measurement.net_weight_kg))} кг</span>`
      : `<span class="driver-line-net">Ящики: ${esc(numberText(measurement.box_count))} · Тара: ${esc(numberText(measurement.tare_weight_per_box_kg))} кг/ящ. · Грязный: ${esc(numberText(measurement.gross_weight_kg))} кг · Нетто: ${esc(numberText(measurement.net_weight_kg))} кг</span>`;
    return `<section class="driver-line"><span>${esc(line.name)} <small>${esc(line.unit)}</small><em>План: ${numberText(line.required_qty)} кг</em></span>
      ${saved ? savedDetails : `<div class="driver-line-measurements">
        <label>Ящики<input data-measurement-input data-line-id="${esc(line.line_id)}" data-field="box_count" type="number" inputmode="numeric" min="0" step="1" required></label>
        <label>Тара, кг/ящ.<input data-measurement-input data-line-id="${esc(line.line_id)}" data-field="tare_weight_per_box_kg" type="number" inputmode="decimal" min="0" step="any" required></label>
        <label>Грязный вес, кг<input data-measurement-input data-line-id="${esc(line.line_id)}" data-field="gross_weight_kg" type="number" inputmode="decimal" min="0" step="any" required></label>
        <output data-net-line-id="${esc(line.line_id)}">—</output>
      </div>`}
    </section>`;
  }).join("");
  root().innerHTML = `
    <div class="driver-app-frame">
      ${appHeader(true)}
      <main class="driver-shell driver-store-shell">
        <p class="driver-breadcrumb">${esc(assignment?.route_label || "Назначенный заказ")}</p>
        <header class="driver-header"><button data-back class="driver-secondary" type="button">Назад</button><div><h1>${esc(store.name)}</h1><p class="driver-muted">${completed ? "Магазин выполнен" : (waitingForLoading ? "Ожидается подтверждение загрузки на складе" : "Введите ящики, тару и грязный вес")}</p></div></header>
        <section class="driver-panel driver-store-detail"><div class="driver-lines">${lines}</div>${completed || waitingForLoading ? "" : '<button data-complete class="driver-primary" type="button">Подтвердить отгрузку</button>'}<p data-message class="driver-message">${waitingForLoading ? "Склад ещё не подтвердил загрузку." : ""}</p></section>
      </main>
    </div>`;
  bindFrameActions();
  root().querySelector("[data-back]").addEventListener("click", () => { view = "order"; render(); });
  root().querySelectorAll("[data-measurement-input]").forEach((input) => input.addEventListener("input", refreshNetPreviews));
  refreshNetPreviews();
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
  if (!csrfToken || !online) return false;
  const queued = (await dbAll(QUEUE_STORE)).filter((item) => item.driver_id === driverId);
  queued.sort((a, b) => Number(a.payload?.base_revision) - Number(b.payload?.base_revision));
  for (const operation of queued) {
    // Pre-v4 entries have no proven route identity: never retarget them.
    if (!operation.assignment_id || operation.assignment_id !== operation.payload?.assignment_id) {
      setMessage("Старая офлайн-отгрузка не привязана к маршруту. Нужна проверка администратора; операция сохранена.", true);
      return false;
    }
    try {
      const data = await api(`/api/driver/order/stores/${encodeURIComponent(operation.store_id)}/complete`, {
        method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(operation.payload)
      });
      await dbDelete(QUEUE_STORE, operation.payload.operation_id);
      await cacheAssignment(data.assignment);
    } catch (error) {
      setMessage(error.message || "Отгрузка не отправлена. Операция сохранена на устройстве.", true);
      return false;
    }
  }
  return true;
}

async function loadOrder() {
  try {
    const data = await api("/api/driver/order");
    await cacheAssignment(data.assignment);
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
      view = "order";
      render();
      setMessage(error.message || "Не удалось загрузить заказ", true);
    }
  }
}

async function completeStore() {
  const store = selectedStore();
  if (!store || assignment?.loading_status === "waiting_loading") return;
  const measurements = {};
  let invalid = false;
  root().querySelectorAll("[data-measurement-input]").forEach((input) => {
    const lineId = input.dataset.lineId;
    measurements[lineId] ||= {};
    measurements[lineId][input.dataset.field] = input.value;
  });
  for (const measurement of Object.values(measurements)) {
    const net = measurementNet(measurement);
    if (net === "") invalid = true;
  }
  if (invalid || Object.keys(measurements).length !== (store.lines || []).length) {
    setMessage("Для каждой строки укажите целые ящики, неотрицательную тару и грязный вес не меньше тары", true);
    return;
  }
  const operationId = crypto.randomUUID();
  const payload = {measurements, operation_id: operationId, base_revision: assignment.revision, assignment_id: assignment.assignment_id};
  const button = root().querySelector("[data-complete]");
  button.disabled = true;
  try {
    // Persist before sending, including when the device believes it is online.
    await dbPut(QUEUE_STORE, operationId, {
      driver_id: driverId, assignment_id: assignment.assignment_id, store_id: store.store_id, payload
    });
    applyLocalCompletion(store, measurements);
    await dbPut(ORDER_STORE, driverId, assignment);
    await cacheReturnContext(localReturnContext(assignment));
    view = "order";
    render();
    setMessage("Отгрузка сохранена на устройстве и ожидает синхронизации.");
    if (online) await syncOrder();
  } catch (error) {
    button.disabled = false;
    setMessage(error.message || "Не удалось сохранить отгрузку на устройстве", true);
  }
}

function applyLocalCompletion(store, measurements) {
  store.status = "completed";
  store.completed_at = new Date().toISOString();
  for (const line of store.lines) {
    const measurement = {...measurements[line.line_id], net_weight_kg: measurementNet(measurements[line.line_id])};
    line.shipment_measurement = measurement;
    line.actual_qty = measurement.net_weight_kg;
  }
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
  if (syncing || loggingOut) return;
  syncing = true;
  let finishSync;
  syncFinished = new Promise((resolve) => { finishSync = resolve; });
  try {
    if (!csrfToken || !online) throw new Error("Нет связи с сервером. Изменения сохранены на устройстве.");
    const mileageReady = await flushMileageQueue();
    const shipments = (await dbAll(QUEUE_STORE)).filter((item) => item.driver_id === driverId);
    // Historical returns need no mileage for today, but cannot overtake shipments.
    if (shipments.length && (!mileageReady || !await flushQueue())) {
      throw new Error("Сначала отправьте пробег и все отгрузки. Возвраты сохранены и ждут синхронизации.");
    }
    await flushReturnQueue();
    if (mileageReady) {
      const data = await api("/api/driver/sync", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"});
      await cacheAssignment(data.assignment);
    }
    if (view === "returns") await loadReturnIndex();
    if (view === "return" && returnContext) await loadReturn(returnContext.assignment_id);
    render();
    setMessage("Данные синхронизированы");
  } catch (error) {
    if (error.status === 409 && error.mileage) {
      mileage = error.mileage;
      await saveSession();
    }
    render();
    setMessage(error.message || "Синхронизация недоступна", true);
  } finally {
    syncing = false;
    finishSync();
  }
}

async function logout() {
  loggingOut = true;
  await syncFinished;
  try { await api("/api/driver/logout", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"}); } catch (_) {}
  await clearOfflineData();
  loggingOut = false;
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
    await cacheAssignment(data.assignment);
    await saveSession();
    if (mileage?.required) {
      view = "order";
      render();
    } else if (assignment) {
      view = "order";
      render();
    } else {
      view = "order";
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
      view = "order";
      render();
    }
  }
}

function returnKey(assignmentId, owner = driverId) {
  return `${owner}:${assignmentId}`;
}

function returnFacts(context) {
  return Object.fromEntries((context?.lines || []).map((line) => [line.loading_line_id, {
    loaded_net_kg: String(line.loaded_net_kg), shipped_net_kg: String(line.shipped_net_kg)
  }]));
}

function sameReturnFacts(expected, context) {
  const actual = returnFacts(context);
  const ids = Object.keys(expected || {});
  return ids.length === Object.keys(actual).length && ids.every((id) => actual[id] &&
    ["loaded_net_kg", "shipped_net_kg"].every((field) => {
      const before = Number(expected[id][field]);
      const after = Number(actual[id][field]);
      return Number.isFinite(before) && Number.isFinite(after) && Math.abs(before - after) < 0.000001;
    }));
}

function localReturnContext(current) {
  if (!current?.return_context) return null;
  const context = structuredClone(current.return_context);
  const stores = current.stores || [];
  if (!context.loading_ready || !stores.length || !stores.every((store) => store.status === "completed")) return context;
  const shipped = new Map((context.lines || []).map((line) => [line.loading_line_id, 0]));
  for (const store of stores) {
    for (const line of store.lines || []) {
      const value = line.shipment_measurement?.net_weight_kg ?? line.actual_qty;
      if (!shipped.has(line.loading_line_id) || value == null || value === "" || !Number.isFinite(Number(value)) || Number(value) < 0) return context;
      shipped.set(line.loading_line_id, shipped.get(line.loading_line_id) + Number(value));
    }
  }
  context.complete = true;
  context.local_complete = true;
  context.lines = context.lines.map((line) => ({...line,
    shipped_net_kg: String(shipped.get(line.loading_line_id)),
    available_net_kg: String(Math.max(0, Number(line.loaded_net_kg) - shipped.get(line.loading_line_id)))
  }));
  return context;
}

async function cacheReturnContext(context) {
  if (!context?.assignment_id || !driverId) return;
  const key = returnKey(context.assignment_id);
  const previous = (await dbGet(RETURN_CACHE_STORE, key))?.context;
  // The order snapshot can lag a return review; never downgrade a known document.
  if ((previous?.document?.revision || 0) > (context.document?.revision || 0)) {
    context = {...context, document: previous.document, eligible: false};
  }
  await dbPut(RETURN_CACHE_STORE, key, {driver_id: driverId, context});
}

async function cacheAssignment(current) {
  assignment = current;
  if (!assignment) return;
  const queued = (await dbAll(QUEUE_STORE)).filter((item) => item.driver_id === driverId && item.assignment_id === assignment.assignment_id);
  queued.sort((a, b) => Number(a.payload.base_revision) - Number(b.payload.base_revision));
  for (const operation of queued) {
    const store = assignment.stores?.find((item) => item.store_id === operation.store_id);
    if (store && store.status !== "completed") applyLocalCompletion(store, operation.payload.measurements);
  }
  await dbPut(ORDER_STORE, driverId, assignment);
  await cacheReturnContext(localReturnContext(assignment));
}

function returnStatus(status) {
  return ({submitted: "Отправлен на проверку", accepted: "Принят", rejected: "Отклонён", queued: "Ожидает отправки", draft: "Черновик"})[status] || "Возврат";
}

function editableReturn(context) {
  const status = context?.document?.status;
  return Boolean(context && (context.eligible || (context.loading_ready && context.local_complete)) && context.complete && (!status || status === "rejected"));
}

function documentLines(doc) {
  if (Array.isArray(doc?.lines)) return doc.lines;
  return Object.entries(doc?.lines || {}).map(([id, line]) => ({loading_line_id: id, ...line}));
}

function draftFromContext(context) {
  const lines = {};
  for (const line of documentLines(context.document)) {
    const measure = line.measurement || line;
    lines[line.loading_line_id] = {
      selected: true,
      box_count: String(measure.box_count ?? ""),
      tare_weight_per_box_kg: String(measure.tare_weight_per_box_kg ?? ""),
      gross_weight_kg: String(measure.gross_weight_kg ?? ""),
      reason: line.reason || "", comment: line.comment || ""
    };
  }
  return {driver_id: driverId, assignment_id: context.assignment_id,
    base_revision: context.document?.revision || 0, expected_facts: returnFacts(context), lines};
}

async function loadReturnIndex() {
  const cached = await dbGet(RETURN_CACHE_STORE, `${driverId}:index`);
  returnIndex = cached?.index || {returns: [], assignments: []};
  let fetchError = null;
  if (online) {
    try {
      const data = await api("/api/driver/returns");
      returnIndex = {returns: data.returns || [], assignments: data.assignments || []};
      await dbPut(RETURN_CACHE_STORE, `${driverId}:index`, {driver_id: driverId, index: returnIndex});
    } catch (error) {
      if (error.status === 401 || error.status === 403) throw error;
      fetchError = error;
    }
  }
  const contexts = (await dbAll(RETURN_CACHE_STORE)).filter((item) => item.driver_id === driverId && item.context);
  const known = new Set(returnIndex.assignments.map((item) => item.assignment_id));
  for (const {context} of contexts) {
    if (!known.has(context.assignment_id)) {
      returnIndex.assignments.push({assignment_id: context.assignment_id, route_label: context.route_label});
      known.add(context.assignment_id);
    }
    if (context.document) {
      const index = returnIndex.returns.findIndex((doc) => doc.assignment_id === context.assignment_id);
      if (index < 0) returnIndex.returns.push(context.document);
      else if (Number(context.document.revision) > Number(returnIndex.returns[index].revision)) returnIndex.returns[index] = context.document;
    }
  }
  returnIndex.drafts = (await dbAll(RETURN_DRAFT_STORE)).filter((item) => item.driver_id === driverId);
  returnIndex.queued = (await dbAll(RETURN_QUEUE_STORE)).filter((item) => item.driver_id === driverId);
  if (fetchError) throw fetchError;
}

async function openReturns() {
  try {
    await returnSave;
    await cacheReturnContext(localReturnContext(assignment));
    await loadReturnIndex();
    view = "returns";
    render();
  } catch (error) {
    view = "returns";
    render();
    setMessage(error.message || "Не удалось обновить историю. Показана сохранённая копия.", true);
  }
}

async function loadReturn(assignmentId) {
  const key = returnKey(assignmentId);
  let context = (await dbGet(RETURN_CACHE_STORE, key))?.context;
  let error = null;
  if (online) {
    try {
      const data = await api(`/api/driver/returns/${encodeURIComponent(assignmentId)}`);
      context = data.context;
      await cacheReturnContext(context);
    } catch (failure) {
      if (failure.status === 401 || failure.status === 403 || failure.status === 404) throw failure;
      error = failure;
    }
  }
  if (assignment?.assignment_id === assignmentId) {
    const local = localReturnContext(assignment);
    const pending = (await dbAll(QUEUE_STORE)).some((item) => item.driver_id === driverId && item.assignment_id === assignmentId);
    if (local?.local_complete && pending && (!context || sameReturnFacts(returnFacts(assignment.return_context), context))) {
      context = {...local, document: context?.document || local.document};
    }
  }
  if (!context) throw error || new Error("Для этого маршрута нет сохранённых данных. Подключитесь к серверу.");
  returnContext = context;
  returnOperation = await dbGet(RETURN_QUEUE_STORE, key) || null;
  returnDraft = await dbGet(RETURN_DRAFT_STORE, key) || draftFromContext(context);
  if (!returnOperation && context.document?.status === "rejected" && returnDraft.base_revision !== context.document.revision) returnDraft = draftFromContext(context);
  return error;
}

async function openReturn(assignmentId) {
  try {
    await returnSave;
    await cacheReturnContext(localReturnContext(assignment));
    const error = await loadReturn(assignmentId);
    view = "return";
    render();
    if (error) setMessage("Сервер недоступен. Показана сохранённая копия; черновик сохраняется на устройстве.", true);
  } catch (error) {
    setMessage(error.message || "Не удалось открыть возврат", true);
  }
}

function renderReturns() {
  const rows = new Map((returnIndex.assignments || []).map((item) => [item.assignment_id, {...item}]));
  for (const doc of returnIndex.returns || []) rows.set(doc.assignment_id, {...rows.get(doc.assignment_id), ...doc});
  for (const draft of returnIndex.drafts || []) {
    const row = rows.get(draft.assignment_id) || {assignment_id: draft.assignment_id};
    if (!row.status || row.status === "rejected") row.local_status = "draft";
    rows.set(draft.assignment_id, row);
  }
  for (const operation of returnIndex.queued || []) {
    const row = rows.get(operation.assignment_id) || {assignment_id: operation.assignment_id};
    row.local_status = "queued";
    rows.set(operation.assignment_id, row);
  }
  root().innerHTML = `<div class="driver-app-frame">${appHeader(true)}<main class="driver-shell driver-returns">
    <header class="driver-header"><button data-return-back class="driver-secondary" type="button">К маршруту</button><h1>Возвраты</h1></header>
    <p class="driver-muted">Остатки после завершения всех магазинов. Доступны и предыдущие маршруты.</p>
    <section class="driver-panel driver-return-list">${rows.size ? [...rows.values()].map((row) => `<button class="driver-return-entry" data-return-id="${esc(row.assignment_id)}" type="button">
      <strong>${esc(row.route_label || row.assignment_id)}</strong><span>${esc(row.order_number || "")}</span>
      <span>${esc(row.local_status ? returnStatus(row.local_status) : (row.status ? returnStatus(row.status) : "Оформить возврат"))}</span>
      ${row.total_net_kg != null ? `<span>${esc(row.total_net_kg)} кг</span>` : ""}
      <small>${esc(row.submitted_at || row.created_at || "")}</small></button>`).join("") : '<p class="driver-muted">Нет доступных маршрутов или возвратов.</p>'}</section>
    <button data-return-sync class="driver-primary" type="button">Синхронизировать</button><p data-message class="driver-message" role="status"></p>
    </main></div>`;
  bindFrameActions();
  root().querySelector("[data-return-back]").addEventListener("click", () => { view = "order"; render(); });
  root().querySelector("[data-return-sync]").addEventListener("click", syncOrder);
  root().querySelectorAll("[data-return-id]").forEach((button) => button.addEventListener("click", () => openReturn(button.dataset.returnId)));
}

function renderReturn() {
  if (!returnContext) { view = "returns"; renderReturns(); return; }
  const context = returnContext;
  const doc = context.document;
  const editable = editableReturn(context) && !returnOperation;
  const changed = returnDraft && !sameReturnFacts(returnDraft.expected_facts, context);
  const locked = doc && ["submitted", "accepted"].includes(doc.status);
  const entries = locked ? documentLines(doc) : context.lines || [];
  const lines = entries.map((source) => {
    const id = source.loading_line_id;
    const saved = returnDraft?.lines[id] || {};
    const measure = source.measurement || source;
    if (locked) return `<section class="driver-return-line"><h2>${esc(source.name || id)}</h2>
      <p>Ящики: ${esc(measure.box_count)} · Тара: ${esc(measure.tare_weight_per_box_kg)} кг/ящ. · Грязный вес: ${esc(measure.gross_weight_kg)} кг</p>
      <p>Нетто: ${esc(measure.net_weight_kg ?? measurementNet(measure))} кг</p><p>${esc(source.reason)}${source.comment ? ` — ${esc(source.comment)}` : ""}</p></section>`;
    const noRemainder = Number(source.available_net_kg) <= 0;
    return `<section class="driver-return-line" data-return-line="${esc(id)}">
      <label class="driver-return-select"><input data-return-selected type="checkbox" ${saved.selected ? "checked" : ""} ${!editable || (noRemainder && !saved.selected) ? "disabled" : ""}><strong>${esc(source.name)}</strong></label>
      <p class="driver-muted">План: ${esc(source.planned_kg)} кг · Загружено: ${esc(source.loaded_net_kg)} кг · Отгружено: ${esc(source.shipped_net_kg)} кг · Доступно: ${esc(source.available_net_kg)} кг</p>
      <fieldset ${!editable || !saved.selected ? "disabled" : ""}><legend class="driver-muted">Параметры возврата</legend>
        <div class="driver-return-measurements">
          <label>Ящики<input data-return-field="box_count" type="number" inputmode="numeric" min="0" step="1" value="${esc(saved.box_count || "")}" required></label>
          <label>Тара, кг/ящ.<input data-return-field="tare_weight_per_box_kg" type="number" inputmode="decimal" min="0" step="any" value="${esc(saved.tare_weight_per_box_kg || "")}" required></label>
          <label>Грязный вес, кг<input data-return-field="gross_weight_kg" type="number" inputmode="decimal" min="0" step="any" value="${esc(saved.gross_weight_kg || "")}" required></label>
        </div>
        <output>Нетто: ${esc(measurementNet(saved) || "—")} кг</output>
        <label>Причина<select data-return-field="reason" required><option value="">Выберите причину</option>${(context.reasons || []).map((reason) => `<option value="${esc(reason)}" ${saved.reason === reason ? "selected" : ""}>${esc(reason)}</option>`).join("")}</select></label>
        <label>Комментарий <small>(обязателен для «Другое»)</small><textarea data-return-field="comment" rows="2" maxlength="2000">${esc(saved.comment || "")}</textarea></label>
      </fieldset></section>`;
  }).join("");
  root().innerHTML = `<div class="driver-app-frame">${appHeader(true)}<main class="driver-shell driver-returns">
    <header class="driver-header"><button data-return-back class="driver-secondary" type="button">К возвратам</button><div><h1>Возврат остатка</h1><p class="driver-muted">${esc(context.route_label || context.assignment_id)}</p></div></header>
    <section class="driver-panel driver-return-document"><p class="driver-return-status">${esc(returnOperation ? returnStatus("queued") : (doc ? returnStatus(doc.status) : "Черновик"))}${doc ? ` · Версия ${esc(doc.version ?? doc.revision)} · ${esc(doc.total_net_kg)} кг` : ""}</p>
      ${doc?.submitted_at ? `<p class="driver-muted">Отправлен: ${esc(doc.submitted_at)}</p>` : ""}
      ${!editable && !locked && !returnOperation ? `<p class="driver-message driver-message-error">${esc(context.error || "Сначала завершите все магазины. Нужна подтверждённая загрузка.")}</p>` : ""}
      ${changed && !locked ? '<p class="driver-message driver-message-error">Основа черновика изменилась. Проверьте новые остатки.</p>' : ""}
      ${returnOperation ? `<p class="driver-muted">${returnOperation.server_rejected ? "Сервер отклонил документ. Проверьте данные и продолжите редактирование." : returnOperation.sent_body ? "Отправка начата. При повторе будет отправлен тот же документ без изменений." : "Документ ждёт отправки всех отгрузок."}</p>` : ""}
      <form data-return-form class="driver-return-form">${lines || '<p class="driver-muted">Нет товаров для возврата.</p>'}
        ${editable ? '<button data-return-submit class="driver-primary" type="submit">Отправить возврат на проверку</button>' : ""}</form>
      ${!locked && ((changed && !returnOperation) || (returnOperation && (!returnOperation.sent_body || returnOperation.server_rejected))) ? '<button data-return-rebase class="driver-secondary" type="button">Проверить остатки и продолжить редактирование</button>' : ""}
      <p data-return-saved class="driver-muted">${returnDraft && !locked ? "Черновик автоматически сохраняется на этом устройстве" : ""}</p>
      ${doc?.history?.length ? `<h2>История</h2><ol class="driver-return-history">${doc.history.map((event) => `<li><strong>${esc(returnStatus(event.kind))}</strong> · ${esc(event.at)} · ${esc(typeof event.actor === "object" ? (event.actor?.name || event.actor?.id || event.actor?.kind || "") : event.actor)}${event.comment ? `<p>${esc(event.comment)}</p>` : ""}</li>`).join("")}</ol>` : ""}
      <button data-return-sync class="driver-secondary" type="button">Синхронизировать</button>
      <p data-message class="driver-message ${returnOperation?.error ? "driver-message-error" : ""}" role="status">${esc(returnOperation?.error || "")}</p>
    </section></main></div>`;
  bindFrameActions();
  root().querySelector("[data-return-back]").addEventListener("click", openReturns);
  root().querySelector("[data-return-sync]").addEventListener("click", syncOrder);
  root().querySelector("[data-return-form]").addEventListener("submit", submitReturn);
  root().querySelectorAll("[data-return-selected], [data-return-field]").forEach((input) => input.addEventListener("input", updateReturnDraft));
  root().querySelector("[data-return-rebase]")?.addEventListener("click", rebaseReturnDraft);
}

async function rebaseReturnDraft() {
  if ((returnOperation?.sent_body && !returnOperation.server_rejected) || syncing) return;
  try {
    await returnSave;
    if (returnOperation?.server_rejected) {
      if (!online) throw new Error("Подключитесь к серверу, чтобы проверить отклонённый документ.");
      const {context} = await api(`/api/driver/returns/${encodeURIComponent(returnContext.assignment_id)}`);
      await cacheReturnContext(context);
      returnContext = context;
      render();
    }
    if (["submitted", "accepted"].includes(returnContext.document?.status)) {
      setMessage("На сервере уже есть отправленный или принятый возврат. Он доступен только для просмотра.", true);
      return;
    }
    if (!window.confirm("Проверьте показанные остатки. Вернуть неотправленный или отклонённый сервером документ в черновик и использовать эти данные?")) return;
    returnDraft.expected_facts = returnFacts(returnContext);
    returnDraft.base_revision = returnContext.document?.revision || 0;
    await saveReturnDraft();
    // Explicit driver recovery only: preserve entered lines, then create a new ID on submit.
    await dbDelete(RETURN_QUEUE_STORE, returnKey(returnContext.assignment_id));
    returnOperation = null;
    render();
  } catch (error) {
    setMessage(error.message || "Не удалось обновить черновик", true);
  }
}

function validateReturnDraft(draft, context) {
  if (!editableReturn(context)) throw new Error(context.error || "Возврат доступен после завершения всех магазинов и подтверждения загрузки.");
  const lines = {};
  for (const [id, line] of Object.entries(draft.lines || {})) {
    if (!line.selected) continue;
    const source = context.lines?.find((item) => item.loading_line_id === id);
    const fields = ["box_count", "tare_weight_per_box_kg", "gross_weight_kg"];
    if (fields.some((field) => String(line[field] ?? "").trim() === "")) throw new Error("Заполните ящики, тару и грязный вес выбранных товаров.");
    const netText = measurementNet(line);
    const net = Number(netText);
    if (!source || netText === "" || net <= 0 || !Number.isFinite(Number(source.available_net_kg)) || net - Number(source.available_net_kg) > 0.000001) throw new Error("Нетто возврата должно быть больше нуля и не превышать загруженный остаток после отгрузок.");
    if (!(context.reasons || []).includes(line.reason)) throw new Error("Укажите причину для каждого выбранного товара.");
    if (line.reason === "Другое" && !String(line.comment || "").trim()) throw new Error("Для причины «Другое» заполните комментарий.");
    lines[id] = Object.fromEntries([...fields, "reason", "comment"].map((field) => [field, String(line[field] ?? "").trim()]));
  }
  if (!Object.keys(lines).length) throw new Error("Выберите хотя бы один товар для возврата.");
  return lines;
}

function saveReturnDraft() {
  const snapshot = structuredClone(returnDraft);
  returnSave = returnSave.catch(() => {}).then(() => dbPut(RETURN_DRAFT_STORE, returnKey(snapshot.assignment_id, snapshot.driver_id), snapshot));
  returnSave.then(() => {
    if (returnDraft?.assignment_id === snapshot.assignment_id) {
      const note = root()?.querySelector("[data-return-saved]");
      if (note) note.textContent = "Черновик сохранён на устройстве";
    }
  }).catch(() => setMessage("Не удалось сохранить черновик на устройстве. Не закрывайте страницу.", true));
  return returnSave;
}

function updateReturnDraft() {
  if (!returnDraft || returnOperation) return;
  root().querySelectorAll("[data-return-line]").forEach((section) => {
    const line = returnDraft.lines[section.dataset.returnLine] ||= {};
    line.selected = section.querySelector("[data-return-selected]").checked;
    section.querySelectorAll("[data-return-field]").forEach((input) => { line[input.dataset.returnField] = input.value; });
    section.querySelector("fieldset").disabled = !line.selected;
    const net = measurementNet(line);
    section.querySelector("output").textContent = net === "" ? "Нетто: —" : `Нетто: ${net} кг`;
  });
  saveReturnDraft();
}

async function submitReturn(event) {
  event.preventDefault();
  if (returnOperation) return;
  const button = root().querySelector("[data-return-submit]");
  button.disabled = true;
  try {
    updateReturnDraft();
    await returnSave;
    const lines = validateReturnDraft(returnDraft, returnContext);
    if (!sameReturnFacts(returnDraft.expected_facts, returnContext)) throw new Error("Загрузка или отгрузки изменились. Проверьте остатки и обновите основу черновика.");
    const operation = {driver_id: driverId, assignment_id: returnContext.assignment_id,
      expected_facts: structuredClone(returnDraft.expected_facts), created_at: new Date().toISOString(),
      payload: {operation_id: crypto.randomUUID(), base_revision: returnDraft.base_revision, facts_token: "", lines}};
    await dbPut(RETURN_QUEUE_STORE, returnKey(operation.assignment_id), operation);
    returnOperation = operation;
    render();
    setMessage("Возврат сохранён в очереди. Он будет отправлен после всех отгрузок.");
    if (online) await syncOrder();
  } catch (error) {
    button.disabled = false;
    setMessage(error.message || "Не удалось сохранить возврат", true);
  }
}

async function flushReturnQueue() {
  if (!csrfToken || !online) return;
  if ((await dbAll(QUEUE_STORE)).some((item) => item.driver_id === driverId)) throw new Error("Возвраты ожидают отправки всех отгрузок.");
  const queued = (await dbAll(RETURN_QUEUE_STORE)).filter((item) => item.driver_id === driverId);
  queued.sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)));
  for (const operation of queued) {
    const key = returnKey(operation.assignment_id);
    const path = `/api/driver/returns/${encodeURIComponent(operation.assignment_id)}`;
    let posting = false;
    try {
      if (operation.server_rejected) throw new Error(operation.error || "Сервер отклонил документ. Требуется проверка и редактирование.");
      if (!operation.sent_body) {
        const {context} = await api(path);
        await cacheReturnContext(context);
        if (returnContext?.assignment_id === operation.assignment_id) returnContext = context;
        if (!context?.eligible || !context.complete) throw new Error(context?.error || "Маршрут ещё не готов к возврату на сервере.");
        if (!sameReturnFacts(operation.expected_facts, context)) throw new Error("Загрузка или отгрузки изменились. Возврат сохранён; проверьте остатки перед повторной отправкой.");
        if ((context.document?.revision || 0) !== operation.payload.base_revision) throw new Error("Версия возврата изменилась. Обновите данные перед отправкой.");
        validateReturnDraft({lines: Object.fromEntries(Object.entries(operation.payload.lines).map(([id, line]) => [id, {...line, selected: true}]))}, context);
        operation.payload.facts_token = context.facts_token;
        operation.sent_body = JSON.stringify(operation.payload);
        // Persist exact bytes before POST; a lost response must replay them unchanged.
        await dbPut(RETURN_QUEUE_STORE, key, operation);
      }
      posting = true;
      const data = await api(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: operation.sent_body});
      if (!data.ok || !data.document) throw new Error("Сервер не подтвердил сохранение возврата.");
      const cached = (await dbGet(RETURN_CACHE_STORE, key))?.context;
      if (cached) await cacheReturnContext({...cached, document: data.document, eligible: false});
      await dbDelete(RETURN_DRAFT_STORE, key);
      await dbDelete(RETURN_QUEUE_STORE, key);
      if (returnContext?.assignment_id === operation.assignment_id) {
        returnContext = {...returnContext, document: data.document, eligible: false};
        returnDraft = null;
        returnOperation = null;
      }
    } catch (error) {
      operation.error = error.message || "Не удалось отправить возврат";
      if (posting && [400, 409].includes(error.status)) operation.server_rejected = error.status;
      await dbPut(RETURN_QUEUE_STORE, key, operation);
      if (returnContext?.assignment_id === operation.assignment_id) returnOperation = operation;
      if (posting && operation.server_rejected) {
        try {
          const {context} = await api(path);
          await cacheReturnContext(context);
          if (returnContext?.assignment_id === operation.assignment_id) returnContext = context;
        } catch (_) {
          // Keep the rejected operation and draft; rebase requires a fresh context.
        }
      }
      throw error;
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
restoreSession();
