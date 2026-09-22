# GEOSAT V905 - VISION REAL 2026 - FIX 4MB + MODELOS NUEVOS
import telebot, os, sqlite3, datetime, threading, time, requests, base64, io
from groq import Groq
from dotenv import load_dotenv
from flask import Flask
from PIL import Image

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

MODEL1 = "meta-llama/llama-4-maverick-17b-128e-instruct"
MODEL2 = "meta-llama/llama-4-scout-17b-16e-instruct"
MODEL_TEXT = "llama-3.3-70b-versatile"
print(f"V905 VISION {MODEL1}")

bot = telebot.TeleBot(TOKEN, threaded=False)
client = Groq(api_key=GROQ_KEY)
app = Flask(__name__)

con = sqlite3.connect("geosat_v800.db", check_same_thread=False, isolation_level=None)
cur = con.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS facts (user_id TEXT, fact TEXT, summary TEXT, created TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS cooldown (user_id TEXT PRIMARY KEY, last INTEGER)")
con.commit()

def compress_image(data):
    try:
        img = Image.open(io.BytesIO(data))
        img = img.convert("RGB")
        img.thumbnail((1024, 1024)) # baja a 1024 para quedar <4MB base64
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70, optimize=True)
        print(f"Comprimido {len(data)} -> {len(buf.getvalue())}")
        return buf.getvalue()
    except: return data

def ask_vision(uid, msg, b64):
    for model in [MODEL1, MODEL2]:
        try:
            print(f"Probando {model}")
            r = client.chat.completions.create(
                model=model,
                messages=[{"role":"user","content":[
                    {"type":"text","text":f"Lee TODO el texto de la imagen literal. Usuario pregunta: {msg}. Si es curso, da instructor, certificado, modalidad. Responde caleño."},
                    {"type":"image_url","image_url":{"url": f"data:image/jpeg;base64,{b64}"}}
                ]}],
                max_tokens=1200, temperature=0.2
            )
            return r.choices[0].message.content
        except Exception as e:
            print(f"Fallo {model}: {e}")
            last_e = e
            continue
    return f"Oelo ve, Groq está caído ahorita: {last_e}. Pero mándame el texto y te ayudo."

def ask_text(uid, msg):
    r=client.chat.completions.create(model=MODEL_TEXT, messages=[{"role":"system","content":"Eres Geosat caleño"},{"role":"user","content":msg}], max_tokens=800)
    return r.choices[0].message.content

@bot.message_handler(commands=['start'])
def s(m): bot.reply_to(m,"GEOSAT V905 LISTO - Ya leo fotos reales")

@bot.message_handler(content_types=['photo'])
def photo(m):
    try:
        file_id=m.photo[-1].file_id
        fi=bot.get_file(file_id)
        data=bot.download_file(fi.file_path)
        data=compress_image(data)
        b64=base64.b64encode(data).decode('utf-8')
        print(f"B64 len {len(b64)}")
        cap=m.caption or "Que dice ahi ve, leelo todo"
        resp=ask_vision(str(m.from_user.id), cap, b64)
        bot.reply_to(m, resp)
    except Exception as e:
        bot.reply_to(m, f"Error photo handler: {e}")

@bot.message_handler(func=lambda m: True)
def all_msg(m):
    bot.reply_to(m, ask_text(str(m.from_user.id), m.text))

@app.route('/')
def home(): return f"V905 LIVE {datetime.datetime.now()}"
def run_flask(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT",10000)))
def run_bot():
    while True:
        try: bot.infinity_polling(timeout=60, long_polling_timeout=60, skip_pending=True)
        except Exception as e: print(e); time.sleep(5)

if __name__=="__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    run_bot()
