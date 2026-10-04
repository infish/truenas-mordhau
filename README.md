# Mordhau Server for TrueNAS

A Dockerized Mordhau dedicated server for TrueNAS SCALE Custom Apps, plus a
small web panel for changing maps without touching the console or config.

- `server/` – SteamCMD-based server image (`infish1997/mordhau-server`).
  Installs/updates Mordhau Dedicated Server (app `629800`), writes `Game.ini`
  and `Engine.ini` from environment variables, and supervises the server
  process so the panel can restart it.
- `panel/` – web panel image (`infish1997/mordhau-panel`): live map changes
  over RCON, rotation and startup map editor, and a raw RCON console.
- `compose.truenas.yaml` – paste into TrueNAS: Apps > Discover Apps >
  Custom App > Install via YAML.
- `compose.local-build.yaml` – builds and runs both images locally.

## How maps and modes work

The game mode is part of the map name: `FFA_Camp` is Camp in free-for-all,
`TDM_Camp` is the same map in team deathmatch. Prefixes: `FFA` free-for-all,
`TDM` team deathmatch, `SKM` skirmish, `FL` frontline, `INV` invasion,
`HRD` horde, `BR` battle royale, `DU` duel. The panel lists every map it
finds in the installed server's `.pak` files, grouped by prefix.

- **Change map now** sends `changelevel <map>` over RCON. Instant, nobody
  is disconnected.
- **Rotation & startup map** writes `/data/panel/settings.env`. The server
  applies it on its next start; "Save & restart" asks the server container's
  supervisor to restart the game process right away (no SteamCMD update, about
  a minute of downtime). Saved settings override `DEFAULT_MAP` and
  `MAP_ROTATION` from the app config.
- **Players** lists who is online (refreshed every 5 seconds) with per-player
  actions: make/remove admin, move team, kill, mute, kick, ban, rename. Also
  add/remove bots, message everyone, extend the match, and the ban and mute
  lists with unban/unmute. Players are targeted by PlayFab ID, never by name.
  Ban and mute durations are in minutes; "Permanent" sends 0. Reasons are sent
  as one word (spaces become underscores) because `ban` reads the duration
  after the reason.
- **Console** sends any RCON command, e.g. `help` or `playerlist`.

Admins, bans and mutes added over RCON are saved by the game in `Game.ini`.
The entrypoint only rewrites the keys it manages there, so they survive
restarts even with `APPLY_ENV_ON_START: "true"`.

## Setup

1. Build and push both images (needs `docker login` first):

   ```bash
   ./build-and-push.sh latest
   ```

2. Create the dataset `/mnt/Apps/MordhauServer` with write access for the
   `apps` user (UID/GID `568`).

3. Install `compose.truenas.yaml` via YAML in TrueNAS. It contains no
   passwords. The server starts downloading the game files, then waits for
   setup.

4. In TrueNAS, open Apps > the Mordhau app > Logs and find the
   "Mordhau panel setup code" in the panel container's log. The code is new
   each time the panel starts, until setup is done.

5. Open `http://<truenas-ip>:37080`, enter the setup code, choose the panel
   password, server name, join and admin passwords, max players and whether
   to list the server publicly, then click Finish. The game server starts.

Everything from the setup screen can be changed later under **Server
settings** in the panel. Maps and rotation are set under **Rotation &
startup map**.

### Where settings live

All of it is under `/data/panel` on the dataset:

| File | Contents |
| --- | --- |
| `server.env` | server name, passwords, max players, public listing (written by the panel; each key overrides the app's environment variable) |
| `settings.env` | startup map and rotation |
| `panel-auth.env` | panel password hash and session key |
| `rcon.env` | generated RCON password shared by both containers |
| `effective.env` | what the server last started with (no secrets) |

Installs that set `PANEL_PASSWORD` and `RCON_PASSWORD` in the app config keep
working: setup is skipped and those values are used. To change the panel
password in the panel instead, remove `PANEL_PASSWORD` from the app config
(the panel then shows the setup screen once). If you set `RCON_PASSWORD`, set
it on both containers or on neither.

The panel uses a login page with a 30-day session cookie, without TLS, so keep
port 37080 on your LAN or tailnet and do not forward it from the internet.

## Ports

| Port | Use |
| --- | --- |
| 37000 tcp/udp | game |
| 37001 tcp/udp | RCON (enabled when `RCON_PASSWORD` is set) |
| 37002 tcp/udp | beacon |
| 37003 tcp/udp | Steam query (the panel reads the live map and player count here) |
| 37080 tcp | panel |

## Connecting over Tailscale

With `ADVERTISE_SERVER: "false"` the server is not listed publicly. Connect
from the Mordhau console with `open <truenas-tailscale-ip>:37000`.

## Updating

Restarting the app runs SteamCMD again when `UPDATE_ON_START` is `"true"`.
Set `STEAM_VALIDATE: "true"` to have SteamCMD validate files. A restart from
the panel skips SteamCMD.

## Development

```bash
uv sync
uv run pytest
```

After changing panel dependencies, regenerate the hashed requirements the
image installs:

```bash
uv export --no-dev --no-emit-project -o panel/requirements.txt
```

## Backup

Snapshot the dataset mounted at `/data`. The important paths are
`config/Game.ini`, `config/Engine.ini`, `panel/`, `server/Mordhau/Saved`,
and `logs`.

See `docs/config-notes.md` for config details.
