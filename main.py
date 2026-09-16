import os, re, threading, traceback
from collections import defaultdict
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

BOT_TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# MEMORIA por chat
chat_history = defaultdict(list)
MAX_HISTORY = 10

app = Flask(__name__)
@app.route('/')
def home():
    return "Geosat069 Bot VIVO! 🛰️"

def run_web():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

# Detectar coordenadas tipo 3.4516,-76.5320
COORD_REGEX = r"^-?\d{1,3}\.\d+,\s*-?\d{1,3}\.\d+$"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "¡Hola! Soy Geosat069 🛰️\n\n"
        "1. Pregúntame de satélites: Sentinel, Landsat, órbitas\n"
        "2. Mándame coordenadas ej: 3.4516,-76.5320 y te doy el mapa\n"
        "3. Recuerdo lo que hablamos\n\n"
        "Comandos: /start /ayuda /mapa 3.4516,-76.5320"
    )

async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Mándame coordenadas o pregúntame: ¿qué hace Sentinel-2? ¿qué es una órbita LEO?")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.strip()
        chat_id = update.message.chat_id

        # 2. HERRAMIENTA: si son coordenadas
        if re.match(COORD_REGEX, text):
            lat, lon = text.split(',')
            map_link = f"https://www.google.com/maps?q={lat.strip()},{lon.strip()}"
            await update.message.reply_text(f"📍 Coordenadas recibidas: {text}\n🗺️ Mapa: {map_link}\n\nDime, ¿qué quieres saber de esta zona?")
            # guardamos también en memoria
            chat_history[chat_id].append({"role": "user", "content": f"Coordenadas: {text}"})
            return

        # 1 y 3. INFO + MEMORIA
        if not client:
            await update.message.reply_text("Me falta GROQ_API_KEY")
            return

        # armar historial
        history = chat_history[chat_id][-MAX_HISTORY:]
        messages = [
            {"role": "system", "content": "Eres Geosat069, experto en satélites, teledetección, Sentinel, Landsat, GIS. Responde corto, útil, en español. Si te dan coordenadas, analízalas. Recuerdas la charla."}
        ] + history + [{"role": "user", "content": text}]

        completion = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=messages
        )
        reply = completion.choices[0].message.content

        # guardar en memoria
        chat_history[chat_id].append({"role": "user", "content": text})
        chat_history[chat_id].append({"role": "assistant", "content": reply})
        if len(chat_history[chat_id]) > MAX_HISTORY:
            chat_history[chat_id] = chat_history[chat_id][-MAX_HISTORY:]

        await update.message.reply_text(reply)

    except Exception as e:
        print(f"ERROR: {e}", flush=True)
        traceback.print_exc()
        await update.message.reply_text("Uy, me trabé un segundo, intenta de nuevo 🛰️")

def run_bot_polling():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ayuda", ayuda))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    threading.Thread(target=run_web, daemon=True).start()
    run_bot_polling()
