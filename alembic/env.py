"""
Alembic env.py — entorno de migración async para TradAI.

Usa la misma cadena de conexión que config/settings.py y detecta
automáticamente los modelos SQLAlchemy en database/models.py.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

# ── Importar modelos y config ────────────────────────────────
import sys
from pathlib import Path

# Asegurar que el raíz del proyecto está en sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import DATABASE_URL          # noqa: E402
from database.models import Base                   # noqa: E402

# ── Alembic Config ───────────────────────────────────────────
config = context.config

# Interpretar archivo logging desde alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata para autogenerate
target_metadata = Base.metadata

# Sobreescribir URL con la de settings (respeta .env)
config.set_main_option("sqlalchemy.url", DATABASE_URL)


def run_migrations_offline() -> None:
    """Ejecutar migraciones en modo offline (genera SQL sin conexión)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """Helper síncrono para ejecutar migraciones."""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Ejecutar migraciones en modo async (online)."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Punto de entrada para migraciones online."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
