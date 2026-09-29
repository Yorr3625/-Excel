let csrfToken = "";
let loader = null;
let vehicles = [];
let selectedVehicleId = "";
let assignments = [];
let view = "login";

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

function root() {
  return document.getElementById("loader-app");
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
  const element = root()?.querySelector("[data-message]");
  if (element) {
    element.textContent = message || "";
    element.className = error ? "driver-message driver-message-error" : "driver-message";
  }
}

async function api(path, options = {}) {
  const headers = {...(options.headers || {})};
  if (options.method && options.method !== "GET") headers["X-Loader-CSRF"] = csrfToken;
  const response = await fetch(await apiUrl(path), {...options, headers, credentials: "include"});
  let data = {};
  try { data = await response.json(); } catch (_) {}
  if (!response.ok) {
    const error = new Error(data.error || `HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return data;
}

function render() {
  if (!root()) return;
  if (view === "login") renderLogin();
  else if (view === "vehicles") renderVehicles();
  else renderOrders();
}

function renderLogin() {
  root().innerHTML = `
    <main class="driver-shell driver-login-shell">
      <section class="driver-panel driver-login-panel">
        <img class="driver-logo" src="/icon-192.svg" alt="Логистика">
        <h1>Рабочее место грузчика</h1>
        <p class="driver-muted">Войдите по индивидуальному коду и PIN-коду</p>
        <form data-login-form class="driver-form">
          <label>Код сотрудника<input name="loader_id" autocomplete="username" required maxlength="128"></label>
          <label>PIN-код<input name="pin" type="password" inputmode="numeric" autocomplete="current-password" required minlength="4" maxlength="12"></label>
          <button class="driver-primary" type="submit">Войти</button>
        </form>
        <p data-message class="driver-message"></p>
      </section>
    </main>`;
  root().querySelector("[data-login-form]").addEventListener("submit", login);
}

function renderVehicles() {
  const cards = vehicles.map((vehicle) => `<button class="driver-store" data-vehicle-id="${esc(vehicle.id)}">
    <span>${esc([vehicle.name, vehicle.plate].filter(Boolean).join(" · "))}</span><strong>Открыть</strong>
  </button>`).join("");
  root().innerHTML = `
    <main class="driver-shell">
      <header class="driver-header"><div><h1>Выберите машину</h1><p class="driver-muted">Доступны машины с текущими назначениями</p></div><button data-logout class="driver-secondary">Выйти</button></header>
      <p data-message class="driver-message"></p>
      <section class="driver-panel"><div class="driver-store-list">${cards || "<p class=\"driver-muted\">Сейчас нет доступных назначений</p>"}</div></section>
    </main>`;
  root().querySelector("[data-logout]").addEventListener("click", logout);
  root().querySelectorAll("[data-vehicle-id]").forEach((button) => {
    button.addEventListener("click", () => selectVehicle(button.dataset.vehicleId));
  });
}

function assignmentCard(assignment) {
  const storeCards = (assignment.stores || []).map((store) => {
    const lines = (store.lines || []).map((line) => `<tr><td>${esc(line.name)}</td><td>${esc(line.unit)}</td><td>${numberText(line.required_qty)}</td></tr>`).join("");
    return `<section class="driver-panel"><h2>${esc(store.name)}</h2><p class="driver-muted">${store.status === "completed" ? "Магазин выполнен" : "Запланирован"}</p><div class="driver-table-wrap"><table class="driver-table"><thead><tr><th>Товар</th><th>Ед.</th><th>План</th></tr></thead><tbody>${lines}</tbody></table></div></section>`;
  }).join("");
  return `<section class="driver-panel"><h2>${esc(assignment.route_label || "Маршрут")}</h2><p class="driver-muted">${esc(assignment.driver_name || "Водитель не указан")}</p></section>${storeCards}`;
}

function renderOrders() {
  const vehicle = vehicles.find((item) => item.id === selectedVehicleId) || {};
  root().innerHTML = `
    <main class="driver-shell">
      <header class="driver-header"><div><h1>${esc([vehicle.name, vehicle.plate].filter(Boolean).join(" · ") || "Выбранная машина")}</h1><p class="driver-muted">Заказы доступны только для этой машины</p></div><div><button data-change class="driver-secondary">Сменить</button> <button data-logout class="driver-secondary">Выйти</button></div></header>
      <p data-message class="driver-message"></p>
      <div class="driver-store-list">${assignments.map(assignmentCard).join("") || "<p class=\"driver-muted\">Для машины нет текущих назначений</p>"}</div>
    </main>`;
  root().querySelector("[data-change]").addEventListener("click", () => { view = "vehicles"; render(); });
  root().querySelector("[data-logout]").addEventListener("click", logout);
}

async function login(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const button = event.currentTarget.querySelector("button");
  button.disabled = true;
  setMessage("Проверяем данные…");
  try {
    const data = await api("/api/loader/login", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({loader_id: form.get("loader_id"), pin: form.get("pin")})
    });
    loader = data.loader;
    csrfToken = data.csrf_token;
    await loadVehicles();
  } catch (error) {
    setMessage(error.message || "Ошибка входа", true);
    button.disabled = false;
  }
}

async function loadVehicles() {
  try {
    const data = await api("/api/loader/vehicles");
    vehicles = data.vehicles || [];
    view = "vehicles";
    render();
  } catch (error) {
    view = "login";
    render();
    setMessage(error.message || "Не удалось загрузить машины", true);
  }
}

async function selectVehicle(vehicleId) {
  try {
    await api("/api/loader/vehicle", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({vehicle_id: vehicleId})
    });
    selectedVehicleId = vehicleId;
    const data = await api("/api/loader/orders");
    assignments = data.assignments || [];
    view = "orders";
    render();
  } catch (error) {
    setMessage(error.message || "Не удалось открыть назначения", true);
  }
}

async function logout() {
  try {
    await api("/api/loader/logout", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: "{}"
    });
  } catch (_) {}
  csrfToken = "";
  loader = null;
  vehicles = [];
  selectedVehicleId = "";
  assignments = [];
  view = "login";
  render();
}

async function restoreSession() {
  try {
    const data = await api("/api/loader/me");
    loader = data.loader;
    csrfToken = data.csrf_token || "";
    selectedVehicleId = data.vehicle_id || "";
    const vehicleData = await api("/api/loader/vehicles");
    vehicles = vehicleData.vehicles || [];
    if (selectedVehicleId && vehicles.some((vehicle) => vehicle.id === selectedVehicleId)) {
      const ordersData = await api("/api/loader/orders");
      assignments = ordersData.assignments || [];
      view = "orders";
    } else {
      selectedVehicleId = "";
      view = "vehicles";
    }
  } catch (_) {
    view = "login";
  }
  render();
}

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/service-worker.js").catch(() => {});
restoreSession();
