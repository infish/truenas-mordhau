"use strict";

const form = document.getElementById("login-form");
const error = document.getElementById("login-error");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = form.querySelector("button");
  button.disabled = true;
  error.hidden = true;
  try {
    const response = await fetch(new URL("/login", location.origin), {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Panel-Request": "1" },
      body: JSON.stringify({ password: document.getElementById("password").value }),
    });
    if (response.ok) {
      location.replace("/");
      return;
    }
    error.textContent = response.status === 401 ? "Wrong password." : `Login failed (${response.status}).`;
  } catch {
    error.textContent = "Cannot reach the panel.";
  }
  error.hidden = false;
  button.disabled = false;
});
