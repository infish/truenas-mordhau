# TrueNAS SCALE Mordhau App

This bundle gives you a Dockerized Mordhau dedicated server for TrueNAS SCALE/TrueNAS Community Edition Apps. It is designed for the Custom App "Install via YAML" flow, not a VM.

It follows the same working pattern as the 7 Days To Die app:

- Installs/updates the Mordhau Dedicated Server with SteamCMD app `629800`.
- Stores server files, SteamCMD cache, config, and logs under `/data`.
- Creates a first-run `Game.ini` and `Engine.ini` under `/data/config`.
- Creates Steam `sdk32` and `sdk64` library links so the game server can initialize Steam/EOS networking.
- Publishes the Mordhau game, beacon, query, and optional RCON ports.

## Epic Launcher Clients

You can launch Mordhau from Epic. The dedicated server still comes from SteamCMD. Mordhau's own hosting guide says there is no Epic Games Store equivalent for hosting, but SteamCMD servers work for players on both Steam and Epic.

## Files

- `compose.truenas.yaml` - paste into TrueNAS Apps > Discover Apps > Custom App > Install via YAML.
- `compose.local-build.yaml` - optional local test compose that builds the image from `image/`.
- `image/Dockerfile` - SteamCMD-based image.
- `image/entrypoint.sh` - install/update/configure/run logic.
- `build-and-push.ps1` and `build-and-push.sh` - helper scripts to build and push the image.
- `examples/truenas-wizard-fields.md` - guided Custom App wizard notes.
- `examples/config-notes.md` - Mordhau config and connection notes.

## Quick Start

1. In Docker Hub, create a public repository:

   ```text
   mordhau-server
   ```

2. Build and push the image from this folder:

   PowerShell:

   ```powershell
   .\build-and-push.ps1 -Image docker.io/infish1997/mordhau-server:latest
   ```

   Bash:

   ```bash
   ./build-and-push.sh docker.io/infish1997/mordhau-server:latest
   ```

3. In TrueNAS, create a dataset for the server, for example:

   ```text
   /mnt/Apps/MordhauServer
   ```

   Give the `apps` user/group ownership or write access. In numeric terms, that is usually UID `568` and GID `568`.

4. Edit `compose.truenas.yaml` if your dataset path is different:

   ```yaml
   source: /mnt/Apps/MordhauServer
   ```

5. Install in TrueNAS:

   ```text
   Apps > Discover Apps > Custom App > more_vert > Install via YAML
   ```

   Paste the edited compose YAML and install.

6. First startup downloads the dedicated server. It can take a few minutes.

## Connecting Over Tailscale

For private access, the default config does not advertise the server:

```yaml
ADVERTISE_SERVER: "false"
```

Connect directly from Mordhau using your TrueNAS Tailscale IP and the game port:

```text
open <truenas-tailscale-ip>:37000
```

No router port forwarding is needed when every player joins from your tailnet.

## Ports

The compose publishes:

- `37000/tcp` and `37000/udp` - game port
- `37001/tcp` and `37001/udp` - adjacent game/RCON-friendly port
- `37002/tcp` and `37002/udp` - beacon port
- `37003/tcp` and `37003/udp` - query port

RCON is only configured if you set `RCON_PASSWORD`.

## Updating

Restarting the app runs SteamCMD again. With `UPDATE_ON_START: "true"`, it applies available Mordhau dedicated server updates before starting. Set `STEAM_VALIDATE: "true"` when you want SteamCMD to validate files.

## Backup

Snapshot or back up the dataset mounted at `/data`. The most important paths are:

```text
config/Game.ini
config/Engine.ini
server/Mordhau/Saved
logs
steamcmd
```
