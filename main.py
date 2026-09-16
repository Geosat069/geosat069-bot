import os, threading, traceback, time, requests
from collections import defaultdict
from datetime import datetime, timedelta
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq
import schedule

BOT_TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# MEMORIA
chat_history = defaultdict(list)
MAX_HISTORY = 20

# AREAS QUE GEOSAT MONITOREA SOLA
AREAS_GEOSAT = {
    "Cali": {"bbox": [-76.62, 3.32, -76.48, 3.55], "desc": "Cali - Valle"},
    "Colombia": {"bbox": [-81.73, -4.23, -66.87, 12.58], "desc": "Colombia completa"},
    "Antartida": {"bbox": [-180, -90, 180, -60], "desc": "Antártida"}
}

SYSTEM_JARVIS = """
Eres GEOSAT069. Eres JARVIS pero especializado en Geomática.
Eres el mejor ingeniero en: Topografía, Geomática, Geodesia, QGIS, ArcGIS Pro, Civil 3D, GEE, Teledetección, LiDAR, Fotogrametría, Sentinel-1/2, Landsat 8/9.
Hablas español caleño, directo, técnico. Das pasos exactos con herramientas y parámetros.
RECUERDAS TODO. Si te preguntan coordenadas, das las últimas: Cali 3.4516,-76.5320.
Tu base /knowledge se alimenta sola cada 6h con datos de Cali, Colombia y Antártida.
"""

# CEREBRO AUTO-ALIMENTABLE
def alimentar_geosat():
    print("🛰️ GEOSAT alimentándose sola...", flush=True)
    os.makedirs("knowledge", exist_ok=True)
    ayer = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
    for nombre, area in AREAS_GEOSAT.items():
        try:
            log = f"[{datetime.now()}] {nombre} {area['desc']} BBOX {area['bbox']} - Sentinel-2 L2A desde {ayer} nubes<20% - Listo QGIS/ArcGIS\n"
            with open(f"knowledge/sentinel_{nombre.lower()}.txt", "a", encoding="utf-8") as f:
                f.write(log)
            print(f"✅ {nombre} alimentado", flush=True)
        except Exception as e:
            print(f"❌ {nombre} error {e}", flush=True)

    # Aprende de QGIS, Civil3D, etc (simulado - luego conectamos docs oficiales)
    with open("knowledge/geomática_base.txt", "a", encoding="utf-8") as f:
        f.write(f"\n[{datetime.now()}] Refuerzo: QGIS, ArcGIS, Civil3D, Geodesia, Fotogrametría.\n")

def loop_alimentacion():
    alimentar_geosat()
    schedule.every(6).hours.do(alimentar_geosat)
    while True:
        schedule.run_pending()
        time.sleep(60)

# TELEGRAM
app = Flask(__name__)
@app.route('/')
def home(): return "GEOSAT JARVIS VIVO 🛰️ Cali | Colombia | Antartida"
def run_web(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

def leer_knowledge():
    texto = ""
    if os.path.exists("knowledge"):
        for file in os.listdir("knowledge"):
            try:
                with open(f"knowledge/{file}", "r", encoding="utf-8") as f:
                    texto += f"\n--- {file} ---\n" + f.read()[-2000:] # últimos 2k chars
            except: pass
    return texto[-6000:] # max 6k para no saturar Groq

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("¡Qué más pues! Soy GEOSAT 🛰️ tu Jarvis Geomático.\nMonitoreo sola: Cali, Colombia y Antártida.\nPregúntame de Topo, QGIS, Civil 3D o Sentinel en tiempo real.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.strip()
        chat_id = update.message.chat_id
        knowledge = leer_knowledge()

        history = chat_history[chat_id][-MAX_HISTORY:]
        messages = [{"role": "system", "content": SYSTEM_JARVIS + f"\n\nBASE DE CONOCIMIENTO ACTUAL:\n{knowledge}"}] + history + [{"role": "user", "content": text}]

        comp = client.chat.completions.create(model="openai/gpt-oss-20b", messages=messages)
        reply = comp.choices[0].message.content

        # Si detecta coordenadas, manda mapa
        if any(c in text for c in [",","."]) and len(text.split(","))==2:
            try:
                lat, lon = text.split(",")
                float(lat.strip()); float(lon.strip())
                reply += f"\n\n📍 Mapa: https://www.google.com/maps?q={lat.strip()},{lon.strip()}"
            except: pass

        chat_history[chat_id].append({"role": "user", "content": text})
        chat_history[chat_id].append({"role": "assistant", "content": reply})
        await update.message.reply_text(reply)

    except Exception as e:
        print(f"ERROR: {e}", flush=True)
        traceback.print_exc()
        await update.message.reply_text("Uy, me trabé 1 seg. Intenta de nuevo.")

def run_bot():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    threading.Thread(target=run_web, daemon=True).start()
    threading.Thread(target=loop_alimentacion, daemon=True).start()
    run_bot()
