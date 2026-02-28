# 📈 TradAI — Bot de Trading Algorítmico con IA

Bot de señales de inversión que corre 24/7 en un servidor,
monitoriza mercados en tiempo real y se administra completamente
por **Telegram**. Ahora opera en modo **broker-first con Trading212**
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
| **Aprendizaje** | IA analiza aciertos/errores pasados para optimizarse |
| **Benchmark** | Comparación semanal con SPY y tracking de NAV |
| **Alertas avanzadas** | Alertas de precio, volumen y RSI (sobrecompra/sobreventa) |
| **Caché** | Sistema de caché en memoria para reducir llamadas API |
| **Deduplicación** | Evita señales duplicadas en 24h |
| **Tickers Dinámicos** | Descubrimiento automático de tickers desde los índices (S&P 500, DAX, CAC, MIB, FTSE, IBEX, AEX) |
| **Justificación de Señales** | Cada señal de compra/venta incluye justificación detallada: scores, fundamentales, análisis IA |
| **Objetivos de Inversión** | Tesis, catalizadores, riesgos, precios objetivo y convicción por empresa |
| **Calendario Earnings** | Monitorización automática de resultados, alertas ≤7 días, análisis pre-earnings |
| **Coste OpenAI** | Tracking real de tokens, costes por modelo y rate limiting configurable |
| **Dashboard Web** | Panel web con resumen de portfolio, posiciones, señales y métricas (FastAPI + htmx) |
| **Confirmaciones** | Botones inline para confirmar compras/ventas |
| **Telegram** | 22+ comandos para administración completa |
| **Multi-mercado** | NASDAQ, NYSE, IBEX 35, DAX, CAC 40, FTSE MIB, FTSE 100, AEX con horarios y festivos |
| **Migraciones** | Alembic para migraciones de base de datos + auto-sync de columnas |
| **Tests** | Suite de tests con pytest para componentes críticos |

## 🏗️ Arquitectura

```
TradAI/
├── main.py                    # Punto de entrada (Telegram + Scheduler + Web)
├── config/
│   ├── settings.py            # Configuración central desde .env
│   └── markets.py             # Horarios de mercado y mapping tickers
├── database/
│   ├── connection.py          # Conexión async PostgreSQL + Unit of Work
│   ├── models.py              # 15+ modelos SQLAlchemy (incl. DividendPayment)
│   ├── repository.py          # Façade re-exportadora
│   └── repos/                 # Sub-módulos CRUD por dominio
│       ├── portfolio.py       # Portfolio, Position, Operation
│       ├── signals.py         # Signal, Watchlist, Earnings
│       ├── config.py          # Auto Mode, Alerts, Objectives
│       └── analytics.py       # Learning, OpenAI Usage, Dividends
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
│   └── utils.py               # Utilidades compartidas (clamp)
├── portfolio/
│   └── portfolio_manager.py   # Gestión de carteras + cash tracking
├── signals/
│   ├── signal_engine.py       # Façade del motor de señales
│   ├── builders.py            # Justificación y contexto determinista
│   ├── portfolio_signals.py   # Señales para posiciones abiertas
│   └── scanner.py             # Escaneo de oportunidades
├── ai/
│   ├── analyst.py             # Análisis IA + rate limiting + cost tracking
│   ├── watchlist.py           # Watchlist generada por IA
│   └── learning.py            # Aprendizaje de errores
├── backtesting/
│   ├── engine.py              # Motor de backtest
│   └── metrics.py             # Sharpe, drawdown, alpha, win rate
├── notifications/
│   └── __init__.py            # Sistema centralizado de notificaciones Telegram
├── web/
│   ├── app.py                 # Aplicación FastAPI
│   ├── routes.py              # Rutas web + API JSON
│   ├── templates/             # Templates Jinja2 + htmx
│   └── static/                # CSS/JS
├── telegram_bot/
│   ├── bot.py                 # Configuración del bot + inline keyboards
│   └── handlers/              # 22+ comandos de Telegram (modularizados)
│       ├── portfolio_cmds.py  # Cartera, buy, sell, capital, dividendos
│       ├── analysis_cmds.py   # Analizar, scan, comparar, backtest, ETF, insider, diversificación
│       ├── management_cmds.py # Alertas, auto mode, costes, earnings, help
│       ├── callbacks.py       # Botones inline (confirmaciones)
│       └── helpers.py         # Utilidades compartidas
├── scheduler/
│   ├── jobs.py                # 10+ tareas programadas (incl. alertas volumen/RSI)
│   └── auto_mode.py           # Motor del modo automático
├── alembic/                   # Migraciones de base de datos
│   ├── env.py                 # Entorno async de Alembic
│   └── versions/              # Archivos de migraciones
├── tests/                     # Suite de tests (pytest)
├── Dockerfile                 # Multi-stage build optimizado
└── docker-compose.yml         # PostgreSQL + App + Web dashboard
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
- `TRADING212_API_KEY` / `TRADING212_API_SECRET` — Credenciales del broker
- `TRADING212_MODE=demo` — Mantener demo para backtesting/operativa segura

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

### Operaciones (con confirmación inline)
| Comando | Ejemplo |
|---|---|
| `/buy TICKER CANTIDAD PRECIO` | `/buy AAPL 10 185.50` |
| `/sell TICKER CANTIDAD PRECIO` | `/sell AAPL 5 200.00` |

### Análisis
| Comando | Descripción |
|---|---|
| `/analizar TICKER` | Análisis completo con IA según estrategia activa |
| `/scan` | Escanear mejores oportunidades del universo |
| `/comparar TICKER1 TICKER2` | Comparar dos tickers lado a lado |
| `/macro` | Análisis macroeconómico con IA |
| `/backtest [TICKERS...]` | Backtest sobre cartera demo (o tickers indicados) con métricas y aprendizaje |
| `/etf` | Ver categorías de ETFs disponibles |
| `/etf CATEGORÍA` | Analizar ETFs de una categoría |
| `/insider TICKER` | Análisis de operaciones de insiders |
| `/diversificacion` | Análisis de correlación y diversificación del portfolio |
| `/dividendos` | Ver dividendos cobrados y resumen |

### Historial y Alertas
| Comando | Descripción |
|---|---|
| `/historial` | Últimas señales generadas |
| `/alertas` | Ver alertas activas |
| `/alertas crear TICKER precio_max 200` | Crear alerta de precio máximo |
| `/alertas crear TICKER precio_min 150` | Crear alerta de precio mínimo |
| `/alertas crear TICKER rsi_max 70` | Alerta RSI sobrecompra |
| `/alertas crear TICKER rsi_min 30` | Alerta RSI sobreventa |
| `/alertas crear TICKER volumen 2.0` | Alerta de volumen anómalo (x veces media) |
| `/alertas borrar ID` | Eliminar una alerta |

### Watchlist
| Comando | Descripción |
|---|---|
| `/watchlist` | Ver watchlist activa (máx 5) |
| `/watchlist generar` | IA genera nueva watchlist con tesis y objetivos |
| `/watchlist quitar TICKER` | Quitar de watchlist |

### Objetivos de Inversión
| Comando | Descripción |
|---|---|
| `/objetivo` | Ver todos los objetivos activos |
| `/objetivo TICKER` | Ver objetivo de un ticker |
| `/objetivo TICKER tesis ...` | Definir tesis de inversión |
| `/objetivo TICKER entrada 150` | Precio de entrada objetivo |
| `/objetivo TICKER salida 200` | Precio de salida objetivo |
| `/objetivo TICKER catalizadores ...` | Definir catalizadores |
| `/objetivo TICKER riesgos ...` | Definir riesgos |
| `/objetivo TICKER conviccion 8` | Nivel de convicción (1-10) |
| `/objetivo TICKER borrar` | Eliminar objetivo |

### Earnings
| Comando | Descripción |
|---|---|
| `/earnings` | Calendario de earnings (cartera + watchlist) |
| `/earnings TICKER` | Historial de resultados de un ticker |

### Estrategia (con selector de botones)
| Comando | Descripción |
|---|---|
| `/strategy` | Ver estrategia activa + selector visual |
| `/strategy value` | Value investing clásico |
| `/strategy growth` | Crecimiento agresivo |
| `/strategy dividend` | Dividendos / income |
| `/strategy balanced` | Equilibrado value + growth |
| `/strategy conservative` | Ultra conservador |

### Costes y Modo Auto
| Comando | Descripción |
|---|---|
| `/costes` | Uso y costes estimados de OpenAI |
| `/auto` | Ver estado del modo automático |
| `/auto on / off` | Activar / desactivar |
| `/auto scan 30` | Intervalo de scan (min) |
| `/auto analyze 60` | Intervalo de análisis (min) |
| `/auto summary 9 0` | Hora del resumen diario |

## 🛡️ Gestión de Riesgos

El sistema emula las reglas de un fondo de inversión:

- **Regla del 5%**: Ninguna posición puede superar el 5% del portfolio
- **Diversificación sectorial**: Máximo 20% en un mismo sector
- **Stop-Loss automático**: 8% por defecto (configurable), con opción ATR-based
- **Take-Profit**: 25% por defecto (configurable), con opción ATR-based
- **Trailing Stop**: Protección dinámica de beneficios
- **Position sizing**: Basado en convicción (score) y reglas de riesgo

## 🧠 Scoring de Estrategia

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

## ⏰ Tareas Programadas

| Frecuencia | Tarea |
|---|---|
| Cada 10 min | Actualizar precios (solo en horario de mercado) |
| Cada hora | Re-evaluar señales de posiciones |
| Cada hora | Comprobar alertas personalizadas de precio |
| Diario 7:00 | Resumen del portfolio por Telegram |
| Diario 8:00 | Guardar contexto geopolítico |
| Diario 18:00 | Snapshot del portfolio (NAV tracking) |
| Domingo 20:00 | Insights de aprendizaje semanal |
| Domingo 21:00 | Resumen semanal con benchmark (vs SPY) |
| Diario 9:30 | Calendario de earnings (alerta ≤7 días, análisis pre-earnings ≤3 días) |
| Cada 5 min | Ciclo del modo automático |
| Cada 60 min (configurable) | Backtest autónomo sobre cartera demo |

Los horarios de mercado se gestionan automáticamente con soporte de festivos:
- **NASDAQ/NYSE**: 9:30 – 16:00 (ET)
- **IBEX 35**: 9:00 – 17:30 (CET)
- **DAX/XETRA**: 9:00 – 17:30 (CET)
- **CAC 40 (Euronext Paris)**: 9:00 – 17:30 (CET)
- **FTSE MIB (Milán)**: 9:00 – 17:30 (CET)
- **FTSE 100 (LSE)**: 8:00 – 16:30 (GMT)
- **AEX (Euronext Amsterdam)**: 9:00 – 17:30 (CET)

## 📊 Stack Tecnológico

- **Python 3.12+**
- **PostgreSQL 16** (con SQLAlchemy 2.x async + Alembic)
- **python-telegram-bot 21+** (bot de Telegram con inline keyboards)
- **FastAPI + Jinja2 + htmx** (dashboard web)
- **yfinance** (datos de mercado y precios)
- **OpenAI** (análisis IA con prompts adaptados por estrategia + rate limiting)
- **APScheduler** (tareas programadas)
- **exchange_calendars** (festivos de mercado)
- **Docker Compose** (despliegue con multi-stage build)
- **pytest** (tests unitarios)

## 🌐 Dashboard Web

TradAI incluye un dashboard web accesible en `http://localhost:8080` (configurable):

- **KPIs**: Valor total, P&L, posiciones, señales 30d, coste OpenAI
- **Posiciones**: Tabla con P&L individual, sector, precio medio/actual
- **Señales**: Últimas señales con tipo (BUY/SELL/HOLD), score y detalle
- **Auto-refresh**: Actualización automática cada 60 segundos
- **API JSON**: Endpoints `/api/portfolio`, `/api/signals`, `/api/openai-usage`, `/api/health`

Variables de configuración:
- `WEB_ENABLED` — Activar/desactivar (default: `true`)
- `WEB_PORT` — Puerto (default: `8080`)
- `WEB_HOST` — Interfaz (default: `0.0.0.0`)

## 📄 Licencia

MIT
