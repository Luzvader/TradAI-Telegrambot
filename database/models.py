"""
Modelos SQLAlchemy para TradAI.
Todas las tablas necesarias para portfolios, operaciones, señales,
watchlist, earnings, aprendizaje y contexto.
"""

import enum
from datetime import UTC, datetime
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ── Enums ────────────────────────────────────────────────────


class PortfolioType(str, enum.Enum):
    REAL = "real"
    BACKTEST = "backtest"


class OperationSide(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class SignalType(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class PositionStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"


class WatchlistStatus(str, enum.Enum):
    ACTIVE = "active"
    REMOVED = "removed"
    PROMOTED = "promoted"  # Pasó a cartera


class AssetType(str, enum.Enum):
    STOCK = "stock"  # Acción individual
    ETF = "etf"      # ETF / fondo cotizado


class AutoModeType(str, enum.Enum):
    OFF = "off"    # Modo automático desactivado
    ON = "on"      # Full auto: ejecuta operaciones sin intervención
    SAFE = "safe"  # Auto con confirmación: pide aprobación antes de operar


class OperationOrigin(str, enum.Enum):
    MANUAL = "manual"      # Operación manual del usuario
    AUTO = "auto"          # Operación del modo automático (ON)
    SAFE = "safe"          # Operación confirmada vía modo SAFE
    BACKTEST = "backtest"  # Operación de backtesting
    IMPORT = "import"      # Importada desde broker


class StrategyType(str, enum.Enum):
    VALUE = "value"               # Value investing clásico
    GROWTH = "growth"             # Crecimiento agresivo
    DIVIDEND = "dividend"         # Dividendos / income
    BALANCED = "balanced"         # Equilibrado value + growth
    CONSERVATIVE = "conservative" # Ultra conservador / defensivo


# ── Tablas ───────────────────────────────────────────────────


class Portfolio(Base):
    __tablename__ = "portfolios"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    portfolio_type = Column(Enum(PortfolioType), nullable=False)
    strategy = Column(Enum(StrategyType), default=StrategyType.VALUE)
    initial_capital = Column(Float, nullable=True, default=0)  # Capital inicial
    cash = Column(Float, nullable=False, default=0)  # Efectivo disponible
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    positions = relationship("Position", back_populates="portfolio", lazy="selectin")
    operations = relationship("Operation", back_populates="portfolio", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("name", "portfolio_type", name="uq_portfolio_name_type"),
    )


class Position(Base):
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False)
    ticker = Column(String(20), nullable=False)
    market = Column(String(20), nullable=False, default="NASDAQ")
    sector = Column(String(100), nullable=True)
    shares = Column(Float, nullable=False, default=0)
    avg_price = Column(Float, nullable=False, default=0)
    current_price = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    status = Column(Enum(PositionStatus), default=PositionStatus.OPEN)
    opened_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    closed_at = Column(DateTime(timezone=True), nullable=True)

    portfolio = relationship("Portfolio", back_populates="positions")

    __table_args__ = (
        Index("ix_positions_portfolio_status", "portfolio_id", "status"),
        Index("ix_positions_ticker", "ticker"),
    )


class Operation(Base):
    __tablename__ = "operations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False)
    ticker = Column(String(20), nullable=False)
    market = Column(String(20), nullable=False, default="NASDAQ")
    side = Column(Enum(OperationSide), nullable=False)
    price = Column(Float, nullable=False)
    amount_usd = Column(Float, nullable=False)
    shares = Column(Float, nullable=False)
    origin = Column(Enum(OperationOrigin), default=OperationOrigin.MANUAL, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    notes = Column(Text, nullable=True)

    portfolio = relationship("Portfolio", back_populates="operations")

    __table_args__ = (
        Index("ix_operations_portfolio_timestamp", "portfolio_id", "timestamp"),
        Index("ix_operations_ticker", "ticker"),
    )


class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), nullable=False)
    market = Column(String(20), nullable=False, default="NASDAQ")
    signal_type = Column(Enum(SignalType), nullable=False)
    price = Column(Float, nullable=True)
    value_score = Column(Float, nullable=True)
    risk_score = Column(Float, nullable=True)
    reasoning = Column(Text, nullable=True)
    ai_analysis = Column(Text, nullable=True)
    acted_on = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    __table_args__ = (
        Index("ix_signals_ticker_type_created", "ticker", "signal_type", "created_at"),
        Index("ix_signals_created_at", "created_at"),
    )


class WatchlistItem(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), nullable=False)
    market = Column(String(20), nullable=False, default="NASDAQ")
    asset_type = Column(Enum(AssetType), default=AssetType.STOCK, nullable=False)
    sector = Column(String(100), nullable=True)
    reason = Column(Text, nullable=True)
    ai_notes = Column(Text, nullable=True)
    status = Column(Enum(WatchlistStatus), default=WatchlistStatus.ACTIVE)
    added_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    removed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_watchlist_status", "status"),
    )


class EarningsEvent(Base):
    __tablename__ = "earnings_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), nullable=False)
    report_date = Column(DateTime(timezone=True), nullable=True)
    fiscal_quarter = Column(String(10), nullable=True)  # e.g. "Q1 2026"
    expected_eps = Column(Float, nullable=True)
    actual_eps = Column(Float, nullable=True)
    expected_revenue = Column(Float, nullable=True)
    actual_revenue = Column(Float, nullable=True)
    surprise_pct = Column(Float, nullable=True)
    ai_analysis = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    __table_args__ = (
        UniqueConstraint("ticker", "report_date", name="uq_earnings_ticker_date"),
        Index("ix_earnings_report_date", "report_date"),
    )


class DividendPayment(Base):
    """Tracking de dividendos cobrados por posición."""
    __tablename__ = "dividend_payments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False)
    ticker = Column(String(20), nullable=False)
    market = Column(String(20), nullable=False, default="NASDAQ")
    ex_date = Column(DateTime(timezone=True), nullable=True)
    pay_date = Column(DateTime(timezone=True), nullable=True)
    amount_per_share = Column(Float, nullable=False)
    shares_held = Column(Float, nullable=False)
    total_amount = Column(Float, nullable=False)
    currency = Column(String(10), nullable=False, default="USD")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    portfolio = relationship("Portfolio")

    __table_args__ = (
        Index("ix_dividends_portfolio_ticker", "portfolio_id", "ticker"),
    )


class LearningLog(Base):
    """Registro de aprendizaje: la IA analiza operaciones cerradas
    para extraer lecciones y mejorar futuras decisiones."""
    __tablename__ = "learning_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    operation_id = Column(Integer, ForeignKey("operations.id"), nullable=True)
    ticker = Column(String(20), nullable=False)
    side = Column(Enum(OperationSide), nullable=False)
    entry_price = Column(Float, nullable=True)
    exit_price = Column(Float, nullable=True)
    profit_pct = Column(Float, nullable=True)
    holding_days = Column(Integer, nullable=True)
    outcome = Column(String(20), nullable=True)  # "win", "loss", "breakeven"
    what_went_well = Column(Text, nullable=True)
    what_went_wrong = Column(Text, nullable=True)
    lessons_learned = Column(Text, nullable=True)
    market_context_at_entry = Column(Text, nullable=True)
    source = Column(String(20), nullable=False, default="real")  # "real", "backtest"
    strategy_used = Column(String(30), nullable=True)  # Estrategia que generó la operación
    origin = Column(String(20), nullable=True)  # "manual", "auto", "safe", "import"
    total_dividends = Column(Float, nullable=True)  # Dividendos cobrados durante posición
    entry_signal_score = Column(Float, nullable=True)  # Score en el momento de compra
    entry_rsi = Column(Float, nullable=True)  # RSI en el momento de compra
    entry_macd_signal = Column(String(20), nullable=True)  # "bullish", "bearish", "neutral"
    diversification_score_at_entry = Column(Float, nullable=True)  # Score diversificación
    market_regime = Column(String(30), nullable=True)  # "fear", "greed", "neutral"
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class MarketContext(Base):
    """Resúmenes periódicos del contexto geopolítico y sectorial."""
    __tablename__ = "market_contexts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    context_type = Column(String(50), nullable=False)  # "geopolitical", "sector", "macro"
    summary = Column(Text, nullable=False)
    source = Column(String(200), nullable=True)
    relevance_score = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class AutoModeConfig(Base):
    """Configuración del modo automático por portfolio."""
    __tablename__ = "auto_mode_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False, unique=True)
    mode = Column(Enum(AutoModeType), default=AutoModeType.OFF, nullable=False)
    scan_interval_minutes = Column(Integer, default=60)       # Cada cuánto ejecutar scan
    analyze_interval_minutes = Column(Integer, default=120)   # Cada cuánto re-analizar posiciones
    macro_interval_minutes = Column(Integer, default=240)     # Cada cuánto actualizar macro
    watchlist_auto_manage = Column(Boolean, default=True)     # Gestionar watchlist automáticamente
    daily_summary_hour = Column(Integer, default=9)           # Hora del resumen diario (España)
    daily_summary_minute = Column(Integer, default=0)
    notify_signals = Column(Boolean, default=True)            # Enviar señales por Telegram
    notify_watchlist_changes = Column(Boolean, default=True)  # Notificar cambios en watchlist
    last_scan_at = Column(DateTime(timezone=True), nullable=True)
    last_analyze_at = Column(DateTime(timezone=True), nullable=True)
    last_macro_at = Column(DateTime(timezone=True), nullable=True)
    last_daily_summary_at = Column(DateTime(timezone=True), nullable=True)
    last_watchlist_at = Column(DateTime(timezone=True), nullable=True)  # Persistido en DB
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    portfolio = relationship("Portfolio")


class PortfolioSnapshot(Base):
    """Snapshot diario del valor del portfolio para tracking histórico (NAV)."""
    __tablename__ = "portfolio_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False)
    total_value = Column(Float, nullable=False)       # Valor posiciones + cash
    invested_value = Column(Float, nullable=False)     # Coste de posiciones
    cash = Column(Float, nullable=False, default=0)
    num_positions = Column(Integer, nullable=False, default=0)
    pnl = Column(Float, nullable=True)
    pnl_pct = Column(Float, nullable=True)
    benchmark_value = Column(Float, nullable=True)     # Valor del benchmark (SPY)
    snapshot_date = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))

    portfolio = relationship("Portfolio")


class CustomAlert(Base):
    """Alertas personalizadas creadas por el usuario."""
    __tablename__ = "custom_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), nullable=False)
    market = Column(String(20), nullable=False, default="NASDAQ")
    alert_type = Column(String(30), nullable=False)   # "price_below", "price_above", "rsi_above", "rsi_below"
    threshold = Column(Float, nullable=False)
    message = Column(Text, nullable=True)
    triggered = Column(Boolean, default=False)
    triggered_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    __table_args__ = (
        Index("ix_alerts_triggered", "triggered"),
    )


class OpenAIUsage(Base):
    """Tracking de uso de tokens de OpenAI."""
    __tablename__ = "openai_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model = Column(String(50), nullable=False)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    estimated_cost_usd = Column(Float, nullable=True)
    context = Column(String(100), nullable=True)      # "analyze", "macro", "learning", etc.
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    __table_args__ = (
        Index("ix_openai_usage_created", "created_at"),
    )


class AnalysisLog(Base):
    """Registro completo de cada análisis ejecutado.

    Almacena el resultado sin resumir de ``analyze_ticker`` para que el
    motor de aprendizaje pueda comparar predicción vs. realidad y
    extraer patrones útiles.
    """
    __tablename__ = "analysis_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), nullable=False)
    market = Column(String(20), nullable=False, default="NASDAQ")
    strategy_used = Column(String(30), nullable=True)
    signal = Column(String(10), nullable=False)           # BUY / SELL / HOLD
    overall_score = Column(Float, nullable=True)
    value_score = Column(Float, nullable=True)
    quality_score = Column(Float, nullable=True)
    safety_score = Column(Float, nullable=True)
    price_at_analysis = Column(Float, nullable=True)
    margin_of_safety = Column(Float, nullable=True)
    pe_ratio = Column(Float, nullable=True)
    roe = Column(Float, nullable=True)
    debt_to_equity = Column(Float, nullable=True)
    dividend_yield = Column(Float, nullable=True)
    reasoning = Column(Text, nullable=True)               # JSON list → joined text
    tech_summary = Column(Text, nullable=True)
    price_summary = Column(Text, nullable=True)
    ai_analysis = Column(Text, nullable=True)             # Resumen IA (completo)
    broker_tradable = Column(Boolean, nullable=True)      # T212 tradable?
    deterministic_context = Column(Text, nullable=True)   # Contexto determinista completo
    source = Column(String(20), nullable=False, default="manual")  # manual / auto / scan
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    __table_args__ = (
        Index("ix_analysis_logs_ticker", "ticker"),
        Index("ix_analysis_logs_created", "created_at"),
    )


class InvestmentObjective(Base):
    """Objetivos de inversión por empresa.

    Permite al agente (o al usuario) definir qué vigila de cada empresa:
    precio objetivo, tesis de inversión, catalizadores esperados, etc.
    Se usa para evaluar progreso y justificar recomendaciones.
    """
    __tablename__ = "investment_objectives"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), nullable=False)
    market = Column(String(20), nullable=False, default="NASDAQ")
    # Tesis de inversión (por qué nos interesa)
    thesis = Column(Text, nullable=True)
    # Precio objetivo de compra (a qué precio interesaría entrar)
    target_entry_price = Column(Float, nullable=True)
    # Precio objetivo de salida (a qué precio vender)
    target_exit_price = Column(Float, nullable=True)
    # Catalizadores esperados (ej: "earnings Q1", "aprobación regulatoria")
    catalysts = Column(Text, nullable=True)
    # Riesgos identificados
    risks = Column(Text, nullable=True)
    # Horizonte temporal ("corto", "medio", "largo")
    time_horizon = Column(String(20), nullable=True, default="medio")
    # Convicción (1-10)
    conviction = Column(Integer, nullable=True)
    # Generado por IA o manual
    source = Column(String(20), nullable=False, default="ai")  # "ai" o "manual"
    # Estado
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
