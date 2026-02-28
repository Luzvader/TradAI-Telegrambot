"""
Conexión asíncrona a PostgreSQL con SQLAlchemy 2.x.
Incluye reconexión automática y health check.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config.settings import DATABASE_URL

logger = logging.getLogger(__name__)

engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,       # Detecta conexiones rotas antes de usarlas
    pool_recycle=1800,         # Recicla conexiones cada 30 min
    pool_timeout=30,           # Timeout esperando conexión del pool
    connect_args={
        "server_settings": {"statement_timeout": "30000"},  # 30s max por query
    },
)

async_session_factory = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Genera una sesión asíncrona para uso con 'async with'."""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def unit_of_work() -> AsyncGenerator[AsyncSession, None]:
    """
    Unit of Work: sesión transaccional que agrupa múltiples operaciones.
    Commit al final si no hay error, rollback automático si hay excepción.

    Uso:
        async with unit_of_work() as session:
            session.add(obj1)
            session.add(obj2)
            # commit automático al salir del bloque
    """
    async with async_session_factory() as session:
        async with session.begin():
            try:
                yield session
            except Exception:
                await session.rollback()
                raise


async def init_db() -> None:
    """Crea todas las tablas definidas en models.py y sincroniza columnas faltantes."""
    from database.models import Base  # noqa: F811

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # ── Auto-migración: detectar columnas faltantes en tablas existentes ──
    async with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            for col in table.columns:
                if col.primary_key:
                    continue
                try:
                    check = text(
                        "SELECT 1 FROM information_schema.columns "
                        "WHERE table_name = :t AND column_name = :c"
                    )
                    result = await conn.execute(
                        check, {"t": table.name, "c": col.name}
                    )
                    if result.scalar() is not None:
                        continue  # columna ya existe

                    # Determinar tipo SQL
                    col_type = col.type.compile(engine.dialect)
                    nullable = "" if col.nullable else " NOT NULL"
                    default = ""
                    if col.default is not None:
                        dv = col.default.arg
                        if callable(dv):
                            # Lambdas (datetime.now) → no se pueden poner como DEFAULT SQL
                            nullable = ""  # forzar nullable para evitar error
                        elif isinstance(dv, (int, float)):
                            default = f" DEFAULT {dv}"
                        elif isinstance(dv, str):
                            default = f" DEFAULT '{dv}'"
                        elif isinstance(dv, bool):
                            default = f" DEFAULT {'true' if dv else 'false'}"

                    # Si NOT NULL sin default, quitar NOT NULL (la tabla puede tener filas)
                    if nullable == " NOT NULL" and not default:
                        nullable = ""

                    ddl = f'ALTER TABLE {table.name} ADD COLUMN "{col.name}" {col_type}{nullable}{default}'
                    await conn.execute(text(ddl))
                    logger.info(f"🔧 Columna añadida: {table.name}.{col.name}")
                except Exception as e:
                    logger.warning(f"Error migrando {table.name}.{col.name}: {e}")

    logger.info("✅ Base de datos inicializada correctamente")


async def close_db() -> None:
    """Cierra el pool de conexiones."""
    await engine.dispose()
    logger.info("🔒 Conexión a base de datos cerrada")


async def health_check() -> dict:
    """
    Comprueba la salud de la conexión a la base de datos.
    Devuelve estado, latencia y tamaño del pool.
    """
    import time

    result = {
        "status": "unhealthy",
        "latency_ms": None,
        "pool_size": engine.pool.size() if hasattr(engine.pool, "size") else None,
        "pool_checked_in": engine.pool.checkedin() if hasattr(engine.pool, "checkedin") else None,
        "pool_checked_out": engine.pool.checkedout() if hasattr(engine.pool, "checkedout") else None,
    }

    try:
        start = time.monotonic()
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        elapsed = (time.monotonic() - start) * 1000
        result["status"] = "healthy"
        result["latency_ms"] = round(elapsed, 2)
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"❌ Health check fallido: {e}")

    return result
