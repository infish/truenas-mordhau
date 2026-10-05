"use strict";

const state = {
  modes: [],          // [{prefix, label, maps: [...]}]
  activeMode: null,
  selectedMap: null,
  liveMap: null,
  rotation: [],
  defaultMap: null,
  dirty: false,       // rotation editor has unsaved edits
  icons: { version: 0, icons: {} }, // map pictures from tools/import_map_icons.py
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

function iconUrl(map) {
  const file = state.icons.icons[map] || state.icons.icons["*"];
  return file ? `/api/map-icons/${encodeURIComponent(file)}?v=${state.icons.version}` : null;
}

function mapIcon(map, className) {
  const url = iconUrl(map);
  return url ? el("img", { src: url, alt: "", loading: "lazy", className, draggable: false }) : null;
}

async function loadIcons() {
  try {
    state.icons = await api("GET", "/api/map-icons");
  } catch {
    state.icons = { version: 0, icons: {} };
  }
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
  const previousLiveMap = state.liveMap;
  if (server.online) {
    state.liveMap = server.map;
    setStatus("online", `${server.name} · ${server.map} · ${server.players}/${server.max_players} players`);
  } else {
    state.liveMap = null;
    setStatus("offline", "Server offline or starting");
  }
  $("rcon-warning").hidden = data.rcon_configured;
  state.rconConfigured = data.rcon_configured;
  applySettings(data.settings);
  // Rebuilding the grid every refresh would reload its pictures; only the
  // "live" marker depends on the status.
  if (state.liveMap !== previousLiveMap) renderMapGrid();
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
    const icon = mapIcon(map, "map-icon");
    const button = el("button", { title: map, className: icon ? "has-icon" : "" },
      [icon, el("span", { className: "map-name", textContent: shortName(map) })].filter(Boolean));
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
    const children = [mapIcon(map, "rotation-icon"), el("span", { className: "name", textContent: map }), up, down, remove];
    return el("li", {}, children.filter(Boolean));
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

// ---- Players -------------------------------------------------------------

// Durations are in minutes; 0 is permanent.
const DURATIONS = [["10 minutes", 10], ["1 hour", 60], ["1 day", 1440], ["1 week", 10080], ["Permanent", 0]];
const playerRows = new Map(); // PlayFab ID -> row elements, kept across refreshes

async function refreshPlayers() {
  if (state.rconConfigured === false) {
    $("players-summary").textContent = "Needs RCON.";
    return;
  }
  let data;
  try {
    data = await api("GET", "/api/players");
  } catch (error) {
    $("players-summary").textContent = `Player list unavailable: ${error.message}`;
    return;
  }
  const people = data.players.length;
  const parts = [`${people} player${people === 1 ? "" : "s"}`];
  if (data.bots) parts.push(`${data.bots} bot${data.bots === 1 ? "" : "s"}`);
  $("players-summary").textContent = parts.join(" · ");
  renderPlayers(data.players);
}

function renderPlayers(players) {
  const list = $("player-list");
  const seen = new Set();
  for (const player of players) {
    seen.add(player.id);
    let row = playerRows.get(player.id);
    if (!row) {
      row = createPlayerRow(player.id);
      playerRows.set(player.id, row);
    }
    updatePlayerRow(row, player);
    list.append(row.li); // re-appending keeps server order without rebuilding rows
  }
  for (const [id, row] of playerRows) {
    if (!seen.has(id)) {
      row.li.remove();
      playerRows.delete(id);
    }
  }
}

function createPlayerRow(id) {
  const row = { id, player: null };
  row.name = el("span", { className: "player-name" });
  row.meta = el("span", { className: "player-meta" });
  const toggle = el("button", { textContent: "Actions", className: "small" });
  toggle.setAttribute("aria-expanded", "false");

  row.adminBtn = el("button");
  row.teamBtn = el("button");
  const kill = el("button", { textContent: "Kill", className: "danger" });
  row.adminBtn.addEventListener("click", () => playerAction(row, row.player.admin ? "unadmin" : "admin"));
  row.teamBtn.addEventListener("click", () => playerAction(row, "team", { team: row.player.team === 0 ? 1 : 0 }));
  kill.addEventListener("click", () => playerAction(row, "kill", {}, `Kill ${row.player.name}?`));

  const reason = el("input", { type: "text", placeholder: "Reason (optional)", maxLength: 200 });
  const duration = el("select", {}, DURATIONS.map(([label, minutes]) =>
    el("option", { value: String(minutes), textContent: label })));
  duration.value = "60";
  const mute = el("button", { textContent: "Mute" });
  const unmute = el("button", { textContent: "Unmute" });
  const kick = el("button", { textContent: "Kick", className: "danger" });
  const ban = el("button", { textContent: "Ban", className: "danger" });
  const minutes = () => Number(duration.value);
  mute.addEventListener("click", () => playerAction(row, "mute", { duration: minutes() }));
  unmute.addEventListener("click", () => playerAction(row, "unmute"));
  kick.addEventListener("click", () =>
    playerAction(row, "kick", { reason: reason.value }, `Kick ${row.player.name}?`));
  ban.addEventListener("click", () => {
    const label = duration.selectedOptions[0].textContent.toLowerCase();
    playerAction(row, "ban", { reason: reason.value, duration: minutes() }, `Ban ${row.player.name} (${label})?`);
  });

  const newName = el("input", { type: "text", placeholder: "New name", maxLength: 200 });
  const rename = el("button", { textContent: "Rename" });
  rename.addEventListener("click", () => {
    if (newName.value.trim()) playerAction(row, "rename", { name: newName.value }).then(() => { newName.value = ""; });
  });

  const actions = el("div", { className: "player-actions", hidden: true }, [
    el("div", { className: "tool-row" }, [row.adminBtn, row.teamBtn, kill]),
    el("div", { className: "tool-row" }, [reason, duration]),
    el("div", { className: "tool-row" }, [mute, unmute, kick, ban]),
    el("div", { className: "tool-row" }, [newName, rename]),
  ]);
  toggle.addEventListener("click", () => {
    actions.hidden = !actions.hidden;
    toggle.setAttribute("aria-expanded", String(!actions.hidden));
  });

  const info = el("div", { className: "player-info" }, [row.name, row.meta]);
  row.li = el("li", { className: "player" }, [el("div", { className: "player-head" }, [info, toggle]), actions]);
  return row;
}

function updatePlayerRow(row, player) {
  row.player = player;
  row.name.replaceChildren(player.name);
  if (player.admin) row.name.append(el("span", { className: "badge", textContent: "admin" }));
  row.meta.textContent = `Team ${player.team} · ${player.ping} ms`;
  row.adminBtn.textContent = player.admin ? "Remove admin" : "Make admin";
  row.teamBtn.textContent = `Move to team ${player.team === 0 ? 1 : 0}`;
}

async function playerAction(row, action, body = {}, confirmText = null) {
  if (confirmText && !confirm(confirmText)) return;
  try {
    const result = await api("POST", `/api/players/${encodeURIComponent(row.id)}/${action}`, body);
    notify(result.output || `Sent: ${result.command}`);
    setTimeout(refreshPlayers, 500);
  } catch (error) {
    notify(`${action} failed: ${error.message}`, true);
  }
}

async function botsAction(action) {
  const team = $("bot-team").value;
  const body = { action, amount: Number($("bot-amount").value), team: team === "" ? null : Number(team) };
  try {
    const result = await api("POST", "/api/bots", body);
    notify(result.output || `Sent: ${result.command}`);
    setTimeout(refreshPlayers, 1000);
  } catch (error) {
    notify(`Bots failed: ${error.message}`, true);
  }
}

async function loadEntries(path, listId, action, label) {
  const list = $(listId);
  try {
    const { entries } = await api("GET", path);
    if (!entries.length) {
      list.replaceChildren(el("li", { className: "hint", textContent: "Empty." }));
      return;
    }
    list.replaceChildren(...entries.map((entry) => {
      const children = [el("span", { className: "entry-text", textContent: entry.text })];
      if (entry.id) {
        const button = el("button", { textContent: label, className: "small" });
        button.addEventListener("click", async () => {
          try {
            const result = await api("POST", `/api/players/${encodeURIComponent(entry.id)}/${action}`);
            notify(result.output || `Sent: ${result.command}`);
            loadEntries(path, listId, action, label);
          } catch (error) {
            notify(`${label} failed: ${error.message}`, true);
          }
        });
        children.push(button);
      }
      return el("li", {}, children);
    }));
  } catch (error) {
    list.replaceChildren(el("li", { className: "hint", textContent: error.message }));
  }
}

async function checkMatch() {
  try {
    $("match-output").textContent = (await api("GET", "/api/match")).output;
  } catch (error) {
    $("match-output").textContent = error.message;
  }
}

// ---- Server settings -----------------------------------------------------

function passwordHint(isSet) {
  if (isSet === true) return "Unchanged (a password is set)";
  if (isSet === false) return "Unchanged (none set)";
  return "Unchanged";
}

function showServerSettings(view) {
  $("ss-name").value = view.server_name ?? "";
  $("ss-max-players").value = view.max_players ?? "";
  $("ss-advertise").checked = Boolean(view.advertise);
  for (const [field, isSet] of [["server-password", view.server_password_set], ["admin-password", view.admin_password_set]]) {
    $(`ss-${field}`).value = "";
    $(`ss-${field}`).placeholder = passwordHint(isSet);
    $(`ss-${field}`).disabled = false;
    $(`ss-clear-${field}`).checked = false;
  }
  const envManaged = view.panel_password_managed_by === "env";
  $("pp-env-note").hidden = !envManaged;
  $("panel-password-form").hidden = envManaged;
}

async function loadServerSettings() {
  try {
    showServerSettings(await api("GET", "/api/server-settings"));
  } catch (error) {
    notify(`Could not load server settings: ${error.message}`, true);
  }
}

async function saveServerSettings(restart) {
  if (!$("server-settings-form").reportValidity()) return;
  if (restart && !confirm("Restart the server now? Everyone on it will be disconnected for about a minute.")) return;
  const body = {
    server_name: $("ss-name").value,
    max_players: Number($("ss-max-players").value),
    advertise: $("ss-advertise").checked,
    server_password: $("ss-server-password").value || null,
    clear_server_password: $("ss-clear-server-password").checked,
    admin_password: $("ss-admin-password").value || null,
    clear_admin_password: $("ss-clear-admin-password").checked,
    restart,
  };
  try {
    const view = await api("PUT", "/api/server-settings", body);
    showServerSettings(view);
    notify(restart ? "Saved. Restarting the server…" : "Saved. Applies on the next server restart.");
    if (restart) refreshStatus();
  } catch (error) {
    notify(`Save failed: ${error.message}`, true);
  }
}

async function changePanelPassword(event) {
  event.preventDefault();
  if ($("pp-new").value !== $("pp-new-2").value) {
    notify("The new passwords do not match.", true);
    return;
  }
  try {
    await api("POST", "/api/panel-password", { current: $("pp-current").value, new: $("pp-new").value });
    event.target.reset();
    notify("Panel password changed. Other devices need to log in again.");
  } catch (error) {
    notify(`Password change failed: ${error.message}`, true);
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

$("ss-save").addEventListener("click", () => saveServerSettings(false));
$("ss-save-restart").addEventListener("click", () => saveServerSettings(true));
for (const field of ["server-password", "admin-password"]) {
  $(`ss-clear-${field}`).addEventListener("change", (event) => {
    $(`ss-${field}`).disabled = event.target.checked;
    if (event.target.checked) $(`ss-${field}`).value = "";
  });
}
$("panel-password-form").addEventListener("submit", changePanelPassword);
$("bots-add").addEventListener("click", () => botsAction("add"));
$("bots-remove").addEventListener("click", () => botsAction("remove"));
$("say-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = $("say-input");
  if (!input.value.trim()) return;
  try {
    await api("POST", "/api/say", { message: input.value });
    notify("Message sent.");
    input.value = "";
  } catch (error) {
    notify(`Message failed: ${error.message}`, true);
  }
});
$("match-check").addEventListener("click", checkMatch);
for (const button of document.querySelectorAll("[data-extend]")) {
  button.addEventListener("click", async () => {
    try {
      const result = await api("POST", "/api/match/extend", { seconds: Number(button.dataset.extend) });
      notify(result.output || "Match extended.");
      checkMatch();
    } catch (error) {
      notify(`Extend failed: ${error.message}`, true);
    }
  });
}
$("bans").addEventListener("toggle", (event) => {
  if (event.target.open) loadEntries("/api/bans", "ban-list", "unban", "Unban");
});
$("mutes").addEventListener("toggle", (event) => {
  if (event.target.open) loadEntries("/api/mutes", "mute-list", "unmute", "Unmute");
});

function tick() {
  if (document.hidden) return;
  refreshStatus().then(refreshPlayers);
}

loadIcons().then(loadMaps).then(tick);
loadServerSettings();
setInterval(tick, 5000);
document.addEventListener("visibilitychange", tick);
