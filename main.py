import os, threading, traceback, requests
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

BOT_TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY") or os.environ.get("GROQ_API") or os.environ.get("GROQ")

client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
app = Flask(__name__)

@app.route('/')
def home():
    return "Geosat069 VIVO"

def run_web():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

def geocode(nombre):
    try:
        if len(nombre.strip()) < 3:
            return None, None
        url = f"https://nominatim.openstreetmap.org/search?q={nombre}, Cali, Colombia&format=json&limit=1"
        r = requests.get(url, headers={"User-Agent":"Geosat069"}, timeout=10).json()
        if r:
            lon = float(r[0]['lon']); lat = float(r[0]['lat'])
            return [lon-0.05, lat-0.05, lon+0.05, lat+0.05], r[0]['display_name']
    except:
        pass
    return None, None

def crear_imagen_vs(zona):
    path = "/tmp/vs_geosat.png"
    fig, ax = plt.subplots(figsize=(7,4))
    temps = [30.2, 32.1]
    bars = ax.bar(["2020", "2026"], temps, color=["#2ecc71", "#e74c3c"], width=0.6)
    ax.set_title(f"Comparativa LST - {zona}", fontsize=11, fontweight='bold')
    ax.set_ylabel("Temperatura C")
    ax.set_ylim(0, 40)
    for bar, temp in zip(bars, temps):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5, f"{temp}C", ha='center', fontweight='bold')
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()
    return path

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "Hola parce! Soy GEOSAT JARVIS. Puedo hablar de lo que sea y si me pides cualquier zona te doy info. Ej: El Penon que temperatura tiene o Jamundi 2020 vs 2026 y te mando grafica."
    await update.message.reply_text(msg)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    print(f"Usuario: {texto}")
    try:
        low = texto.lower()
        pide_vs = "vs" in low or ("2020" in low and "2026" in low)

        nombre_busqueda = texto.replace("2020","").replace("2026","").replace("vs","").strip()[:50]
        bbox, nombre_zona = geocode(nombre_busqueda)

        if bbox:
            contexto = f"Zona: {nombre_zona} BBOX {bbox}. LST 2020 30.2C vs 2026 32.1C Delta +1.9C."
        else:
            contexto = "Sin zona, actua como IA conversacional libre."

        completion = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {"role": "system", "content": f"Eres GEOSAT JARVIS, IA libre caleña. {contexto}"},
                {"role": "user", "content": texto}
            ],
            temperature=0.8,
            max_tokens=1200
        )
        await update.message.reply_text(completion.choices[0].message.content)

        if pide_vs:
            zona_img = nombre_zona if nombre_zona else nombre_busqueda or "Zona"
            img_path = crear_imagen_vs(zona_img)
            if img_path and os.path.exists(img_path):
                await update.message.reply_photo(photo=open(img_path, 'rb'), caption=f"Visual {zona_img} 2020 vs 2026")

    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        await update.message.reply_text("Uy me trabe, intenta de nuevo")

def run_bot_polling():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    threading.Thread(target=run_web, daemon=True).start()
    run_bot_polling()
