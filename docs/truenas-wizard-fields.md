# TrueNAS Custom App Wizard Fields

Use this if you prefer the guided Custom App wizard instead of "Install via YAML".

## Application Name

- Application Name: `mordhau`
- Version: accept default

## Image Configuration

- Repository: `docker.io/infish1997/mordhau-server`
- Tag: `latest`
- Pull Policy: `Always pull image` while testing

## Container Configuration

- Timezone: `Europe/Prague`
- Restart Policy: `Unless Stopped`
- Environment Variables:
  - `UPDATE_ON_START` = `true`
  - `STEAM_VALIDATE` = `false`
  - `APPLY_ENV_ON_START` = `false`
  - `SERVER_NAME` = `Home Mordhau`
  - `SERVER_PASSWORD` = blank or your join password
  - `ADMIN_PASSWORD` = long random password
  - `RCON_PASSWORD` = long random password (required by the panel)
  - `MAX_PLAYERS` = `16`
  - `ADVERTISE_SERVER` = `false`
  - `DEFAULT_MAP` = `FFA_ThePit`
  - `MAP_ROTATION` = `FFA_ThePit,FFA_Camp,TDM_Camp`
  - `GAME_PORT` = `37000`
  - `BEACON_PORT` = `37002`
  - `QUERY_PORT` = `37003`
  - `RCON_PORT` = `37001`

## Security Context

- Privileged: off
- User ID: `568`
- Group ID: `568`

## Network

- Host Network: off
- Ports:
  - Container `37000`, Host `37000`, TCP
  - Container `37000`, Host `37000`, UDP
  - Container `37001`, Host `37001`, TCP
  - Container `37001`, Host `37001`, UDP
  - Container `37002`, Host `37002`, TCP
  - Container `37002`, Host `37002`, UDP
  - Container `37003`, Host `37003`, TCP
  - Container `37003`, Host `37003`, UDP

## Storage

- Type: Host Path
- Host Path: `/mnt/Apps/MordhauServer`
- Mount Path: `/data`
- ACL: give the `apps` user/group ownership or write access

## Panel

The wizard creates a single container. To run the web panel too, use
"Install via YAML" with `compose.truenas.yaml` instead.
