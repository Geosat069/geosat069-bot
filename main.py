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

import topo

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("geosat")
logging.getLogger("httpx").setLevel(logging.WARNING)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")
MODELO = os.getenv("MODELO", "openai/gpt-oss-20b")
ESFUERZO = os.getenv("REASONING_EFFORT", "low")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", "0") or 0)
NOMBRE = os.getenv("NOMBRE_USUARIO", "Jhon")
LAT = float(os.getenv("LAT", "3.4516"))
LON = float(os.getenv("LON", "-76.5320"))
ZONA = os.getenv("ZONA_HORARIA", "America/Bogota")
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

memoria = None
cliente = None

class Memoria:
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
        self._ejecutar(f"CREATE TABLE IF NOT EXISTS hechos (id {pk}, texto TEXT NOT NULL, fecha TEXT NOT NULL)")
        self._ejecutar(f"CREATE TABLE IF NOT EXISTS mensajes (id {pk}, chat_id BIGINT NOT NULL, rol TEXT NOT NULL, contenido TEXT NOT NULL, fecha TEXT NOT NULL)")

    @staticmethod
    def _ahora():
        return datetime.now(timezone.utc).isoformat()

    def guardar_hecho(self, texto):
        texto = (texto or "").strip()[:500]
        if not texto:
            return False
        self._ejecutar(f"INSERT INTO hechos (texto, fecha) VALUES ({self.ph}, {self.ph})", (texto, self._ahora()))
        return True

    def buscar_hechos(self, consulta, n=5):
        palabras = list(dict.fromkeys(re.findall(r"\w{4,}", consulta.lower())))[:8]
        if not palabras:
            return []
        cond = " OR ".join([f"LOWER(texto) LIKE {self.ph}"] * len(palabras))
        filas = self._ejecutar(f"SELECT texto FROM hechos WHERE {cond} ORDER BY id DESC LIMIT {int(n)}", tuple(f"%{p}%" for p in palabras), leer=True)
        return [f[0] for f in filas]

    def ultimos_hechos(self, n=15):
        return self._ejecutar(f"SELECT id, texto FROM hechos ORDER BY id DESC LIMIT {int(n)}", leer=True)

    def borrar_hechos(self):
        self._ejecutar("DELETE FROM hechos")

    def guardar_mensaje(self, chat_id, rol, contenido):
        self._ejecutar(f"INSERT INTO mensajes (chat_id, rol, contenido, fecha) VALUES ({self.ph}, {self.ph}, {self.ph}, {self.ph})", (chat_id, rol, contenido, self._ahora()))

    def historial(self, chat_id, n=10):
        filas = self._ejecutar(f"SELECT rol, contenido FROM mensajes WHERE chat_id = {self.ph} ORDER BY id DESC LIMIT {int(n)}", (chat_id,), leer=True)
        return [{"role": r, "content": c} for r, c in reversed(filas)]

    def recortar_historial(self, chat_id, conservar=200):
        self._ejecutar(f"DELETE FROM mensajes WHERE chat_id = {self.ph} AND id NOT IN (SELECT id FROM mensajes WHERE chat_id = {self.ph} ORDER BY id DESC LIMIT {int(conservar)})", (chat_id, chat_id))

    def borrar_historial(self, chat_id):
        self._ejecutar(f"DELETE FROM mensajes WHERE chat_id = {self.ph}", (chat_id,))

def clima_actual(lat=None, lon=None):
    lat = LAT if lat is None else lat
    lon = LON if lon is None else lon
    r = requests.get("https://api.open-meteo.com/v1/forecast", params={"latitude": lat, "longitude": lon, "current": "temperature_2m,relative_humidity_2m,wind_speed_10m", "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max", "timezone": "auto", "forecast_days": 1}, timeout=10)
    r.raise_for_status()
    d = r.json()
    c, dia = d["current"], d["daily"]
    return (f"Ahora: {c['temperature_2m']} °C, humedad {c['relative_humidity_2m']}%, viento {c['wind_speed_10m']} km/h. Hoy: mín {dia['temperature_2m_min'][0]} °C, máx {dia['temperature_2m_max'][0]} °C, prob. de lluvia {dia['precipitation_probability_max'][0]}%.")

def serie_temperatura_hoy():
    r = requests.get("https://api.open-meteo.com/v1/forecast", params={"latitude": LAT, "longitude": LON, "hourly": "temperature_2m", "timezone": "auto", "forecast_days": 1}, timeout=10)
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

TOOLS_BASE = [
    {"type": "function", "function": {"name": "obtener_clima", "description": "Clima actual y pronóstico de hoy.", "parameters": {"type": "object", "properties": {"latitud": {"type": "number"}, "longitud": {"type": "number"}}}}},
    {"type": "function", "function": {"name": "hora_actual", "description": "Fecha y hora actuales.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "guardar_recuerdo", "description": "Guarda un dato duradero e importante.", "parameters": {"type": "object", "properties": {"texto": {"type": "string"}}, "required": ["texto"]}}},
]
TOOLS = TOOLS_BASE + topo.TOOLS

async def ejecutar_tool(nombre, argumentos_json):
    try:
        args = json.loads(argumentos_json or "{}")
    except json.JSONDecodeError:
        args = {}
    try:
        if nombre in topo.FUNCIONES:
            return await asyncio.to_thread(topo.ejecutar, nombre, args)
        if nombre == "obtener_clima":
            return await asyncio.to_thread(clima_actual, args.get("latitud"), args.get("longitud"))
        if nombre == "hora_actual":
            return hora_actual()
        if nombre == "guardar_recuerdo":
            ok = await asyncio.to_thread(memoria.guardar_hecho, args.get("texto", ""))
            return "Guardado." if ok else "Texto vacío"
        return f"Herramienta desconocida: {nombre}"
    except Exception as e:
        log.exception("Error en tool %s", nombre)
        return f"Error al ejecutar {nombre}: {e}"

def prompt_sistema(hechos):
    recuerdos = "\n".join(f"- {h}" for h in hechos) if hechos else "(ninguno relevante)"
    return (f"Eres GEOSAT, asistente experto de {NOMBRE} en topografía, geomática, drones, Civil 3D, AutoCAD, QGIS y Python. Fecha y hora actuales: {hora_actual()}.\n"
            "Reglas:\n- Responde en español, claro y corto. Texto plano: sin Markdown.\n"
            "- Cálculos (coordenadas, distancias, azimuts, áreas, poligonales, niveles, GSD): usa SIEMPRE las herramientas; nunca hagas cuentas de memoria.\n"
            "- Si faltan datos, pregunta antes de calcular.\n"
            "- Contexto Colombia: sistema oficial MAGNA-SIRGAS Origen Nacional (EPSG:9377). Para Cali, la zona MAGNA es Oeste (EPSG:3115).\n"
            "- Para exportar archivos usa /exportar.\n"
            "- No inventes datos, normas ni valores.\n"
            f"Recuerdos relevantes:\n{recuerdos}")

async def responder(mensajes):
    for _ in range(5):
        r = await cliente.chat.completions.create(model=MODELO, messages=mensajes, tools=TOOLS, tool_choice="auto", temperature=0.3, extra_body={"reasoning_effort": ESFUERZO})
        msg = r.choices[0].message
        if not msg.tool_calls:
            return (msg.content or "").strip()
        mensajes.append({"role": "assistant", "content": msg.content or "", "tool_calls": [{"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}} for tc in msg.tool_calls]})
        for tc in msg.tool_calls:
            resultado = await ejecutar_tool(tc.function.name, tc.function.arguments)
            mensajes.append({"role": "tool", "tool_call_id": tc.id, "content": resultado})
    return "No pude completar la consulta con las herramientas."

def autorizado(update: Update) -> bool:
    u = update.effective_user
    return bool(u) and ALLOWED_USER_ID!= 0 and u.id == ALLOWED_USER_ID

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
    await update.message.reply_text(f"Tu ID de Telegram es: {update.effective_user.id}")

@solo_yo
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("GEOSAT V2.1 en línea: topografía, geomática, drones, Civil 3D, AutoCAD, QGIS y Python.\nEj: Convierte 3.4516, -76.5320 de WGS84 a Origen Nacional\nDistancia y azimut entre (1000,1000) y (1100,1180) en origen nacional\nGSD dron a 100 m, sensor 13.2 mm, focal 8.8 mm, ancho 5472 alto 3648\n\nComandos:\n/sistemas - sistemas\n/clima - clima\n/grafica - temperatura\n/exportar - CSV KML DXF\n/recordar <texto>\n/corregir <texto>\n/memoria\n/olvidar todo\n/reset")

@solo_yo
async def cmd_sistemas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(topo.sistemas())

@solo_yo
async def cmd_corregir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = " ".join(context.args).strip()
    if not texto:
        await update.message.reply_text("Uso: /corregir <la corrección>")
        return
    await asyncio.to_thread(memoria.guardar_hecho, f"CORRECCIÓN: {texto}")
    await update.message.reply_text("Aprendido. Lo tendré en cuenta.")

@solo_yo
async def cmd_clima(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text(await asyncio.to_thread(clima_actual))
    except Exception:
        await update.message.reply_text("No pude obtener el clima ahora.")

@solo_yo
async def cmd_grafica(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = " ".join(context.args)
    try:
        if args:
            valores = [float(x) for x in re.split(r"[,\s;]+", args) if x]
            if len(valores) < 2:
                raise ValueError
            buf = await asyncio.to_thread(grafica_linea, "GEOSAT - Serie", [str(i + 1) for i in range(len(valores))], valores)
            pie = f"{len(valores)} datos"
        else:
            horas, temps = await asyncio.to_thread(serie_temperatura_hoy)
            buf = await asyncio.to_thread(grafica_linea, "Temperatura de hoy (°C)", [h[-5:] for h in horas], temps)
            pie = "Fuente: Open-Meteo"
        await update.message.reply_photo(photo=buf, caption=pie)
    except ValueError:
        await update.message.reply_text("Uso: /grafica 23.5 24.1 25 (mín 2 números), o solo /grafica")
    except Exception:
        await update.message.reply_text("No pude generar la gráfica.")

@solo_yo
async def cmd_recordar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = " ".join(context.args).strip()
    if not texto:
        await update.message.reply_text("Uso: /recordar <dato>")
        return
    await asyncio.to_thread(memoria.guardar_hecho, texto)
    await update.message.reply_text("Guardado.")

@solo_yo
async def cmd_memoria(update: Update, context: ContextTypes.DEFAULT_TYPE):
    filas = await asyncio.to_thread(memoria.ultimos_hechos)
    if not filas:
        await update.message.reply_text("Aún no hay recuerdos.")
        return
    await update.message.reply_text("Recuerdos:\n" + "\n".join(f"- {t}" for _, t in filas)[:4000])

@solo_yo
async def cmd_olvidar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if " ".join(context.args).strip().lower()!= "todo":
        await update.message.reply_text("Confirma con: /olvidar todo")
        return
    await asyncio.to_thread(memoria.borrar_hechos)
    await update.message.reply_text("Recuerdos borrados.")

@solo_yo
async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.to_thread(memoria.borrar_historial, update.effective_chat.id)
    await update.message.reply_text("Historial borrado.")

@solo_yo
async def cmd_exportar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = " ".join(context.args)
    if not texto:
        await update.message.reply_text("Uso: /exportar <sistema> <Este,Norte; Este,Norte;...>\nEj: /exportar origen_nacional 1000,1000;1100,1000;1100,1100;1000,1100\nTe devuelve CSV, KML y DXF.")
        return
    try:
        partes = texto.split(maxsplit=1)
        if len(partes) == 1:
            # si no pone sistema, asume origen_nacional
            sis = "origen_nacional"
            pts_txt = partes[0]
        else:
            # intenta detectar si primera palabra es sistema
            posible_sis = partes[0].lower()
            if any(k in posible_sis for k in ["origen","wgs84","magna","utm","oeste","bogota","311"]):
                sis = partes[0]
                pts_txt = partes[1]
            else:
                sis = "origen_nacional"
                pts_txt = texto
        puntos = []
        for p in pts_txt.split(";"):
            if "," in p:
                x,y = p.split(",")
                puntos.append([float(x.strip()), float(y.strip())])
        if len(puntos) < 3:
            raise ValueError("Mínimo 3 puntos")
        csv = await asyncio.to_thread(topo.exportar_csv, puntos, sis, "geosat")
        kml = await asyncio.to_thread(topo.exportar_kml, puntos, sis, "geosat")
        dxf = await asyncio.to_thread(topo.exportar_dxf, puntos, sis, "geosat")
        await update.message.reply_document(document=io.BytesIO(csv.encode()), filename="geosat_puntos.csv", caption=f"{len(puntos)} puntos en {sis} - CSV")
        await update.message.reply_document(document=io.BytesIO(kml.encode()), filename="geosat_google_earth.kml", caption="Abre en Google Earth")
        await update.message.reply_document(document=io.BytesIO(dxf.encode()), filename="geosat_autocad.dxf", caption="Abre en AutoCAD / Civil 3D")
    except Exception as e:
        await update.message.reply_text(f"No pude exportar: {e}")

@solo_yo
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    texto = update.message.text
    await context.bot.send_chat_action(chat_id, "typing")
    try:
        hechos = await asyncio.to_thread(memoria.buscar_hechos, texto)
        hist = await asyncio.to_thread(memoria.historial, chat_id, 8)
        mensajes = [{"role": "system", "content": prompt_sistema(hechos)}] + hist + [{"role": "user", "content": texto}]
        respuesta = await responder(mensajes)
    except groq.RateLimitError:
        await update.message.reply_text("Límite de Groq. Espera 1 min.")
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

web = Flask(__name__)
@web.route("/")
def inicio():
    return "GEOSAT V2.1 vivo", 200

def iniciar_web():
    puerto = int(os.getenv("PORT", "10000"))
    threading.Thread(target=lambda: web.run(host="0.0.0.0", port=puerto), daemon=True).start()
    log.info("Servidor keep-alive en puerto %s", puerto)

def main():
    global memoria, cliente
    faltan = [n for n, v in (("BOT_TOKEN", BOT_TOKEN), ("GROQ_API_KEY", GROQ_API_KEY)) if not v]
    if faltan:
        raise SystemExit(f"Faltan ENV: {', '.join(faltan)}")
    if ALLOWED_USER_ID == 0:
        log.warning("ALLOWED_USER_ID no definido: solo /id responderá")
    memoria = Memoria()
    cliente = AsyncGroq(api_key=GROQ_API_KEY)
    iniciar_web()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(CommandHandler(["start", "ayuda"], cmd_start))
    app.add_handler(CommandHandler("sistemas", cmd_sistemas))
    app.add_handler(CommandHandler("corregir", cmd_corregir))
    app.add_handler(CommandHandler("clima", cmd_clima))
    app.add_handler(CommandHandler("grafica", cmd_grafica))
    app.add_handler(CommandHandler("recordar", cmd_recordar))
    app.add_handler(CommandHandler("memoria", cmd_memoria))
    app.add_handler(CommandHandler("olvidar", cmd_olvidar))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("exportar", cmd_exportar))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    app.add_error_handler(al_error)
    log.info("GEOSAT iniciado")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
