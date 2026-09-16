import os, threading, traceback, requests
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

# --- Variables recientes ---
BOT_TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN") or os.environ.get("BOT")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY") or os.environ.get("GROQ_API") or os.environ.get("GROQ")

client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

app = Flask(__name__)
@app.route('/')
def home():
    return "Geosat069 Bot VIVO!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def geocode(nombre):
    try:
        if not nombre.strip(): return [-76.62, 3.32, -76.48, 3.55], "Cali"
        url = f"https://nominatim.openstreetmap.org/search?q={nombre}, Cali, Colombia&format=json&limit=1"
        r = requests.get(url, headers={"User-Agent":"Geosat069"}, timeout=10).json()
        if r:
            lon = float(r[0]['lon']); lat = float(r[0]['lat'])
            return [lon-0.05, lat-0.05, lon+0.05, lat+0.05], r[0]['display_name']
    except Exception as e:
        print(f"Geocode error: {e}")
    return [-76.62, 3.32, -76.48, 3.55], nombre.title() if nombre else "Cali"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("¡Hola! Soy Geosat069 🛰️ ¿Qué zona comparamos? Ej: Pance 2020 vs 2026")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    print(f"Usuario dice: {texto}")
    try:
        # Lógica para el vs de año que me pediste
        zona_limpia = texto.replace("2020","").replace("2026","").replace("vs","").replace("temperatura","").strip()[:40]
        bbox, nombre_zona = geocode(zona_limpia)

        prompt_vs = f"Eres GEOSAT JARVIS. Analiza LST para {nombre_zona} BBOX {bbox}. Compara 2020 ~30°C vs 2026 ~32°C Delta +2°C. Explica el cambio y da link a Copernicus. Pregunta del usuario: {texto}"

        completion = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {"role": "system", "content": "Eres Geosat069, útil, amigable y experto en análisis satelital térmico LST de Cali. Responde en español corto, técnico y caleño."},
                {"role": "user", "content": prompt_vs}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        await update.message.reply_text(completion.choices[0].message.content)

    except Exception as e:
        print(f"ERROR GROQ: {e}")
        traceback.print_exc()
        await update.message.reply_text("Uy, me trabé un segundo. Intenta de nuevo 🙏")

def run_bot_polling():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    threading.Thread(target=run_web, daemon=True).start()
    run_bot_polling()
