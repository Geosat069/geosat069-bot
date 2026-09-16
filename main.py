import threading
import os
from flask import Flask

# --- Servidor web falso para que Render no te cierre el bot (GRATIS) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot Geosat069 activo 24/7"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web, daemon=True).start()
# --- Fin del truco ---

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from supabase import create_client
from groq import Groq

TOKEN = os.getenv("TELEGRAM_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GROQ_KEY = os.getenv("GROQ_API_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
groq_client = Groq(api_key=GROQ_KEY) if GROQ_KEY else None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("¡Hola! Soy Geosat069 bot, activo 24/7 ✅")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    try:
        # Guardar en Supabase (opcional)
        # supabase.table("mensajes").insert({"usuario": str(update.effective_user.id), "texto": user_text}).execute()

        if groq_client:
            completion = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": user_text}]
            )
            respuesta = completion.choices[0].message.content
        else:
            respuesta = f"Recibí: {user_text}"

        await update.message.reply_text(respuesta)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Bot iniciado...")
    application.run_polling()

if __name__ == "__main__":
    main()
