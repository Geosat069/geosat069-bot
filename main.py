import os, requests, threading, time
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_KEY) if GROQ_KEY else None

app_flask = Flask(__name__)
@app_flask.route('/')
def home(): return "GEOSAT LIVE"

def geocode(n):
    try:
        r = requests.get(f"https://nominatim.openstreetmap.org/search?q={n}, Cali, Colombia&format=json&limit=1", headers={"User-Agent":"Geosat"}, timeout=10).json()
        if r: return [float(r[0]['lon'])-0.05, float(r[0]['lat'])-0.05, float(r[0]['lon'])+0.05, float(r[0]['lat'])+0.05], r[0]['display_name']
    except: pass
    return [-76.62, 3.32, -76.48, 3.55], "Cali"

async def start(update, context):
    await update.message.reply_text("🛰️ GEOSAT JARVIS LIVE. Pregúntame: Ej `Pance 2020 vs 2026`")

async def handle(update, context):
    try:
        texto = update.message.text
        bbox, nombre = geocode(texto.replace("temperatura","").replace("2020","").replace("2026","").replace("vs","")[:20])

        prompt = f"Eres GEOSAT JARVIS. Zona {nombre} BBOX {bbox}. Da análisis LST 2020 ~30C vs 2026 ~32C +2C. Da link Copernicus Browser y código GEE para esa BBOX. Usuario preguntó: {texto}"

        if client:
            resp = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role":"user","content":prompt}])
            out = resp.choices[0].message.content
        else:
            out = f"Zona {nombre} BBOX {bbox}\n2020: 30°C\n2026: 32°C\nDelta +2°C\nCopernicus: https://browser.dataspace.copernicus.eu/"

        await update.message.reply_text(out[:4000])
    except Exception as e:
        print(e)
        await update.message.reply_text("Uy me trabé 1 seg, intenta de nuevo con una zona: Ej `Aguablanca`")

def run_bot():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.run_polling()

def run_flask():
    app_flask.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))

if __name__=="__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    run_bot()
