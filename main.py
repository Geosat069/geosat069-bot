import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from supabase import create_client
from groq import Groq

TOKEN = os.getenv("TELEGRAM_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GROQ_KEY = os.getenv("GROQ_API_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL else None
groq_client = Groq(api_key=GROQ_KEY) if GROQ_KEY else None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot Geosat069 activo ✅\nEnvíame un mensaje!")

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    if groq_client:
        resp = groq_client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[{"role":"user","content": user_text}]
        )
        answer = resp.choices[0].message.content
    else:
        answer = f"Recibí: {user_text}"
    await update.message.reply_text(answer)

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    print("Bot iniciado...")
    app.run_polling()

if __name__ == "__main__":
    main()
