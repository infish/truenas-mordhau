#!/usr/bin/env python3
"""Gives the Mordhau app its icon in the TrueNAS Apps list.

TrueNAS gives every custom (YAML) app the same blank metadata, and the YAML
cannot set an icon. This sets the icon in the app's own metadata file and asks
TrueNAS to rebuild its app list. TrueNAS does not rewrite that file when you
edit a custom app, so the icon stays until the app is deleted.

Run it on TrueNAS (System > Shell, or ssh) as root:

    sudo python3 truenas-set-app-icon.py              # finds the Mordhau app itself
    sudo python3 truenas-set-app-icon.py mordhau      # or name the app
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml  # ships with TrueNAS

ICON = ("https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/629760/"
        "1ce1643c91aa49fee0b63c68f8fb56f8a08d540b.ico")  # Mordhau's icon on Steam's CDN
APPS_DIR = Path("/mnt/.ix-apps/app_configs")
IMAGE_MARKER = "mordhau-panel"


def midclt(*args: str) -> str:
    return subprocess.check_output(["midclt", "call", *args], text=True)


def find_mordhau_apps() -> list[str]:
    apps = json.loads(midclt("app.query", "[]", '{"select": ["name", "custom_app"]}'))
    found = []
    for app in apps:
        if not app.get("custom_app"):
            continue
        config = json.loads(midclt("app.config", app["name"]))
        images = [svc.get("image", "") for svc in config.get("services", {}).values()]
        if any(IMAGE_MARKER in image for image in images):
            found.append(app["name"])
    return found


def set_icon(app: str) -> None:
    path = APPS_DIR / app / "metadata.yaml"
    if not path.is_file():
        raise SystemExit(f"{path} not found: is {app!r} the right app name?")
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict) or not isinstance(data.get("metadata"), dict):
        raise SystemExit(f"{path} does not look like TrueNAS app metadata; not touching it")
    if data["metadata"].get("icon") == ICON:
        print(f"{app}: icon already set")
        return

    backup = path.with_name(f"metadata.yaml.bak-icon-{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(path, backup)
    data["metadata"]["icon"] = ICON
    info = path.stat()
    tmp = path.with_name("metadata.yaml.tmp-icon")
    tmp.write_text(yaml.safe_dump(data, default_flow_style=False, sort_keys=False))
    os.chmod(tmp, info.st_mode & 0o7777)
    os.chown(tmp, info.st_uid, info.st_gid)
    os.replace(tmp, path)
    print(f"{app}: icon set (backup: {backup})")


def main() -> None:
    if os.geteuid() != 0:
        raise SystemExit("Run this with sudo on TrueNAS.")
    apps = sys.argv[1:] or find_mordhau_apps()
    if not apps:
        raise SystemExit("No Mordhau app found. Pass the app name, e.g. sudo python3 truenas-set-app-icon.py mordhau")
    for app in apps:
        set_icon(app)
    # Rebuild TrueNAS's combined app list from the per-app files.
    subprocess.run(["midclt", "call", "-j", "app.metadata_generate"], check=True, stdout=subprocess.DEVNULL)
    for app in apps:
        result = json.loads(midclt("app.query", json.dumps([["name", "=", app]]), '{"select": ["metadata"]}'))
        icon = result[0]["metadata"].get("icon") if result else None
        print(f"{app}: {'icon active' if icon == ICON else 'icon NOT active, check the output above'}")
    print("Reload the TrueNAS Apps page to see it.")


if __name__ == "__main__":
    main()
