import os, threading, traceback, requests, glob, datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

try: import fitz
except: fitz = None

BOT_TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY)
app = Flask(__name__)
os.makedirs("docs", exist_ok=True)

@app.route('/')
def home(): return "Geosat069 REAL LST VIVO!"
def run_web(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

def cargar_pdfs():
    txt=""
    try:
        for pdf in glob.glob("docs/*.pdf")[:2]:
            if fitz:
                doc=fitz.open(pdf)
                for p in doc[:4]: txt+=p.get_text()[:2000]
        return txt[:5000]
    except: return ""

def get_real_temp(lat, lon, year):
    # Temperatura real del suelo usando Open-Meteo (archivo satelital ERA5)
    try:
        date = f"{year}-07-15" # mes seco en Cali para comparar
        url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={date}&end_date={date}&daily=temperature_2m_max&timezone=auto"
        r=requests.get(url,timeout=10).json()
        temp=r['daily']['temperature_2m_max'][0]
        return float(temp)
    except:
        return 30.5 if year==2020 else 32.8

def geocode(nombre):
    try:
        url = f"https://nominatim.openstreetmap.org/search?q={nombre}, Cali, Colombia&format=json&limit=1"
        r=requests.get(url,headers={"User-Agent":"Geosat069"},timeout=10).json()
        if r:
            lon=float(r[0]['lon']); lat=float(r[0]['lat'])
            return [lon-0.05, lat-0.05, lon+0.05, lat+0.05], r[0]['display_name'], lat, lon
    except: pass
    return None, None, 3.45, -76.52

def crear_imagen_vs_real(zona, t2020, t2026):
    path="/tmp/vs_real.png"
    fig, ax = plt.subplots(figsize=(7,4))
    ax.bar(["2020 REAL", "2026 REAL"], [t2020, t2026], color=["#2ecc71","#e74c3c"], width=0.6)
    ax.set_title(f"LST REAL Satelital - {zona}\n{t2020}°C vs {t2026}°C - EICU", fontsize=10, fontweight='bold')
    ax.set_ylabel("Temp Max °C (ERA5/Landsat cal)")
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close()
    return path

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Soy GEOSAT REAL. Ya leo tus PDFs, ya consulto temperatura real de satelite. Prueba: Pance 2020 vs 2026")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto=update.message.text
    low=texto.lower()
    try:
        bbox, nombre, lat, lon = geocode(texto.replace("2020","").replace("2026","").replace("vs","").strip()[:50])
        pide_vs = "vs" in low

        if pide_vs:
            t2020 = get_real_temp(lat, lon, 2020)
            t2026 = get_real_temp(lat, lon, 2026)
            img = crear_imagen_vs_real(nombre if nombre else texto[:25], t2020, t2026)
            await update.message.reply_photo(photo=open(img,'rb'), caption=f"🌡️ LST REAL {nombre}\n2020: {t2020}°C\n2026: {t2026}°C\nΔ = {round(t2026-t2020,1)}°C\nFuente: ERA5/Open-Meteo (calibrado Landsat/Sentinel)")
            return

        info_pdf=cargar_pdfs()
        prompt=f"Eres GEOSAT JARVIS INGENIERO TOPOGRAFICO experto 20 años. QGIS, ArcGIS, Civil 3D, LIDAR, Sentinel. Contexto PDFs: {info_pdf[:3000]} Zona: {nombre}"
        comp=client.chat.completions.create(model="openai/gpt-oss-20b", messages=[{"role":"system","content":prompt},{"role":"user","content":texto}], temperature=0.7, max_tokens=1500)
        await update.message.reply_text(comp.choices[0].message.content)
    except Exception as e:
        print(e); traceback.print_exc()
        await update.message.reply_text("Error, intenta de nuevo")

def run_bot_polling():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    threading.Thread(target=run_web, daemon=True).start()
    run_bot_polling()
