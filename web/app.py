"""
FastAPI web application entrypoint.

Responsibilities:
- authentication middleware (Telegram web code + session cookie)
- JSON API routing
- serving Angular SPA build through routes defined in web.routes
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from web.auth import SESSION_COOKIE, auth_manager
from web.routes import router

_WEB_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="TradAI Dashboard",
    description="Panel de control para TradAI",
    docs_url=None,
    redoc_url=None,
)

# Jinja is still used for /login page.
templates = Jinja2Templates(directory=str(_WEB_DIR / "templates"))

# Public routes that do not require an authenticated session.
_PUBLIC_PATHS = {"/login", "/api/health"}
_PUBLIC_PREFIXES = ("/static",)


class AuthMiddleware(BaseHTTPMiddleware):
    """Redirect unauthenticated requests to /login."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if path in _PUBLIC_PATHS or path.startswith(_PUBLIC_PREFIXES):
            return await call_next(request)

        session_token = request.cookies.get(SESSION_COOKIE)
        if auth_manager.validate_session(session_token):
            return await call_next(request)

        return RedirectResponse(url="/login", status_code=302)


app.add_middleware(AuthMiddleware)

static_dir = _WEB_DIR / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(router)
