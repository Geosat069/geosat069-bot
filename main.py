import os
import json
import datetime
import requests
from flask import Flask, request
import telebot
from telebot.types import Update
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io

# --- CONFIG ---
TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_ID = int(os.getenv("ALLOWED_USER_ID", "7732665137"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://geosat069-bot.onrender.com")
LAT = os.getenv("LAT", "3.4516")
LON = os.getenv("LON", "-76.5320")
WEATHER_KEY = os.getenv("OPENWEATHER_KEY", "")

bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)

MEMORY_FILE = "memoria.json"
if not os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, "w") as f:
        json.dump([], f)

# --- FUNCIONES ---
def es_autorizado(message):
    if message.from_user.id!= ALLOWED_ID:
        bot.reply_to(message, f"⛔ Acceso denegado. Tu ID: {message.from_user.id}")
        return False
    return True

def get_clima_texto():
    try:
        if not WEATHER_KEY:
            r = requests.get(f"https://wttr.in/{LAT},{LON}?format=j1", timeout=10)
            data = r.json()
            curr = data['current_condition'][0]
            return (
                f"🌤️ *Clima parcela*\n"
                f"📍 {LAT},{LON}\n"
                f"Temp: {curr['temp_C']}°C (siente {curr['FeelsLikeC']}°C)\n"
                f"Humedad: {curr['humidity']}%\n"
                f"Viento: {curr['windspeedKmph']} km/h\n"
                f"Cielo: {curr['weatherDesc'][0]['value']}"
            )
        else:
            url = f"https://api.openweathermap.org/data/2.5/weather?lat={LAT}&lon={LON}&appid={WEATHER_KEY}&units=metric&lang=es"
            r = requests.get(url, timeout=10).json()
            return (
                f"🌤️ *{r['name']}*: {r['weather'][0]['description']}\n"
                f"Temp: {r['main']['temp']}°C\n"
                f"Humedad: {r['main']['humidity']}%\n"
                f"Viento: {r['wind']['speed']} m/s"
            )
    except Exception as e:
        return f"Error clima: {e}"

def generar_grafica(valores=None):
    if valores is None:
        valores = [0.62, 0.65, 0.63, 0.68, 0.71, 0.69, 0.73]
    dias = [f"D-{i}" for i in range(len(valores),0,-1)]

    plt.figure(figsize=(6,4))
    plt.plot(dias, valores, marker='o', linewidth=2)
    plt.title("GEOSAT - NDVI últimos días")
    plt.ylabel("NDVI")
    plt.grid(True, alpha=0.3)
    plt.ylim(0,1)
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    plt.close()
    return buf

def cargar_memoria():
    try:
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def guardar_nota(texto):
    mem = cargar_memoria()
    fecha = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    entrada = f"[{fecha}] {texto}"
    mem.append(entrada)
    with open(MEMORY_FILE, "w") as f:
        json.dump(mem, f, indent=2, ensure_ascii=False)
    return entrada

# --- COMANDOS TELEGRAM ---
@bot.message_handler(commands=['id'])
def cmd_id(message):
    bot.reply_to(message, f"Tu ID: {message.from_user.id}")

@bot.message_handler(commands=['start','ayuda'])
def cmd_start(message):
    if not es_autorizado(message): return
    bot.reply_to(message,
        "🛰️ *GEOSAT V2 ONLINE*\n"
        "WEBHOOK Gratis - No se apaga\n\n"
        "/clima - Clima de tu parcela\n"
        "/grafica - Gráfica NDVI\n"
        "/grafica 0.5 0.6 0.8 - con tus datos\n"
        "/recordar texto - Guarda nota\n"
        "/memoria - Ver notas\n"
        "/olvidar - Borrar todo\n"
        "/id - Tu ID",
        parse_mode="Markdown")

@bot.message_handler(commands=['clima'])
def cmd_clima(message):
    if not es_autorizado(message): return
    bot.reply_to(message, get_clima_texto(), parse_mode="Markdown")

@bot.message_handler(commands=['grafica'])
def cmd_grafica(message):
    if not es_autorizado(message): return
    partes = message.text.split()
    vals = None
    if len(partes) > 1:
        try:
            vals = [float(x) for x in partes[1:]]
        except:
            pass
    buf = generar_grafica(vals)
    bot.send_photo(message.chat.id, buf, caption="📈 GEOSAT")

@bot.message_handler(commands=['recordar'])
def cmd_recordar(message):
    if not es_autorizado(message): return
    txt = message.text.replace('/recordar','').strip()
    if not txt:
        bot.reply_to(message, "Uso: /recordar riego lote 1 hoy")
        return
    entrada = guardar_nota(txt)
    bot.reply_to(message, f"✅ Guardado: {entrada}")

@bot.message_handler(commands=['memoria'])
def cmd_memoria(message):
    if not es_autorizado(message): return
    mem = cargar_memoria()
    if not mem:
        bot.reply_to(message, "Memoria vacía. Usa /recordar algo")
    else:
        ult = "\n".join([f"- {m}" for m in mem[-15:]])
        bot.reply_to(message, f"🧠 Últimas {len(mem)}:\n{ult}")

@bot.message_handler(commands=['olvidar'])
def cmd_olvidar(message):
    if not es_autorizado(message): return
    with open(MEMORY_FILE, "w") as f:
        json.dump([], f)
    bot.reply_to(message, "🗑️ Borrado")

@bot.message_handler(func=lambda m: True)
def default(message):
    if not es_autorizado(message): return
    bot.reply_to(message, f"Recibido: {message.text}\nGuardo? /recordar {message.text}")

# --- WEBHOOK ---
@app.route('/')
def index():
    return "GEOSAT V2 vivo", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_str = request.get_data().decode('utf-8')
        update = Update.de_json(json_str)
        bot.process_new_updates([update])
        return "ok", 200
    return "no", 403

def setup_webhook():
    try:
        bot.remove_webhook()
        bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
        print(f"Webhook -> {WEBHOOK_URL}/webhook")
    except Exception as e:
        print(f"Error webhook {e}")

setup_webhook()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
