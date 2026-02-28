"""
Aplicación FastAPI principal del dashboard web.
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from web.routes import router

_WEB_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="TradAI Dashboard",
    description="Panel de control para TradAI",
    docs_url="/api/docs",
    redoc_url=None,
)

# Plantillas Jinja2
templates = Jinja2Templates(directory=str(_WEB_DIR / "templates"))

# Archivos estáticos (CSS/JS)
static_dir = _WEB_DIR / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Rutas
app.include_router(router)
