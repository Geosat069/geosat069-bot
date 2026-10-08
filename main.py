"""
GEOSAT - Bot de Telegram con IA (Groq + openai/gpt-oss-20b)

- Memoria persistente: Postgres externo (DATABASE_URL) o SQLite local si no hay.
- Historial de conversación por chat.
- Tools reales: clima, hora, guardar recuerdos.
- Acceso restringido a tu usuario de Telegram (ALLOWED_USER_ID).
"""
import asyncio
import functools
import io
import json
import logging
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import groq
import requests
from dotenv import load_dotenv
from flask import Flask
from groq import AsyncGroq
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("geosat")

# ---------------------------------------------------------------- configuración
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")
MODELO = os.getenv("MODELO", "openai/gpt-oss-20b")
ESFUERZO = os.getenv("REASONING_EFFORT", "low")  # low | medium | high
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", "0") or 0)
NOMBRE = os.getenv("NOMBRE_USUARIO", "Jhon")
LAT = float(os.getenv("LAT", "3.4516"))  # Cali por defecto
LON = float(os.getenv("LON", "-76.5320"))
ZONA = os.getenv("ZONA_HORARIA", "America/Bogota")

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

memoria = None  # se crean en main()
cliente = None


# ---------------------------------------------------------------------- memoria
class Memoria:
    """Hechos duraderos + historial. Postgres si hay DATABASE_URL; si no, SQLite."""

    def __init__(self):
        self.pg = bool(DATABASE_URL)
        self.ph = "%s" if self.pg else "?"
        if self.pg:
            import psycopg2

            self._psycopg2 = psycopg2
        else:
            os.makedirs("memoria", exist_ok=True)
        self._crear_tablas()
        log.info("Memoria lista (%s)", "Postgres" if self.pg else "SQLite local")

    def _conectar(self):
        if self.pg:
            return self._psycopg2.connect(DATABASE_URL, connect_timeout=10)
        return sqlite3.connect("memoria/bot.db")

    def _ejecutar(self, sql, params=(), leer=False):
        con = self._conectar()
        try:
            cur = con.cursor()
            cur.execute(sql, params)
            filas = cur.fetchall() if leer else None
            con.commit()
            return filas
        finally:
            con.close()

    def _crear_tablas(self):
        pk = "SERIAL PRIMARY KEY" if self.pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
        self._ejecutar(
            f"CREATE TABLE IF NOT EXISTS hechos "
            f"(id {pk}, texto TEXT NOT NULL, fecha TEXT NOT NULL)"
        )
        self._ejecutar(
            f"CREATE TABLE IF NOT EXISTS mensajes "
            f"(id {pk}, chat_id BIGINT NOT NULL, rol TEXT NOT NULL, "
            f"contenido TEXT NOT NULL, fecha TEXT NOT NULL)"
        )

    @staticmethod
    def _ahora():
        return datetime.now(timezone.utc).isoformat()

    # --- hechos
    def guardar_hecho(self, texto):
        texto = (texto or "").strip()[:500]
        if not texto:
            return False
        self._ejecutar(
            f"INSERT INTO hechos (texto, fecha) VALUES ({self.ph}, {self.ph})",
            (texto, self._ahora()),
        )
        return True

    def buscar_hechos(self, consulta, n=5):
        palabras = list(dict.fromkeys(re.findall(r"\w{4,}", consulta.lower())))[:8]
        if not palabras:
            return []
        cond = " OR ".join([f"LOWER(texto) LIKE {self.ph}"] * len(palabras))
        filas = self._ejecutar(
            f"SELECT texto FROM hechos WHERE {cond} ORDER BY id DESC LIMIT {int(n)}",
            tuple(f"%{p}%" for p in palabras),
            leer=True,
        )
        return [f[0] for f in filas]

    def ultimos_hechos(self, n=15):
        return self._ejecutar(
            f"SELECT id, texto FROM hechos ORDER BY id DESC LIMIT {int(n)}", leer=True
        )

    def borrar_hechos(self):
        self._ejecutar("DELETE FROM hechos")

    # --- historial
    def guardar_mensaje(self, chat_id, rol, contenido):
        self._ejecutar(
            f"INSERT INTO mensajes (chat_id, rol, contenido, fecha) "
            f"VALUES ({self.ph}, {self.ph}, {self.ph}, {self.ph})",
            (chat_id, rol, contenido, self._ahora()),
        )

    def historial(self, chat_id, n=10):
        filas = self._ejecutar(
            f"SELECT rol, contenido FROM mensajes WHERE chat_id = {self.ph} "
            f"ORDER BY id DESC LIMIT {int(n)}",
            (chat_id,),
            leer=True,
        )
        return [{"role": r, "content": c} for r, c in reversed(filas)]

    def recortar_historial(self, chat_id, conservar=200):
        self._ejecutar(
            f"DELETE FROM mensajes WHERE chat_id = {self.ph} AND id NOT IN "
            f"(SELECT id FROM mensajes WHERE chat_id = {self.ph} "
            f"ORDER BY id DESC LIMIT {int(conservar)})",
            (chat_id, chat_id),
        )

    def borrar_historial(self, chat_id):
        self._ejecutar(f"DELETE FROM mensajes WHERE chat_id = {self.ph}", (chat_id,))


# ------------------------------------------------------------------- herramientas
def clima_actual(lat=None, lon=None):
    lat = LAT if lat is None else lat
    lon = LON if lon is None else lon
    r = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "timezone": "auto",
            "forecast_days": 1,
        },
        timeout=10,
    )
    r.raise_for_status()
    d = r.json()
    c, dia = d["current"], d["daily"]
    return (
        f"Ahora: {c['temperature_2m']} °C, humedad {c['relative_humidity_2m']}%, "
        f"viento {c['wind_speed_10m']} km/h. "
        f"Hoy: mín {dia['temperature_2m_min'][0]} °C, máx {dia['temperature_2m_max'][0]} °C, "
        f"prob. de lluvia {dia['precipitation_probability_max'][0]}%."
    )


def serie_temperatura_hoy():
    r = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": LAT,
            "longitude": LON,
            "hourly": "temperature_2m",
            "timezone": "auto",
            "forecast_days": 1,
        },
        timeout=10,
    )
    r.raise_for_status()
    h = r.json()["hourly"]
    return h["time"], h["temperature_2m"]


def grafica_linea(titulo, etiquetas, valores):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 4), dpi=100)
    ax.plot(range(len(valores)), valores, marker="o", color="#d9480f")
    paso = max(1, len(etiquetas) // 8)
    idx = list(range(0, len(etiquetas), paso))
    ax.set_xticks(idx)
    ax.set_xticklabels([etiquetas[i] for i in idx])
    ax.set_title(titulo)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf


def hora_actual():
    ahora = datetime.now(ZoneInfo(ZONA))
    return f"{DIAS[ahora.weekday()]} {ahora:%d/%m/%Y %H:%M} ({ZONA})"


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "obtener_clima",
            "description": "Clima actual y pronóstico de hoy. Sin argumentos usa la ubicación por defecto del usuario.",
            "parameters": {
                "type": "object",
                "properties": {
                    "latitud": {"type": "number"},
                    "longitud": {"type": "number"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hora_actual",
            "description": "Fecha y hora actuales del usuario.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "guardar_recuerdo",
            "description": (
                "Guarda un dato duradero e importante sobre el usuario o sus proyectos "
                "(preferencias, datos de trabajo). No guardes cosas triviales ni "
                "contraseñas, claves o datos sensibles."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "texto": {"type": "string", "description": "El dato, en una frase corta"}
                },
                "required": ["texto"],
            },
        },
    },
]


async def ejecutar_tool(nombre, argumentos_json):
    try:
        args = json.loads(argumentos_json or "{}")
    except json.JSONDecodeError:
        args = {}
    try:
        if nombre == "obtener_clima":
            return await asyncio.to_thread(clima_actual, args.get("latitud"), args.get("longitud"))
        if nombre == "hora_actual":
            return hora_actual()
        if nombre == "guardar_recuerdo":
            ok = await asyncio.to_thread(memoria.guardar_hecho, args.get("texto", ""))
            return "Guardado." if ok else "Texto vacío; no se guardó nada."
        return f"Herramienta desconocida: {nombre}"
    except Exception as e:  # el modelo recibe el error y puede explicarlo
        log.exception("Error en tool %s", nombre)
        return f"Error al ejecutar {nombre}: {e}"


# --------------------------------------------------------------------------- IA
def prompt_sistema(hechos):
    recuerdos = "\n".join(f"- {h}" for h in hechos) if hechos else "(ninguno relevante)"
    return (
        f"Eres GEOSAT, asistente técnico personal de {NOMBRE}, enfocado en topografía "
        f"y geodesia. Fecha y hora actuales: {hora_actual()}.\n"
        "Reglas:\n"
        "- Responde en español, claro y corto (se lee en un celular).\n"
        "- Texto plano: sin Markdown, sin tablas, sin asteriscos.\n"
        "- No inventes datos. Para clima u hora usa las herramientas.\n"
        "- Usa guardar_recuerdo solo para datos duraderos y útiles, nunca para claves "
        "ni datos sensibles.\n"
        f"Recuerdos relevantes sobre {NOMBRE}:\n{recuerdos}"
    )


async def responder(mensajes):
    for _ in range(4):  # máximo 4 vueltas de herramientas
        r = await cliente.chat.completions.create(
            model=MODELO,
            messages=mensajes,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.5,
            extra_body={"reasoning_effort": ESFUERZO},
        )
        msg = r.choices[0].message
        if not msg.tool_calls:
            return (msg.content or "").strip()
        mensajes.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            }
        )
        for tc in msg.tool_calls:
            resultado = await ejecutar_tool(tc.function.name, tc.function.arguments)
            mensajes.append({"role": "tool", "tool_call_id": tc.id, "content": resultado})
    return "No pude completar la consulta con las herramientas."


# ---------------------------------------------------------------------- Telegram
def autorizado(update: Update) -> bool:
    u = update.effective_user
    return bool(u) and ALLOWED_USER_ID != 0 and u.id == ALLOWED_USER_ID


def solo_yo(func):
    @functools.wraps(func)
    async def envoltura(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not autorizado(update):
            uid = update.effective_user.id if update.effective_user else "?"
            log.warning("Acceso denegado al usuario %s", uid)
            return
        await func(update, context)

    return envoltura


async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Sin restricción: sirve para descubrir tu ID y ponerlo en ALLOWED_USER_ID.
    await update.message.reply_text(f"Tu ID de Telegram es: {update.effective_user.id}")


@solo_yo
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "GEOSAT en línea.\n"
        "/clima - clima de hoy\n"
        "/grafica - temperatura de hoy (o /grafica 23.5 24 25)\n"
        "/recordar <texto> - guardar un dato\n"
        "/memoria - ver lo guardado\n"
        "/olvidar todo - borrar recuerdos\n"
        "/reset - borrar el historial de la charla\n"
        "Escríbeme cualquier cosa y te respondo."
    )


@solo_yo
async def cmd_clima(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text(await asyncio.to_thread(clima_actual))
    except Exception:
        log.exception("Error de clima")
        await update.message.reply_text("No pude obtener el clima ahora.")


@solo_yo
async def cmd_grafica(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = " ".join(context.args)
    try:
        if args:
            valores = [float(x) for x in re.split(r"[,\s;]+", args) if x]
            if len(valores) < 2:
                raise ValueError
            buf = await asyncio.to_thread(
                grafica_linea, "GEOSAT - Serie", [str(i + 1) for i in range(len(valores))], valores
            )
            pie = f"{len(valores)} datos"
        else:
            horas, temps = await asyncio.to_thread(serie_temperatura_hoy)
            buf = await asyncio.to_thread(
                grafica_linea, "Temperatura de hoy (°C)", [h[-5:] for h in horas], temps
            )
            pie = "Fuente: Open-Meteo"
        await update.message.reply_photo(photo=buf, caption=pie)
    except ValueError:
        await update.message.reply_text(
            "Uso: /grafica 23.5 24.1 25 (mínimo 2 números), o solo /grafica "
            "para la temperatura de hoy."
        )
    except Exception:
        log.exception("Error de gráfica")
        await update.message.reply_text("No pude generar la gráfica.")


@solo_yo
async def cmd_recordar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = " ".join(context.args).strip()
    if not texto:
        await update.message.reply_text("Uso: /recordar <dato a guardar>")
        return
    await asyncio.to_thread(memoria.guardar_hecho, texto)
    await update.message.reply_text("Guardado.")


@solo_yo
async def cmd_memoria(update: Update, context: ContextTypes.DEFAULT_TYPE):
    filas = await asyncio.to_thread(memoria.ultimos_hechos)
    if not filas:
        await update.message.reply_text("Aún no hay recuerdos guardados.")
        return
    await update.message.reply_text("Recuerdos (los más recientes):\n" + "\n".join(f"- {t}" for _, t in filas)[:4000])


@solo_yo
async def cmd_olvidar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if " ".join(context.args).strip().lower() != "todo":
        await update.message.reply_text("Esto borra todos los recuerdos. Confirma con: /olvidar todo")
        return
    await asyncio.to_thread(memoria.borrar_hechos)
    await update.message.reply_text("Recuerdos borrados.")


@solo_yo
async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.to_thread(memoria.borrar_historial, update.effective_chat.id)
    await update.message.reply_text("Historial de la conversación borrado.")


@solo_yo
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    texto = update.message.text
    await context.bot.send_chat_action(chat_id, "typing")
    try:
        hechos = await asyncio.to_thread(memoria.buscar_hechos, texto)
        hist = await asyncio.to_thread(memoria.historial, chat_id, 10)
        mensajes = (
            [{"role": "system", "content": prompt_sistema(hechos)}]
            + hist
            + [{"role": "user", "content": texto}]
        )
        respuesta = await responder(mensajes)
    except groq.RateLimitError:
        await update.message.reply_text("Llegué al límite de Groq. Espera un minuto e intenta de nuevo.")
        return
    except Exception:
        log.exception("Error al responder")
        await update.message.reply_text("Tuve un problema al consultar el modelo. Intenta de nuevo.")
        return

    respuesta = respuesta or "No pude generar una respuesta."
    await asyncio.to_thread(memoria.guardar_mensaje, chat_id, "user", texto)
    await asyncio.to_thread(memoria.guardar_mensaje, chat_id, "assistant", respuesta)
    await asyncio.to_thread(memoria.recortar_historial, chat_id)
    for i in range(0, len(respuesta), 4000):
        await update.message.reply_text(respuesta[i : i + 4000])


async def al_error(update, context: ContextTypes.DEFAULT_TYPE):
    log.error("Error no controlado", exc_info=context.error)


# --------------------------------------------------------------------- keep-alive
web = Flask(__name__)


@web.route("/")
def inicio():
    return "GEOSAT vivo", 200


def iniciar_web():
    puerto = int(os.getenv("PORT", "10000"))  # Render define PORT
    threading.Thread(
        target=lambda: web.run(host="0.0.0.0", port=puerto), daemon=True
    ).start()
    log.info("Servidor keep-alive en el puerto %s", puerto)


# ------------------------------------------------------------------------- inicio
def main():
    global memoria, cliente
    faltan = [n for n, v in (("BOT_TOKEN", BOT_TOKEN), ("GROQ_API_KEY", GROQ_API_KEY)) if not v]
    if faltan:
        raise SystemExit(f"Faltan variables de entorno: {', '.join(faltan)}")
    if ALLOWED_USER_ID == 0:
        log.warning("ALLOWED_USER_ID no está definido: el bot solo responderá a /id")

    memoria = Memoria()
    cliente = AsyncGroq(api_key=GROQ_API_KEY)
    iniciar_web()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("clima", cmd_clima))
    app.add_handler(CommandHandler("grafica", cmd_grafica))
    app.add_handler(CommandHandler("recordar", cmd_recordar))
    app.add_handler(CommandHandler("memoria", cmd_memoria))
    app.add_handler(CommandHandler("olvidar", cmd_olvidar))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    app.add_error_handler(al_error)
    log.info("GEOSAT iniciado")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
