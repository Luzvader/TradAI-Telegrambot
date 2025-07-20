# TradAI

> Plataforma de *algo-trading* de criptomonedas con backend **FastAPI** y panel web en **Next.js + Material UI**.

TradAI permite consultar precios en tiempo real, crear/gestionar estrategias y ejecutar un motor de trading desde una interfaz web moderna. Todo el flujo se realiza mediante una API REST (autodocumentada) y WebSockets.

---

## 1. Arquitectura

| Capa        | Stack                        | Descripción breve                              |
|-------------|-----------------------------|------------------------------------------------|
| Frontend    | Next.js / React 18<br>Material UI | Panel de control: dashboard, mercados, estrategias, ajustes. |
| API Backend | FastAPI + Uvicorn           | Endpoints REST + Swagger, WebSocket opcional para *stream* de precios. |
| Servicios   | `services/` (Python)        | Capa de negocio: precios (*TradingView*), estrategias, motor de órdenes. |
| Motor bot   | `BotEngine` (hilo *daemon*) | Ejecuta reglas/estrategias de forma continua. |
| Datos       | Archivos JSON / CSV         | Historial de órdenes, estrategias y opciones. |

---

## 2. Requisitos

* Python ≥ 3.10
* Node ≥ 18
* Git (opcional, para clonar)

---

## 3. Instalación desde cero

```bash
# 1) Clona el proyecto (o descarga el ZIP)
git clone https://github.com/tuusuario/tradai.git
cd tradai

# 2) Backend – entorno virtual y dependencias
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS/Linux
source .venv/bin/activate
pip install -r requirements.txt

# 3) Frontend – dependencias npm
yarn install         # o npm install
```

---

## 4. Ejecución

### 4.1 Backend (HTTPS)

```bash
python -m tradai.serve       # => https://127.0.0.1:8000
```
La primera vez se genera un certificado autofirmado en `~/.tradai_ssl/`.

* Docs Swagger: `https://127.0.0.1:8000/docs`
* Docs Redoc : `https://127.0.0.1:8000/redoc`

### 4.2 Frontend (dev hot-reload)

```bash
cd frontend
npm run dev                  # => http://localhost:3000
```
El proxy del `next.config.js` reenvía las peticiones `/api/*` al backend.

---

## 5. Uso rápido

1. Visita el panel en `http://localhost:3000`.
2. Abre la pestaña **Markets** para ver precios en tiempo real.
3. Crea una estrategia en **Strategies** y guárdala.
4. Activa el bot con el botón **Start Bot** o via `POST /bot/start`.

---

## 6. API principal

| Método | Endpoint | Descripción básica |
|--------|----------|--------------------|
| GET    | /markets?symbols=BTC,ETH | Precio y variación de símbolos |
| GET    | /monitor?symbols=BTC,ETH&timeframe=15m | Precio + indicadores |
| POST   | /strategies | Crear estrategia EMA o rule-based |
| GET    | /strategies | Listar estrategias guardadas |
| GET    | /strategies/{id} | Obtener estrategia |
| DELETE | /strategies/{id} | Eliminar estrategia |
| POST   | /bot/start | Iniciar motor de estrategias |
| POST   | /bot/stop  | Detener motor |
| GET    | /orders    | Historial de órdenes |
| GET    | /pnl       | Devuelve la ganancia/perdida acumulada |
| POST   | /chat      | Enviar un mensaje al bot (echo simple) |

Consulta Swagger para parámetros detallados y ejemplos.

---

## 7. Variables de entorno (opcional)

| Variable            | Propósito                        |
|---------------------|----------------------------------|
| `OPENAI_API_KEY`    | Generación de estrategias con LLM |
| `BINANCE_API_KEY`   | Trading en cuenta real           |
| `BINANCE_API_SECRET`| «                                |

También puedes guardar estas claves vía `POST /options` o en la sección **Settings** del panel.

---

## 8. Tests

```bash
pytest -q
```
Las pruebas utilizan **httpx** para llamar a la API de forma asíncrona y cubren los servicios principales.

---

## 9. Despliegue

TradAI funciona en cualquier VPS/VM con Python y Node. Para producción:

1. Construye el frontend: `npm run build && npm run export`.
2. Sirve los archivos estáticos (Nginx) y ejecuta el backend con **gunicorn + uvicorn workers**.

---

## 10. Licencia

MIT © 2025 – José Martínez Montero
