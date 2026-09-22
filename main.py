# GEOSAT V900 DIOS - VISION + GOOGLE + VOZ COLOMBIANA
import telebot, os, sqlite3, datetime, threading, time, requests, tempfile
from groq import Groq
from dotenv import load_dotenv
from flask import Flask
import edge_tts, asyncio
from duckduckgo_search import DDGS

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

def get_models():
    try:
        r = requests.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {GROQ_KEY}"}, timeout=10).json()
        ids = [m['id'] for m in r['data']]
        fast = next((m for m in ["openai/gpt-oss-20b","llama-3.1-8b-instant"] if m in ids), ids[0])
        smart = next((m for m in ["openai/gpt-oss-120b","llama-3.3-70b-versatile"] if m in ids), ids[0])
        vision = next((m for m in ["llama-3.2-90b-vision-preview","llama-3.2-11b-vision-preview"] if m in ids), smart)
        return fast, smart, vision
    except:
        return "openai/gpt-oss-20b","openai/gpt-oss-120b","llama-3.2-90b-vision-preview"

MODEL_FAST, MODEL_SMART, MODEL_VISION = get_models()
print(f"V900 DIOS {MODEL_FAST} / {MODEL_SMART} / {MODEL_VISION}")

SYSTEM_PROMPT = """Eres GEOSAT V900 DIOS, de Cali, Colombia. 100% caleño: "oelo ve", "parcero", "vos", "melo". Sos la IA mas avanzada, si tenes info web USALA. Si tenes memoria usala. Corto, potente, caleño. Nunca digas que sos de Meta."""

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

def search_web(q):
    try:
        with DDGS() as ddgs:
            res = list(ddgs.text(q, max_results=4))
        return "\n".join([f"- {r['title']}: {r['body'][:180]}" for r in res]) if res else ""
    except: return ""

def need_search(t):
    keys=["que paso","quien gano","clima","hoy","noticia","precio","dolar","america","cali","quien es","donde"]
    return any(k in t.lower() for k in keys)

def save_fact(uid, text):
    try:
        s=client.chat.completions.create(model=MODEL_FAST, messages=[{"role":"system","content":"Resume en 1 frase clave."},{"role":"user","content":text}], max_tokens=50).choices[0].message.content
    except: s=text[:80]
    cur.execute("INSERT INTO facts VALUES (?,?,?,?)",(uid,text,s,str(datetime.datetime.now()))); con.commit()

def get_memory(uid):
    rows=cur.execute("SELECT summary FROM facts WHERE user_id=? ORDER BY rowid DESC LIMIT 12",(uid,)).fetchall()
    return "\n".join([f"- {r[0]}" for r in rows])

def is_voice_on(uid):
    r=cur.execute("SELECT voice FROM settings WHERE user_id=?",(uid,)).fetchone()
    return r and r[0]==1
def set_voice(uid,on): cur.execute("INSERT OR REPLACE INTO settings VALUES (?,?)",(uid,1 if on else 0)); con.commit()

def check_spam(uid):
    now=int(time.time())
    last=cur.execute("SELECT last FROM cooldown WHERE user_id=?",(uid,)).fetchone()
    if last and now-last[0]<2: return True
    cur.execute("INSERT OR REPLACE INTO cooldown VALUES (?,?)",(uid,now)); con.commit()
    return False

def ask_groq(uid, msg, image_url=None, has_search=False):
    mem=get_memory(uid)
    web=search_web(msg) if has_search else ""
    ctx=f"MEMORIA:\n{mem}\n\nWEB:\n{web}\n\nMENSAJE:{msg}"
    messages=[{"role":"system","content":SYSTEM_PROMPT}]
    model=MODEL_SMART
    if image_url:
        messages.append({"role":"user","content":[{"type":"text","text":ctx},{"type":"image_url","image_url":{"url":image_url}}]})
        model=MODEL_VISION
    else:
        messages.append({"role":"user","content":ctx})
    try:
        c=client.chat.completions.create(model=model, messages=messages, temperature=0.8, max_tokens=700)
        return c.choices[0].message.content
    except Exception as e:
        print(e)
        c=client.chat.completions.create(model=MODEL_FAST, messages=[{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":msg}], max_tokens=600)
        return c.choices[0].message.content

async def tts_col(text, path):
    await edge_tts.Communicate(text, "es-CO-SalomeNeural").save(path)

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
    if m.text.startswith('/start'): bot.reply_to(m, "¡OELO! Soy GEOSAT V900 DIOS 🔥\nVeo fotos, busco en Google y hablo caleña.\n/voz /memoria /clima")
    elif m.text.startswith('/voz'):
        nv=not is_voice_on(uid); set_voice(uid,nv)
        bot.reply_to(m, "Voz caleña activada ve!" if nv else "Voz apagada.")
    elif m.text.startswith('/memoria'): bot.reply_to(m, f"Recuerdo:\n{get_memory(uid) or 'Nada aun.'}")
    elif m.text.startswith('/clima'):
        info=search_web("clima Cali hoy")
        bot.reply_to(m, ask_groq(uid, f"Clima Cali con esto: {info}", has_search=False))

@bot.message_handler(content_types=['photo'])
def handle_photo(m):
    uid=str(m.from_user.id)
    if check_spam(uid): return
    bot.send_chat_action(m.chat.id,'typing')
    fi=bot.get_file(m.file_id)
    url=f"https://api.telegram.org/file/bot{TOKEN}/{fi.file_path}"
    cap=m.caption or "Que ves en esta imagen?"
    resp=ask_groq(uid, cap, image_url=url)
    bot.reply_to(m, resp)
    if is_voice_on(uid): send_voice(m.chat.id, resp)

@bot.message_handler(content_types=['voice'])
def handle_voice(m):
    uid=str(m.from_user.id)
    if check_spam(uid): return
    try:
        fi=bot.get_file(m.voice.file_id)
        data=bot.download_file(fi.file_path)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.ogg') as f: f.write(data); fn=f.name
        with open(fn,"rb") as af: tr=client.audio.transcriptions.create(model="whisper-large-v3", file=af, language="es").text
        os.unlink(fn)
        if len(tr)>3: save_fact(uid,tr)
        resp=ask_groq(uid,tr,has_search=need_search(tr))
        bot.send_message(m.chat.id, resp) if not is_voice_on(uid) else send_voice(m.chat.id, resp)
    except Exception as e: bot.reply_to(m, f"Audio fail: {e}")

@bot.message_handler(func=lambda m: True)
def all_msg(m):
    uid=str(m.from_user.id)
    if check_spam(uid): return
    t=m.text
    if any(k in t.lower() for k in ["me llamo","soy ","vivo en","mi nombre","me gusta"]): save_fact(uid,t)
    bot.send_chat_action(m.chat.id,'typing')
    resp=ask_groq(uid,t,has_search=need_search(t))
    bot.reply_to(m, resp) if not is_voice_on(uid) else send_voice(m.chat.id, resp)

@app.route('/')
def home(): return f"V900 DIOS ONLINE {datetime.datetime.now()}"

def run_flask(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT",10000)))
def run_bot():
    while True:
        try: bot.infinity_polling(timeout=60, long_polling_timeout=60, skip_pending=True)
        except Exception as e: print(e); time.sleep(5)

if __name__=="__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    run_bot()
