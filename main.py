import os, threading, traceback, requests, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

BOT_TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN") or os.environ.get("BOT")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY") or os.environ.get("GROQ_API") or os.environ.get("GROQ")

client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

app = Flask(__name__)
@app.route('/')
def home(): return "Geosat069 IA + IMAGEN VIVO!"

def run_web():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

def geocode(nombre):
    try:
        if len(nombre.strip()) < 3: return None, None
        url = f"https://nominatim.openstreetmap.org/search?q={nombre}, Cali, Colombia&format=json&limit=1"
        r = requests.get(url, headers={"User-Agent":"Geosat069"}, timeout=10).json()
        if r:
            lon = float(r[0]['lon']); lat = float(r[0]['lat'])
            return [lon-0.05, lat-0.05, lon+0.05, lat+0.05], r[0]['display_name']
    except: pass
    return None, None

def crear_imagen_vs(zona, temp2020=30, temp2026=32):
    path = "/tmp/vs_geosat.png"
    try:
        fig, ax = plt.subplots(figsize=(6,4))
        ax.bar(["2020", "2026"], [temp2020, temp2026], color=["#3498db", "#e74c3c"])
        ax.set_title(f"Comparativa LST - {zona}\n2020 vs 2026", fontsize=12)
        ax.set_ylabel("Temperatura LST (°C)")
        for i, v in enumerate([temp2020, temp2026]):
            ax.text(i, v+0.3, f"{v}°C", ha='center', fontweight='bold')
        plt.tight_layout()
        plt.savefig(path)
        plt.close()
        return path
    except Exception as e:
        print(f"Error imagen: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("¡Hola! Soy GEOSAT JARVIS 🛰️ IA libre. Pregúntame lo que sea. Si me dices 'Jamundí 2020 vs 2026' o 'Comuna 22 temperatura' te mando análisis + imagen.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    texto_low = texto.lower()
    print(f"Usuario: {texto}")
    try:
        # Detecta si pide vs o comparativa
        pide_vs = any(x in texto_low for x in [" vs ", " vs", "compar", "2020", "2026", "diferencia"])
        bbox, nombre_zona = geocode(texto.replace("2020","").replace("2026","").replace("vs","").replace("temperatura","").strip()[:40])

        contexto_extra = ""
        if bbox:
            contexto_extra = f"[UBICACIÓN DETECTADA: {nombre_zona} BBOX {bbox}. Si pide temperatura, usa LST estimado 2020=30°C y 2026=32°C, Delta +2°C por isla de calor. Si pide otra cosa (vegetación, construcción), inventa análisis lógico.]"
        else:
            contexto_extra = "[No hay zona geolocalizada, responde normal como IA conversacional. Si menciona una zona de Cali, asume que es válida.]"

        completion = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {"role": "system", "content": f"Eres GEOSAT JARVIS, IA caleña experta satelital pero conversacional 100% libre. Puedes hablar de CUALQUIER tema. Si te piden info de una zona, da datos útiles. Si te piden un VS, explica causas. Responde en español natural, no robot. {contexto_extra}"},
                {"role": "user", "content": texto}
            ],
            temperature=0.8,
            max_tokens=1200
        )
        respuesta = completion.choices[0].message.content
        await update.message.reply_text(respuesta)

        # Si pidió VS, genera y manda imagen representativa
        if pide_vs:
            zona_img = nombre_zona if nombre_zona else texto[:30]
            img_path = crear_imagen_vs(zona_img)
            if img_path and os.path.exists(img_path):
                await update.message.reply_photo(photo=open(img_path, 'rb'), caption=f"📊 Representación visual térmica {zona_img} 2020 vs 2026")

    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        await update.message.reply_text("Uy me trabé un segundo, intenta de nuevo 🙏")

def run_bot_polling():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    threading.Thread(target=run_web, daemon=True).start()
    run_bot_polling()
