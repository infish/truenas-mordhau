# Configuration reference

Most people never need this page: the setup screen and the panel cover the
everyday settings. This is the full list for when you want more control.

## Where settings come from

For server name, passwords, max players and public listing, the server uses,
in this order:

1. **What you saved in the panel** (`/data/panel/server.env`), key by key.
2. **The app's YAML** (environment variables below).
3. **Built-in defaults.**

For the startup map and rotation: the panel's **Rotation & startup map**
(`/data/panel/settings.env`) first, then the YAML, then defaults.

## Server container (`server`)

| Variable | Default | Meaning |
| --- | --- | --- |
| `TZ` | `UTC` | Time zone for logs, e.g. `Europe/London`. |
| `UPDATE_ON_START` | `true` | Update the Mordhau server from Steam whenever the container starts. Restarts from the panel skip this. |
| `STEAM_VALIDATE` | `false` | Also verify all game files (slower). Useful after a broken update. |
| `STEAM_BRANCH` | empty | Steam beta branch, if Mordhau publishes one. |
| `WAIT_FOR_SETUP` | `false` | Wait for the panel's setup screen before the first start. The install YAML sets it to `true`. |
| `SERVER_NAME` | `Home Mordhau` | Server name. |
| `SERVER_PASSWORD` | empty | Join password. Empty means anyone can join. |
| `ADMIN_PASSWORD` | empty | Password for `adminlogin` in the game console. |
| `MAX_PLAYERS` | `16` | Player slots. |
| `ADVERTISE_SERVER` | `false` | List the server in Mordhau's public server browser. |
| `DEFAULT_MAP` | `FFA_ThePit` | Map the server starts on. |
| `MAP_ROTATION` | `FFA_ThePit,FFA_Camp,TDM_Camp` | Comma-separated rotation, any length. |
| `MAP_ROTATION_1`, `_2`, … | | Older one-map-per-variable form; used when `MAP_ROTATION` is not set. |
| `RCON_PASSWORD` | generated | Remote console password. Leave unset: the panel generates one and shares it. If you set it, set the same value on the panel. |
| `APPLY_ENV_ON_START` | `false` | Rewrite the managed `Game.ini` settings from the YAML on every start. Not needed once the panel manages settings. |
| `GAME_PORT` | `37000` | Game port. |
| `BEACON_PORT` | `37002` | Beacon port. |
| `QUERY_PORT` | `37003` | Steam query port (server browser, panel status). |
| `RCON_PORT` | `37001` | RCON port, used by the panel inside the app. |
| `NET_SERVER_MAX_TICK_RATE` | `60` | Server tick rate. |
| `LAN_SERVER_MAX_TICK_RATE` | `60` | Tick rate for LAN games. |
| `RESTART_GRACE_SECONDS` | `30` | How long a panel restart waits for the game to stop before forcing it. |
| `RCON_WAIT_SECONDS` | `30` | Without `RCON_PASSWORD`, how long the server waits at start for the panel to create the shared RCON password. |

If you change a port, change the matching `ports:` entry in the YAML to the
same number on both sides (`target` and `published`).

## Panel container (`panel`)

| Variable | Default | Meaning |
| --- | --- | --- |
| `PANEL_PASSWORD` | unset | Unset: the password is chosen on the setup screen and can be changed in the panel. Set: this is the password, and setup is skipped. |
| `RCON_PASSWORD` | generated | Only if you also set it on the server. |
| `PANEL_USERNAME` | `admin` | Username for scripts using HTTP Basic auth (the login page only asks for the password). |
| `RCON_HOST` / `RCON_PORT` | `server` / `37001` | Where the panel finds RCON. |
| `QUERY_HOST` / `QUERY_PORT` | `server` / `37003` | Where the panel asks for the server status. |
| `PORT` | `8080` | Port inside the container (published as 37080). |

## Files in the dataset

Everything lives in the dataset you mounted at `/data`:

| Path | Contents |
| --- | --- |
| `server/` | Mordhau server files from Steam. |
| `steamcmd/` | SteamCMD cache. |
| `config/Game.ini` | Game settings. The game also saves admins, bans and mutes here. |
| `config/Engine.ini` | Engine settings (tick rate, logging). |
| `logs/` | Mordhau server logs. |
| `panel/server.env` | Server settings saved in the panel. Each line overrides the matching YAML variable. |
| `panel/settings.env` | Startup map and rotation saved in the panel. |
| `panel/panel-auth.env` | Panel password **hash** and session key. |
| `panel/rcon.env` | Generated RCON password, shared by both containers. |
| `panel/effective.env` | What the server last started with (no passwords). |

`Game.ini` is updated, not overwritten: the server only rewrites the settings
it manages (`ServerName`, `ServerPassword`, `AdminPassword`, `MaxSlots`,
`bAdvertiseServerViaSteam`, `bUseOfficialBanList`, `bUseOfficialMuteList`,
`RconPassword`, `RconPort`, `MaxPlayers`, `MapRotation`). Anything else you add
by hand, and the game's own admin, ban and mute lists, are kept.

## Installs that keep settings in the YAML

You can skip the panel's setup and keep everything in the YAML, as older
versions of this project did: set `PANEL_PASSWORD` and `RCON_PASSWORD` on the
panel, `RCON_PASSWORD` and the server variables on the server, and leave
`WAIT_FOR_SETUP` unset. Anything you later save in the panel's Server
settings takes precedence over the YAML.

To move such an install to panel-managed settings, remove `PANEL_PASSWORD`
and both `RCON_PASSWORD` lines from the YAML and redeploy. The panel then shows
the setup screen once (with a new setup code in its log).

## Running without TrueNAS

`compose.truenas.yaml` is a normal Docker Compose file and works on any Linux
machine with Docker:

1. Make a folder for the data and give it to user 568:

   ```bash
   sudo mkdir -p /srv/mordhau && sudo chown 568:568 /srv/mordhau
   ```

2. In `compose.truenas.yaml`, change both `source:` lines to that folder.
3. Start it and print the setup code:

   ```bash
   docker compose -f compose.truenas.yaml up -d
   docker compose -f compose.truenas.yaml logs panel
   ```

4. Open `http://<machine-ip>:37080` and finish setup.
