# Using the panel

Open `http://<your-truenas-ip>:37080` and log in with your panel password.
The panel works the same on a phone, a laptop or a desktop.

The bar at the top shows the server's state: a **green dot** with the server
name, the current map and the player count means it is running; a **red dot**
means it is offline or still starting.

## Change map now

Switches the map **immediately**. Everyone on the server loads into the new
map; nobody is disconnected.

1. Pick a **mode** (Free-for-all, Team deathmatch, Skirmish, ...).
2. Pick a **map**. The map that is running now is marked **● live**.
3. Click **Change to …**.

In Mordhau the mode is part of the map name: `FFA_Camp` is Camp in
free-for-all, `TDM_Camp` is the same map in team deathmatch. The panel reads
the list of maps from the installed server, so it is always complete.

| Prefix | Mode |
| --- | --- |
| FFA | Free-for-all |
| TDM | Team deathmatch |
| SKM | Skirmish |
| FL | Frontline |
| INV | Invasion |
| HRD | Horde |
| DIH | Demon Invasion (horde event) |
| BR | Battle royale |
| DU | Duel |
| SG, TF | Shown by their short name |

Maps from mods are not in the list. Open **Other map name (mods)** and type
the map name instead.

## Players

Refreshes every 5 seconds while the page is open. Admins have an **admin**
badge. Click **Actions** next to a player:

| Button | What it does |
| --- | --- |
| **Make admin / Remove admin** | Gives or takes admin rights. Admins can use admin commands in their game console. It is saved and survives restarts. |
| **Move to team …** | Moves the player to the other team. |
| **Kill** | Kills the player's character. |
| **Mute / Unmute** | Mutes the player for the chosen time, or lifts it. |
| **Kick** | Removes the player; they can rejoin. |
| **Ban** | Removes the player and blocks them for the chosen time. |
| **Rename** | Changes the player's name on the server. |

The **reason** box is used by Kick and Ban; spaces in it are sent as
underscores. Kick, Ban and Kill ask for confirmation.

> **The gun:** admins can type `ParryThis` in their in-game console (the `~`
> key) to get Mordhau's hidden gun.

Below the player list:

- **Bots:** add or remove bots, optionally on one team.
- **Message everyone:** shows a message to all players.
- **Match time:** **Check** shows the remaining time; **+5 min** and
  **+10 min** extend the current match.
- **Ban list / Mute list:** shows everyone banned or muted, with **Unban** and
  **Unmute** buttons.

## Rotation & startup map

- **Startup map:** the map the server starts on after a restart.
- **Rotation:** the maps the server plays one after another. Add maps with
  the mode and map pickers and **Add**; reorder with ↑ ↓; remove with ✕.

Changes apply after a server restart:

- **Save** stores them for the next restart.
- **Save & restart** restarts the game right away (about a minute; players
  are disconnected and can rejoin).
- **Use app defaults** removes the panel's rotation and goes back to the
  values from the app's YAML, if you set any there.

The line "Running with: …" shows what the server actually started with.

## Server settings

Server name, max players, public listing, join password and admin password.
These are the same settings as on the setup screen.

- Password fields are **empty on purpose**: the panel never shows saved
  passwords. It says whether one is set. Leave a field empty to keep the
  current password, type a new one to change it, or tick **No join password**
  / **No admin password** to remove it.
- **Save** applies on the next restart; **Save & restart** applies now.

**Change panel password** changes your login for the panel. Other devices are
logged out and need the new password. (If your panel password is set in the
app's YAML as `PANEL_PASSWORD`, change it there instead.)

## Console

Sends any command to the server, for things the panel has no button for.
Type `help` to see every command the server understands. Useful ones:

| Command | Does |
| --- | --- |
| `help` | Lists all commands |
| `playerlist` | Players with their PlayFab IDs |
| `maplist` | Maps the server knows about |
| `info` | Server information |
| `chatlog 20` | The last 20 chat messages |

## Logging out

**Log out** at the top right. Logins otherwise last 30 days per browser.
