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
# Opcionales para clima: pon tu lat/lon de tu parcela en Render Environment
LAT = os.getenv("LAT", "-3.45")
LON = os.getenv("LON", "-76.30")
WEATHER_KEY = os.getenv("OPENWEATHER_KEY", "")

bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)

MEMORY_FILE = "memoria.json"
if not os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, "w") as f:
        json.dump([], f)

def es_autorizado(message):
    if message.from_user.id!= ALLOWED_ID:
        bot.reply_to(message, f"Acceso denegado. Tu ID: {message.from_user.id}")
        return False
    return True

# --- COMANDOS ---
@bot.message_handler(commands=['id'])
def cmd_id(message):
    bot.reply_to(message, f"Tu ID de Telegram es: {message.from_user.id}")

@bot.message_handler(commands=['start', 'ayuda'])
def cmd_start(message):
    if not es_autorizado(message): return
    bot.reply_to(message,
        "🛰️ *GEOSAT en línea*\n\n"
        "/clima - Clima de hoy en tu parcela\n"
        "/grafica - Gráfica NDVI / humedad últimos 7 días\n"
        "/memoria - Guarda nota: /memoria riego hoy\n"
        "/id - Ver tu ID\n"
        "/ayuda - Este menú\n\n"
        "Modo: WEBHOOK Gratis - No se apaga",
        parse_mode="Markdown")

@bot.message_handler(commands=['clima'])
def cmd_clima(message):
    if not es_autorizado(message): return
    try:
        if not WEATHER_KEY:
            # Fallback sin API key - usa wttr.in gratis
            r = requests.get(f"https://wttr.in/{LAT},{LON}?format=j1", timeout=10)
            data = r.json()
            curr = data['current_condition'][0]
            bot.reply_to(message, f"🌤️ Clima ahora ({LAT},{LON}):\nTemp: {curr['temp_C']}°C\nHumedad: {curr['humidity']}%\nViento: {curr['windspeedKmph']} km/h\nDesc: {curr['weatherDesc'][0]['value']}")
        else:
            url = f"https://api.openweathermap.org/data/2.5/weather?lat={LAT}&lon={LON}&appid={WEATHER_KEY}&units=metric&lang=es"
            r = requests.get(url, timeout=10).json()
            bot.reply_to(message, f"🌤️ {r['name']}: {r['weather'][0]['description']}\nTemp: {r['main']['temp']}°C\nHumedad: {r['main']['humidity']}%\nViento: {r['wind']['speed']} m/s")
    except Exception as e:
        bot.reply_to(message, f"Error clima: {e}")

@bot.message_handler(commands=['grafica'])
def cmd_grafica(message):
    if not es_autorizado(message): return
    # Datos demo - aquí conecta tu API de satelite o sensor
    dias = [f"D-{i}" for i in range(7,0,-1)]
    valores = [0.62, 0.65, 0.63, 0.68, 0.71, 0.69, 0.73]

    plt.figure()
    plt.plot(dias, valores, marker='o')
    plt.title("GEOSAT - NDVI últimos 7 días")
    plt.ylabel("NDVI")
    plt.grid(True)

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    bot.send_photo(message.chat.id, buf, caption="📈 Tu parcela - tendencia en verde (mejorando)")

@bot.message_handler(commands=['memoria'])
def cmd_memoria(message):
    if not es_autorizado(message): return
    texto = message.text.replace('/memoria','').strip()
    with open(MEMORY_FILE, "r") as f:
        mem = json.load(f)

    if texto == "":
        if not mem:
            bot.reply_to(message, "Memoria vacía. Escribe: /memoria riego lote 1 hoy")
        else:
            ultimos = "\n".join([f"- {m}" for m in mem[-10:]])
            bot.reply_to(message, f"🧠 Últimas 10 notas:\n{ultimos}")
    else:
        fecha = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        mem.append(f"[{fecha}] {texto}")
        with open(MEMORY_FILE, "w") as f:
            json.dump(mem, f)
        bot.reply_to(message, f"✅ Guardado: {texto}")

# --- WEBHOOK FLASK ---
@app.route('/')
def index():
    return "GEOSAT vivo", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_str = request.get_data().decode('utf-8')
        update = Update.de_json(json_str)
        bot.process_new_updates([update])
        return "ok", 200
    return "error", 403

# Configurar webhook al arrancar
def setup_webhook():
    try:
        bot.remove_webhook()
        bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
        print(f"Webhook set to {WEBHOOK_URL}/webhook")
    except Exception as e:
        print(f"Error webhook: {e}")

setup_webhook()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
