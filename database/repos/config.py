"""
Repositorio – Auto Mode, Investment Objectives, Custom Alerts.
"""

import logging
from datetime import UTC, datetime
from typing import Sequence

from sqlalchemy import select, update

from database.connection import async_session_factory
from database.models import (
    AutoModeConfig,
    AutoModeType,
    CustomAlert,
    InvestmentObjective,
)

logger = logging.getLogger(__name__)


# ── Auto Mode ────────────────────────────────────────────────


async def get_auto_mode_config(portfolio_id: int) -> AutoModeConfig | None:
    """Obtiene la configuración de modo auto para un portfolio."""
    async with async_session_factory() as session:
        stmt = select(AutoModeConfig).where(
            AutoModeConfig.portfolio_id == portfolio_id
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def get_or_create_auto_mode_config(portfolio_id: int) -> AutoModeConfig:
    """Obtiene o crea la configuración de modo auto."""
    async with async_session_factory() as session:
        stmt = select(AutoModeConfig).where(
            AutoModeConfig.portfolio_id == portfolio_id
        )
        result = await session.execute(stmt)
        config = result.scalar_one_or_none()
        if config is None:
            config = AutoModeConfig(portfolio_id=portfolio_id, mode=AutoModeType.OFF)
            session.add(config)
            await session.commit()
            await session.refresh(config)
        return config


async def set_auto_mode(portfolio_id: int, mode: AutoModeType) -> AutoModeConfig:
    """Establece el modo automático: OFF, ON o SAFE.

    Al activar (ON o SAFE), inicializa los timestamps de última ejecución
    a 'ahora' para que cada tarea espere su intervalo completo antes de
    ejecutarse por primera vez (evita que todas disparen a la vez).
    """
    async with async_session_factory() as session:
        stmt = select(AutoModeConfig).where(
            AutoModeConfig.portfolio_id == portfolio_id
        )
        result = await session.execute(stmt)
        config = result.scalar_one_or_none()
        now = datetime.now(UTC)
        active = mode != AutoModeType.OFF
        if config is None:
            config = AutoModeConfig(
                portfolio_id=portfolio_id,
                mode=mode,
                last_scan_at=now if active else None,
                last_analyze_at=now if active else None,
                last_macro_at=now if active else None,
            )
            session.add(config)
        else:
            config.mode = mode
            config.updated_at = now
            # Al activar, resetear timestamps para que esperen su intervalo
            if active:
                config.last_scan_at = config.last_scan_at or now
                config.last_analyze_at = config.last_analyze_at or now
                config.last_macro_at = config.last_macro_at or now
        await session.commit()
        await session.refresh(config)
        return config


# Alias de compatibilidad
async def toggle_auto_mode(portfolio_id: int, enabled: bool) -> AutoModeConfig:
    """Compatibilidad: convierte bool a AutoModeType."""
    mode = AutoModeType.ON if enabled else AutoModeType.OFF
    return await set_auto_mode(portfolio_id, mode)


async def update_auto_mode_config(
    portfolio_id: int, **kwargs
) -> AutoModeConfig | None:
    """Actualiza campos de configuración del modo auto."""
    async with async_session_factory() as session:
        stmt = select(AutoModeConfig).where(
            AutoModeConfig.portfolio_id == portfolio_id
        )
        result = await session.execute(stmt)
        config = result.scalar_one_or_none()
        if config is None:
            return None
        for key, value in kwargs.items():
            if hasattr(config, key):
                setattr(config, key, value)
        config.updated_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(config)
        return config


async def update_auto_mode_timestamps(
    portfolio_id: int, **kwargs
) -> None:
    """Actualiza los timestamps de última ejecución del modo auto."""
    async with async_session_factory() as session:
        stmt = select(AutoModeConfig).where(
            AutoModeConfig.portfolio_id == portfolio_id
        )
        result = await session.execute(stmt)
        config = result.scalar_one_or_none()
        if config:
            for key, value in kwargs.items():
                if hasattr(config, key):
                    setattr(config, key, value)
            await session.commit()


async def get_all_active_auto_modes() -> Sequence[AutoModeConfig]:
    """Obtiene todas las configuraciones de modo auto activas (ON o SAFE)."""
    async with async_session_factory() as session:
        stmt = select(AutoModeConfig).where(
            AutoModeConfig.mode.in_([AutoModeType.ON, AutoModeType.SAFE])
        )
        result = await session.execute(stmt)
        return result.scalars().all()


# ── Custom Alerts ────────────────────────────────────────────


async def create_custom_alert(
    ticker: str,
    alert_type: str,
    threshold: float,
    market: str = "NASDAQ",
    message: str | None = None,
) -> CustomAlert:
    """Crea una alerta personalizada."""
    async with async_session_factory() as session:
        alert = CustomAlert(
            ticker=ticker.upper(),
            market=(market or "NASDAQ").upper(),
            alert_type=alert_type,
            threshold=threshold,
            message=message,
        )
        session.add(alert)
        await session.commit()
        await session.refresh(alert)
        return alert


async def get_active_alerts() -> Sequence[CustomAlert]:
    """Obtiene todas las alertas no disparadas."""
    async with async_session_factory() as session:
        stmt = select(CustomAlert).where(CustomAlert.triggered == False)
        result = await session.execute(stmt)
        return result.scalars().all()


async def trigger_alert(alert_id: int) -> None:
    """Marca una alerta como disparada."""
    async with async_session_factory() as session:
        stmt = (
            update(CustomAlert)
            .where(CustomAlert.id == alert_id)
            .values(triggered=True, triggered_at=datetime.now(UTC))
        )
        await session.execute(stmt)
        await session.commit()


async def delete_alert(alert_id: int) -> bool:
    """Elimina una alerta."""
    async with async_session_factory() as session:
        alert = await session.get(CustomAlert, alert_id)
        if alert is None:
            return False
        await session.delete(alert)
        await session.commit()
        return True


# ── Investment Objectives ────────────────────────────────────


async def save_investment_objective(
    ticker: str,
    market: str = "NASDAQ",
    thesis: str | None = None,
    target_entry_price: float | None = None,
    target_exit_price: float | None = None,
    catalysts: str | None = None,
    risks: str | None = None,
    time_horizon: str | None = "medio",
    conviction: int | None = None,
    source: str = "ai",
) -> InvestmentObjective:
    """Crea o actualiza un objetivo de inversión para un ticker."""
    async with async_session_factory() as session:
        market_norm = (market or "NASDAQ").upper()
        # Buscar si ya existe uno activo
        stmt = select(InvestmentObjective).where(
            InvestmentObjective.ticker == ticker.upper(),
            InvestmentObjective.market == market_norm,
            InvestmentObjective.active == True,
        )
        result = await session.execute(stmt)
        obj = result.scalar_one_or_none()

        if obj is None:
            obj = InvestmentObjective(
                ticker=ticker.upper(),
                market=market_norm,
                thesis=thesis,
                target_entry_price=target_entry_price,
                target_exit_price=target_exit_price,
                catalysts=catalysts,
                risks=risks,
                time_horizon=time_horizon,
                conviction=conviction,
                source=source,
            )
            session.add(obj)
        else:
            # Actualizar campos si se proporcionan
            if thesis is not None:
                obj.thesis = thesis
            if target_entry_price is not None:
                obj.target_entry_price = target_entry_price
            if target_exit_price is not None:
                obj.target_exit_price = target_exit_price
            if catalysts is not None:
                obj.catalysts = catalysts
            if risks is not None:
                obj.risks = risks
            if time_horizon is not None:
                obj.time_horizon = time_horizon
            if conviction is not None:
                obj.conviction = conviction
            obj.updated_at = datetime.now(UTC)

        await session.commit()
        await session.refresh(obj)
        return obj


async def get_investment_objective(
    ticker: str, market: str | None = None
) -> InvestmentObjective | None:
    """Obtiene el objetivo activo para un ticker (opcionalmente filtrado por mercado)."""
    async with async_session_factory() as session:
        stmt = select(InvestmentObjective).where(InvestmentObjective.active == True)
        stmt = stmt.where(InvestmentObjective.ticker == ticker.upper())
        if market:
            stmt = stmt.where(InvestmentObjective.market == market.upper())
        stmt = stmt.order_by(InvestmentObjective.updated_at.desc())
        result = await session.execute(stmt)
        return result.scalars().first()


async def get_all_active_objectives() -> Sequence[InvestmentObjective]:
    """Obtiene todos los objetivos activos."""
    async with async_session_factory() as session:
        stmt = select(InvestmentObjective).where(
            InvestmentObjective.active == True,
        ).order_by(InvestmentObjective.updated_at.desc())
        result = await session.execute(stmt)
        return result.scalars().all()


async def deactivate_objective(
    ticker: str, market: str | None = None
) -> bool:
    """Desactiva el objetivo de un ticker (opcionalmente filtrado por mercado)."""
    async with async_session_factory() as session:
        stmt = select(InvestmentObjective).where(InvestmentObjective.active == True)
        stmt = stmt.where(InvestmentObjective.ticker == ticker.upper())
        if market:
            stmt = stmt.where(InvestmentObjective.market == market.upper())
        result = await session.execute(stmt)
        objs = list(result.scalars().all())
        if not objs:
            return False
        now = datetime.now(UTC)
        for obj in objs:
            obj.active = False
            obj.updated_at = now
        await session.commit()
        return True
