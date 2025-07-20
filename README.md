# TradAI

Bot de trading por LLM.

Este repositorio contiene una versión inicial del bot de trading escrito en
Python. El bot obtiene datos de los mercados de TradingView para los pares de
criptomonedas definidos por el usuario utilizando siempre **USDT** como moneda
base.

**Aviso:** este software no constituye asesoramiento financiero ni de
inversión. Cualquier operación de compra o venta realizada a partir de él se
efectúa bajo el riesgo exclusivo del usuario.

## Uso rápido

Instalar las dependencias (solo `requests` es necesaria y viene incluida en la
imagen estándar):

```bash
pip install -r requirements.txt  # si existen dependencias adicionales
```

Ejecutar el script de ejemplo para obtener datos de mercado:

```bash
python -m tradai.bot BTC ETH
```

Esto imprimirá por pantalla la información recibida desde TradingView para los
pares `BTCUSDT` y `ETHUSDT`.

## Monitoreo continuo

Para iniciar un monitoreo simple ejecuta:

```bash
python -c "from tradai.monitor import monitor_prices; monitor_prices(['BTC','ETH'])"
```
 codex/add-cli-argument-for-refresh-interval
También puedes ejecutarlo directamente como módulo y ajustar el intervalo de
refresco (en segundos) con ``--interval``:

```bash
python -m tradai.monitor BTC ETH XRP --interval 60
```
`BTC`, `ETH`, `XRP` y `SOL` cada 5 minutos. Al iniciarlo se pide la
temporalidad (5m, 15m, 1h, 4h, 1d o 1w) sobre la que se evaluarán las
velas y, opcionalmente, cuántas velas atrás se quiere comparar la vela
actual. El monitoreo se detiene escribiendo `s` y presionando Enter.



## Panel de control web (Next.js)

El nuevo frontend está construido con **Next.js + Material UI** y funciona como un panel de control completo para TradAI: dashboard de precios, monitor de mercados, gestión de estrategias y ajustes.

### Instalación rápida

Ejecuta el instalador automático que prepara backend y frontend en Windows / PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

El script realizará:

1. Crear/activar un entorno virtual Python en `.venv` e instalar dependencias de `requirements.txt`.
2. Instalar las dependencias del frontend en `frontend/` con `npm install`.

### Cómo arrancar

En una primera terminal (backend HTTPS – FastAPI):

```bash
python -m tradai.serve     # https://127.0.0.1:8000
```

En una segunda terminal (frontend Next.js):

```bash
cd frontend
npm run dev                # http://localhost:3000
```

Gracias al proxy definido en `next.config.js`, el frontend reenvía las peticiones `/api/*` al backend, por lo que no necesitas configurar CORS.

### Funcionalidades iniciales del panel

* **Dashboard** – resumen de precios de BTC, ETH, XRP, SOL y BNB.
* **Markets** – tabla en tiempo real de precios para los símbolos seleccionados.
* **Strategies** – listado de estrategias almacenadas (CRUD en desarrollo).
* **Settings** – gestión de claves OpenAI, Binance, etc. (pendiente).

### Consumir la API directamente

Si prefieres acceder vía REST, los endpoints siguen disponibles en FastAPI:

* `GET /markets?symbols=BTC,ETH`
* `GET /monitor?symbols=BTC,ETH&timeframe=15m`
* `POST /wallet` para configurar la cartera (tipo y credenciales)
* `GET /wallet` para consultar balances
* `POST /options` / `GET /options` para gestionar claves y ajustes

### Arranque rápido

```bash
python -m tradai.serve
```

La primera ejecución generará un certificado autofirmado en `~/.tradai_ssl/` y
el servidor se iniciará en `https://127.0.0.1:8000`.

Abre `https://127.0.0.1:8000` y utiliza la interfaz:

* Ingresa símbolos separados por coma (ej. `BTC,ETH`).
* Pulsa **Consultar** para una consulta puntual.
* Pulsa **Monitorear** para refrescos automáticos cada minuto.
* **Detener** finaliza el monitoreo.
* **Opciones** permite guardar claves de OpenAI y Binance para futuras sesiones.

También puedes consumir la API REST directamente:

* `GET /markets?symbols=BTC,ETH`
* `GET /monitor?symbols=BTC,ETH&timeframe=15m`
* `POST /wallet` para configurar la cartera (tipo y credenciales)
* `GET /wallet` para consultar balances
* `POST /options` para guardar claves API y otros ajustes
* `GET /options` para consultarlos

### Configuración de la cartera

Ejemplo para guardar una cartera demo:

```bash
curl -X POST http://127.0.0.1:8000/wallet -H "Content-Type: application/json" \
     -d '{"type":"demo"}'
```

Para Binance se requieren `api_key` y `api_secret`:

```bash
curl -X POST http://127.0.0.1:8000/wallet -H "Content-Type: application/json" \
     -d '{"type":"binance","api_key":"TU_KEY","api_secret":"TU_SECRET"}'
```

Las credenciales y otras claves de API se guardan en el archivo `options.xml`
en la raíz del proyecto. Este archivo se genera automáticamente por la
aplicación y no se incluye en el repositorio. Asegúrate de protegerlo y evitar
compartir tus claves.

## Definición de estrategias

El bot permite definir **estrategias** en un archivo YAML. Cada estrategia indica
los símbolos a monitorear, el marco temporal y las reglas de entrada o salida.
Un ejemplo básico es:

```yaml
nombre: cruz_ema
symbols:
  - BTC
  - ETH
timeframe: 15m
reglas:
  - condicion: EMA20 > EMA50
    accion: BUY
  - condicion: EMA20 < EMA50
    accion: SELL
```

Guarda la estrategia como `mi_estrategia.yml` y ejecútala con:

```bash
python -m tradai.bot --strategy mi_estrategia.yml
```

## Ejecución automática desde la API y la web

El bot puede activarse desde la API mediante `POST /bot/start` y detenerse con
`POST /bot/stop`. Desde la interfaz web existe un botón **Activar bot** que
permite iniciar el motor de estrategias de forma continua utilizando los
símbolos por defecto. Las órdenes generadas se registran en un archivo local.

## Consulta del historial de órdenes

Cada orden ejecutada se almacena en `~/.tradai_orders`. También puedes acceder
al historial mediante `GET /orders` o desde la
sección **Historial** en la interfaz web, la cual muestra fecha, símbolo, lado y
cantidad de cada operación realizada.

## Integración opcional con LLM

TradAI puede sugerir estrategias automáticamente utilizando un modelo de lenguaje. Para habilitar esta característica añade tu clave de OpenAI en el
archivo `options.xml` bajo el elemento `<openai_api_key>`.


Una vez configurado, puedes invocar `POST /llm/strategy` enviando un JSON con
el campo `prompt` que describa tu idea. El endpoint devolverá la propuesta de
estrategia en formato JSON y, opcionalmente, la guardará si añades `"save": true`.

En la interfaz web encontrarás un formulario *Sugerir estrategia con LLM* donde
escribes la idea, obtienes la propuesta y puedes guardarla directamente. Esta
integración es experimental y completamente opcional.
