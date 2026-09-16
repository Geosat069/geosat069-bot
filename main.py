import os, sys, threading, traceback, asyncio
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

print("--- ARRANCANDO SCRIPT ---", flush=True)
BOT_TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

print(f"BOT_TOKEN existe? {bool(BOT_TOKEN)}", flush=True)
print(f"GROQ existe? {bool(GROQ_API_KEY)}", flush=True)

client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

app = Flask(__name__)
@app.route('/')
def home():
    return "Geosat069 Bot VIVO!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    print(f"Web corriendo en puerto {port}", flush=True)
    app.run(host='0.0.0.0', port=port)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("¡Hola! Soy Geosat069 🛰️ ¿En qué te ayudo?")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not client:
            await update.message.reply_text("Me falta la API de GROQ")
            return
        completion = client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[
                {"role": "system", "content": "Eres Geosat069, útil y amigable. Responde en español, corto."},
                {"role": "user", "content": update.message.text}
            ]
        )
        await update.message.reply_text(completion.choices[0].message.content)
    except Exception as e:
        print(f"ERROR GROQ: {e}", flush=True)
        traceback.print_exc()
        await update.message.reply_text("Uy, me trabé. Intenta de nuevo")

def run_bot_polling():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    print("Bot iniciado... Haciendo polling FIX 20.7", flush=True)
    try:
        application = Application.builder().token(BOT_TOKEN).build()

        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        application.run_polling(drop_pending_updates=True)
    except Exception as e:
        print(f"ERROR FATAL BOT: {e}", flush=True)
        traceback.print_exc()

if __name__ == '__main__':
    threading.Thread(target=run_bot_polling, daemon=True).start()
    run_web()
