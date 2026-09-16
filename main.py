import os
import asyncio
import threading
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

# --- CONFIGURACIÓN ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

client = Groq(api_key=GROQ_API_KEY)

# --- SERVIDOR WEB PARA RENDER (Para que no se duerma) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Geosat069 Bot está VIVO!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- LÓGICA DEL BOT ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("¡Hola! Soy Geosat069 🛰️ ¿En qué te ayudo hoy?")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    print(f"Usuario: {user_message}")

    try:
        completion = client.chat.completions.create(
            model="openai/gpt-oss-20b", # Modelo nuevo que SI funciona
            messages=[
                {"role": "system", "content": "Eres Geosat069, un asistente útil, amigable y experto. Responde siempre en español, de forma clara y corta."},
                {"role": "user", "content": user_message}
            ],
            temperature=0.7,
            max_tokens=1024
        )
        respuesta = completion.choices[0].message.content
        await update.message.reply_text(respuesta)

    except Exception as e:
        print(f"ERROR GROQ: {e}") # Solo se ve en los logs de Render
        await update.message.reply_text("Uy, me trabé un segundo. ¿Me lo puedes preguntar de nuevo? 🙏")

async def run_bot():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot de Telegram iniciado...")
    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    # Mantener vivo
    while True:
        await asyncio.sleep(3600)

def start_bot_thread():
    asyncio.run(run_bot())

if __name__ == '__main__':
    # Inicia el bot en un hilo separado
    bot_thread = threading.Thread(target=start_bot_thread)
    bot_thread.daemon = True
    bot_thread.start()

    # Inicia el servidor web
    run_web()
