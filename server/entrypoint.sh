#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '[mordhau] %s\n' "$*"
}

truthy() {
  case "${1:-}" in
    true|TRUE|True|1|yes|YES|Yes|on|ON|On) return 0 ;;
    *) return 1 ;;
  esac
}

ini_bool() {
  if truthy "${1:-}"; then
    printf 'True'
  else
    printf 'False'
  fi
}

valid_map() {
  [[ "${1:-}" =~ ^[A-Za-z0-9_]+$ ]]
}

# Appends comma-separated map names to effective_rotation, skipping invalid ones.
add_rotation_maps() {
  local item
  local -a items
  IFS=',' read -ra items <<< "$1"
  for item in "${items[@]}"; do
    item="${item//[[:space:]]/}"
    [[ -z "$item" ]] && continue
    if valid_map "$item"; then
      effective_rotation+=("$item")
    else
      log "Ignoring invalid map name in rotation: ${item}"
    fi
  done
}

# Resolves the startup map and rotation. Precedence: panel settings file,
# then MAP_ROTATION (comma-separated), then MAP_ROTATION_1..N, then defaults.
load_map_settings() {
  local i var key value
  effective_default_map="${DEFAULT_MAP:-FFA_ThePit}"
  effective_rotation=()

  if [[ -n "${MAP_ROTATION:-}" ]]; then
    add_rotation_maps "$MAP_ROTATION"
  else
    for i in $(seq 1 100); do
      var="MAP_ROTATION_${i}"
      [[ -n "${!var:-}" ]] && add_rotation_maps "${!var}"
    done
  fi

  if [[ -f "$panel_settings" ]]; then
    local -a panel_rotation=()
    local panel_has_rotation="false"
    while IFS='=' read -r key value || [[ -n "$key" ]]; do
      value="${value%$'\r'}"
      case "$key" in
        DEFAULT_MAP)
          if valid_map "$value"; then
            effective_default_map="$value"
          else
            log "Ignoring invalid DEFAULT_MAP in ${panel_settings}: ${value}"
          fi
          ;;
        MAP_ROTATION)
          panel_has_rotation="true"
          local -a saved_rotation=("${effective_rotation[@]}")
          effective_rotation=()
          add_rotation_maps "$value"
          panel_rotation=("${effective_rotation[@]}")
          effective_rotation=("${saved_rotation[@]}")
          ;;
      esac
    done < "$panel_settings"
    if [[ "$panel_has_rotation" == "true" && ${#panel_rotation[@]} -gt 0 ]]; then
      effective_rotation=("${panel_rotation[@]}")
    fi
  fi

  if [[ ${#effective_rotation[@]} -eq 0 ]]; then
    effective_rotation=(FFA_ThePit FFA_Camp TDM_Camp)
  fi

  if ! valid_map "$effective_default_map"; then
    log "Invalid DEFAULT_MAP '${effective_default_map}', using ${effective_rotation[0]}"
    effective_default_map="${effective_rotation[0]}"
  fi
}

# Replaces the given keys inside one INI section with new lines, keeping every
# other line intact: hand edits, and the Admins/BannedPlayers/MutedPlayers
# entries the game itself writes when RCON adds admins, bans or mutes.
# Usage: replace_ini_keys <file> <section> "<Key1 Key2 ...>" "<new lines>"
replace_ini_keys() {
  local ini="$1"
  local tmp="${ini}.tmp"
  [[ -f "$ini" ]] || : > "$ini"
  INI_SECTION="$2" INI_KEYS="$3" INI_LINES="$4" \
    awk '
      BEGIN {
        section = ENVIRON["INI_SECTION"]
        block = ENVIRON["INI_LINES"]
        n = split(ENVIRON["INI_KEYS"], keys, " ")
        for (i = 1; i <= n; i++) managed[keys[i]] = 1
      }
      { line = $0; sub(/\r$/, "", line) }
      line ~ /^\[/ { in_section = (line == section) }
      in_section && line !~ /^\[/ {
        key = line; sub(/=.*/, "", key); sub(/^[+-]/, "", key)
        if (key in managed) next
      }
      { print }
      line == section && !done { if (block != "") print block; done = 1 }
      END { if (!done && block != "") { if (NR > 0) print ""; print section; print block } }
    ' "$ini" > "$tmp"
  mv "$tmp" "$ini"
}

apply_rotation() {
  replace_ini_keys "$1" "[/Script/Mordhau.MordhauGameMode]" "MapRotation" \
    "$(printf 'MapRotation=%s\n' "${effective_rotation[@]}")"
}

write_effective_settings() {
  local tmp="${effective_settings}.tmp"
  local joined
  joined="$(IFS=','; printf '%s' "${effective_rotation[*]}")"
  {
    printf 'DEFAULT_MAP=%s\n' "$effective_default_map"
    printf 'MAP_ROTATION=%s\n' "$joined"
    printf 'STARTED_AT=%s\n' "$(date +%s)"
  } > "$tmp"
  mv "$tmp" "$effective_settings"
}

write_configs() {
  local game_ini="$1"
  local engine_ini="$2"
  local advertise
  advertise="$(ini_bool "${ADVERTISE_SERVER:-false}")"

  local session_lines
  session_lines="$(cat <<EOF
ServerName=${SERVER_NAME:-Home Mordhau}
bAdvertiseServerViaSteam=${advertise}
bUseOfficialBanList=True
bUseOfficialMuteList=True
ServerPassword=${SERVER_PASSWORD:-}
AdminPassword=${ADMIN_PASSWORD:-}
MaxSlots=${MAX_PLAYERS:-16}
EOF
)"
  if [[ -n "${RCON_PASSWORD:-}" ]]; then
    session_lines+=$'\n'"RconPassword=${RCON_PASSWORD}"$'\n'"RconPort=${RCON_PORT:-37001}"
  fi

  # Update only the keys this script owns; anything else in Game.ini stays.
  replace_ini_keys "$game_ini" "[/Script/Mordhau.MordhauGameSession]" \
    "ServerName bAdvertiseServerViaSteam bUseOfficialBanList bUseOfficialMuteList ServerPassword AdminPassword MaxSlots RconPassword RconPort" \
    "$session_lines"
  replace_ini_keys "$game_ini" "[/Script/Engine.GameSession]" "MaxPlayers" "MaxPlayers=${MAX_PLAYERS:-16}"
  apply_rotation "$game_ini"

  cat > "$engine_ini" <<EOF
[/Script/OnlineSubsystemUtils.IpNetDriver]
NetServerMaxTickRate=${NET_SERVER_MAX_TICK_RATE:-60}
LanServerMaxTickRate=${LAN_SERVER_MAX_TICK_RATE:-60}

[IpDrv.TcpNetDriver]
NetServerMaxTickRate=${NET_SERVER_MAX_TICK_RATE:-60}
LanServerMaxTickRate=${LAN_SERVER_MAX_TICK_RATE:-60}

[Core.Log]
LogMordhauGameInstance=Log
LogMordhauGameSession=Log
LogMordhauWebAPI=Log
LogMordhauPlayerController=Log
LogPlayFabAPI=Log
LogMatchmaking=Log
LogStreaming=Error
LogClass=Error
EOF
}

steam_app_id="${STEAM_APP_ID:-629800}"
server_dir="${SERVER_DIR:-/data/server}"
config_dir="${CONFIG_DIR:-/data/config}"
steamcmd_cache_dir="${STEAMCMD_CACHE_DIR:-/data/steamcmd}"
log_dir="${LOG_DIR:-/data/logs}"
game_ini="${GAME_INI:-${config_dir}/Game.ini}"
engine_ini="${ENGINE_INI:-${config_dir}/Engine.ini}"
game_port="${GAME_PORT:-37000}"
beacon_port="${BEACON_PORT:-37002}"
query_port="${QUERY_PORT:-37003}"
panel_dir="${PANEL_DIR:-/data/panel}"
panel_settings="${panel_dir}/settings.env"
effective_settings="${panel_dir}/effective.env"
restart_request="${panel_dir}/restart-request"

mkdir -p "$server_dir" "$config_dir" "$steamcmd_cache_dir" "$log_dir" "$panel_dir"
mkdir -p "$steamcmd_cache_dir/Steam" "${HOME}/.steam/sdk32" "${HOME}/.steam/sdk64"

if [[ ! -e "${HOME}/Steam" ]]; then
  ln -s "$steamcmd_cache_dir/Steam" "${HOME}/Steam"
fi

export STEAMEXE="${STEAMCMDDIR}/steamcmd.sh"
export STEAMCMD_HOME="$steamcmd_cache_dir"
export LD_LIBRARY_PATH="${STEAMCMDDIR}/linux32:${STEAMCMDDIR}/linux64:${LD_LIBRARY_PATH:-}"

if truthy "${UPDATE_ON_START:-true}" || [[ ! -x "${server_dir}/Mordhau/Binaries/Linux/MordhauServer-Linux-Shipping" ]]; then
  log "Installing/updating Mordhau Dedicated Server app ${steam_app_id}"

  steam_args=(
    +force_install_dir "$server_dir"
    +login anonymous
    +app_update "$steam_app_id"
  )

  if [[ -n "${STEAM_BRANCH:-}" ]]; then
    steam_args+=(-beta "$STEAM_BRANCH")
  fi

  if truthy "${STEAM_VALIDATE:-false}"; then
    steam_args+=(validate)
  fi

  steam_args+=(+quit)
  "${STEAMCMDDIR}/steamcmd.sh" "${steam_args[@]}"
else
  log "Skipping SteamCMD update because UPDATE_ON_START is false and server binary exists"
fi

if [[ -f "${STEAMCMDDIR}/linux32/steamclient.so" ]]; then
  ln -sf "${STEAMCMDDIR}/linux32/steamclient.so" "${HOME}/.steam/sdk32/steamclient.so"
  ln -sf "${STEAMCMDDIR}/linux32/steamclient.so" "${server_dir}/Mordhau/Binaries/Linux/steamclient.so"
fi

if [[ -f "${STEAMCMDDIR}/linux64/steamclient.so" ]]; then
  ln -sf "${STEAMCMDDIR}/linux64/steamclient.so" "${HOME}/.steam/sdk64/steamclient.so"
fi

printf '%s\n' "$steam_app_id" > "${server_dir}/steam_appid.txt"
printf '%s\n' "$steam_app_id" > "${server_dir}/Mordhau/Binaries/Linux/steam_appid.txt"

saved_config_parent="${server_dir}/Mordhau/Saved/Config"
saved_config_dir="${saved_config_parent}/LinuxServer"
saved_log_dir="${server_dir}/Mordhau/Saved/Logs"
mkdir -p "$saved_config_parent" "${server_dir}/Mordhau/Saved"

if [[ -d "$saved_config_dir" && ! -L "$saved_config_dir" ]] && [[ -z "$(find "$saved_config_dir" -mindepth 1 -maxdepth 1 2>/dev/null)" ]]; then
  rmdir "$saved_config_dir"
fi

if [[ ! -e "$saved_config_dir" ]]; then
  ln -s "$config_dir" "$saved_config_dir"
fi

if [[ -d "$saved_log_dir" && ! -L "$saved_log_dir" ]] && [[ -z "$(find "$saved_log_dir" -mindepth 1 -maxdepth 1 2>/dev/null)" ]]; then
  rmdir "$saved_log_dir"
fi

if [[ ! -e "$saved_log_dir" ]]; then
  ln -s "$log_dir" "$saved_log_dir"
fi

server_binary="${server_dir}/Mordhau/Binaries/Linux/MordhauServer-Linux-Shipping"
if [[ ! -x "$server_binary" ]]; then
  log "Server binary was not found at ${server_binary}"
  log "Check the SteamCMD output above for download or permission errors."
  exit 1
fi

configure_server() {
  load_map_settings

  if [[ ! -f "$game_ini" || ! -f "$engine_ini" ]] || truthy "${APPLY_ENV_ON_START:-false}"; then
    log "Writing environment-backed Mordhau config"
    write_configs "$game_ini" "$engine_ini"
  elif [[ -f "$panel_settings" ]]; then
    log "Applying panel map rotation to existing Game.ini"
    apply_rotation "$game_ini"
  fi

  write_effective_settings
}

server_pid=""
stopping="false"

on_stop_signal() {
  stopping="true"
  if [[ -n "$server_pid" ]]; then
    kill -TERM "$server_pid" 2>/dev/null || true
  fi
}
trap on_stop_signal TERM INT

# Waits for the server to exit; escalates to SIGKILL after the grace period.
stop_server() {
  local waited=0
  kill -TERM "$server_pid" 2>/dev/null || true
  while kill -0 "$server_pid" 2>/dev/null; do
    if (( waited >= ${RESTART_GRACE_SECONDS:-30} * 2 )); then
      log "Server did not stop in time, killing it"
      kill -KILL "$server_pid" 2>/dev/null || true
      break
    fi
    sleep 0.5
    waited=$((waited + 1))
  done
}

cd "$(dirname "$server_binary")"
rm -f "$restart_request"

# Supervise the server so the panel can request a fast restart (no SteamCMD
# run) by creating ${restart_request}. Any other exit stops the container.
while true; do
  configure_server

  log "Starting server"
  log "Map: ${effective_default_map}"
  log "Rotation: ${effective_rotation[*]}"
  log "Game.ini: ${game_ini}"
  log "Engine.ini: ${engine_ini}"
  log "Logs: ${log_dir}"

  ./MordhauServer-Linux-Shipping \
    Mordhau "$effective_default_map" \
    -MultiHome=0.0.0.0 \
    -Port="$game_port" \
    -BeaconPort="$beacon_port" \
    -QueryPort="$query_port" \
    -GAMEINI="$game_ini" \
    -ENGINEINI="$engine_ini" \
    -log &
  server_pid=$!
  if [[ "$stopping" == "true" ]]; then
    stop_server
  fi

  restarting="false"
  while kill -0 "$server_pid" 2>/dev/null && [[ "$stopping" == "false" ]]; do
    if [[ -e "$restart_request" ]]; then
      rm -f "$restart_request"
      log "Restart requested by panel"
      restarting="true"
      stop_server
      break
    fi
    sleep "${RESTART_POLL_SECONDS:-2}" &
    wait $! || true
  done

  status=0
  while true; do
    wait "$server_pid" || status=$?
    kill -0 "$server_pid" 2>/dev/null || break
  done
  server_pid=""

  if [[ "$stopping" == "true" ]]; then
    log "Server stopped"
    exit 0
  fi
  if [[ "$restarting" == "true" ]]; then
    continue
  fi
  log "Server exited with status ${status}"
  exit "$status"
done
