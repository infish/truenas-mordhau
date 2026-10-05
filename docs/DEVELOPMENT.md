# Development

## How it works

The app is two containers sharing one dataset mounted at `/data`.

```text
 server container                        panel container
 ────────────────                        ───────────────
 entrypoint.sh                           FastAPI app + static HTML/JS
  1. SteamCMD install/update              - login, setup, server settings
  2. wait for setup (optional)            - map list from .pak files
  3. write Game.ini / Engine.ini          - player actions, console
  4. run MordhauServer, restart  ◄─RCON── - RCON client
     it when the panel asks      ◄─A2S─── - live status (Steam query)

            both mount the same dataset at /data;
            they share settings through /data/panel/*.env
```

- **Shared files** (`/data/panel`): the panel writes `server.env`,
  `settings.env`, `rcon.env` and `restart-request`; the server writes
  `effective.env`. The server's supervisor loop polls for `restart-request`
  and restarts only the game process (no SteamCMD), applying the new files.
- **Game.ini** is merged key by key (`replace_ini_keys` in the entrypoint) so
  the game's own `Admins`, `BannedPlayers` and `MutedPlayers` entries survive.
- **Maps** come from the `.umap` names in the server's `.pak` indexes
  (`maps.py`; supports pak v10+ directory indexes, with a regex fallback for
  older formats). The prefix (`FFA_`, `TDM_`, …) is the mode.
- **RCON** (`rcon.py`) opens a short connection per command. Player actions
  always target the PlayFab ID, and every argument is validated in
  `commands.py` before it reaches RCON.
- **Auth** (`auth.py`): the panel password is either `PANEL_PASSWORD` or a
  scrypt hash from the setup screen. Sessions are HMAC-signed cookies
  (HttpOnly, SameSite=Strict); every write also needs an `X-Panel-Request`
  header as CSRF protection. Without any password the panel is in setup mode
  and prints a one-time setup code to its log.

## Layout

```text
server/                 server image (Dockerfile, entrypoint.sh)
panel/                  panel image
  mordhau_panel/        Python package
    app.py              HTTP routes
    auth.py             passwords, setup code, sessions, RCON secret
    commands.py         RCON command building and output parsing
    maps.py             map discovery from .pak files
    rcon.py, a2s.py     protocol clients
    settings.py         rotation settings (settings.env)
    server_settings.py  server settings (server.env)
    static/             HTML, CSS, JS (no build step)
  requirements.txt      pinned, hashed dependencies for the image
tools/
  import_map_icons.py   standalone (stdlib only) importer for map pictures:
                        reads .pak files, decodes DXT1/DXT5, writes PNG, uploads
tests/                  pytest suite (fakes for RCON and A2S, entrypoint harness)
compose.truenas.yaml    install file for TrueNAS
compose.local-build.yaml builds both images locally
build-and-push.sh       builds (and pushes) both images
```

## Run the tests

Needs [uv](https://docs.astral.sh/uv/) and bash.

```bash
uv sync
uv run pytest
```

The entrypoint tests run the real `server/entrypoint.sh` against a fake
server binary, so they cover config writing, restarts and setup waiting
without downloading Mordhau.

## Run locally

```bash
docker compose -f compose.local-build.yaml up --build
```

This downloads the real Mordhau server into `./data` (several GB). The panel
is on `http://localhost:37080` with the password from the compose file.

## Build and publish images

```bash
./build-and-push.sh latest            # build and push
./build-and-push.sh latest --no-push  # build only
REGISTRY=docker.io/<you> ./build-and-push.sh latest
```

After changing panel dependencies, regenerate the hashed requirements:

```bash
uv export --no-dev --no-emit-project -o panel/requirements.txt
```

## Map pictures

The server's paks have no usable textures (servers are cooked without them),
so pictures come from a game client. `tools/import_map_icons.py` reads each
map's metadata asset (`Maps/<Map>/Metadata/BP_*Metadata`), which names its
levels and its thumbnail (`UI/UIAssets/Menu/Thumbnails/<Map>Thumb`). Levels
listed in several metadata assets take the most specific one (DIH and Legacy
overrides); unlisted levels match a thumbnail by name, then by map folder.
The 512x264 thumbnails are halved and uploaded as PNG with a manifest to
`PUT /api/map-icons/<file>` and `PUT /api/map-icons`.

## Useful facts about Mordhau's RCON

- `playerlist` prints `<PlayFabID>, <name>, <ping> ms, team <n>` per player,
  then `There are N bots.`
- `help` lists every command the server supports.
- The game display name of the current map (A2S) is like `The Pit`, not the
  level name `FFA_ThePit`.
