# Troubleshooting

To see what a container is doing: **Apps** → **mordhau** → **Workloads** →
the **logs** icon next to **server** or **panel**.

## Setup

### I can't find the setup code

Open the **panel** container's log (not the server's). The code is in a box
of `=` signs near the top: `Mordhau panel setup code: XXXX-XXXX`. If the log
is long, use the search in the log viewer for `setup code`.

### "Wrong setup code"

The code changes whenever the panel container restarts. Look for the
**newest** code in the log. Dashes, spaces and capitals do not matter.

### The setup screen does not appear, I get a login page

Setup is already done, or `PANEL_PASSWORD` is set in the YAML. Log in with
that password. To start over, see "I forgot the panel password".

## Server

### The status dot stays red after installing

On the first install the server downloads several GB from Steam before it can
start, and it waits until you finish setup. Check the **server** log:

- `Waiting for setup` → finish the setup screen.
- SteamCMD progress lines → still downloading; wait.
- `Starting server` → it is starting; give it a minute.

### <a id="permission-denied"></a>"Permission denied" in the server or panel log

The containers run as the `apps` user (UID 568) and cannot write to the
dataset. Fix: **Datasets** → your dataset → **Permissions** → **Edit** and
give the `apps` user full control (or recreate the dataset with the **Apps**
preset). Then restart the app.

### "No maps found yet" in the panel

The panel reads the maps from the installed server files. They appear once
the first download has finished.

### The server crashed or keeps restarting

Look at the end of the **server** log. If an update broke the files, set
`STEAM_VALIDATE: "true"` in the YAML, redeploy once, and set it back to
`"false"` afterwards.

## Panel

### The panel shows a line of text like `{"detail": ...}` or looks outdated

Your browser has an old copy. Reload with **Ctrl+Shift+R** (Mac:
**Cmd+Shift+R**).

### "RCON password was rejected"

`RCON_PASSWORD` is set on only one of the two containers, or to different
values. Set the same value on both, or remove it from both (then the panel
generates one). Redeploy afterwards.

### "Cannot reach RCON" / "RCON timed out"

The game server is not running yet, or is restarting. Wait a minute. If it
lasts, check the server log.

### I forgot the panel password

Edit the app's YAML and add your new password to the **panel** service:

```yaml
    environment:
      TZ: Europe/Prague
      PANEL_PASSWORD: "my-new-password"
```

Save. The panel now uses that password, and you can log in again.

To start fresh instead (setup screen with a new setup code), delete the stored
password file from the TrueNAS shell (**System** → **Shell**), using your
dataset path, then restart the app:

```bash
sudo rm /mnt/tank/MordhauServer/panel/panel-auth.env
```

Setup then asks for all server settings again; maps, admins and bans are
kept.

## Playing

### Friends cannot connect

- From outside your home: they need [Tailscale or port forwarding](PLAYING.md).
- With port forwarding: forward **UDP** 37000, 37002 and 37003 to the TrueNAS
  IP, and make sure friends use your **public** IP.
- Check that the server is green in the panel.

### The server is not in the public server browser

- **List publicly** must be on (**Server settings**), followed by a restart.
- For players outside your home, UDP 37003 must be forwarded.
- It can take a few minutes to appear.

### Admins lost their rights after a restart

That was a bug in early versions, which rewrote `Game.ini` from scratch.
Update the app; admins, bans and mutes are kept since then. Re-add the
missing admins once from the panel.

## Installing

### "Port already in use" when installing

Another app uses one of the ports (37000, 37002, 37003, 37080). Change the
`published:` number of that port in the YAML, e.g. `published: 37081` for the
panel, and open the panel on the new port. If you move the panel, also change
`port: 37080` under `x-portals` at the top, so the **Web UI** button follows.
