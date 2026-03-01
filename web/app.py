"""
Aplicación FastAPI principal del dashboard web.

Incluye middleware de autenticación: todas las rutas (excepto /login,
/static y /api/health) requieren una sesión válida generada mediante
el comando /web de Telegram.
"""

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
from starlette.middleware.base import BaseHTTPMiddleware

from web.auth import auth_manager, SESSION_COOKIE
from web.routes import router

_WEB_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="TradAI Dashboard",
    description="Panel de control para TradAI",
    docs_url=None,       # Desactivar docs en producción
    redoc_url=None,
)

# Plantillas Jinja2
templates = Jinja2Templates(directory=str(_WEB_DIR / "templates"))


# ── Middleware de autenticación ──────────────────────────────

# Rutas que no requieren autenticación
_PUBLIC_PATHS = {"/login", "/api/health"}
_PUBLIC_PREFIXES = ("/static",)


class AuthMiddleware(BaseHTTPMiddleware):
    """Redirige a /login si no hay sesión válida."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Permitir rutas públicas
        if path in _PUBLIC_PATHS or path.startswith(_PUBLIC_PREFIXES):
            return await call_next(request)

        # Comprobar cookie de sesión
        session_token = request.cookies.get(SESSION_COOKIE)
        if auth_manager.validate_session(session_token):
            return await call_next(request)

        # Sin sesión → redirigir a login
        return RedirectResponse(url="/login", status_code=302)


app.add_middleware(AuthMiddleware)

# Archivos estáticos (CSS/JS)
static_dir = _WEB_DIR / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Rutas
app.include_router(router)
