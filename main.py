# GEOSAT V1004 AUTO - FOTO LEE SOLA - AUTO DISCOVERY VISION
import telebot
import os
import sqlite3
import datetime
import threading
import time
import base64
import io
from groq import Groq
from dotenv import load_dotenv
from flask import Flask
from PIL import Image

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

bot = telebot.TeleBot(TOKEN, threaded=False)
client = Groq(api_key=GROQ_KEY)
app = Flask(__name__)

con = sqlite3.connect("geosat.db", check_same_thread=False, isolation_level=None)
cur = con.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT)")
con.commit()

def get_model():
    r = cur.execute("SELECT value FROM cache WHERE key='v'").fetchone()
    return r[0] if r else None

def save_model(m):
    cur.execute("INSERT OR REPLACE INTO cache VALUES (?,?)", ('v', m))
    con.commit()
    print(f"Modelo bueno guardado: {m}")

def get_vision_models():
    try:
        models_list = client.models.list()
        ids = [m.id for m in models_list.data]
        print(f"Modelos disponibles en Groq: {ids}")
        priority = [
            "meta-llama/llama-4-maverick-17b-128e-instruct",
            "meta-llama/llama-4-scout-17b-16e-instruct",
            "qwen/qwen3-32b",
            "qwen/qwen3-27b"
        ]
        alive = [p for p in priority if p in ids]
        if alive:
            return alive
        return priority
    except Exception as e:
        print(f"Error listando modelos: {e}")
        return [
            "meta-llama/llama-4-maverick-17b-128e-instruct",
            "meta-llama/llama-4-scout-17b-16e-instruct",
            "qwen/qwen3-32b"
        ]

def compress_image(data, max_size=1024):
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((max_size, max_size))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=75, optimize=True)
    return buf.getvalue()

def leer_foto_automatico(b64, caption=""):
    cached = get_model()
    modelos = get_vision_models()
    if cached and cached in modelos:
        modelos = [cached] + [m for m in modelos if m!= cached]
    elif cached:
        modelos = [cached] + modelos

    prompt_text = f"Lee literalmente todo el texto de la imagen. Transcribe completo sin resumir. Si hay numeros de contacto, extraelos. Contexto adicional del usuario: {caption}"

    last_error = ""
    for model in modelos:
        try:
            print(f"Probando vision: {model}")
            response = client.chat.completions.create(
                model=model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                    ]
                }],
                max_tokens=1500,
                temperature=0.1
            )
            save_model(model)
            return response.choices[0].message.content
        except Exception as e:
            last_error = str(e)
            print(f"FAIL {model}: {last_error}")
            continue

    return f"Fallo vision. Ultimo error: {last_error}. Modelos probados: {modelos}. Revisa tu GROQ_API_KEY en Render."

def responder_texto(msg):
    for model in ["openai/gpt-oss-20b", "openai/gpt-oss-120b", "llama-3.3-70b-versatile"]:
        try:
            r = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": msg}],
                max_tokens=1000,
                temperature=0.3
            )
            return r.choices[0].message.content
        except:
            continue
    return "Error en texto, revisa GROQ key."

@bot.message_handler(commands=['start'])
def start(m):
    bot.reply_to(m, "GEOSAT V1004 AUTO LIVE. Manda una foto y la leo automaticamente buscando el modelo de vision activo.")

@bot.message_handler(content_types=['photo'])
def handle_photo(m):
    try:
        bot.send_chat_action(m.chat.id, 'typing')
        file_info = bot.get_file(m.photo[-1].file_id)
        data = bot.download_file(file_info.file_path)
        data = compress_image(data)
        b64 = base64.b64encode(data).decode()
        caption = m.caption or ""
        resultado = leer_foto_automatico(b64, caption)
        bot.reply_to(m, resultado)
    except Exception as e:
        bot.reply_to(m, f"Error procesando foto: {e}")

@bot.message_handler(func=lambda m: True)
def handle_text(m):
    bot.reply_to(m, responder_texto(m.text))

@app.route('/')
def health():
    return f"V1004 AUTO LIVE - Modelo cache: {get_model()} - {datetime.datetime.now()}"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

def run_bot():
    while True:
        try:
            bot.infinity_polling(timeout=90, long_polling_timeout=90, skip_pending=True)
        except Exception as e:
            print(f"Bot error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    run_bot()
