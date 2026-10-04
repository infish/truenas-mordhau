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

write_configs() {
  local game_ini="$1"
  local engine_ini="$2"
  local advertise
  advertise="$(ini_bool "${ADVERTISE_SERVER:-false}")"

  cat > "$game_ini" <<EOF
[/Script/Mordhau.MordhauGameSession]
ServerName=${SERVER_NAME:-Home Mordhau}
bAdvertiseServerViaSteam=${advertise}
bUseOfficialBanList=True
bUseOfficialMuteList=True
ServerPassword=${SERVER_PASSWORD:-}
AdminPassword=${ADMIN_PASSWORD:-}
MaxSlots=${MAX_PLAYERS:-16}
EOF

  if [[ -n "${RCON_PASSWORD:-}" ]]; then
    cat >> "$game_ini" <<EOF
RconPassword=${RCON_PASSWORD}
RconPort=${RCON_PORT:-37001}
EOF
  fi

  cat >> "$game_ini" <<EOF

[/Script/Engine.GameSession]
MaxPlayers=${MAX_PLAYERS:-16}

[/Script/Mordhau.MordhauGameMode]
MapRotation=${MAP_ROTATION_1:-FFA_ThePit}
MapRotation=${MAP_ROTATION_2:-FFA_Camp}
MapRotation=${MAP_ROTATION_3:-TDM_Camp}
EOF

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
default_map="${DEFAULT_MAP:-FFA_ThePit}"

mkdir -p "$server_dir" "$config_dir" "$steamcmd_cache_dir" "$log_dir"
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

first_config="false"
if [[ ! -f "$game_ini" || ! -f "$engine_ini" ]]; then
  first_config="true"
fi

if [[ "$first_config" == "true" ]] || truthy "${APPLY_ENV_ON_START:-false}"; then
  log "Writing environment-backed Mordhau config"
  write_configs "$game_ini" "$engine_ini"
fi

server_binary="${server_dir}/Mordhau/Binaries/Linux/MordhauServer-Linux-Shipping"
if [[ ! -x "$server_binary" ]]; then
  log "Server binary was not found at ${server_binary}"
  log "Check the SteamCMD output above for download or permission errors."
  exit 1
fi

log "Starting server"
log "Map: ${default_map}"
log "Game.ini: ${game_ini}"
log "Engine.ini: ${engine_ini}"
log "Logs: ${log_dir}"

cd "$(dirname "$server_binary")"
exec ./MordhauServer-Linux-Shipping \
  Mordhau "$default_map" \
  -MultiHome=0.0.0.0 \
  -Port="$game_port" \
  -BeaconPort="$beacon_port" \
  -QueryPort="$query_port" \
  -GAMEINI="$game_ini" \
  -ENGINEINI="$engine_ini" \
  -log
