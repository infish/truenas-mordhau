"use strict";

const state = {
  modes: [],          // [{prefix, label, maps: [...]}]
  activeMode: null,
  selectedMap: null,
  liveMap: null,
  rotation: [],
  defaultMap: null,
  dirty: false,       // rotation editor has unsaved edits
  restartPending: false,
};

const $ = (id) => document.getElementById(id);

function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  Object.assign(node, props);
  for (const child of children) node.append(child);
  return node;
}

async function api(method, path, body) {
  const options = { method, headers: { "X-Panel-Request": "1" } };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  // location.origin drops any user:pass@ from the address bar, which fetch rejects.
  const response = await fetch(new URL(path, location.origin), options);
  if (response.status === 401) {
    // Session expired: reloading shows the login page.
    location.reload();
    throw new Error("Not logged in");
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return data;
}

function notify(message, isError = false) {
  const box = $("notice");
  box.textContent = message;
  box.classList.toggle("error", isError);
  box.hidden = false;
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => { box.hidden = true; }, isError ? 10000 : 5000);
}

function shortName(map) {
  return map.includes("_") ? map.slice(map.indexOf("_") + 1) : map;
}

// Steam query reports the display name ("The Pit"), not the level name, so
// compare letters only against the part after the mode prefix.
function looseName(name) {
  return name.toLowerCase().replace(/[^a-z0-9]/g, "");
}

function isLiveMap(map) {
  if (!state.liveMap) return false;
  return map === state.liveMap || looseName(shortName(map)) === looseName(state.liveMap);
}

function allMaps() {
  return state.modes.flatMap((mode) => mode.maps);
}

// ---- Status --------------------------------------------------------------

async function refreshStatus() {
  let data;
  try {
    data = await api("GET", "/api/status");
  } catch (error) {
    setStatus("offline", `Panel error: ${error.message}`);
    return;
  }
  const server = data.server;
  if (server.online) {
    state.liveMap = server.map;
    setStatus("online", `${server.name} · ${server.map} · ${server.players}/${server.max_players} players`);
  } else {
    state.liveMap = null;
    setStatus("offline", "Server offline or starting");
  }
  $("rcon-warning").hidden = data.rcon_configured;
  applySettings(data.settings);
  renderMapGrid();
}

function setStatus(kind, text) {
  $("status").className = `status status-${kind}`;
  $("status-text").textContent = text;
}

function applySettings(settings) {
  const wasPending = state.restartPending;
  state.restartPending = settings.restart_pending;
  $("restart-pending").hidden = !settings.restart_pending;
  if (wasPending && !settings.restart_pending) notify("Server restarted with the new settings.");

  const { effective, saved } = settings;
  let summary = effective
    ? `Running with: start on ${effective.default_map}, rotation ${effective.rotation.join(" → ")}.`
    : "The server has not reported its settings yet (it writes them when it starts).";
  const savedDiffers = saved && (!effective || saved.default_map !== effective.default_map
    || saved.rotation.join(",") !== effective.rotation.join(","));
  if (savedDiffers && !settings.restart_pending) summary += " Saved changes are waiting for a restart.";
  $("running-with").textContent = summary;

  if (state.dirty) return;
  const source = settings.saved || effective;
  const unchanged = source && source.default_map === state.defaultMap
    && source.rotation.join(",") === state.rotation.join(",");
  if (source && !unchanged) {
    state.rotation = [...source.rotation];
    state.defaultMap = source.default_map;
    renderRotation();
  }
}

// ---- Change map now ------------------------------------------------------

async function loadMaps(refresh = false) {
  try {
    const data = await api("GET", `/api/maps${refresh ? "?refresh=true" : ""}`);
    state.modes = data.modes;
    if (data.errors.length) console.warn("Map discovery errors", data.errors);
  } catch (error) {
    notify(`Could not load maps: ${error.message}`, true);
  }
  if (!state.modes.some((m) => m.prefix === state.activeMode)) {
    state.activeMode = state.modes[0]?.prefix ?? null;
  }
  renderModes();
  renderMapGrid();
  renderAddControls();
  renderRotation();
}

function renderModes() {
  const container = $("modes");
  container.replaceChildren(...state.modes.map((mode) => {
    const chip = el("button", {
      className: "chip",
      textContent: mode.label,
      title: `${mode.prefix}_ maps`,
    });
    chip.setAttribute("role", "tab");
    chip.setAttribute("aria-selected", String(mode.prefix === state.activeMode));
    chip.addEventListener("click", () => {
      state.activeMode = mode.prefix;
      renderModes();
      renderMapGrid();
    });
    return chip;
  }));
}

function renderMapGrid() {
  const grid = $("map-grid");
  const mode = state.modes.find((m) => m.prefix === state.activeMode);
  if (!mode) {
    grid.replaceChildren(el("p", {
      className: "empty",
      textContent: "No maps found yet. They appear once the server files are installed (first start).",
    }));
    updateChangeButton();
    return;
  }
  grid.replaceChildren(...mode.maps.map((map) => {
    const button = el("button", { textContent: shortName(map), title: map });
    button.setAttribute("aria-pressed", String(map === state.selectedMap));
    if (isLiveMap(map)) button.classList.add("current");
    button.addEventListener("click", () => {
      state.selectedMap = map;
      $("custom-map").value = "";
      renderMapGrid();
    });
    return button;
  }));
  updateChangeButton();
}

function targetMap() {
  return $("custom-map").value.trim() || state.selectedMap;
}

function updateChangeButton() {
  const map = targetMap();
  const button = $("change-btn");
  button.disabled = !map;
  button.textContent = map ? `Change to ${map}` : "Pick a map";
}

async function changeMap() {
  const map = targetMap();
  if (!map) return;
  const button = $("change-btn");
  button.disabled = true;
  try {
    const result = await api("POST", "/api/changelevel", { map });
    notify(`Changing to ${map}. ${result.output || ""}`.trim());
    setTimeout(refreshStatus, 4000);
  } catch (error) {
    notify(`Map change failed: ${error.message}`, true);
  } finally {
    updateChangeButton();
  }
}

// ---- Rotation editor -----------------------------------------------------

function markDirty() {
  state.dirty = true;
  renderRotation();
}

function renderRotation() {
  const list = $("rotation");
  list.replaceChildren(...state.rotation.map((map, index) => {
    const up = el("button", { textContent: "↑", title: "Move up", disabled: index === 0 });
    const down = el("button", { textContent: "↓", title: "Move down", disabled: index === state.rotation.length - 1 });
    const remove = el("button", { textContent: "✕", title: "Remove", disabled: state.rotation.length === 1 });
    up.addEventListener("click", () => { swap(index, index - 1); });
    down.addEventListener("click", () => { swap(index, index + 1); });
    remove.addEventListener("click", () => { state.rotation.splice(index, 1); markDirty(); });
    return el("li", {}, [el("span", { className: "name", textContent: map }), up, down, remove]);
  }));

  const select = $("default-map");
  const options = new Set([...state.rotation, ...allMaps()]);
  if (state.defaultMap) options.add(state.defaultMap);
  select.replaceChildren(...[...options].map((map) => el("option", { value: map, textContent: map })));
  if (state.defaultMap) select.value = state.defaultMap;
}

function swap(a, b) {
  [state.rotation[a], state.rotation[b]] = [state.rotation[b], state.rotation[a]];
  markDirty();
}

function renderAddControls() {
  const modeSelect = $("add-mode");
  const previous = modeSelect.value;
  modeSelect.replaceChildren(...state.modes.map((mode) =>
    el("option", { value: mode.prefix, textContent: mode.label })));
  if (state.modes.some((m) => m.prefix === previous)) modeSelect.value = previous;
  renderAddMaps();
}

function renderAddMaps() {
  const mode = state.modes.find((m) => m.prefix === $("add-mode").value);
  $("add-map").replaceChildren(...(mode ? mode.maps : []).map((map) =>
    el("option", { value: map, textContent: shortName(map) })));
  $("add-btn").disabled = !mode;
}

async function saveSettings(restart) {
  const defaultMap = $("default-map").value;
  if (!state.rotation.length) {
    notify("Add at least one map to the rotation.", true);
    return;
  }
  if (restart && !confirm("Restart the server now? Everyone on it will be disconnected for about a minute.")) return;
  try {
    const settings = await api("PUT", "/api/settings", { default_map: defaultMap, rotation: state.rotation, restart });
    state.dirty = false;
    applySettings(settings);
    notify(restart ? "Saved. Restarting the server…" : "Saved. Applies on the next server restart.");
  } catch (error) {
    notify(`Save failed: ${error.message}`, true);
  }
}

async function resetSettings() {
  if (!confirm("Remove the panel's rotation settings and go back to the TrueNAS app values on the next restart?")) return;
  try {
    const settings = await api("DELETE", "/api/settings");
    state.dirty = false;
    applySettings(settings);
    notify("Panel settings removed. The app defaults apply on the next restart.");
  } catch (error) {
    notify(`Reset failed: ${error.message}`, true);
  }
}

// ---- Console -------------------------------------------------------------

async function sendCommand(command) {
  const output = $("console-output");
  output.textContent += `> ${command}\n`;
  try {
    const result = await api("POST", "/api/console", { command });
    output.textContent += `${result.output || "(no output)"}\n\n`;
  } catch (error) {
    output.textContent += `Error: ${error.message}\n\n`;
  }
  output.scrollTop = output.scrollHeight;
}

// ---- Wiring --------------------------------------------------------------

$("change-btn").addEventListener("click", changeMap);
$("logout-btn").addEventListener("click", async () => {
  await fetch(new URL("/logout", location.origin), { method: "POST", headers: { "X-Panel-Request": "1" } });
  location.reload();
});
$("custom-map").addEventListener("input", () => {
  state.selectedMap = null;
  renderMapGrid();
});
$("default-map").addEventListener("change", (event) => {
  state.defaultMap = event.target.value;
  state.dirty = true;
});
$("add-mode").addEventListener("change", renderAddMaps);
$("add-btn").addEventListener("click", () => {
  const map = $("add-map").value;
  if (map) {
    state.rotation.push(map);
    markDirty();
  }
});
$("save-btn").addEventListener("click", () => saveSettings(false));
$("save-restart-btn").addEventListener("click", () => saveSettings(true));
$("reset-btn").addEventListener("click", resetSettings);
$("console-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = $("console-input");
  const command = input.value.trim();
  if (command) {
    input.value = "";
    sendCommand(command);
  }
});
for (const chip of document.querySelectorAll("[data-command]")) {
  chip.addEventListener("click", () => sendCommand(chip.dataset.command));
}

loadMaps().then(refreshStatus);
setInterval(refreshStatus, 5000);
