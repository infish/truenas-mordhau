"""HTTP API and static UI for the Mordhau panel."""

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .a2s import QueryError, query_info
from .maps import MapCatalog
from .rcon import RconAuthError, RconClient, RconError
from .settings import SettingsError, SettingsStore, validate_map

STATIC_DIR = Path(__file__).parent / "static"
# Browsers cannot attach custom headers to cross-site form posts, so requiring
# one on writes blocks CSRF against the cached Basic auth credentials.
CSRF_HEADER = "x-panel-request"


@dataclass
class Config:
    panel_password: str
    panel_username: str = "admin"
    data_dir: Path = Path("/data")
    rcon_host: str = "server"
    rcon_port: int = 37001
    rcon_password: str = ""
    query_host: str = "server"
    query_port: int = 37003
    rcon: RconClient | None = field(default=None, repr=False)

    @classmethod
    def from_env(cls) -> "Config":
        password = os.environ.get("PANEL_PASSWORD", "")
        if not password:
            raise SystemExit("PANEL_PASSWORD must be set")
        return cls(
            panel_password=password,
            panel_username=os.environ.get("PANEL_USERNAME", "admin"),
            data_dir=Path(os.environ.get("DATA_DIR", "/data")),
            rcon_host=os.environ.get("RCON_HOST", "server"),
            rcon_port=int(os.environ.get("RCON_PORT", "37001")),
            rcon_password=os.environ.get("RCON_PASSWORD", ""),
            query_host=os.environ.get("QUERY_HOST", "server"),
            query_port=int(os.environ.get("QUERY_PORT", "37003")),
        )


class ChangeLevelRequest(BaseModel):
    map: str


class SettingsRequest(BaseModel):
    default_map: str
    rotation: list[str]
    restart: bool = False


class ConsoleRequest(BaseModel):
    command: str


def create_app(config: Config) -> FastAPI:
    rcon = config.rcon or RconClient(config.rcon_host, config.rcon_port, config.rcon_password)
    catalog = MapCatalog(config.data_dir / "server" / "Mordhau" / "Content" / "Paks")
    store = SettingsStore(config.data_dir / "panel")
    basic = HTTPBasic(realm="Mordhau panel")

    def require_auth(credentials: HTTPBasicCredentials = Depends(basic)) -> None:
        user_ok = secrets.compare_digest(credentials.username.encode(), config.panel_username.encode())
        password_ok = secrets.compare_digest(credentials.password.encode(), config.panel_password.encode())
        if not (user_ok and password_ok):
            raise HTTPException(401, "Wrong username or password", headers={"WWW-Authenticate": "Basic"})

    app = FastAPI(title="Mordhau panel", docs_url=None, redoc_url=None, openapi_url=None,
                  dependencies=[Depends(require_auth)])

    @app.middleware("http")
    async def csrf_guard(request: Request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get(CSRF_HEADER) != "1":
            return JSONResponse({"detail": "Missing panel request header"}, status_code=403)
        response = await call_next(request)
        # Revalidate every load so a new panel image never runs stale JS.
        response.headers.setdefault("Cache-Control", "no-cache")
        return response

    def run_rcon(command: str) -> str:
        try:
            return rcon.command(command)
        except RconAuthError as exc:
            raise HTTPException(502, f"{exc}. Check that RCON_PASSWORD matches on both containers.") from exc
        except RconError as exc:
            raise HTTPException(502, str(exc)) from exc

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/status")
    def status():
        try:
            server = {"online": True, **query_info(config.query_host, config.query_port)}
        except QueryError as exc:
            server = {"online": False, "error": str(exc)}
        return {
            "server": server,
            "rcon_configured": bool(config.rcon_password),
            "settings": store.state(),
        }

    @app.get("/api/maps")
    def maps(refresh: bool = False):
        modes = catalog.modes(refresh=refresh)
        return {"modes": modes, "paks_dir": str(catalog.paks_dir), "errors": catalog.errors}

    @app.post("/api/changelevel")
    def changelevel(body: ChangeLevelRequest):
        try:
            map_name = validate_map(body.map)
        except SettingsError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"output": run_rcon(f"changelevel {map_name}")}

    @app.put("/api/settings")
    def save_settings(body: SettingsRequest):
        try:
            store.save(body.default_map, body.rotation)
        except SettingsError as exc:
            raise HTTPException(400, str(exc)) from exc
        if body.restart:
            store.request_restart()
        return store.state()

    @app.delete("/api/settings")
    def clear_settings():
        store.clear()
        return store.state()

    @app.post("/api/restart")
    def restart():
        store.request_restart()
        return store.state()

    @app.post("/api/console")
    def console(body: ConsoleRequest):
        command = body.command.strip()
        if not command or "\n" in command or "\r" in command:
            raise HTTPException(400, "Enter a single-line command")
        return {"output": run_rcon(command)}

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def main() -> None:
    import uvicorn

    uvicorn.run(create_app(Config.from_env()), host="0.0.0.0", port=int(os.environ.get("PORT", "8080")),
                proxy_headers=False, access_log=False)
