"use strict";

const form = document.getElementById("setup-form");
const error = document.getElementById("setup-error");
const value = (id) => document.getElementById(id).value;

function showError(message) {
  error.textContent = message;
  error.hidden = false;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  error.hidden = true;
  if (value("panel-password") !== value("panel-password-2")) {
    showError("The two panel passwords do not match.");
    return;
  }
  const button = form.querySelector("button");
  button.disabled = true;
  try {
    const response = await fetch(new URL("/setup", location.origin), {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Panel-Request": "1" },
      body: JSON.stringify({
        code: value("code"),
        panel_password: value("panel-password"),
        server_name: value("server-name"),
        server_password: value("server-password"),
        admin_password: value("admin-password"),
        max_players: Number(value("max-players")),
        advertise: document.getElementById("advertise").checked,
      }),
    });
    if (response.ok) {
      location.replace("/");
      return;
    }
    const data = await response.json().catch(() => ({}));
    const detail = typeof data.detail === "string" ? data.detail : `Setup failed (${response.status}).`;
    // 409: setup already finished elsewhere, so go to the login page.
    if (response.status === 409) location.replace("/");
    showError(detail);
  } catch {
    showError("Cannot reach the panel.");
  }
  button.disabled = false;
});
