"""
GEOSAT V2.2 - Fase 3 - Asistente topografía en Telegram
Lee CSV subidos, exporta poligonales con azimut, KML con vértices etiquetados.
Memoria Postgres o SQLite, Tools exactas en topo.py
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
import csv
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import groq
import requests
from dotenv import load_dotenv
from flask import Flask
from groq import AsyncGroq
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

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
DIAS = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"]

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
        log.info("Memoria lista (%s)", "Postgres" if self.pg else "SQLite")
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
    def _ahora(): return datetime.now(timezone.utc).isoformat()
    def guardar_hecho(self, texto):
        texto = (texto or "").strip()[:500]
        if not texto: return False
        self._ejecutar(f"INSERT INTO hechos (texto, fecha) VALUES ({self.ph}, {self.ph})", (texto, self._ahora()))
        return True
    def buscar_hechos(self, consulta, n=5):
        palabras = list(dict.fromkeys(re.findall(r"\w{4,}", consulta.lower())))[:8]
        if not palabras: return []
        cond = " OR ".join([f"LOWER(texto) LIKE {self.ph}"] * len(palabras))
        filas = self._ejecutar(f"SELECT texto FROM hechos WHERE {cond} ORDER BY id DESC LIMIT {int(n)}", tuple(f"%{p}%" for p in palabras), leer=True)
        return [f[0] for f in filas]
    def ultimos_hechos(self, n=15):
        return self._ejecutar(f"SELECT id, texto FROM hechos ORDER BY id DESC LIMIT {int(n)}", leer=True)
    def borrar_hechos(self): self._ejecutar("DELETE FROM hechos")
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
    lat = LAT if lat is None else lat; lon = LON if lon is None else lon
    r = requests.get("https://api.open-meteo.com/v1/forecast", params={"latitude": lat, "longitude": lon, "current": "temperature_2m,relative_humidity_2m,wind_speed_10m", "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max", "timezone": "auto", "forecast_days": 1}, timeout=10)
    r.raise_for_status(); d = r.json(); c, dia = d["current"], d["daily"]
    return f"Ahora: {c['temperature_2m']}°C, hum {c['relative_humidity_2m']}%, viento {c['wind_speed_10m']} km/h. Hoy: min {dia['temperature_2m_min'][0]}°C, max {dia['temperature_2m_max'][0]}°C, lluvia {dia['precipitation_probability_max'][0]}%."

def serie_temperatura_hoy():
    r = requests.get("https://api.open-meteo.com/v1/forecast", params={"latitude": LAT, "longitude": LON, "hourly": "temperature_2m", "timezone": "auto", "forecast_days": 1}, timeout=10)
    r.raise_for_status(); h = r.json()["hourly"]; return h["time"], h["temperature_2m"]

def grafica_linea(titulo, etiquetas, valores):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8,4), dpi=100)
    ax.plot(range(len(valores)), valores, marker="o", color="#d9480f")
    paso = max(1, len(etiquetas)//8); idx = list(range(0, len(etiquetas), paso))
    ax.set_xticks(idx); ax.set_xticklabels([etiquetas[i] for i in idx]); ax.set_title(titulo); ax.grid(alpha=0.3)
    fig.tight_layout(); buf = io.BytesIO(); fig.savefig(buf, format="png"); plt.close(fig); buf.seek(0); return buf

def hora_actual():
    ahora = datetime.now(ZoneInfo(ZONA)); return f"{DIAS[ahora.weekday()]} {ahora:%d/%m/%Y %H:%M} ({ZONA})"

TOOLS_BASE = [
{"type":"function","function":{"name":"obtener_clima","description":"Clima actual hoy. Sin args usa Cali.","parameters":{"type":"object","properties":{"latitud":{"type":"number"},"longitud":{"type":"number"}}}}},
{"type":"function","function":{"name":"hora_actual","description":"Fecha y hora actuales.","parameters":{"type":"object","properties":{}}}},
{"type":"function","function":{"name":"guardar_recuerdo","description":"Guarda dato duradero importante, 1 frase, no claves.","parameters":{"type":"object","properties":{"texto":{"type":"string"}},"required":["texto"]}}},
]
TOOLS = TOOLS_BASE + topo.TOOLS

async def ejecutar_tool(nombre, argumentos_json):
    try: args = json.loads(argumentos_json or "{}")
    except: args = {}
    try:
        if nombre in topo.FUNCIONES: return await asyncio.to_thread(topo.ejecutar, nombre, args)
        if nombre=="obtener_clima": return await asyncio.to_thread(clima_actual, args.get("latitud"), args.get("longitud"))
        if nombre=="hora_actual": return hora_actual()
        if nombre=="guardar_recuerdo": ok = await asyncio.to_thread(memoria.guardar_hecho, args.get("texto","")); return "Guardado." if ok else "Vacío"
        return f"Tool desconocida: {nombre}"
    except Exception as e:
        log.exception("Error tool %s", nombre); return f"Error en {nombre}: {e}"

def prompt_sistema(hechos):
    recuerdos = "\n".join(f"- {h}" for h in hechos) if hechos else "(ninguno)"
    return f"Eres GEOSAT, experto de {NOMBRE} en topografía, geomática, drones, Civil 3D, AutoCAD, QGIS y Python. Fecha: {hora_actual()}.\nReglas: español, corto, sin Markdown. Cálculos usa SIEMPRE tools. Si faltan datos pregunta. Colombia: MAGNA Origen Nacional 9377, Cali es Oeste 3115. Para exportar usa exportar_csv/kml/dxf. Para poligonales usa poligonal_a_puntos. CSV ancho es 5472 de 5472x3648 (alto 3648). No inventes. Recuerda validar con profesional.\nRecuerdos:\n{recuerdos}"

async def responder(mensajes):
    for _ in range(5):
        r = await cliente.chat.completions.create(model=MODELO, messages=mensajes, tools=TOOLS, tool_choice="auto", temperature=0.3, extra_body={"reasoning_effort": ESFUERZO})
        msg = r.choices[0].message
        if not msg.tool_calls: return (msg.content or "").strip()
        mensajes.append({"role":"assistant","content":msg.content or "","tool_calls":[{"id":tc.id,"type":"function","function":{"name":tc.function.name,"arguments":tc.function.arguments}} for tc in msg.tool_calls]})
        for tc in msg.tool_calls:
            resultado = await ejecutar_tool(tc.function.name, tc.function.arguments)
            mensajes.append({"role":"tool","tool_call_id":tc.id,"content":resultado})
    return "No pude completar con tools."

def autorizado(update: Update) -> bool:
    u = update.effective_user; return bool(u) and ALLOWED_USER_ID!=0 and u.id==ALLOWED_USER_ID

def solo_yo(func):
    @functools.wraps(func)
    async def envoltura(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not autorizado(update):
            if update.message and update.message.text and update.message.text.startswith("/id"): return await func(update, context)
            log.warning("Denegado %s", update.effective_user.id if update.effective_user else "?"); return
        await func(update, context)
    return envoltura

async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Tu ID de Telegram es: {update.effective_user.id}")

@solo_yo
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("GEOSAT V2.2 en línea: topografía, drones, Civil3D, QGIS.\nEj:\n- Convierte 3.4516,-76.5320 de WGS84 a Origen Nacional\n- Distancia entre (1000,1000) y (1100,1100) en origen_nacional\n- GSD dron 100m sensor 13.2mm focal 8.8mm 5472x3648\n- Poligonal desde (1000,1000): 100m a 0° 100 a 90° 100 a 180° 100 a 270°\n- Sube un CSV con puntos y te lo convierto\nComandos:\n/sistemas /exportar /clima /grafica /recordar /corregir /memoria /olvidar todo /reset")

@solo_yo
async def cmd_sistemas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(topo.sistemas())

@solo_yo
async def cmd_corregir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = " ".join(context.args).strip()
    if not texto: await update.message.reply_text("Uso: /corregir <lección>"); return
    await asyncio.to_thread(memoria.guardar_hecho, f"CORRECCIÓN: {texto}")
    await update.message.reply_text("Aprendido.")

@solo_yo
async def cmd_clima(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: await update.message.reply_text(await asyncio.to_thread(clima_actual))
    except: await update.message.reply_text("No pude obtener clima.")

@solo_yo
async def cmd_grafica(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = " ".join(context.args)
    try:
        if args:
            valores = [float(x) for x in re.split(r"[,\s;]+", args) if x]
            if len(valores)<2: raise ValueError
            buf = await asyncio.to_thread(grafica_linea, "GEOSAT Serie", [str(i+1) for i in range(len(valores))], valores)
            pie = f"{len(valores)} datos"
        else:
            horas, temps = await asyncio.to_thread(serie_temperatura_hoy)
            buf = await asyncio.to_thread(grafica_linea, "Temp hoy °C", [h[-5:] for h in horas], temps)
            pie = "Open-Meteo"
        await update.message.reply_photo(photo=buf, caption=pie)
    except ValueError: await update.message.reply_text("Uso: /grafica 23.5 24.1 25 o solo /grafica")
    except: await update.message.reply_text("No pude generar gráfica.")

@solo_yo
async def cmd_recordar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = " ".join(context.args).strip()
    if not texto: await update.message.reply_text("Uso: /recordar <dato>"); return
    await asyncio.to_thread(memoria.guardar_hecho, texto); await update.message.reply_text("Guardado.")

@solo_yo
async def cmd_memoria(update: Update, context: ContextTypes.DEFAULT_TYPE):
    filas = await asyncio.to_thread(memoria.ultimos_hechos)
    if not filas: await update.message.reply_text("Sin recuerdos."); return
    await update.message.reply_text("Recuerdos:\n" + "\n".join(f"- {t}" for _,t in filas)[:4000])

@solo_yo
async def cmd_olvidar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if " ".join(context.args).strip().lower()!= "todo": await update.message.reply_text("Confirma: /olvidar todo"); return
    await asyncio.to_thread(memoria.borrar_hechos); await update.message.reply_text("Recuerdos borrados.")

@solo_yo
async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.to_thread(memoria.borrar_historial, update.effective_chat.id); await update.message.reply_text("Historial borrado.")

@solo_yo
async def cmd_exportar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = " ".join(context.args)
    if not texto:
        await update.message.reply_text("Uso:\n/exportar origen_nacional 1000,1000;1100,1000;1100,1100\nPoligonal: /exportar origen_nacional poligonal 1000,1000 100m 0° 100m 90° 100m 180° 100m 270°")
        return
    try:
        puntos = []
        sis = "origen_nacional"
        low = texto.lower()
        if "poligonal" in low or re.search(r"\d+\s*m", low):
            init = re.search(r"(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)", texto)
            tramos_raw = re.findall(r"(\d+(?:\.\d+)?)\s*m?\s*(?:a\s*)?([0-9°'\"\.]+)", texto, re.I)
            if not init: raise ValueError("Falta punto inicial Este,Norte")
            # primera coincidencia es el punto inicial, la filtramos si es igual
            tramos = []
            for d,az in tramos_raw:
                # evita tomar el punto inicial como tramo si coincide
                if abs(float(d)-float(init.group(1)))<0.01: continue
                tramos.append((float(d), az))
            if not tramos:
                # intenta parsear sin 'm'
                nums = re.findall(r"(\d+(?:\.\d+)?)\s*(?:a\s*)?([0-9°'\"\.]+)", texto)
                tramos = [(float(d), az) for d,az in nums[-4:]]
            partes = texto.split()
            if partes and partes[0] and not "," in partes[0]: sis = partes[0].lower()
            if sis=="oeste_oeste": sis="oeste_oeste"
            e0,n0 = float(init.group(1)), float(init.group(2))
            puntos = await asyncio.to_thread(topo.poligonal_a_puntos, e0, n0, tramos)
        else:
            partes = texto.split(maxsplit=1)
            if len(partes)>1 and "," not in partes[0]:
                sis = partes[0].lower(); pts_txt = partes[1]
            else:
                pts_txt = texto
            for p in pts_txt.replace(";"," ").split():
                if "," in p:
                    try:
                        x,y = p.split(","); puntos.append([float(x.strip()), float(y.strip())])
                    except: continue
            # también separa por ;
            if not puntos:
                for p in pts_txt.split(";"):
                    if "," in p:
                        x,y = p.split(","); puntos.append([float(x.strip()), float(y.strip())])
        if len(puntos)<3: raise ValueError("Necesito mínimo 3 puntos")
        csv_out = await asyncio.to_thread(topo.exportar_csv, puntos, sis, "geosat")
        kml_out = await asyncio.to_thread(topo.exportar_kml, puntos, sis, "GEOSAT_Poligono")
        dxf_out = await asyncio.to_thread(topo.exportar_dxf, puntos, sis, "GEOSAT")
        await update.message.reply_document(document=io.BytesIO(csv_out.encode()), filename="geosat_puntos.csv", caption=f"{len(puntos)} pts en {sis}")
        await update.message.reply_document(document=io.BytesIO(kml_out.encode()), filename="geosat_google_earth.kml", caption="Con vértices V1,V2...")
        await update.message.reply_document(document=io.BytesIO(dxf_out.encode()), filename="geosat_autocad.dxf", caption="AutoCAD Civil 3D")
    except Exception as e:
        log.exception("exportar"); await update.message.reply_text(f"No pude exportar: {e}")

@solo_yo
async def doc_recibido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not update.message.document: return
        fname = update.message.document.file_name or "puntos.csv"
        if not fname.lower().endswith((".csv",".txt")):
            await update.message.reply_text("Sube un CSV o TXT con Este,Norte por línea."); return
        f = await update.message.document.get_file()
        buf = io.BytesIO(); await f.download_to_memory(buf); buf.seek(0)
        texto = buf.getvalue().decode('utf-8', errors='ignore')
        if len(texto)>300000: await update.message.reply_text("Archivo muy grande máx 300k"); return

        puntos=[]
        for line in texto.splitlines():
            if not line.strip(): continue
            if any(c.isalpha() for c in line.split(",")[0][:2]): continue
            parts = re.split(r"[,\s;]+", line.strip())
            if len(parts)>=2:
                try: puntos.append([float(parts[0].replace(",",".")), float(parts[1].replace(",","."))])
                except: continue

        if len(puntos)<3: await update.message.reply_text("No leí 3 puntos válidos. Formato: Este,Norte por línea"); return

        low = fname.lower()
        sis_origen = "origen_nacional"
        if "wgs84" in low or "4326" in low: sis_origen = "wgs84"
        elif "3115" in low or "oeste" in low: sis_origen = "oeste"
        elif "3116" in low or "bogota" in low: sis_origen = "bogota"

        csv_out = await asyncio.to_thread(topo.exportar_csv, puntos, sis_origen, "importado")
        kml_out = await asyncio.to_thread(topo.exportar_kml, puntos, sis_origen, "importado_"+sis_origen)
        dxf_out = await asyncio.to_thread(topo.exportar_dxf, puntos, sis_origen, "importado")

        await update.message.reply_text(f"Leí {len(puntos)} pts en {sis_origen} de {fname}. Generando CSV+KML+DXF:")
        await update.message.reply_document(document=io.BytesIO(csv_out.encode()), filename=f"convertido_{sis_origen}_a_wgs84.csv")
        await update.message.reply_document(document=io.BytesIO(kml_out.encode()), filename=f"convertido_{fname.split('.')[0]}.kml")
        await update.message.reply_document(document=io.BytesIO(dxf_out.encode()), filename=f"convertido_{fname.split('.')[0]}.dxf")
    except Exception as e:
        log.exception("doc"); await update.message.reply_text(f"Error archivo: {e}")

@solo_yo
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id; texto = update.message.text
    await context.bot.send_chat_action(chat_id, "typing")
    try:
        hechos = await asyncio.to_thread(memoria.buscar_hechos, texto)
        hist = await asyncio.to_thread(memoria.historial, chat_id, 8)
        mensajes = [{"role":"system","content":prompt_sistema(hechos)}] + hist + [{"role":"user","content":texto}]
        respuesta = await responder(mensajes)
    except groq.RateLimitError:
        await update.message.reply_text("Límite Groq, espera 1 min."); return
    except Exception:
        log.exception("responder"); await update.message.reply_text("Error con modelo, reintenta."); return
    respuesta = respuesta or "Sin respuesta."
    await asyncio.to_thread(memoria.guardar_mensaje, chat_id, "user", texto)
    await asyncio.to_thread(memoria.guardar_mensaje, chat_id, "assistant", respuesta)
    await asyncio.to_thread(memoria.recortar_historial, chat_id)
    for i in range(0, len(respuesta), 4000): await update.message.reply_text(respuesta[i:i+4000])

async def al_error(update, context: ContextTypes.DEFAULT_TYPE): log.error("Error no controlado", exc_info=context.error)

web = Flask(__name__)
@web.route("/")
def inicio(): return "GEOSAT V2.2 vivo", 200
def iniciar_web():
    puerto = int(os.getenv("PORT","10000"))
    threading.Thread(target=lambda: web.run(host="0.0.0.0", port=puerto), daemon=True).start()
    log.info("Keep-alive puerto %s", puerto)

def main():
    global memoria, cliente
    faltan = [n for n,v in (("BOT_TOKEN",BOT_TOKEN),("GROQ_API_KEY",GROQ_API_KEY)) if not v]
    if faltan: raise SystemExit(f"Faltan ENV: {', '.join(faltan)}")
    if ALLOWED_USER_ID==0: log.warning("ALLOWED_USER_ID no definido: solo /id responderá")
    memoria = Memoria(); cliente = AsyncGroq(api_key=GROQ_API_KEY); iniciar_web()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(CommandHandler(["start","ayuda"], cmd_start))
    app.add_handler(CommandHandler("sistemas", cmd_sistemas))
    app.add_handler(CommandHandler("corregir", cmd_corregir))
    app.add_handler(CommandHandler("clima", cmd_clima))
    app.add_handler(CommandHandler("grafica", cmd_grafica))
    app.add_handler(CommandHandler("recordar", cmd_recordar))
    app.add_handler(CommandHandler("memoria", cmd_memoria))
    app.add_handler(CommandHandler("olvidar", cmd_olvidar))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("exportar", cmd_exportar))
    app.add_handler(MessageHandler(filters.Document.ALL, doc_recibido))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    app.add_error_handler(al_error)
    log.info("GEOSAT V2.2 iniciado"); app.run_polling(drop_pending_updates=True)

if __name__=="__main__": main()
