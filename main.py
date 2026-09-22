# GEOSAT V903 FIX VISION REAL
import telebot, os, sqlite3, datetime, threading, time, requests, tempfile, base64
from groq import Groq
from dotenv import load_dotenv
from flask import Flask
import edge_tts, asyncio

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")
MODEL_VISION = "meta-llama/llama-4-scout-17b-16e-instruct"
MODEL_TEXT = "llama-3.3-70b-versatile"
MODEL_FAST = "llama-3.1-8b-instant"

print(f"V903 VISION={MODEL_VISION}")

SYSTEM_PROMPT = """Eres GEOSAT V903 de Cali. Hablas caleño: oelo ve, parcero, vos. Cuando te manden imagen, TENES QUE LEER TODO EL TEXTO que ves en la imagen, no digas nunca que no ves imagen. Si es un curso, di nombre del curso, instructor, certificado."""

bot = telebot.TeleBot(TOKEN, threaded=False)
client = Groq(api_key=GROQ_KEY)
app = Flask(__name__)

con = sqlite3.connect("geosat_v800.db", check_same_thread=False, isolation_level=None)
cur = con.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS facts (user_id TEXT, fact TEXT, summary TEXT, created TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS settings (user_id TEXT PRIMARY KEY, voice INTEGER DEFAULT 0)")
cur.execute("CREATE TABLE IF NOT EXISTS cooldown (user_id TEXT PRIMARY KEY, last INTEGER)")
con.commit()

def get_clima_cali():
    try:
        r = requests.get("https://wttr.in/Cali+Colombia?format=j1", timeout=10).json()
        return f"Cali {r['current_condition'][0]['temp_C']}°C {r['current_condition'][0]['weatherDesc'][0]['value']}"
    except: return "Cali 26°C soleado"

def get_memory(uid):
    rows=cur.execute("SELECT summary FROM facts WHERE user_id=? ORDER BY rowid DESC LIMIT 8",(uid,)).fetchall()
    return "\n".join([f"- {r[0]}" for r in rows])

def check_spam(uid):
    now=int(time.time()); last=cur.execute("SELECT last FROM cooldown WHERE user_id=?",(uid,)).fetchone()
    if last and now-last[0]<1: return True
    cur.execute("INSERT OR REPLACE INTO cooldown VALUES (?,?)",(uid,now)); con.commit(); return False

def ask_groq(uid, msg, b64_image=None):
    mem=get_memory(uid)
    if b64_image:
        try:
            print("Enviando imagen a Groq vision...")
            resp = client.chat.completions.create(
                model=MODEL_VISION,
                messages=[{"role":"user","content":[
                    {"type":"text","text":f"Lee todo el texto de esta imagen. Usuario dice: {msg}. Memoria: {mem}"},
                    {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64_image}"}}
                ]}],
                max_tokens=1000, temperature=0.2
            )
            return resp.choices[0].message.content
        except Exception as e:
            print(f"Fallo vision {e}")
            return f"Parcero, Groq vision falló: {e}. Pero dime que dice la foto y te ayudo. (Error técnico visión)"
    else:
        c=client.chat.completions.create(model=MODEL_TEXT, messages=[{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":f"MEMORIA:{mem}\n{msg}"}], max_tokens=800)
        return c.choices[0].message.content

async def tts_col(text, path): await edge_tts.Communicate(text, "es-CO-SalomeNeural").save(path)

@bot.message_handler(commands=['start','voz','memoria','clima'])
def cmds(m):
    if m.text.startswith('/start'): bot.reply_to(m, "GEOSAT V903 VISION REAL ACTIVO 🔥\nYa leo fotos 100%. Mandame la de Geologia de nuevo.")

@bot.message_handler(content_types=['photo'])
def handle_photo(m):
    uid=str(m.from_user.id)
    if check_spam(uid): return
    bot.send_chat_action(m.chat.id,'typing')
    try:
        print(f"Foto recibida de {uid}")
        file_id = m.photo[-1].file_id
        fi=bot.get_file(file_id)
        data=bot.download_file(fi.file_path)
        print(f"Foto descargada {len(data)} bytes")
        b64 = base64.b64encode(data).decode('utf-8')
        cap=m.caption or "Que dice aqui ve? lee todo"
        resp=ask_groq(uid, cap, b64_image=b64)
        bot.reply_to(m, resp)
    except Exception as e:
        print(f"Error photo handler: {e}")
        bot.reply_to(m, f"Error real: {e}")

@bot.message_handler(func=lambda m: True)
def all_msg(m):
    uid=str(m.from_user.id)
    if check_spam(uid): return
    bot.send_chat_action(m.chat.id,'typing')
    resp=ask_groq(uid, m.text)
    bot.reply_to(m, resp)

@app.route('/')
def home(): return f"V903 LIVE {datetime.datetime.now()}"
def run_flask(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT",10000)))
def run_bot():
    while True:
        try: bot.infinity_polling(timeout=60, long_polling_timeout=60, skip_pending=True)
        except Exception as e: print(e); time.sleep(5)

if __name__=="__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    run_bot()
