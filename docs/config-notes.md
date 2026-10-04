# Mordhau Config Notes

The container creates:

```text
/data/config/Game.ini
/data/config/Engine.ini
```

On TrueNAS, that maps to:

```text
/mnt/Apps/MordhauServer/config/Game.ini
/mnt/Apps/MordhauServer/config/Engine.ini
```

## Environment Versus INI Files

On first run, the container writes selected environment variables into the INI files. After that, the INI files are left alone by default.

Use this if you want compose variables to overwrite the INI files on the next start:

```yaml
APPLY_ENV_ON_START: "true"
```

Put it back after the config is updated:

```yaml
APPLY_ENV_ON_START: "false"
```

## Map Rotation

`DEFAULT_MAP` is the map the server boots into. `MAP_ROTATION` is a
comma-separated list with no length limit:

```yaml
MAP_ROTATION: "FFA_ThePit,FFA_Camp,TDM_Camp,SKM_Grad"
```

The older `MAP_ROTATION_1`, `MAP_ROTATION_2`, ... variables still work (any
number of them) when `MAP_ROTATION` is unset.

Rotation and startup map saved from the panel are stored in
`/data/panel/settings.env` and take precedence over these variables. Use the
panel's "Use app defaults" button to go back to the app values. With
`APPLY_ENV_ON_START: "false"`, an existing Game.ini keeps its rotation until
the panel saves a new one.

## Tailscale-Only Server

The default is private/unadvertised:

```yaml
ADVERTISE_SERVER: "false"
```

Connect from the Mordhau console with:

```text
open <truenas-tailscale-ip>:37000
```

For a passworded server:

```text
open <truenas-tailscale-ip>:37000?ServerPassword=<password>
```

## Admin Login

In game, open the console and run:

```text
AdminLogin <your admin password>
```

## Common Maps

Some useful defaults:

```text
FFA_ThePit
FFA_Camp
FFA_Contraband
FFA_Grad
FFA_MountainPeak
FFA_Taiga
TDM_Camp
TDM_Grad
SKM_Camp
```
