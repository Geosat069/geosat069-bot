# GEOSAT V800 AUTO-HEALING - RENDER + TERMUX OK - FINAL DEFINITIVO CALEÑO
import telebot, os, sqlite3, datetime, threading, time, requests, re
from groq import Groq
from dotenv import load_dotenv
from flask import Flask, send_file
load_dotenv()

TOKEN=os.getenv("TELEGRAM_TOKEN")
GROQ_KEY=os.getenv("GROQ_API_KEY")

print("=== V800 AUTO-HEALING - DETECTANDO MODELOS VIVOS ===")

def get_live_models():
    try:
        r=requests.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {GROQ_KEY}"}, timeout=10).json()
        ids=[m['id'] for m in r['data']]
        print(f"Modelos vivos: {ids[:8]}")
        fast_candidates=["openai/gpt-oss-20b","llama-3.1-8b-instant","llama3-8b-8192","gemma2-9b-it","qwen/qwen3-32b"]
        smart_candidates=["openai/gpt-oss-120b","llama-3.3-70b-versatile","llama3-70b-8192","qwen/qwen3-32b","llama-3.1-70b-versatile"]
        fast=next((m for m in fast_candidates if m in ids), ids[0])
        smart=next((m for m in smart_candidates if m in ids), ids[0])
        return fast, smart
    except Exception as e:
        print(f"Fallback por error {e}")
        return "openai/gpt-oss-20b", "openai/gpt-oss-120b"

MODEL_FAST, MODEL_SMART = get_live_models()
print(f"USANDO FAST={MODEL_FAST} SMART={MODEL_SMART}")

SYSTEM_PROMPT = """
Eres GEOSAT V800, una IA nacida en Cali, Colombia. Sos caleño parcero.
Hablas con flow: usas 'oe', 've', 'parcero', 'vos', 'que mas pues'.
Sos inteligente, auto-healing, nunca te caes, pro 24/7.
Respondes corto, útil, con un toque de humor caleño. No eres formal.
Si te preguntan quien te hizo, di que fue Geosat069, el duro de Cali.
Guarda datos importantes del usuario para recordarlo.
"""

bot=telebot.TeleBot(TOKEN, threaded=False)
client=Groq(api_key=GROQ_KEY)

for i in range(2):
    try:
        bot.remove_webhook()
        requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=true", timeout=10)
        time.sleep(1)
    except: pass

con=sqlite3.connect("geosat_v800.db", check_same_thread=False, isolation_level=None)
cur=con.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS facts (user_id TEXT, fact TEXT, created TEXT)")
cur.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(fact, user_id)")
cur.execute("CREATE TABLE IF NOT EXISTS datos_oficiales (anio INTEGER PRIMARY KEY, temp REAL)")
con.commit()

if cur.execute("SELECT COUNT(*) FROM datos_oficiales").fetchone()[0]==0:
    cur.execute("INSERT INTO datos_oficiales VALUES (2024, 27.5)")
    con.commit()

def save_fact(user_id, text):
    now=str(datetime.datetime.now())
    cur.execute("INSERT INTO facts VALUES (?,?,?)",(user_id,text,now))
    cur.execute("INSERT INTO memory_fts VALUES (?,?)",(text,user_id))
    con.commit()

def get_memory(user_id):
    try:
        rows=cur.execute("SELECT fact FROM facts WHERE user_id=? ORDER BY rowid DESC LIMIT 5",(user_id,)).fetchall()
        return "\n".join([r[0] for r in rows])
    except: return ""

def ask_groq(user_id, msg):
    mem=get_memory(user_id)
    try:
        prompt = f"Memoria del usuario:\n{mem}\n\nMensaje actual: {msg}" if mem else msg
        comp=client.chat.completions.create(
            model=MODEL_SMART,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8,
            max_tokens=800
        )
        return comp.choices[0].message.content
    except Exception as e:
        print(f"Error SMART {e}, probando FAST")
        try:
            comp=client.chat.completions.create(
                model=MODEL_FAST,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": msg}
                ],
                temperature=0.8
            )
            return comp.choices[0].message.content
        except Exception as e2:
            return f"Oe parcero, me cai un momentico: {e2} - pero ya me auto-healeo ve"

@bot.message_handler(commands=['start','help'])
def start_cmd(m):
    bot.reply_to(m, "¡Oelo parcero! 🔥 Soy GEOSAT V800, ya estoy 24/7 en la nube sin depender de Termux. ¡Dime que más pues, en que te ayudo ve!")

@bot.message_handler(func=lambda m: True)
def all_msg(m):
    uid=str(m.from_user.id)
    text=m.text
    # Guardar si parece dato importante
    if len(text) > 15 and any(x in text.lower() for x in ["soy","me llamo","vivo en","me gusta","trabajo"]):
        save_fact(uid, text)
    bot.send_chat_action(m.chat.id, 'typing')
    resp=ask_groq(uid, text)
    bot.reply_to(m, resp)

# FLASK PARA RENDER
app=Flask(__name__)
@app.route('/')
def home():
    return f"GEOSAT V800 LIVE - FAST={MODEL_FAST} SMART={MODEL_SMART} - Up 24/7 - {datetime.datetime.now()}"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

def run_bot():
    while True:
        try:
            print("Bot polling iniciado...")
            bot.infinity_polling(timeout=60, long_polling_timeout=60, skip_pending=True)
        except Exception as e:
            print(f"Polling caido {e}, reiniciando en 5s")
            time.sleep(5)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    run_bot()
