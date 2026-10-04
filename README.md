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
- **Console** sends any RCON command, e.g. `help` or `playerlist`.

## Setup

1. Build and push both images (needs `docker login` first):

   ```bash
   ./build-and-push.sh latest
   ```

2. Create the dataset `/mnt/Apps/MordhauServer` with write access for the
   `apps` user (UID/GID `568`).

3. Edit `compose.truenas.yaml`: replace every `CHANGE_ME_*` value. Use the
   same `RCON_PASSWORD` in both services. `PANEL_PASSWORD` is the login for
   the panel (username `admin` by default).

4. Install via YAML in TrueNAS. The first start downloads the server, which
   takes a few minutes.

5. Open the panel at `http://<truenas-ip>:37080`.

The panel uses HTTP Basic auth without TLS, so keep port 37080 on your LAN or
tailnet and do not forward it from the internet.

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
`config/Game.ini`, `config/Engine.ini`, `panel/settings.env`,
`server/Mordhau/Saved`, and `logs`.

See `docs/config-notes.md` for config details.
