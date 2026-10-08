import os, json, datetime, requests, base64
from flask import Flask, request
import telebot
from telebot.types import Update
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io

# --- TUS ENVIRONMENT EXACTOS DE LA FOTO ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODELO = os.getenv("MODELO")
DATABASE_URL = os.getenv("DATABASE_URL")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", "7732665137"))

LAT = os.getenv("LAT", "3.4516")
LON = os.getenv("LON", "-76.5320")

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)

MEMORY_FILE = "memoria.json"
if not os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, "w") as f:
        json.dump([], f)
os.makedirs("fotos", exist_ok=True)

def ask_groq(prompt):
    if not GROQ_API_KEY:
        return "❌ Falta GROQ_API_KEY en Render"
    if not MODELO:
        return "❌ Falta MODELO en Render"
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": MODELO,
            "messages": [
                {"role": "system", "content": "Eres GEOSAT, ingeniero agrónomo experto en cultivos tropicales de Colombia. Responde corto, práctico, en español."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 800
        }
        r = requests.post(url, headers=headers, json=payload, timeout=25)
        data = r.json()
        if "choices" not in data:
            return f"Error Groq: {data}"
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Error: {e}"

def ask_gemini_vision(image_path):
    if not GEMINI_API_KEY:
        return "Foto guardada, pero necesitas GEMINI_API_KEY para analizar."
    try:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [
                {"text": "Eres agronomo. Diagnostica esta hoja, enfermedad y tratamiento corto en español."},
                {"inline_data": {"mime_type": "image/jpeg", "data": b64}}
            ]}]
        }
        r = requests.post(url, json=payload, timeout=30)
        j = r.json()
        return j["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return f"Error vision: {e}"

def get_clima():
    try:
        r = requests.get(f"https://wttr.in/{LAT},{LON}?format=j1", timeout=10).json()
        c = r["current_condition"][0]
        return f"🌤️ {c['temp_C']}°C Hum:{c['humidity']}% {c['weatherDesc'][0]['value']}"
    except:
        return "Clima no disponible"

def es_autorizado(m):
    if m.from_user.id!= ALLOWED_USER_ID:
        bot.reply_to(m, f"⛔ No autorizado. Tu ID: {m.from_user.id}")
        return False
    return True

# --- COMANDOS ---
@bot.message_handler(commands=['id'])
def cmd_id(m):
    bot.reply_to(m, f"ID tuyo: {m.from_user.id}\nPermitido: {ALLOWED_USER_ID}\nMODELO: {MODELO}\nGROQ: {'OK' if GROQ_API_KEY else 'FALTA'}\nGEMINI: {'OK' if GEMINI_API_KEY else 'FALTA'}\nWEBHOOK: {WEBHOOK_URL}")

@bot.message_handler(commands=['start','ayuda'])
def cmd_start(m):
    if not es_autorizado(m): return
    bot.reply_to(m,
        f"🛰️ *GEOSAT FINAL*\nModelo: `{MODELO}`\nGROQ: {'✅' if GROQ_API_KEY else '❌'} GEMINI: {'✅' if GEMINI_API_KEY else '❌'}\n\n"
        "/ia <pregunta>\n/consejo\n/clima\n/pronostico\n/grafica\n/recordar texto\n/memoria\nEnvía foto de hoja",
        parse_mode="Markdown")

@bot.message_handler(commands=['clima'])
def cmd_clima(m):
    if not es_autorizado(m): return
    bot.reply_to(m, get_clima())

@bot.message_handler(commands=['pronostico'])
def cmd_pron(m):
    if not es_autorizado(m): return
    try:
        r = requests.get(f"https://wttr.in/{LAT},{LON}?format=j1", timeout=10).json()
        txt = "📅 Pronóstico 3 días:\n"
        for d in r['weather']:
            txt += f"{d['date']}: {d['mintempC']}/{d['maxtempC']}°C lluvia {d['hourly'][4]['chanceofrain']}%\n"
        bot.reply_to(m, txt)
    except Exception as e:
        bot.reply_to(m, f"Error: {e}")

@bot.message_handler(commands=['ia'])
def cmd_ia(m):
    if not es_autorizado(m): return
    q = m.text.replace('/ia','').strip()
    if not q:
        bot.reply_to(m, "Escribe: /ia como controlo trips?")
        return
    bot.send_chat_action(m.chat.id, 'typing')
    bot.reply_to(m, f"🤖 {ask_groq(q)}")

@bot.message_handler(commands=['consejo'])
def cmd_consejo(m):
    if not es_autorizado(m): return
    bot.send_chat_action(m.chat.id, 'typing')
    clima = get_clima()
    try:
        mem = json.load(open(MEMORY_FILE))[-8:]
        mem_txt = "\n".join(mem)
    except:
        mem_txt = "Sin notas"
    bot.reply_to(m, f"{clima}\n\n{ask_groq(f'Clima {clima}. Notas: {mem_txt}. Dame 3 consejos practicos para hoy en parcela tropical.')}" )

@bot.message_handler(commands=['grafica'])
def cmd_graf(m):
    if not es_autorizado(m): return
    vals = [0.62,0.65,0.63,0.68,0.71,0.69,0.73]
    plt.figure(figsize=(6,4))
    plt.plot(vals, marker='o')
    plt.title(f"NDVI - {MODELO}")
    plt.grid(True, alpha=0.3)
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    plt.close()
    bot.send_photo(m.chat.id, buf, caption=f"📈 {MODELO}")

@bot.message_handler(commands=['recordar'])
def cmd_rec(m):
    if not es_autorizado(m): return
    txt = m.text.replace('/recordar','').strip()
    if not txt: return
    fecha = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    mem = json.load(open(MEMORY_FILE)) if os.path.exists(MEMORY_FILE) else []
    mem.append(f"[{fecha}] {txt}")
    json.dump(mem, open(MEMORY_FILE,"w"), indent=2, ensure_ascii=False)
    bot.reply_to(m, f"✅ Guardado: {txt}")

@bot.message_handler(commands=['memoria'])
def cmd_mem(m):
    if not es_autorizado(m): return
    mem = json.load(open(MEMORY_FILE)) if os.path.exists(MEMORY_FILE) else []
    bot.reply_to(m, "\n".join(mem[-15:]) if mem else "Vacía")

@bot.message_handler(content_types=['photo'])
def handle_foto(m):
    if not es_autorizado(m): return
    try:
        info = bot.get_file(m.photo[-1].file_id)
        data = bot.download_file(info.file_path)
        path = f"fotos/{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        with open(path, "wb") as f:
            f.write(data)
        bot.reply_to(m, "📸 Analizando hoja...")
        bot.send_chat_action(m.chat.id, 'typing')
        bot.reply_to(m, f"🔬 {ask_gemini_vision(path)}")
    except Exception as e:
        bot.reply_to(m, f"Error foto: {e}")

@bot.message_handler(func=lambda m: True)
def default(m):
    if not es_autorizado(m): return
    bot.send_chat_action(m.chat.id, 'typing')
    bot.reply_to(m, ask_groq(m.text))

@app.route('/')
def index():
    return f"GEOSAT OK - {MODELO} - GROQ {'OK' if GROQ_API_KEY else 'FALTA'} - GEMINI {'OK' if GEMINI_API_KEY else 'FALTA'}", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_data().decode('utf-8'))
    bot.process_new_updates([update])
    return "ok", 200

def setup_webhook():
    try:
        bot.remove_webhook()
        bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
        print(f"Webhook {WEBHOOK_URL}/webhook")
    except Exception as e:
        print(e)

setup_webhook()
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
