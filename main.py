import os, threading, traceback
from collections import defaultdict
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

BOT_TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# Memoria simple para que GEOSAT recuerde
chat_history = defaultdict(list)
MAX_HISTORY = 12

app = Flask(__name__)
@app.route('/')
def home(): return "Geosat069 VIVO 🛰️"
def run_web(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Soy Geosat069 🛰️ Tu asistente geoespacial. ¿En qué te ayudo?")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.strip()
        chat_id = update.message.chat_id

        if not client:
            await update.message.reply_text("Falta GROQ_API_KEY en Render")
            return

        history = chat_history[chat_id][-MAX_HISTORY:]
        messages = [
            {"role": "system", "content": "Eres Geosat069. Eres un asistente experto en satélites, teledetección, GIS, Sentinel, Landsat. Hablas español, directo, útil, cercano como de Cali. Recuerdas la conversación."}
        ] + history + [{"role": "user", "content": text}]

        completion = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=messages
        )
        reply = completion.choices[0].message.content

        chat_history[chat_id].append({"role": "user", "content": text})
        chat_history[chat_id].append({"role": "assistant", "content": reply})

        await update.message.reply_text(reply)

    except Exception as e:
        print(f"ERROR: {e}", flush=True)
        traceback.print_exc()
        await update.message.reply_text("Uy, me trabé. Intenta de nuevo")

def run_bot_polling():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    threading.Thread(target=run_web, daemon=True).start()
    run_bot_polling()
