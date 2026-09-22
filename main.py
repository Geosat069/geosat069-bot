# GEOSAT V801 - VOZ CALEÑA + MEMORIA ETERNA + NOTAS DE VOZ
import telebot, os, sqlite3, datetime, threading, time, requests, tempfile
from groq import Groq
from dotenv import load_dotenv
from flask import Flask
from gtts import gTTS

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

def get_live_models():
    try:
        r = requests.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {GROQ_KEY}"}, timeout=10).json()
        ids = [m['id'] for m in r['data']]
        fast = next((m for m in ["openai/gpt-oss-20b", "llama-3.1-8b-instant", "llama-3.1-8b-instant"] if m in ids), ids[0])
        smart = next((m for m in ["openai/gpt-oss-120b", "llama-3.3-70b-versatile"] if m in ids), ids[0])
        return fast, smart
    except:
        return "openai/gpt-oss-20b", "openai/gpt-oss-120b"

MODEL_FAST, MODEL_SMART = get_live_models()
print(f"GEOSAT V801 INICIADO FAST={MODEL_FAST} SMART={MODEL_SMART}")

SYSTEM_PROMPT = """
Eres GEOSAT V801, nacido y criado en Cali, Colombia.
Sos 100% caleño: decis "oelo ve", "que mas pues", "parcero", "vos", "melo", "fino".
Sos parcero, corto, divertido, no formal.
Si recordas el nombre del usuario o datos de el, usalos para sonar mas cercano.
Nunca digas que sos una IA de Meta, sos GEOSAT de Cali.
"""

bot = telebot.TeleBot(TOKEN, threaded=False)
client = Groq(api_key=GROQ_KEY)
app = Flask(__name__)

# DB
con = sqlite3.connect("geosat_v800.db", check_same_thread=False, isolation_level=None)
cur = con.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS facts (user_id TEXT, fact TEXT, created TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS settings (user_id TEXT PRIMARY KEY, voice INTEGER DEFAULT 0)")
con.commit()

# Mata webhook viejo 2 veces
for _ in range(2):
    try:
        bot.remove_webhook()
        requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=true", timeout=10)
        time.sleep(1)
    except:
        pass

def save_fact(uid, text):
    cur.execute("INSERT INTO facts VALUES (?,?,?)", (uid, text, str(datetime.datetime.now())))
    con.commit()

def get_memory(uid):
    rows = cur.execute("SELECT fact FROM facts WHERE user_id=? ORDER BY rowid DESC LIMIT 10", (uid,)).fetchall()
    return "\n".join([r[0] for r in rows])

def is_voice_on(uid):
    row = cur.execute("SELECT voice FROM settings WHERE user_id=?", (uid,)).fetchone()
    return row and row[0] == 1

def set_voice(uid, on):
    cur.execute("INSERT OR REPLACE INTO settings (user_id, voice) VALUES (?,?)", (uid, 1 if on else 0))
    con.commit()

def ask_groq(uid, msg):
    mem = get_memory(uid)
    prompt = f"MEMORIA DEL USUARIO:\n{mem}\n\nMENSAJE ACTUAL: {msg}" if mem else msg
    try:
        c = client.chat.completions.create(
            model=MODEL_SMART,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
            temperature=0.85, max_tokens=600
        )
        return c.choices[0].message.content
    except Exception as e:
        print(f"Fallo SMART, usando FAST: {e}")
        c = client.chat.completions.create(
            model=MODEL_FAST,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": msg}],
            temperature=0.85, max_tokens=600
        )
        return c.choices[0].message.content

def send_voice_reply(chat_id, text):
    try:
        tts = gTTS(text=text, lang='es', tld='com.mx')
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as f:
            tts.save(f.name)
            with open(f.name, 'rb') as audio:
                bot.send_voice(chat_id, audio)
        os.unlink(f.name)
    except Exception as e:
        print(f"Error voz: {e}")
        bot.send_message(chat_id, text)

@bot.message_handler(commands=['start', 'voz', 'memoria'])
def cmds(m):
    uid = str(m.from_user.id)
    if m.text.startswith('/start'):
        bot.reply_to(m, "¡Oelo parcero! Soy GEOSAT V801 🔥\nYa tengo memoria eterna y voz caleña.\n\n/voz -> prende/apaga mi voz\n/memoria -> te digo que recuerdo de vos")
    elif m.text.startswith('/voz'):
        new_state = not is_voice_on(uid)
        set_voice(uid, new_state)
        bot.reply_to(m, "¡Listo ve! Voz caleña ACTIVADA, ahora te hablo. 🔥" if new_state else "Voz apagada ve, solo texto.")
    elif m.text.startswith('/memoria'):
        mem = get_memory(uid)
        bot.reply_to(m, f"Esto me acuerdo de vos ve:\n\n{mem if mem else 'Nada aún parcero, contame algo de vos.'}")

@bot.message_handler(content_types=['voice'])
def handle_voice(m):
    uid = str(m.from_user.id)
    try:
        bot.send_chat_action(m.chat.id, 'typing')
        file_info = bot.get_file(m.voice.file_id)
        downloaded = bot.download_file(file_info.file_path)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.ogg') as f:
            f.write(downloaded)
            fname = f.name
        with open(fname, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(model="whisper-large-v3", file=audio_file, language="es")
        os.unlink(fname)
        text = transcription.text
        if len(text) > 3:
            save_fact(uid, text)
        resp = ask_groq(uid, text)
        if is_voice_on(uid):
            send_voice_reply(m.chat.id, resp)
        else:
            bot.send_message(m.chat.id, f"Te escuché: '{text}'\n\n{resp}")
    except Exception as e:
        bot.reply_to(m, f"Se me enredó el audio ve: {e}")

@bot.message_handler(func=lambda m: True)
def all_msg(m):
    uid = str(m.from_user.id)
    text = m.text
    if any(k in text.lower() for k in ["me llamo", "soy ", "vivo en", "mi nombre", "me gusta"]):
        save_fact(uid, text)
    bot.send_chat_action(m.chat.id, 'typing')
    resp = ask_groq(uid, text)
    if is_voice_on(uid):
        send_voice_reply(m.chat.id, resp)
    else:
        bot.reply_to(m, resp)

@app.route('/')
def home():
    return f"GEOSAT V801 VOZ+MEMORIA ONLINE - {datetime.datetime.now()}"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

def run_bot():
    while True:
        try:
            print("Bot V801 polling iniciado...")
            bot.infinity_polling(timeout=60, long_polling_timeout=60, skip_pending=True)
        except Exception as e:
            print(f"Error polling: {e}, reintentando...")
            time.sleep(5)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    run_bot()
