"""
Gestor de riesgos – reglas de concentración estilo fondo de inversión.
  • Regla del 5%: máxima concentración por ticker.
  • Máximo 20% por sector.
  • Stop-loss y take-profit sugeridos (fijo o basado en ATR).
  • Trailing stop-loss.

Las comprobaciones son INFORMATIVAS (warnings), no bloquean operaciones
porque el portfolio es un tracker de operaciones reales del usuario.
"""

import logging
from dataclasses import dataclass

from config.settings import (
    DEFAULT_STOP_LOSS_PCT,
    DEFAULT_TAKE_PROFIT_PCT,
    MAX_SECTOR_CONCENTRATION,
    MAX_TICKER_CONCENTRATION,
)
from database.models import Position

logger = logging.getLogger(__name__)


@dataclass
class RiskCheck:
    """Resultado de la validación de riesgos."""
    warnings: list[str]        # Advertencias de concentración
    ticker_concentration: float
    sector_concentration: float
    suggested_stop_loss: float
    suggested_take_profit: float

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0


def calculate_portfolio_value(positions: list[Position]) -> float:
    """Calcula el valor total del portfolio (suma de posiciones abiertas)."""
    return sum(
        (p.current_price or p.avg_price) * p.shares
        for p in positions
        if p.status.value == "open"
    )


def calculate_atr_stop_loss(
    price: float, atr: float | None, multiplier: float = 2.0
) -> float:
    """Calcula stop-loss basado en ATR. Fallback a porcentaje fijo si no hay ATR."""
    if atr is not None and atr > 0:
        sl = price - (atr * multiplier)
        return round(max(sl, price * 0.85), 4)  # Mínimo 15% de protección
    return round(price * (1 - DEFAULT_STOP_LOSS_PCT), 4)


def calculate_atr_take_profit(
    price: float, atr: float | None, multiplier: float = 3.0
) -> float:
    """Calcula take-profit basado en ATR (ratio 1.5:1 vs SL). Fallback a % fijo."""
    if atr is not None and atr > 0:
        tp = price + (atr * multiplier)
        return round(tp, 4)
    return round(price * (1 + DEFAULT_TAKE_PROFIT_PCT), 4)


def calculate_trailing_stop(
    current_price: float,
    highest_price: float,
    atr: float | None,
    trailing_pct: float = 0.08,
) -> float:
    """
    Calcula trailing stop-loss dinámico.
    Se ajusta hacia arriba con el precio, nunca baja.
    Si hay ATR, usa 2×ATR como distancia. Si no, usa porcentaje.
    """
    reference = max(current_price, highest_price)
    if atr is not None and atr > 0:
        trailing_distance = atr * 2.0
    else:
        trailing_distance = reference * trailing_pct
    return round(reference - trailing_distance, 4)


def check_risk(
    positions: list[Position],
    ticker: str,
    sector: str | None,
    amount_usd: float,
    price: float,
) -> RiskCheck:
    """
    Evalúa riesgos de concentración para una operación.
    Devuelve warnings informativos, no bloquea.
    """
    total_value = calculate_portfolio_value(positions)
    # Sumar el valor de la nueva operación al total
    total_with_new = total_value + amount_usd

    if total_with_new <= 0:
        return RiskCheck(
            warnings=[],
            ticker_concentration=0,
            sector_concentration=0,
            suggested_stop_loss=round(price * (1 - DEFAULT_STOP_LOSS_PCT), 4),
            suggested_take_profit=round(price * (1 + DEFAULT_TAKE_PROFIT_PCT), 4),
        )

    # ── 1) Concentración por ticker (regla del 5%) ──────────
    current_ticker_value = sum(
        (p.current_price or p.avg_price) * p.shares
        for p in positions
        if p.ticker == ticker.upper() and p.status.value == "open"
    )
    new_ticker_value = current_ticker_value + amount_usd
    ticker_concentration = new_ticker_value / total_with_new

    # ── 2) Concentración por sector (máx 20%) ──────────────
    sector_concentration = 0.0
    if sector:
        current_sector_value = sum(
            (p.current_price or p.avg_price) * p.shares
            for p in positions
            if p.sector == sector and p.status.value == "open"
        )
        new_sector_value = current_sector_value + amount_usd
        sector_concentration = new_sector_value / total_with_new

    # ── Warnings (informativos) ─────────────────────────────
    warnings = []

    if ticker_concentration > MAX_TICKER_CONCENTRATION:
        warnings.append(
            f"⚠️ Concentración en {ticker}: {ticker_concentration*100:.1f}% "
            f"(máx recomendado {MAX_TICKER_CONCENTRATION*100:.0f}%)"
        )

    if sector and sector_concentration > MAX_SECTOR_CONCENTRATION:
        warnings.append(
            f"⚠️ Concentración sector '{sector}': {sector_concentration*100:.1f}% "
            f"(máx recomendado {MAX_SECTOR_CONCENTRATION*100:.0f}%)"
        )

    # Stop-loss y take-profit sugeridos
    sl = round(price * (1 - DEFAULT_STOP_LOSS_PCT), 4)
    tp = round(price * (1 + DEFAULT_TAKE_PROFIT_PCT), 4)

    result = RiskCheck(
        warnings=warnings,
        ticker_concentration=round(ticker_concentration, 4),
        sector_concentration=round(sector_concentration, 4),
        suggested_stop_loss=sl,
        suggested_take_profit=tp,
    )

    if warnings:
        logger.warning(f"⚠️ Advertencias de riesgo para {ticker}: {' | '.join(warnings)}")
    else:
        logger.info(
            f"✅ Riesgo OK para {ticker}: ticker={ticker_concentration*100:.1f}%, "
            f"sector={sector_concentration*100:.1f}%"
        )

    return result


def check_stop_loss_take_profit(
    position: Position,
) -> dict[str, bool | float | None]:
    """Comprueba si se ha alcanzado el stop-loss o take-profit."""
    result: dict[str, bool | float | None] = {
        "stop_loss_hit": False,
        "take_profit_hit": False,
        "current_price": position.current_price,
        "pnl_pct": None,
    }

    if position.current_price is None:
        return result

    pnl_pct = (position.current_price - position.avg_price) / position.avg_price
    result["pnl_pct"] = round(pnl_pct * 100, 2)

    if position.stop_loss and position.current_price <= position.stop_loss:
        result["stop_loss_hit"] = True

    if position.take_profit and position.current_price >= position.take_profit:
        result["take_profit_hit"] = True

    return result
