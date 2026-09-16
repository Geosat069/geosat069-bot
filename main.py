import os
import threading
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

# --- CONFIGURACIÓN ---
BOT_TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

print(f"BOT_TOKEN existe? {bool(BOT_TOKEN)}")
print(f"GROQ_KEY existe? {bool(GROQ_API_KEY)}")

if GROQ_API_KEY:
    client = Groq(api_key=GROQ_API_KEY)
else:
    client = None
    print("ERROR: GROQ_API_KEY no está en Render!")

# --- WEB PARA RENDER ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Geosat069 Bot está VIVO!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- BOT ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("¡Hola! Soy Geosat069 🛰️ ¿En qué te ayudo hoy?")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    print(f"Usuario dice: {user_message}")

    if not client:
        await update.message.reply_text("Me falta la clave de Groq en Render 😅")
        return

    try:
        completion = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {"role": "system", "content": "Eres Geosat069, útil y amigable. Si te preguntan clima en tiempo real di que no tienes internet en vivo. Responde siempre en español, corto."},
                {"role": "user", "content": user_message}
            ],
            temperature=0.7,
            max_tokens=800
        )
        respuesta = completion.choices[0].message.content
        await update.message.reply_text(respuesta)
    except Exception as e:
        print(f"ERROR GROQ: {e}")
        await update.message.reply_text("Uy, me trabé un segundo. Intenta de nuevo 🙏")

def run_bot_polling():
    try:
        print("Iniciando Bot de Telegram...")
        token = BOT_TOKEN.strip() if BOT_TOKEN else None
        print(f"Token largo: {len(token) if token else 0}")
        application = Application.builder().token(token).build()
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        print("Bot de Telegram iniciado... Haciendo polling")
        application.run_polling(drop_pending_updates=True)
    except Exception as e:
        import traceback
        print(f"ERROR FATAL BOT: {e}")
        traceback.print_exc()

if __name__ == '__main__':
    # Hilo del bot
    bot_thread = threading.Thread(target=run_bot_polling)
    bot_thread.daemon = True
    bot_thread.start()

    # Web
    run_web()
