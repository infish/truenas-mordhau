"""HTTP API and static UI for the Mordhau panel."""

import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .a2s import QueryError, query_info
from .auth import COOKIE_NAME, SESSION_SECONDS, SessionSigner
from .commands import (
    CommandError,
    bots_command,
    extend_match_command,
    ids_in,
    list_entries,
    parse_playerlist,
    player_command,
    say_command,
)
from .maps import MapCatalog
from .rcon import RconAuthError, RconClient, RconError
from .settings import SettingsError, SettingsStore, validate_map

STATIC_DIR = Path(__file__).parent / "static"
# Browsers cannot attach custom headers to cross-site form posts, so requiring
# one on writes blocks CSRF (on top of the SameSite session cookie).
CSRF_HEADER = "x-panel-request"
FAILED_LOGIN_DELAY = 1.0


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


class LoginRequest(BaseModel):
    password: str


class PlayerActionRequest(BaseModel):
    reason: str | None = None
    duration: int | None = None
    team: int | None = None
    name: str | None = None


class BotsRequest(BaseModel):
    action: str
    amount: int
    team: int | None = None


class SayRequest(BaseModel):
    message: str


class ExtendMatchRequest(BaseModel):
    seconds: int


def create_app(config: Config) -> FastAPI:
    rcon = config.rcon or RconClient(config.rcon_host, config.rcon_port, config.rcon_password)
    catalog = MapCatalog(config.data_dir / "server" / "Mordhau" / "Content" / "Paks")
    store = SettingsStore(config.data_dir / "panel")
    signer = SessionSigner(config.panel_password)
    # auto_error=False: no WWW-Authenticate challenge, so browsers show the
    # login page instead of a native popup. Basic auth still works for scripts.
    basic = HTTPBasic(auto_error=False)

    def password_ok(password: str) -> bool:
        return secrets.compare_digest(password.encode(), config.panel_password.encode())

    def authenticated(request: Request, credentials: HTTPBasicCredentials | None) -> bool:
        if signer.valid(request.cookies.get(COOKIE_NAME)):
            return True
        if credentials is None:
            return False
        user_ok = secrets.compare_digest(credentials.username.encode(), config.panel_username.encode())
        return user_ok and password_ok(credentials.password)

    def require_auth(request: Request, credentials: HTTPBasicCredentials | None = Depends(basic)) -> None:
        if not authenticated(request, credentials):
            raise HTTPException(401, "Not logged in")

    app = FastAPI(title="Mordhau panel", docs_url=None, redoc_url=None, openapi_url=None)
    api = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])

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
    def index(request: Request, credentials: HTTPBasicCredentials | None = Depends(basic)):
        page = "index.html" if authenticated(request, credentials) else "login.html"
        return FileResponse(STATIC_DIR / page)

    @app.post("/login")
    def login(body: LoginRequest, response: Response):
        if not password_ok(body.password):
            time.sleep(FAILED_LOGIN_DELAY)
            raise HTTPException(401, "Wrong password")
        response.set_cookie(COOKIE_NAME, signer.issue(), max_age=SESSION_SECONDS,
                            httponly=True, samesite="strict")
        return {"ok": True}

    @app.post("/logout")
    def logout(response: Response):
        response.delete_cookie(COOKIE_NAME, httponly=True, samesite="strict")
        return {"ok": True}

    @api.get("/status")
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

    @api.get("/maps")
    def maps(refresh: bool = False):
        modes = catalog.modes(refresh=refresh)
        return {"modes": modes, "paks_dir": str(catalog.paks_dir), "errors": catalog.errors}

    @api.post("/changelevel")
    def changelevel(body: ChangeLevelRequest):
        try:
            map_name = validate_map(body.map)
        except SettingsError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"output": run_rcon(f"changelevel {map_name}")}

    @api.put("/settings")
    def save_settings(body: SettingsRequest):
        try:
            store.save(body.default_map, body.rotation)
        except SettingsError as exc:
            raise HTTPException(400, str(exc)) from exc
        if body.restart:
            store.request_restart()
        return store.state()

    @api.delete("/settings")
    def clear_settings():
        store.clear()
        return store.state()

    @api.post("/restart")
    def restart():
        store.request_restart()
        return store.state()

    def build(builder, *args, **kwargs) -> str:
        try:
            return builder(*args, **kwargs)
        except CommandError as exc:
            raise HTTPException(400, str(exc)) from exc

    @api.get("/players")
    def players():
        players, bots = parse_playerlist(run_rcon("playerlist"))
        admins = ids_in(run_rcon("adminlist"))
        return {
            "players": [{**vars(p), "admin": p.id in admins} for p in players],
            "bots": bots,
        }

    @api.post("/players/{target}/{action}")
    def player_action(target: str, action: str, body: PlayerActionRequest | None = None):
        body = body or PlayerActionRequest()
        command = build(player_command, action, target, reason=body.reason, duration=body.duration,
                        team=body.team, name=body.name)
        return {"command": command, "output": run_rcon(command)}

    @api.post("/bots")
    def bots(body: BotsRequest):
        command = build(bots_command, body.action, body.amount, body.team)
        return {"command": command, "output": run_rcon(command)}

    @api.post("/say")
    def say(body: SayRequest):
        return {"output": run_rcon(build(say_command, body.message))}

    @api.get("/bans")
    def bans():
        return {"entries": list_entries(run_rcon("banlist"))}

    @api.get("/mutes")
    def mutes():
        return {"entries": list_entries(run_rcon("mutelist"))}

    @api.get("/match")
    def match():
        return {"output": run_rcon("getmatchduration")}

    @api.post("/match/extend")
    def extend_match(body: ExtendMatchRequest):
        return {"output": run_rcon(build(extend_match_command, body.seconds))}

    @api.post("/console")
    def console(body: ConsoleRequest):
        command = body.command.strip()
        if not command or "\n" in command or "\r" in command:
            raise HTTPException(400, "Enter a single-line command")
        return {"output": run_rcon(command)}

    app.include_router(api)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def main() -> None:
    import uvicorn

    uvicorn.run(create_app(Config.from_env()), host="0.0.0.0", port=int(os.environ.get("PORT", "8080")),
                proxy_headers=False, access_log=False)
