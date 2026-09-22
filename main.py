# GEOSAT V1007 - FIX DEFINITIVO - LEE SOLO SIN APT-GET - RENDER FREE OK
import telebot
import os
import threading
import time
import datetime
import requests
import io
from flask import Flask
from PIL import Image
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

bot = telebot.TeleBot(TOKEN, threaded=False)
client = Groq(api_key=GROQ_KEY)
app = Flask(__name__)

def ocr_space(image_bytes):
    try:
        r = requests.post(
            "https://api.ocr.space/parse/image",
            files={"file": ("img.jpg", image_bytes)},
            data={"language": "spa", "isOverlayRequired": False, "OCREngine": 2},
            timeout=40
        )
        j = r.json()
        if not j.get("IsErroredOnProcessing"):
            txt = j["ParsedResults"][0]["ParsedText"]
            if len(txt.strip()) > 10:
                return txt.strip()
    except Exception as e:
        print(f"OCR error: {e}")
    return None

def organizar(texto_ocr):
    prompt = f"Organiza este texto extraido de una imagen de un curso. Extrae todo literal. Texto OCR: {texto_ocr}"
    for model in ["openai/gpt-oss-20b", "llama-3.1-8b-instant", "llama-3.3-70b-versatile"]:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1200,
                temperature=0.1
            )
            return resp.choices[0].message.content
        except:
            continue
    return texto_ocr

@bot.message_handler(commands=['start'])
def cmd_start(m):
    bot.reply_to(m, "GEOSAT V1007 LIVE. Manda foto y la leo automatico.")

@bot.message_handler(content_types=['photo'])
def handle_photo(m):
    try:
        bot.send_chat_action(m.chat.id, 'typing')
        f = bot.get_file(m.photo[-1].file_id)
        data = bot.download_file(f.file_path)
        texto = ocr_space(data)
        if not texto:
            bot.reply_to(m, "No pude leer texto nitido. Reenvia la foto sin filtros y con buena luz.")
            return
        final = organizar(texto)
        bot.reply_to(m, final)
    except Exception as e:
        bot.reply_to(m, f"Error foto: {e}")

@bot.message_handler(func=lambda m: True)
def handle_text(m):
    try:
        r = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[{"role": "user", "content": m.text}],
            max_tokens=800
        )
        bot.reply_to(m, r.choices[0].message.content)
    except Exception as e:
        bot.reply_to(m, f"Error: {e}")

@app.route('/')
def health():
    return f"V1007 OK {datetime.datetime.now()}"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

def run_bot():
    while True:
        try:
            bot.infinity_polling(timeout=90, long_polling_timeout=90, skip_pending=True)
        except Exception as e:
            print(e)
            time.sleep(5)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    run_bot()
