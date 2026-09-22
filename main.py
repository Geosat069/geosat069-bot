# GEOSAT V902 DIOS - VISION FIX DEFINITIVO
import telebot, os, sqlite3, datetime, threading, time, requests, tempfile, base64
from groq import Groq
from dotenv import load_dotenv
from flask import Flask
import edge_tts, asyncio

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

def get_models():
    try:
        r = requests.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {GROQ_KEY}"}, timeout=10).json()
        ids = [m['id'] for m in r['data']]
        fast = next((m for m in ["openai/gpt-oss-20b","llama-3.1-8b-instant"] if m in ids), ids[0])
        smart = next((m for m in ["openai/gpt-oss-120b","llama-3.3-70b-versatile"] if m in ids), ids[0])
        vision = next((m for m in ["llama-3.2-90b-vision-preview","llama-3.2-11b-vision-preview","meta-llama/llama-4-scout-17b-16e-instruct"] if m in ids), smart)
        return fast, smart, vision
    except:
        return "openai/gpt-oss-20b","openai/gpt-oss-120b","llama-3.2-90b-vision-preview"

MODEL_FAST, MODEL_SMART, MODEL_VISION = get_models()
print(f"V902 {MODEL_FAST} / {MODEL_SMART} / {MODEL_VISION}")

SYSTEM_PROMPT = """Eres GEOSAT V902 DIOS, de Cali. Sos caleño 100%: decí "oelo ve", "parcero", "vos", "melo", "sisas". Si ves imagen, DESCRIBELA COMPLETA y LEE TODO EL TEXTO que veas. Si es aviso de trabajo, extrae fecha, lugar, requisitos. Corto, útil y potente."""

bot = telebot.TeleBot(TOKEN, threaded=False)
client = Groq(api_key=GROQ_KEY)
app = Flask(__name__)

con = sqlite3.connect("geosat_v800.db", check_same_thread=False, isolation_level=None)
cur = con.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS facts (user_id TEXT, fact TEXT, summary TEXT, created TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS settings (user_id TEXT PRIMARY KEY, voice INTEGER DEFAULT 0)")
cur.execute("CREATE TABLE IF NOT EXISTS cooldown (user_id TEXT PRIMARY KEY, last INTEGER)")
con.commit()

for _ in range(2):
    try:
        bot.remove_webhook()
        requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=true", timeout=10)
    except: pass

def get_clima_cali():
    try:
        r = requests.get("https://wttr.in/Cali+Colombia?format=j1", timeout=10).json()
        temp = r['current_condition'][0]['temp_C']
        desc = r['current_condition'][0]['weatherDesc'][0]['value']
        hum = r['current_condition'][0]['humidity']
        return f"Clima Cali: {temp}°C, {desc}, Humedad {hum}%"
    except: return "Cali 24-28°C, parcialmente nublado, tipico caleño"

def get_memory(uid):
    rows=cur.execute("SELECT summary FROM facts WHERE user_id=? ORDER BY rowid DESC LIMIT 10",(uid,)).fetchall()
    return "\n".join([f"- {r[0]}" for r in rows])

def save_fact(uid, text):
    try:
        s=client.chat.completions.create(model=MODEL_FAST, messages=[{"role":"system","content":"Resume en 1 frase."},{"role":"user","content":text}], max_tokens=50).choices[0].message.content
    except: s=text[:80]
    cur.execute("INSERT INTO facts VALUES (?,?,?,?)",(uid,text,s,str(datetime.datetime.now()))); con.commit()

def is_voice_on(uid):
    r=cur.execute("SELECT voice FROM settings WHERE user_id=?",(uid,)).fetchone()
    return r and r[0]==1

def set_voice(uid,on):
    cur.execute("INSERT OR REPLACE INTO settings VALUES (?,?)",(uid,1 if on else 0)); con.commit()

def check_spam(uid):
    now=int(time.time()); last=cur.execute("SELECT last FROM cooldown WHERE user_id=?",(uid,)).fetchone()
    if last and now-last[0]<2: return True
    cur.execute("INSERT OR REPLACE INTO cooldown VALUES (?,?)",(uid,now)); con.commit(); return False

def ask_groq(uid, msg, b64_image=None):
    mem=get_memory(uid)
    extra=""
    if "clima" in msg.lower() and "cali" in msg.lower():
        extra = get_clima_cali()
    ctx=f"MEMORIA:{mem}\nDATO EXTRA:{extra}\nMENSAJE:{msg}"
    messages=[{"role":"system","content":SYSTEM_PROMPT}]
    model=MODEL_SMART
    if b64_image:
        messages.append({"role":"user","content":[{"type":"text","text":ctx},{"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64_image}"}}]})
        model=MODEL_VISION
    else:
        messages.append({"role":"user","content":ctx})
    try:
        c=client.chat.completions.create(model=model, messages=messages, temperature=0.7, max_tokens=900)
        return c.choices[0].message.content
    except Exception as e:
        print(f"Vision fallo {e}, usando fast")
        c=client.chat.completions.create(model=MODEL_FAST, messages=[{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":msg}], max_tokens=700)
        return c.choices[0].message.content

async def tts_col(text, path): await edge_tts.Communicate(text, "es-CO-SalomeNeural").save(path)

def send_voice(chat_id, text):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as f: path=f.name
        asyncio.run(tts_col(text, path))
        with open(path,'rb') as a: bot.send_voice(chat_id, a)
        os.unlink(path)
    except: bot.send_message(chat_id, text)

@bot.message_handler(commands=['start','voz','memoria','clima'])
def cmds(m):
    uid=str(m.from_user.id)
    if m.text.startswith('/start'): bot.reply_to(m, "GEOSAT V902 DIOS ACTIVO 🔥\nYa VEO fotos 100% y CLIMA REAL.\n/voz /memoria /clima")
    elif m.text.startswith('/voz'):
        nv=not is_voice_on(uid); set_voice(uid,nv); bot.reply_to(m, "Voz caleña ON" if nv else "OFF")
    elif m.text.startswith('/memoria'): bot.reply_to(m, get_memory(uid) or "Nada guardado")
    elif m.text.startswith('/clima'): bot.reply_to(m, ask_groq(uid, f"Dame clima de Cali caleño con esto: {get_clima_cali()}"))

@bot.message_handler(content_types=['photo'])
def handle_photo(m):
    uid=str(m.from_user.id)
    if check_spam(uid): return
    bot.send_chat_action(m.chat.id,'typing')
    try:
        file_id = m.photo[-1].file_id
        fi=bot.get_file(file_id)
        data=bot.download_file(fi.file_path)
        b64 = base64.b64encode(data).decode('utf-8')
        cap=m.caption or "Que ves en esta imagen? Describe detallado, lee todo el texto si hay."
        resp=ask_groq(uid, cap, b64_image=b64)
        bot.reply_to(m, resp)
        if is_voice_on(uid): send_voice(m.chat.id, resp)
    except Exception as e:
        print(f"Error photo: {e}")
        bot.reply_to(m, f"Error vision: {e}")

@bot.message_handler(content_types=['voice'])
def handle_voice(m):
    uid=str(m.from_user.id)
    if check_spam(uid): return
    try:
        fi=bot.get_file(m.voice.file_id); data=bot.download_file(fi.file_path)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.ogg') as f: f.write(data); fn=f.name
        with open(fn,"rb") as af: tr=client.audio.transcriptions.create(model="whisper-large-v3", file=af, language="es").text
        os.unlink(fn)
        if len(tr)>3: save_fact(uid,tr)
        resp=ask_groq(uid,tr)
        bot.send_message(m.chat.id, resp) if not is_voice_on(uid) else send_voice(m.chat.id, resp)
    except Exception as e: bot.reply_to(m, f"Audio fail: {e}")

@bot.message_handler(func=lambda m: True)
def all_msg(m):
    uid=str(m.from_user.id)
    if check_spam(uid): return
    t=m.text
    if any(k in t.lower() for k in ["me llamo","soy ","vivo en","mi nombre","me gusta"]): save_fact(uid,t)
    bot.send_chat_action(m.chat.id,'typing')
    resp=ask_groq(uid,t)
    bot.reply_to(m, resp) if not is_voice_on(uid) else send_voice(m.chat.id, resp)

@app.route('/')
def home(): return f"V902 LIVE {datetime.datetime.now()}"
def run_flask(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT",10000)))
def run_bot():
    while True:
        try: bot.infinity_polling(timeout=60, long_polling_timeout=60, skip_pending=True)
        except Exception as e: print(e); time.sleep(5)

if __name__=="__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    run_bot()
