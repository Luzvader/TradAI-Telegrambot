"""
Watchlist IA - genera y mantiene una watchlist de hasta 25 posiciones
(acciones + ETFs) fuera de la cartera que merecen estudio.

La watchlist se compone de:
  - Hasta 20 acciones seleccionadas por la IA.
  - Hasta 5 ETFs complementarios alineados con la estrategia activa.
"""

import asyncio
import json
import logging
from typing import Any

from ai.analyst import _call_llm
from config.markets import format_price, get_currency_symbol, MARKET_CURRENCY
from data.fundamentals import fetch_fundamentals
from database import repository as repo
from database.models import AssetType, PortfolioType, StrategyType
from strategy.selector import get_strategy_analyzer

logger = logging.getLogger(__name__)

# ── Configuración de tamaños ────────────────────────────────

MAX_WATCHLIST_SIZE = 25
MAX_STOCKS = 20
MAX_ETFS = 5
# Lote por llamada LLM (evita respuestas demasiado largas / costosas)
STOCKS_PER_LLM_CALL = 10

# ── ETFs recomendados por estrategia ────────────────────────
# Nota: El universo canónico de ETFs vive en strategy/etf_config.py.
# Este mapa se mantiene para el prompt de la watchlist IA,
# enriqueciendo la sugerencia del LLM con ETFs orientados a
# cada estrategia. _get_etfs_for_strategy() usa el universo
# canónico como fuente primaria.

ETF_STRATEGY_MAP: dict[StrategyType, dict[str, list[str]]] = {
    StrategyType.VALUE: {
        "core_value": ["VTV", "VONV", "IUSV", "RPV", "VLUE", "SPYV"],
        "intl_value": ["EFV", "FNDF", "IVAL", "GVAL"],
        "small_value": ["IWN", "VBR", "SLYV", "AVUV"],
        "dividend_value": ["SCHD", "VYM", "HDV", "DVY"],
        "sector_defensive": ["XLP", "XLU", "XLV"],
    },
    StrategyType.GROWTH: {
        "core_growth": ["VUG", "IWF", "SPYG", "SCHG", "VONG", "MGK"],
        "tech_growth": ["QQQ", "XLK", "VGT", "FTEC", "IGV"],
        "innovation": ["ARKK", "ARKG", "ARKW", "SOXX", "SMH", "BOTZ"],
        "intl_growth": ["EFG", "IHDG", "VXUS"],
        "small_growth": ["IWO", "VBK", "SLYG"],
    },
    StrategyType.DIVIDEND: {
        "high_dividend": ["SCHD", "VYM", "HDV", "DVY", "SPHD", "SPYD"],
        "dividend_growth": ["VIG", "DGRO", "NOBL", "SDY", "DGRW"],
        "intl_dividend": ["VYMI", "IDV", "DWX", "SDIV"],
        "reit": ["VNQ", "SCHH", "IYR", "XLRE"],
        "bond_income": ["AGG", "BND", "LQD", "HYG", "TLT", "VCIT"],
    },
    StrategyType.BALANCED: {
        "blend_us": ["VOO", "VTI", "SPY", "IVV", "ITOT"],
        "blend_intl": ["VXUS", "VEA", "EFA", "VWO", "EEM"],
        "multi_asset": ["AOR", "AOA", "VGIT", "GLD"],
        "factor_quality": ["QUAL", "DGRW", "SPHQ", "MOAT"],
        "sector_balanced": ["XLK", "XLV", "XLF", "XLI"],
    },
    StrategyType.CONSERVATIVE: {
        "low_vol": ["SPLV", "USMV", "EFAV", "ACWV"],
        "short_bond": ["SHY", "SHV", "BSV", "VGSH", "BIL"],
        "aggregate_bond": ["AGG", "BND", "BNDX", "VCIT"],
        "tips": ["TIP", "SCHP", "VTIP"],
        "defensive": ["XLP", "XLU", "GLD", "VNQ"],
    },
}


def _get_etfs_for_strategy(strategy: StrategyType) -> list[str]:
    """Devuelve la lista plana de ETFs recomendados para una estrategia."""
    categories = ETF_STRATEGY_MAP.get(strategy, ETF_STRATEGY_MAP[StrategyType.VALUE])
    result: list[str] = []
    for tickers in categories.values():
        result.extend(tickers)
    return list(dict.fromkeys(result))  # Sin duplicados, preserva orden

def _parse_json_array_response(response: str) -> list[dict[str, Any]] | None:
    clean = response.strip()
    if not clean:
        return None
    if clean.startswith("⚠️"):
        return None

    # Limpiar posibles markdown markers
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1]
        clean = clean.rsplit("```", 1)[0].strip()

    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError:
        start = clean.find("[")
        end = clean.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            parsed = json.loads(clean[start : end + 1])
        except Exception:
            return None

    return parsed if isinstance(parsed, list) else None


async def _get_active_strategy() -> StrategyType:
    portfolio = await repo.get_portfolio_by_type(PortfolioType.REAL)
    return portfolio.strategy if portfolio and portfolio.strategy else StrategyType.VALUE


# ── Formato JSON compartido para respuestas ──────────────────

_JSON_FORMAT = (
    "Responde SOLO con un JSON array así:\n"
    "[\n"
    "  {\n"
    '    "ticker": "AAPL",\n'
    '    "market": "NASDAQ",\n'
    '    "currency": "USD",\n'
    '    "reason": "razón detallada de por qué merece estudio",\n'
    '    "thesis": "tesis de inversión concisa",\n'
    '    "target_entry": 150.0,\n'
    '    "target_exit": 200.0,\n'
    '    "catalysts": "catalizadores esperados (earnings, productos, etc.)",\n'
    '    "risks": "principales riesgos identificados",\n'
    '    "conviction": 7,\n'
    '    "time_horizon": "medio"\n'
    "  }\n"
    "]\n"
    "Sin explicaciones adicionales, solo el JSON.\n"
    "conviction: 1-10 (1=baja, 10=muy alta)\n"
    "time_horizon: corto (<6m), medio (6-24m), largo (>24m)\n\n"
    "IMPORTANTE sobre tickers y precios:\n"
    "- USA (NASDAQ/NYSE): ticker sin sufijo (ej: AAPL, MRK), moneda USD\n"
    "- España (IBEX): ticker sin sufijo .MC (ej: SAN, BBVA, TEF), moneda EUR\n"
    "- Alemania (XETRA): ticker sin sufijo .DE (ej: SAP, SIE), moneda EUR\n"
    "- Francia (EURONEXT_PARIS): ticker sin sufijo .PA (ej: MC, TTE, ORA), moneda EUR\n"
    "- Italia (BORSA_ITALIANA): ticker sin sufijo .MI (ej: ISP, UCG), moneda EUR\n"
    "- UK (LSE): ticker sin sufijo .L (ej: SHEL, AZN, VOD), moneda GBp (peniques)\n"
    "- Países Bajos (EURONEXT_AMSTERDAM): ticker sin sufijo .AS (ej: ASML), moneda EUR\n"
    "- target_entry y target_exit DEBEN estar en la moneda nativa del mercado\n"
    "  (USD para US, EUR para Europa continental, GBp para LSE)\n"
    "- target_entry < target_exit siempre\n"
    "- target_entry debe ser ≤ precio actual (zona de compra atractiva)\n"
)

# ── Prompts de análisis profundo de INDUSTRIA ────────────────

_INDUSTRY_ANALYSIS_BLOCK = """
Para cada empresa propuesta, realiza un ANÁLISIS PROFUNDO DE SU INDUSTRIA que incluya:
1) Definición: industria/subindustria exacta, cadena de valor, modelo económico típico (drivers de ingresos, estructura de costes, dónde se captura el margen).
2) Dinámicas competitivas: tipo de competencia (fragmentada vs concentrada), switching costs, efectos de red, economías de escala, barreras de entrada/salida, poder de proveedores/clientes, amenaza de sustitutos.
3) Márgenes medios de la industria: rangos típicos de margen bruto, EBITDA/EBIT y margen neto. Compara con la empresa y explica por qué está por encima o por debajo.
4) Crecimiento medio: CAGR histórico y esperado, separando estructural vs cíclico, impulsores (demografía, tecnología, regulación, penetración, precios/volumen).
5) Retos y riesgos clave: 3-5 retos principales con impacto (alto/medio/bajo) y horizonte (corto/medio/largo).
6) Sensibilidad: clasificar como defensiva / semi-cíclica / cíclica. Cómo se comportan ventas y márgenes en recesiones y ante tipos de interés.
7) Cuota de mercado: principales competidores, cuota estimada de la empresa y top 3-5, tendencia de consolidación.
"""

# ── Prompts de análisis profundo de EMPRESA ──────────────────

_COMPANY_ANALYSIS_BLOCK = """
Para cada empresa propuesta, analiza como analista financiero senior de un gran fondo de inversión:
1) ¿Qué hace la empresa? Core products/services que impulsan valor a largo plazo.
2) ¿Cómo gana dinero? Revenue streams y segmentos operativos, ordenados por importancia (% contribución).
3) ¿Quiénes son sus clientes? Tipos (B2B/B2C, SMBs, enterprises, gobiernos), riesgo de concentración.
4) ¿Quiénes son sus competidores? Directos y alternativos, posicionamiento competitivo.
5) ¿Dónde opera? Desglose geográfico de ingresos.
6) ¿Ingresos recurrentes o puntuales? Contratos, suscripciones, renewal rates, switching costs.
7) ¿Puede subir precios? Pricing power basado en tendencias de márgenes e historial inflacionario.
8) ¿Qué pasa en recesión? Ciclicidad, rendimiento histórico en crisis, warnings del management.
9) ¿Tiene deuda? Estructura de capital: deuda total, vencimientos, coste, comparación con cash y FCF.
"""

# ── Prompts de watchlist por estrategia ──────────────────────


def _build_stock_watchlist_prompt(
    strategy: StrategyType,
    excluded: str,
    batch_size: int = STOCKS_PER_LLM_CALL,
    batch_num: int = 1,
) -> str:
    """Construye el prompt para generar un lote de acciones para la watchlist."""

    markets = "NASDAQ, NYSE, IBEX 35, DAX, CAC 40, FTSE MIB, AEX, FTSE 100"
    common_suffix = (
        f"\nNO incluyas tickers ya en cartera o watchlist (excluir: {excluded}).\n"
        f"\n{_INDUSTRY_ANALYSIS_BLOCK}\n{_COMPANY_ANALYSIS_BLOCK}\n"
        f"Integra ambos análisis (industria + empresa) en los campos 'reason', 'thesis' y 'risks' de cada sugerencia.\n\n"
        f"{_JSON_FORMAT}"
    )

    if strategy == StrategyType.GROWTH:
        return f"""Como analista growth de un fondo institucional, sugiere exactamente {batch_size} acciones (lote {batch_num}) para estudiar como posibles inversiones.
Deben ser empresas que:
- Coticen en {markets}
- Tengan crecimiento fuerte y sostenible (revenue CAGR >15%, earnings acelerando)
- Márgenes sólidos y tendencia expansiva
- TAM (Total Addressable Market) grande y en expansión
- Ventajas competitivas claras (moat tecnológico, red, marca, escala)
- Valoración razonable para growth (PEG <2 preferible, evitar extremos)
- Prioriza empresas con ingresos recurrentes, altos switching costs y pricing power
{common_suffix}"""

    if strategy == StrategyType.DIVIDEND:
        return f"""Como analista dividend/income de un fondo institucional, sugiere exactamente {batch_size} acciones (lote {batch_num}) para estudiar como posibles inversiones.
Deben ser empresas que:
- Coticen en {markets}
- Dividend yield atractivo (>2.5%) y sostenible, con historial de crecimiento de dividendos
- FCF sólido que cubra el dividendo (payout ratio FCF <75%)
- Baja deuda relativa al sector, balance sheet fuerte
- Preferiblemente Dividend Aristocrats o empresas con >10 años de dividendos crecientes
- Negocio defensivo o semi-cíclico con ingresos recurrentes
- Analiza especialmente la sostenibilidad del dividendo en escenarios de recesión
{common_suffix}"""

    if strategy == StrategyType.BALANCED:
        return f"""Como analista balanced (value+growth) de un fondo institucional, sugiere exactamente {batch_size} acciones (lote {batch_num}) para estudiar como posibles inversiones.
Deben ser empresas que:
- Coticen en {markets}
- Combinen valoración razonable (P/E <25) con crecimiento sólido (revenue >10%)
- Calidad del negocio demostrada (ROE >15%, márgenes estables/crecientes)
- Balance sólido con deuda controlada
- Mix equilibrado: incluye tanto defensivas como cíclicas de calidad
- Empresa con ventajas competitivas duraderas y modelo de negocio probado
- Evalúa tanto el upside de crecimiento como el downside protection
{common_suffix}"""

    if strategy == StrategyType.CONSERVATIVE:
        return f"""Como analista ultra-conservador/defensivo de un fondo institucional, sugiere exactamente {batch_size} acciones (lote {batch_num}) para estudiar como posibles inversiones.
Deben ser empresas que:
- Coticen en {markets}
- Sean large/mega caps con negocios predecibles y defensivos
- Beta ≤1.0, baja volatilidad histórica
- Deuda baja (D/E <1), FCF positivo consistente
- Ingresos recurrentes o contratos a largo plazo
- Sectores defensivos: utilities, healthcare, consumer staples, infraestructura
- Prioriza capital preservation: empresas que sobrevivan recesiones sin recortar dividendos
- Analiza especialmente el comportamiento en crisis 2008, 2020 y 2022
{common_suffix}"""

    # VALUE por defecto
    return f"""Actúa como un analista financiero senior de un gran fondo de inversión especializado en Value Investing.
Tu análisis debe ser riguroso, basado en datos financieros oficiales, conservador en supuestos y orientado a la preservación de capital y creación de valor a largo plazo.

Sugiere exactamente {batch_size} acciones (lote {batch_num}) para estudiar como posibles inversiones value.
Deben ser empresas que:
- Coticen en {markets}
- Coticen por debajo de su valor intrínseco (margen de seguridad >15-20%)
- Fundamentales sólidos: P/E razonable, P/B <2, ROE >12%, deuda controlada
- FCF positivo y creciente, preferiblemente con historial de dividendos
- Ventajas competitivas duraderas (moat cuantificable)
- Management alineado con accionistas (insider ownership, recompras racionales)
- Catalizadores identificables a 6-24 meses (earnings, reestructuración, spin-off, etc.)
- Para cada empresa, calcula el margen de seguridad estimado
{common_suffix}"""


def _build_etf_watchlist_prompt(
    strategy: StrategyType,
    excluded: str,
    count: int = MAX_ETFS,
) -> str:
    """Construye el prompt para generar ETFs complementarios alineados con la estrategia."""

    strategy_etf_desc = {
        StrategyType.VALUE: "value investing (value factor, small-cap value, dividend value, mercados emergentes baratos)",
        StrategyType.GROWTH: "growth investing (tecnología, innovación, growth factor, small-cap growth, mercados de alto crecimiento)",
        StrategyType.DIVIDEND: "income/dividendos (high dividend, dividend growth, REITs, renta fija, bonos corporativos, dividendos internacionales)",
        StrategyType.BALANCED: "balanced/diversificado (blend US, internacional, multi-asset, quality factor, sectorial equilibrado)",
        StrategyType.CONSERVATIVE: "conservador/defensivo (low volatility, bonos corto plazo, aggregate bonds, TIPS, sectores defensivos, oro)",
    }

    desc = strategy_etf_desc.get(strategy, strategy_etf_desc[StrategyType.VALUE])

    return f"""Como gestor de carteras institucional, sugiere exactamente {count} ETFs para complementar una cartera de acciones con estrategia {strategy.value}.

Los ETFs deben estar orientados a {desc}.

Criterios de selección:
- Que coticen en mercados US (la mayoría de ETFs relevantes cotizan en NYSE/NASDAQ)
- AUM (Assets Under Management) >$500M preferible para liquidez
- Expense ratio competitivo (<0.50% para pasivos, <0.75% para temáticos)
- Diversificación: incluye distintas categorías (geográfica, sectorial, renta fija, commodities si aplica)
- Complementariedad con las acciones de la cartera (no duplicar exposición)
- Historial mínimo de 3 años

Para cada ETF explica:
- Qué exposición aporta a la cartera
- Por qué es el mejor ETF de su categoría
- Cómo complementa la estrategia {strategy.value}
- Riesgos específicos del ETF (tracking error, liquidez, concentración)

NO incluyas ETFs ya en la cartera (excluir: {excluded}).

{_JSON_FORMAT}"""


async def _process_suggestions(
    suggestions: list[dict[str, Any]],
    current_portfolio_tickers: list[str],
    current_wl_tickers: list[str],
    asset_type: AssetType,
    max_items: int,
) -> list[dict[str, Any]]:
    """
    Procesa y guarda las sugerencias de la IA (acciones o ETFs).
    Devuelve la lista de items añadidos.
    """
    added = []
    for item in suggestions:
        if len(added) >= max_items:
            break

        ticker = item.get("ticker", "").upper()
        if not ticker or ticker in current_portfolio_tickers or ticker in current_wl_tickers:
            continue

        market = item.get("market", "NASDAQ")
        reason = item.get("reason", "")
        thesis = item.get("thesis", "")
        catalysts = item.get("catalysts", "")
        risks = item.get("risks", "")
        conviction = item.get("conviction")
        time_horizon = item.get("time_horizon", "medio")
        target_entry = item.get("target_entry")
        target_exit = item.get("target_exit")

        # Almacenar razón completa (el display se filtra en cada contexto)
        rich_reason = reason

        # Obtener sector y precio real (solo para acciones; ETFs no tienen sector individual)
        sector = None
        actual_price = None
        actual_currency = None
        if asset_type == AssetType.STOCK:
            try:
                fd = await asyncio.to_thread(fetch_fundamentals, ticker, market)
                sector = fd.sector
                actual_price = fd.current_price
                actual_currency = fd.currency
            except Exception:
                pass

        # ── Sanity check de targets vs precio real ──
        if actual_price and actual_price > 0:
            entry = float(target_entry) if target_entry else None
            exit_ = float(target_exit) if target_exit else None

            # Si los targets son absurdos (>5x o <0.2x del precio), invalidarlos
            if entry and (entry > actual_price * 5 or entry < actual_price * 0.05):
                logger.warning(
                    f"Watchlist {ticker}: target_entry {entry} incoherente "
                    f"con precio real {actual_price} {actual_currency} — descartado"
                )
                target_entry = None
            if exit_ and (exit_ > actual_price * 10 or exit_ < actual_price * 0.05):
                logger.warning(
                    f"Watchlist {ticker}: target_exit {exit_} incoherente "
                    f"con precio real {actual_price} {actual_currency} — descartado"
                )
                target_exit = None
            # Si entry > exit, swap (LLM a veces invierte)
            if target_entry and target_exit:
                if float(target_entry) > float(target_exit):
                    target_entry, target_exit = target_exit, target_entry

        ai_notes_prefix = "📊 Acción" if asset_type == AssetType.STOCK else "📦 ETF"
        wl_item = await repo.add_to_watchlist(
            ticker=ticker,
            market=market,
            sector=sector,
            reason=rich_reason,
            ai_notes=f"{ai_notes_prefix} | Convicción: {conviction or 'N/A'}/10",
            asset_type=asset_type,
        )

        # Guardar objetivo de inversión
        if wl_item:
            try:
                await repo.save_investment_objective(
                    ticker=ticker,
                    market=market,
                    thesis=thesis or reason,
                    target_entry_price=float(target_entry) if target_entry else None,
                    target_exit_price=float(target_exit) if target_exit else None,
                    catalysts=catalysts or None,
                    risks=risks or None,
                    time_horizon=time_horizon,
                    conviction=int(conviction) if conviction else None,
                    source="ai",
                )
            except Exception as e:
                logger.warning(f"Error guardando objetivo para {ticker}: {e}")

            added.append({
                "ticker": ticker,
                "market": market,
                "sector": sector,
                "asset_type": asset_type.value,
                "reason": reason,
                "thesis": thesis,
                "catalysts": catalysts,
                "risks": risks,
                "conviction": conviction,
                "target_entry": target_entry,
                "target_exit": target_exit,
            })
            current_wl_tickers.append(ticker)

    return added


async def ai_generate_watchlist(
    current_portfolio_tickers: list[str],
) -> list[dict[str, Any]]:
    """
    Pide a la IA que sugiera hasta 25 tickers (acciones + ETFs) para estudiar,
    excluyendo los que ya están en cartera.

    Genera en lotes para no sobrecargar el LLM:
      - Hasta 2 lotes de ~10 acciones = ~20 acciones
      - 1 lote de ~5 ETFs
    """
    excluded = ", ".join(current_portfolio_tickers) or "ninguno"
    active_strategy = await _get_active_strategy()

    current_watchlist = await repo.get_active_watchlist()
    current_wl_tickers = [w.ticker for w in current_watchlist]
    all_excluded = set(current_portfolio_tickers) | set(current_wl_tickers)

    # Calcular cuánto espacio queda
    remaining_total = MAX_WATCHLIST_SIZE - len(current_wl_tickers)
    if remaining_total <= 0:
        logger.info("📋 Watchlist llena (25 items). No se generan más.")
        return []

    # Calcular cuántas acciones y ETFs actuales hay
    current_stock_count = sum(
        1 for w in current_watchlist
        if not hasattr(w, 'asset_type') or w.asset_type is None or w.asset_type == AssetType.STOCK
    )
    current_etf_count = sum(
        1 for w in current_watchlist
        if hasattr(w, 'asset_type') and w.asset_type == AssetType.ETF
    )

    remaining_stocks = min(MAX_STOCKS - current_stock_count, remaining_total)
    remaining_etfs = min(MAX_ETFS - current_etf_count, remaining_total - max(remaining_stocks, 0))

    all_added: list[dict[str, Any]] = []
    excluded_str = ", ".join(all_excluded) or "ninguno"

    # ── Generar ACCIONES en lotes ──
    if remaining_stocks > 0:
        num_batches = max(1, (remaining_stocks + STOCKS_PER_LLM_CALL - 1) // STOCKS_PER_LLM_CALL)
        for batch_num in range(1, num_batches + 1):
            batch_size = min(STOCKS_PER_LLM_CALL, remaining_stocks - len([a for a in all_added if a.get("asset_type") == "stock"]))
            if batch_size <= 0:
                break

            # Actualizar excluidos con los ya añadidos
            batch_excluded = ", ".join(all_excluded | {a["ticker"] for a in all_added}) or "ninguno"
            prompt = _build_stock_watchlist_prompt(active_strategy, batch_excluded, batch_size, batch_num)

            response = await _call_llm(
                prompt,
                max_tokens=3000,
                context=f"watchlist_stocks_batch{batch_num}",
            )

            if not response or response.startswith("⚠️"):
                logger.warning(f"Watchlist IA (stocks lote {batch_num}): respuesta vacía o error")
                continue

            suggestions = _parse_json_array_response(response)
            if suggestions is None:
                logger.error(f"Error parseando watchlist stocks lote {batch_num}")
                continue

            added = await _process_suggestions(
                suggestions, current_portfolio_tickers, current_wl_tickers,
                AssetType.STOCK, batch_size,
            )
            all_added.extend(added)
            logger.info(f"📋 Watchlist stocks lote {batch_num}: {len(added)} añadidos")

    # ── Generar ETFs ──
    if remaining_etfs > 0:
        etf_excluded = ", ".join(all_excluded | {a["ticker"] for a in all_added}) or "ninguno"
        prompt = _build_etf_watchlist_prompt(active_strategy, etf_excluded, remaining_etfs)

        response = await _call_llm(
            prompt,
            max_tokens=2000,
            context="watchlist_etfs",
        )

        if response and not response.startswith("⚠️"):
            suggestions = _parse_json_array_response(response)
            if suggestions:
                added = await _process_suggestions(
                    suggestions, current_portfolio_tickers, current_wl_tickers,
                    AssetType.ETF, remaining_etfs,
                )
                all_added.extend(added)
                logger.info(f"📋 Watchlist ETFs: {len(added)} añadidos")
            else:
                logger.error("Error parseando watchlist ETFs")

    stock_count = sum(1 for a in all_added if a.get("asset_type") == "stock")
    etf_count = sum(1 for a in all_added if a.get("asset_type") == "etf")
    logger.info(
        f"📋 Watchlist actualizada: {len(all_added)} nuevos "
        f"({stock_count} acciones, {etf_count} ETFs)"
    )
    return all_added


async def refresh_watchlist_analysis() -> list[dict[str, Any]]:
    """Re-analiza los tickers en la watchlist activa."""
    watchlist = await repo.get_active_watchlist()
    results = []
    active_strategy = await _get_active_strategy()
    analyzer = get_strategy_analyzer(active_strategy)

    for item in watchlist:
        try:
            fd = await asyncio.to_thread(fetch_fundamentals, item.ticker, item.market)
            vs = await asyncio.to_thread(analyzer, fd)
            asset_type = (
                item.asset_type.value
                if hasattr(item, 'asset_type') and item.asset_type
                else "stock"
            )
            currency = fd.currency or MARKET_CURRENCY.get(item.market, "USD")
            results.append({
                "ticker": item.ticker,
                "market": item.market,
                "asset_type": asset_type,
                "sector": item.sector,
                "reason": item.reason,
                "overall_score": vs.overall_score,
                "signal": vs.signal,
                "reasoning": vs.reasoning,
                "strategy": vs.strategy,
                "currency": currency,
                "current_price": fd.current_price,
            })
        except Exception as e:
            logger.warning(f"Error analizando watchlist {item.ticker}: {e}")

    return results


async def get_watchlist_summary() -> str:
    """Genera un resumen legible de la watchlist."""
    watchlist = await repo.get_active_watchlist()
    if not watchlist:
        return "📋 Watchlist vacía. Usa /watchlist_generate para crear una."

    # Separar acciones y ETFs
    stocks = [w for w in watchlist if not hasattr(w, 'asset_type') or w.asset_type is None or w.asset_type == AssetType.STOCK]
    etfs = [w for w in watchlist if hasattr(w, 'asset_type') and w.asset_type == AssetType.ETF]

    lines = [f"📋 *WATCHLIST ACTIVA* ({len(watchlist)} items: {len(stocks)} acciones, {len(etfs)} ETFs)\n"]
    active_strategy = await _get_active_strategy()
    analyzer = get_strategy_analyzer(active_strategy)

    # ── Sección Acciones ──
    if stocks:
        lines.append("📊 *ACCIONES*")
        for i, item in enumerate(stocks, 1):
            lines.extend(await _format_watchlist_item(item, i, analyzer))

    # ── Sección ETFs ──
    if etfs:
        lines.append("\n📦 *ETFs*")
        for i, item in enumerate(etfs, 1):
            lines.extend(await _format_watchlist_item(item, i, analyzer))

    return "\n".join(lines)


async def _format_watchlist_item(item, index: int, analyzer) -> list[str]:
    """Formatea un item de la watchlist para el resumen."""
    lines = []
    try:
        fd = await asyncio.to_thread(fetch_fundamentals, item.ticker, item.market)
        if fd is None or fd.current_price is None:
            lines.append(f"{index}. ⚠️ *${item.ticker}* ({item.market}) - Sin datos disponibles")
            return lines
        vs = await asyncio.to_thread(analyzer, fd)

        # Moneda real del activo
        currency = fd.currency or MARKET_CURRENCY.get(item.market, "USD")
        price_str = format_price(fd.current_price, currency)
        pe_str = f"{fd.pe_ratio:.1f}" if fd.pe_ratio is not None else "N/D"

        # Obtener objetivos para sanity check de señal
        obj = await repo.get_investment_objective(item.ticker, market=item.market)
        signal = vs.signal
        signal_note = ""

        if obj:
            entry = obj.target_entry_price
            exit_ = obj.target_exit_price
            price = fd.current_price

            # Sanity checks de señal vs targets
            if signal == "BUY" and exit_ and price > exit_:
                signal = "HOLD"
                signal_note = " (precio > salida)"
            elif signal == "BUY" and entry and price > entry * 1.15:
                signal_note = " (por encima de entrada)"

        emoji = "🟢" if signal == "BUY" else "🔴" if signal == "SELL" else "🟡"
        lines.append(
            f"{index}. {emoji} *${item.ticker}* ({item.market})\n"
            f"   Score: {vs.overall_score:.0f}/100 | Signal: {signal}{signal_note} | Strat: {vs.strategy}\n"
            f"   Precio: {price_str} | P/E: {pe_str} | Moneda: {currency}"
        )

        # Mostrar objetivos de inversión si existen
        if obj:
            if obj.thesis:
                lines.append(f"   📝 Tesis: {obj.thesis}")
            targets = []
            if obj.target_entry_price:
                targets.append(f"Entrada: {format_price(obj.target_entry_price, currency)}")
            if obj.target_exit_price:
                targets.append(f"Salida: {format_price(obj.target_exit_price, currency)}")
            if targets:
                # Señalar incoherencias visualmente
                coherence = ""
                if obj.target_entry_price and obj.target_exit_price and fd.current_price:
                    if fd.current_price > obj.target_exit_price:
                        coherence = " ⚠️ Precio > Salida"
                    elif fd.current_price < obj.target_entry_price:
                        coherence = " 💤 Precio < Entrada (esperar)"
                lines.append(f"   🎯 {' | '.join(targets)}{coherence}")
            if obj.conviction:
                lines.append(f"   💪 Convicción: {obj.conviction}/10 | Horizonte: {obj.time_horizon or 'N/A'}")
            if obj.catalysts:
                lines.append(f"   🚀 Catalizadores: {obj.catalysts}")
            if obj.risks:
                lines.append(f"   ⚠️ Riesgos: {obj.risks}")
        else:
            lines.append(f"   Razón: {item.reason or 'N/A'}")
    except Exception:
        lines.append(f"{index}. ⚠️ *${item.ticker}* - Error obteniendo datos")

    return lines
