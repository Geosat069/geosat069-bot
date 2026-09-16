import os
import threading
import asyncio
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

BOT_TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

app = Flask(__name__)
@app.route('/')
def home():
    return "Geosat069 Bot VIVO!"

def run_web():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("¡Hola! Soy Geosat069 🛰️ ¿En qué te ayudo?")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        completion = client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[
                {"role": "system", "content": "Eres Geosat069, útil y amigable. Responde en español, corto."},
                {"role": "user", "content": update.message.text}
            ]
        )
        await update.message.reply_text(completion.choices[0].message.content)
    except Exception as e:
        print(f"ERROR GROQ: {e}")
        await update.message.reply_text("Uy, me trabé. Intenta de nuevo")

async def run_bot_async():
    print("Iniciando Bot...")
    token = BOT_TOKEN.strip() if BOT_TOKEN else None
    print(f"Token largo: {len(token) if token else 0}")
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Bot iniciado... Haciendo polling")
    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    await application.updater.idle()

def run_bot_polling():
    try:
        asyncio.run(run_bot_async())
    except Exception as e:
        import traceback
        print(f"ERROR FATAL: {e}")
        traceback.print_exc()

if __name__ == '__main__':
    threading.Thread(target=run_bot_polling, daemon=True).start()
    run_web()
