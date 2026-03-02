# 📈 TradAI — Bot de Trading Algorítmico con IA

Bot de señales de inversión que corre 24/7 en un servidor,
monitoriza mercados en tiempo real y se administra completamente
por **Telegram**. Opera en modo **broker-first con Trading212**
(demo por defecto): las operaciones reales se ejecutan en la plataforma
y TradAI mantiene sincronía para análisis, señales y aprendizaje.

## ✨ Características

| Módulo | Descripción |
|---|---|
| **5 Estrategias** | Value, Growth, Dividend, Balanced, Conservative — cada una con prompt IA adaptado |
| **Umbrales configurables** | BUY/SELL/SCAN thresholds vía variables de entorno |
| **Modo Automático** | Scan + análisis + watchlist + resumen diario automáticos |
| **Trading212 Broker-First** | Compras/ventas reales ejecutadas en Trading212 (modo demo/live) |
| **Gestión de Riesgos** | Regla del 5% por ticker, 20% por sector, stop-loss/take-profit, trailing stop, ATR |
| **Cash Tracking** | Seguimiento de capital inicial, cash disponible y NAV |
| **Indicadores Técnicos** | RSI, MACD, Bollinger Bands, ATR integrados en análisis |
| **Backtesting** | Motor de backtest con Sharpe ratio, max drawdown, alpha vs benchmark |
| **ETFs** | Soporte para análisis de ETFs (índices, sectoriales, renta fija, commodities, temáticos) |
| **Dividendos** | Tracking automático de cobros de dividendos por portfolio |
| **Diversificación** | Análisis de correlación entre posiciones con score de diversificación |
| **Insider Activity** | Análisis de operaciones de insiders con clasificación de sentimiento |
| **Watchlist IA** | Hasta 5 acciones fuera de cartera para estudio |
| **Contexto Geopolítico** | IA analiza noticias macro y sectoriales |
| **Earnings** | Monitoriza resultados trimestrales de empresas en cartera |
| **Benchmark** | Comparación semanal con SPY y tracking de NAV |
| **Alertas avanzadas** | Alertas de precio, volumen y RSI (sobrecompra/sobreventa) |
| **Caché** | Sistema de caché en memoria para reducir llamadas API |
| **Deduplicación** | Evita señales duplicadas en 24h |
| **Tickers Dinámicos** | Descubrimiento automático de tickers desde índices (S&P 500, DAX, CAC, MIB, FTSE, IBEX, AEX) |
| **Justificación de Señales** | Cada señal incluye justificación detallada: scores, fundamentales, análisis IA |
| **Objetivos de Inversión** | Tesis, catalizadores, riesgos, precios objetivo y convicción por empresa |
| **Calendario Earnings** | Monitorización automática de resultados, alertas ≤7 días, análisis pre-earnings |
| **Coste OpenAI** | Tracking real de tokens, costes por modelo y rate limiting configurable |
| **Confirmaciones** | Botones inline para confirmar compras/ventas |
| **Telegram** | 24 comandos para administración completa |
| **Multi-mercado** | NASDAQ, NYSE, IBEX 35, DAX, CAC 40, FTSE MIB, FTSE 100, AEX con horarios y festivos |
| **Migraciones** | Alembic para migraciones de base de datos + auto-sync de columnas |
| **Tests** | Suite de tests con pytest para componentes críticos |

### 🧠 Motor de Aprendizaje

El motor de aprendizaje (`ai/learning.py`) cierra el bucle de retroalimentación
conectando datos de múltiples subsistemas para que la IA aprenda de su propia operativa:

| Capacidad | Fuente de datos |
|---|---|
| **Análisis de operaciones cerradas** | `LearningLog` enriquecido con origen, dividendos, indicadores técnicos, contexto de mercado |
| **Rastreo de origen** | Cada operación se etiqueta como `manual`, `auto`, `safe`, `backtest` o `import` |
| **Validación de señales** | Compara señales emitidas (30-120 días) con la evolución real del precio |
| **Retorno ajustado por dividendos** | El P&L incluye dividendos cobrados durante la posesión |
| **Contexto técnico** | RSI, MACD, score de la señal original se almacenan junto a cada trade |
| **Régimen de mercado** | Clasificación bull/bear/uncertain basada en contexto geopolítico |
| **Score de diversificación** | Correlación del portfolio en el momento de entrada |
| **Informes por estrategia** | Rendimiento comparativo por origen y por régimen de mercado |
| **Persistencia de análisis** | Los resultados de `/analizar`, `/scan` y auto-scan se guardan en `AnalysisLog` |
| **Insights y sesgos** | LLM analiza patrones, sesgos cognitivos y oportunidades de mejora |

## 🏗️ Arquitectura

```
TradAI/
├── main.py                    # Punto de entrada (Telegram + Scheduler)
├── config/
│   ├── settings.py            # Configuración central desde .env
│   └── markets.py             # Horarios de mercado y mapping tickers
├── database/
│   ├── connection.py          # Conexión async PostgreSQL + Unit of Work
│   ├── models.py              # 16 modelos SQLAlchemy + 10 enums
│   ├── repository.py          # Façade re-exportadora
│   └── repos/                 # Sub-módulos CRUD por dominio
│       ├── portfolio.py       # Portfolio, Position, Operation (con origin tracking)
│       ├── signals.py         # Signal, Watchlist, Earnings
│       ├── config.py          # Auto Mode, Alerts, Objectives
│       └── analytics.py       # Learning, OpenAI Usage, Dividends, AnalysisLog, Signal Validation
├── data/
│   ├── market_data.py         # Precios con yfinance + caché
│   ├── fundamentals.py        # Datos fundamentales
│   ├── technical.py           # RSI, MACD, Bollinger, ATR
│   ├── ticker_discovery.py    # Descubrimiento dinámico + universo ETF
│   ├── earnings.py            # Resultados trimestrales
│   ├── dividends.py           # Tracking de dividendos
│   ├── insiders.py            # Análisis de operaciones insider
│   ├── news.py                # Noticias y contexto + caché
│   └── cache.py               # Sistema de caché TTL en memoria
├── strategy/
│   ├── score.py               # Tipo de score común (thresholds configurables)
│   ├── selector.py            # Router de estrategia activa
│   ├── value_strategy.py      # Scoring value
│   ├── growth_strategy.py     # Scoring growth
│   ├── dividend_strategy.py   # Scoring dividend
│   ├── balanced_strategy.py   # Scoring balanced
│   ├── conservative_strategy.py # Scoring conservative
│   ├── risk_manager.py        # Gestión de riesgos + ATR + trailing stop
│   ├── screener.py            # Screening dinámico de tickers por índice
│   ├── correlation.py         # Análisis de correlación / diversificación
│   ├── price_analyst.py       # Análisis de precio con IA
│   ├── technical_analyst.py   # Análisis técnico detallado
│   └── utils.py               # Utilidades compartidas (clamp)
├── portfolio/
│   └── portfolio_manager.py   # Gestión de carteras + cash + origin tracking + learning enrichment
├── signals/
│   ├── signal_engine.py       # Façade del motor de señales
│   ├── builders.py            # Justificación y contexto determinista
│   ├── portfolio_signals.py   # Señales para posiciones abiertas
│   └── scanner.py             # Escaneo de oportunidades
├── ai/
│   ├── analyst.py             # Análisis IA + rate limiting + cost tracking
│   ├── watchlist.py           # Watchlist generada por IA
│   └── learning.py            # Motor de aprendizaje (5 funciones + validación de señales)
├── backtesting/
│   ├── engine.py              # Motor de backtest
│   ├── learning_bridge.py     # Puente backtest → aprendizaje
│   └── metrics.py             # Sharpe, drawdown, alpha, win rate
├── broker/
│   ├── base.py                # Interfaz abstracta de broker
│   ├── bridge.py              # Puente broker ↔ portfolio
│   └── trading212.py          # Implementación Trading212 API
├── notifications/
│   └── __init__.py            # Sistema centralizado de notificaciones Telegram
├── telegram_bot/
│   ├── bot.py                 # Configuración del bot + inline keyboards
│   ├── decorators.py          # Decoradores de autorización
│   └── handlers/              # 24 comandos de Telegram (modularizados)
│       ├── portfolio_cmds.py  # Cartera, buy, sell, capital, dividendos
│       ├── analysis_cmds.py   # Analizar, scan, comparar, backtest, ETF, insider, diversificación
│       ├── broker_cmds.py     # Broker sync, import, búsqueda, historial
│       ├── auto_cmds.py       # Modo automático on/off/safe
│       ├── alert_cmds.py      # Alertas de precio, volumen, RSI
│       ├── watchlist_cmds.py  # Watchlist IA
│       ├── objective_cmds.py  # Objetivos de inversión
│       ├── earnings_cmds.py   # Calendario de earnings
│       ├── system_cmds.py     # Help, costes
│       ├── callbacks.py       # Botones inline (confirmaciones)
│       ├── helpers.py         # Utilidades compartidas
│       └── registry.py        # CommandInfo dataclass
├── scheduler/
│   ├── jobs.py                # 15 tareas programadas (incl. validación señales + trend analysis)
│   └── auto_mode.py           # Motor del modo automático + origin tagging + AnalysisLog
├── alembic/                   # Migraciones de base de datos
│   ├── env.py                 # Entorno async de Alembic
│   └── versions/              # Archivos de migraciones
├── tests/                     # Suite de tests (pytest)
├── Dockerfile                 # Multi-stage build optimizado
└── docker-compose.yml         # PostgreSQL + App
```

## 🚀 Instalación

### 1. Clonar y configurar

```bash
git clone https://github.com/tu-usuario/TradAI.git
cd TradAI
cp .env.example .env
# Editar .env con tus claves
```

### 2. Configurar variables de entorno

Edita `.env` con:
- `TELEGRAM_BOT_TOKEN` — Token de [@BotFather](https://t.me/BotFather)
- `TELEGRAM_CHAT_ID` — Tu chat ID (usa [@userinfobot](https://t.me/userinfobot))
- `TELEGRAM_ALLOWED_USERS` — Tu user ID de Telegram
- `OPENAI_API_KEY` — Clave de OpenAI
- `NEWS_API_KEY` — (Opcional) Clave de [NewsAPI](https://newsapi.org)
- `TRADING212_API_KEY` / `TRADING212_API_SECRET` — Credenciales del broker (modo por defecto)
- `TRADING212_DEMO_API_KEY` / `TRADING212_DEMO_API_SECRET` — Credenciales cuenta demo (opcional)
- `TRADING212_LIVE_API_KEY` / `TRADING212_LIVE_API_SECRET` — Credenciales cuenta live (opcional)
- `TRADING212_MODE=demo` — Modo por defecto (demo/live). Si se configuran DEMO+LIVE, ambos se usan

### 3. Arrancar con Docker (recomendado)

```bash
docker-compose up -d
```

Esto levanta PostgreSQL + la aplicación automáticamente.

### 4. Arrancar sin Docker

```bash
pip install -r requirements.txt
# Necesitas PostgreSQL corriendo localmente
# Ajustar DATABASE_URL en .env
python main.py
```

## 📱 Comandos de Telegram

### Cartera y Capital
| Comando | Descripción |
|---|---|
| `/cartera` | Ver cartera: posiciones, señales, earnings, aprendizaje |
| `/capital 10000` | Establecer capital inicial / ver capital actual |
| `/dividendos` | Dividendos cobrados y resumen |

### Operaciones (con confirmación inline)
| Comando | Ejemplo |
|---|---|
| `/buy TICKER CANTIDAD [PRECIO]` | `/buy AAPL 10` o `/buy AAPL 10 185.50` |
| `/sell TICKER CANTIDAD PRECIO` | `/sell AAPL 5 200.00` |

### Broker
| Comando | Descripción |
|---|---|
| `/broker` | Estado de conexión con Trading212 |
| `/broker sync` | Sincronizar posiciones desde el broker |
| `/broker import` | Importar historial de operaciones |
| `/broker buscar TICKER` | Buscar instrumento en Trading212 |
| `/broker historial` | Ver historial de órdenes ejecutadas |

### Análisis
| Comando | Descripción |
|---|---|
| `/analizar TICKER` | Análisis completo con IA según estrategia activa |
| `/scan` | Escanear mejores oportunidades del universo |
| `/comparar TICKER1 TICKER2` | Comparar dos tickers lado a lado |
| `/macro` | Análisis macroeconómico con IA |
| `/backtest [TICKERS...]` | Backtest sobre cartera demo (o tickers indicados) |
| `/etf [CATEGORÍA]` | Ver/analizar ETFs por categoría |
| `/insider TICKER` | Análisis de operaciones de insiders |
| `/diversificacion` | Análisis de correlación y diversificación del portfolio |

### Estrategia (con selector de botones)
| Comando | Descripción |
|---|---|
| `/strategy` | Ver estrategia activa + selector visual |
| `/strategy value\|growth\|dividend\|balanced\|conservative` | Cambiar estrategia |

### Historial, Alertas y Watchlist
| Comando | Descripción |
|---|---|
| `/historial` | Últimas señales generadas |
| `/alertas` | Ver alertas activas |
| `/alertas crear TICKER tipo valor` | Crear alerta (precio_max, precio_min, rsi_max, rsi_min, volumen) |
| `/alertas borrar ID` | Eliminar una alerta |
| `/watchlist` | Ver watchlist activa (máx 5) |
| `/watchlist generar` | IA genera nueva watchlist con tesis y objetivos |
| `/watchlist quitar TICKER` | Quitar de watchlist |

### Objetivos y Earnings
| Comando | Descripción |
|---|---|
| `/objetivo [TICKER]` | Ver/gestionar objetivos de inversión (tesis, catalizadores, riesgos, convicción) |
| `/earnings [TICKER]` | Calendario de earnings / historial de un ticker |

### Sistema
| Comando | Descripción |
|---|---|
| `/auto` | Ver estado del modo automático |
| `/auto on\|off\|safe` | Activar / desactivar / modo seguro |
| `/auto scan\|analyze\|summary ...` | Configurar intervalos y horarios |
| `/costes` | Uso y costes estimados de OpenAI |
| `/help` | Ayuda y lista de comandos |

## 🛡️ Gestión de Riesgos

El sistema emula las reglas de un fondo de inversión:

- **Regla del 5%**: Ninguna posición puede superar el 5% del portfolio
- **Diversificación sectorial**: Máximo 20% en un mismo sector
- **Stop-Loss automático**: 8% por defecto (configurable), con opción ATR-based
- **Take-Profit**: 25% por defecto (configurable), con opción ATR-based
- **Trailing Stop**: Protección dinámica de beneficios
- **Position sizing**: Basado en convicción (score) y reglas de riesgo

## 🧮 Scoring de Estrategia

Cada acción recibe 3 scores (0-100):

| Score | Peso | Factores |
|---|---|---|
| **Value** | 40% | P/E, P/B, P/S, dividendo, margen de seguridad |
| **Quality** | 35% | ROE, márgenes, crecimiento, free cash flow |
| **Safety** | 25% | Deuda, beta, market cap, consenso analistas |

- **Score ≥ BUY_THRESHOLD (70)** → Señal de **COMPRA** 🟢
- **Score entre SELL y BUY** → **HOLD** 🟡
- **Score ≤ SELL_THRESHOLD (30)** → Señal de **VENTA** 🔴

Los umbrales son configurables vía variables de entorno: `SIGNAL_BUY_THRESHOLD`, `SIGNAL_SELL_THRESHOLD`, `SCAN_MIN_SCORE`.

## ⏰ Tareas Programadas (15 jobs)

| Frecuencia | Tarea |
|---|---|
| Cada 10 min | Actualizar precios (solo en horario de mercado) |
| Cada hora | Re-evaluar señales de posiciones |
| Cada hora | Comprobar alertas personalizadas de precio |
| Diario 7:00 | Resumen del portfolio por Telegram |
| Diario 8:00 | Guardar contexto geopolítico |
| Diario 18:00 | Snapshot del portfolio (NAV tracking) |
| Diario 9:30 | Calendario de earnings (alerta ≤7 días, análisis pre-earnings ≤3 días) |
| Cada 5 min | Ciclo del modo automático |
| Cada 60 min | Backtest autónomo sobre cartera demo |
| Semanal Dom 19:00 | Validación de precisión de señales (30-120 días) |
| Semanal Dom 20:00 | Insights de aprendizaje semanal |
| Semanal Dom 21:00 | Resumen semanal con benchmark (vs SPY) |
| Semanal Sáb 10:00 | Análisis de tendencias de snapshots (drawdown, alpha, recovery) |
| Diario | Tracking de dividendos |
| Configurable | Checkeo automático de dividendos |

Los horarios de mercado se gestionan automáticamente con soporte de festivos:
- **NASDAQ/NYSE**: 9:30 – 16:00 (ET)
- **IBEX 35**: 9:00 – 17:30 (CET)
- **DAX/XETRA**: 9:00 – 17:30 (CET)
- **CAC 40 (Euronext Paris)**: 9:00 – 17:30 (CET)
- **FTSE MIB (Milán)**: 9:00 – 17:30 (CET)
- **FTSE 100 (LSE)**: 8:00 – 16:30 (GMT)
- **AEX (Euronext Amsterdam)**: 9:00 – 17:30 (CET)

## 🗄️ Modelos de Datos (16 modelos + 10 enums)

| Modelo | Propósito |
|---|---|
| `Portfolio` | Carteras (real/demo) con estrategia y capital |
| `Position` | Posiciones abiertas/cerradas con precio medio y P&L |
| `Operation` | Compras/ventas con rastreo de origen (`OperationOrigin`) |
| `Signal` | Señales BUY/SELL/HOLD con scores y justificación |
| `WatchlistItem` | Watchlist IA con tesis y estado |
| `EarningsEvent` | Eventos de resultados trimestrales |
| `DividendPayment` | Cobros de dividendos por posición |
| `LearningLog` | Registro de aprendizaje enriquecido (origen, técnicos, contexto, dividendos) |
| `MarketContext` | Contexto geopolítico diario |
| `AutoModeConfig` | Configuración del modo automático |
| `PortfolioSnapshot` | Snapshots diarios de NAV + benchmark |
| `CustomAlert` | Alertas personalizadas de precio/volumen/RSI |
| `OpenAIUsage` | Tracking de tokens y costes por modelo |
| `AnalysisLog` | Análisis completos persistidos (analizar, scan, auto-scan) |
| `InvestmentObjective` | Objetivos de inversión con tesis y catalizadores |
| `PendingLimitOrder` | Órdenes límite pendientes con expiración y reconciliación broker/local |

Enums: `PortfolioType`, `OperationSide`, `SignalType`, `PositionStatus`, `WatchlistStatus`, `AssetType`, `AutoModeType`, `OperationOrigin`, `StrategyType`, `PendingLimitOrderStatus`.

## 📊 Stack Tecnológico

- **Python 3.12+**
- **PostgreSQL 16** (con SQLAlchemy 2.x async + Alembic)
- **python-telegram-bot 21+** (bot de Telegram con inline keyboards)
- **yfinance** (datos de mercado y precios)
- **OpenAI** (análisis IA con prompts adaptados por estrategia + rate limiting)
- **APScheduler** (tareas programadas)
- **exchange_calendars** (festivos de mercado)
- **Docker Compose** (despliegue con multi-stage build)
- **pytest** (tests unitarios)

## 📄 Licencia

MIT
