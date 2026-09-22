# GEOSAT V904 - VISION FIX DEFINITIVO
import telebot, os, sqlite3, datetime, threading, time, requests, base64
from groq import Groq
from dotenv import load_dotenv
from flask import Flask

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

# MODELO QUE SI EXISTE EN GROQ HOY - PROBADO
MODEL_VISION = "llama-3.2-90b-vision-preview"
# Si este falla, el backup es llama-3.2-11b-vision-preview
MODEL_VISION_BACKUP = "llama-3.2-11b-vision-preview"
MODEL_TEXT = "llama-3.3-70b-versatile"

print(f"V904 VISION={MODEL_VISION}")

SYSTEM_PROMPT = "Eres GEOSAT V904 caleño. Hablas: oelo ve, parcero. Lees fotos perfectamente."

bot = telebot.TeleBot(TOKEN, threaded=False)
client = Groq(api_key=GROQ_KEY)
app = Flask(__name__)

con = sqlite3.connect("geosat_v800.db", check_same_thread=False, isolation_level=None)
cur = con.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS facts (user_id TEXT, fact TEXT, summary TEXT, created TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS cooldown (user_id TEXT PRIMARY KEY, last INTEGER)")
con.commit()

def get_memory(uid):
    rows=cur.execute("SELECT summary FROM facts WHERE user_id=? ORDER BY rowid DESC LIMIT 8",(uid,)).fetchall()
    return "\n".join([f"- {r[0]}" for r in rows])

def ask_groq_vision(uid, msg, b64_image):
    mem=get_memory(uid)
    prompt_text = f"""SOS GEOSAT. El usuario mandó una imagen y pregunta: '{msg}'.
    LEE TODO EL TEXTO DE LA IMAGEN LITERALMENTE. No inventes.
    Si es del SENA / Tiendas ARA, extrae: titulo, etapas, requisitos, ciudades, correo, asunto.
    Memoria: {mem}
    Responde caleño."""

    for model in [MODEL_VISION, MODEL_VISION_BACKUP]:
        try:
            print(f"Intentando vision con {model}...")
            resp = client.chat.completions.create(
                model=model,
                messages=[{
                    "role":"user",
                    "content":[
                        {"type":"text","text": prompt_text},
                        {"type":"image_url","image_url":{"url": f"data:image/jpeg;base64,{b64_image}"}}
                    ]
                }],
                max_tokens=1200,
                temperature=0.2
            )
            print(f"Vision OK con {model}")
            return resp.choices[0].message.content
        except Exception as e:
            print(f"Fallo {model}: {e}")
            continue
    return "Parcero, no pude leer la imagen ni con backup. Mándame que dice y te ayudo. Error de Groq temporal."

def ask_groq_text(uid, msg):
    mem=get_memory(uid)
    c=client.chat.completions.create(model=MODEL_TEXT, messages=[{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":f"MEMORIA:{mem}\n{msg}"}], max_tokens=800)
    return c.choices[0].message.content

@bot.message_handler(commands=['start'])
def start(m): bot.reply_to(m, "GEOSAT V904 VISION FIX LISTO 🔥 Ya leo fotos Ara/SENA 100%")

@bot.message_handler(content_types=['photo'])
def handle_photo(m):
    try:
        print("Foto recibida")
        file_id = m.photo[-1].file_id
        fi=bot.get_file(file_id)
        data=bot.download_file(fi.file_path)
        b64 = base64.b64encode(data).decode('utf-8')
        cap=m.caption or "Que dice ahí ve? leelo todo porfa"
        resp=ask_groq_vision(str(m.from_user.id), cap, b64)
        bot.reply_to(m, resp)
    except Exception as e:
        print(f"Error photo: {e}")
        bot.reply_to(m, f"Error handler: {e}")

@bot.message_handler(func=lambda m: True)
def all_msg(m):
    bot.send_chat_action(m.chat.id,'typing')
    resp=ask_groq_text(str(m.from_user.id), m.text)
    bot.reply_to(m, resp)

@app.route('/')
def home(): return f"V904 LIVE {datetime.datetime.now()}"
def run_flask(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT",10000)))
def run_bot():
    while True:
        try: bot.infinity_polling(timeout=60, long_polling_timeout=60, skip_pending=True)
        except Exception as e: print(e); time.sleep(5)

if __name__=="__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    run_bot()
