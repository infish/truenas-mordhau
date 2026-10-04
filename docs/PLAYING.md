# Playing with friends

## Joining from your home network

In Mordhau, open the console with the `~` key and type:

```text
open <your-truenas-ip>:37000
```

for example `open 192.168.1.50:37000`. If the server has a join password, the
game asks for it.

If you ticked **List publicly**, the server also appears in Mordhau's server
browser under its name.

## Friends who are not at your home

Friends need a way to reach your TrueNAS from the internet. Pick **one**:

### Option A: Tailscale (easiest and safest)

[Tailscale](https://tailscale.com) is a free private network between your
devices and your friends' devices. Nothing is opened on your router.

1. Install the **Tailscale** app on TrueNAS (from the TrueNAS app catalog) and
   sign in.
2. Each friend installs Tailscale on their PC, and you
   [share your TrueNAS](https://tailscale.com/kb/1084/sharing) with them (or
   invite them to your tailnet).
3. Friends join with the TrueNAS **Tailscale IP** (shown in the Tailscale
   admin console, starts with `100.`):

   ```text
   open 100.x.y.z:37000
   ```

### Option B: Port forwarding

Open these ports on your **router**, pointing to your TrueNAS IP:

| Port | Protocol | Used for |
| --- | --- | --- |
| 37000 | UDP | Game traffic |
| 37002 | UDP | Beacon |
| 37003 | UDP | Server query (server browser listing) |

Friends then join with your **public** IP (search "what is my IP" from home):

```text
open <your-public-ip>:37000
```

**Never forward port 37080** (the panel) or 37001 (RCON). The panel has no
encryption and is meant for your home network or Tailscale only.

Every router is different; search for "port forwarding" plus your router's
model if you are not sure where the setting is.

## Making friends admin

Two ways:

- **From the panel (recommended):** while they are on the server, open
  **Players** → their **Actions** → **Make admin**. This is tied to their
  account and survives restarts. They do not need any password.
- **With the admin password:** if you set one, they type
  `adminlogin <admin password>` in their game console. This lasts for their
  current session only.

Admins can then use admin commands in their game console, for example
`ParryThis` to get the gun.

## Using the panel away from home

The panel works over Tailscale too: `http://100.x.y.z:37080` from any device
on your tailnet. Do not make it reachable from the open internet.
