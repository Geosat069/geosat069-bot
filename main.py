# GEOSAT V907 - QWEN VISION - UNICO MODELO ACTIVO GROQ 2026
import telebot, os, sqlite3, datetime, threading, time, base64, io
from groq import Groq
from dotenv import load_dotenv
from flask import Flask
from PIL import Image

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

MODEL_VISION = "qwen/qwen3.8-27b"
MODEL_TEXT = "openai/gpt-oss-20b"
print(f"V907 VISION {MODEL_VISION}")

bot = telebot.TeleBot(TOKEN, threaded=False)
client = Groq(api_key=GROQ_KEY)
app = Flask(__name__)

con = sqlite3.connect("geosat_v800.db", check_same_thread=False, isolation_level=None)
cur = con.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS facts (user_id TEXT, fact TEXT, summary TEXT, created TEXT)")
con.commit()

def compress(data):
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((1024, 1024))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=75, optimize=True)
    return buf.getvalue()

def ask_vision(msg, b64):
    try:
        print(f"Probando {MODEL_VISION} len={len(b64)}")
        r = client.chat.completions.create(
            model=MODEL_VISION,
            messages=[{"role":"user","content":[
                {"type":"text","text": f"Lee TODO el texto literal de esta imagen. Es un curso. Usuario pregunta: {msg}. Dame: nombre del curso, instructor, certificado, modalidad, empresa. Responde caleño."},
                {"type":"image_url","image_url":{"url": f"data:image/jpeg;base64,{b64}"}}
            ]}],
            max_tokens=1200, temperature=0.2
        )
        return r.choices[0].message.content
    except Exception as e:
        print(f"FAIL QWEN: {e}")
        return f"Oelo ve, Groq falló: {e}"

def ask_text(msg):
    r=client.chat.completions.create(model=MODEL_TEXT, messages=[{"role":"user","content":msg}], max_tokens=800)
    return r.choices[0].message.content

@bot.message_handler(commands=['start'])
def s(m): bot.reply_to(m,"GEOSAT V907 LIVE - Qwen vision activo - manda foto ya")

@bot.message_handler(content_types=['photo'])
def photo(m):
    try:
        fi=bot.get_file(m.photo[-1].file_id)
        data=bot.download_file(fi.file_path)
        data=compress(data)
        b64=base64.b64encode(data).decode()
        cap=m.caption or "Que dice ahi ve?"
        resp=ask_vision(cap, b64)
        bot.reply_to(m, resp)
    except Exception as e:
        bot.reply_to(m, f"Error handler: {e}")

@bot.message_handler(func=lambda m: True)
def all_msg(m): bot.reply_to(m, ask_text(m.text))

@app.route('/')
def h(): return f"V907 LIVE {MODEL_VISION} {datetime.datetime.now()}"
def run_flask(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT",10000)))
def run_bot():
    while True:
        try: bot.infinity_polling(timeout=60, long_polling_timeout=60, skip_pending=True)
        except Exception as e: print(e); time.sleep(5)

if __name__=="__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    run_bot()
