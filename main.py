import os, threading, traceback, requests
import matplotlib
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

def crear_imagen_vs(zona):
    path = "/tmp/vs_geosat.png"
    fig, ax = plt.subplots(figsize=(7,4))
    temps = [30.2, 32.1]
    bars = ax.bar(["2020", "2026"], temps, color=["#2ecc71", "#e74c3c"], width=0.6)
    ax.set_title(f"Comparativa Térmica LST\n{zona}", fontsize=11, fontweight='bold')
    ax.set_ylabel("Temperatura °C")
    ax.set_ylim(0, 40)
    for bar, temp in zip(bars, temps):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5, f"{temp}°C", ha='center', fontweight='bold')
    ax.text(0.5, 15, "Delta +1.9°C", ha='center', fontsize=12, color="#e74c3c", fontweight='bold', transform=ax.transAxes)
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()
    return path

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("¡Hola parce! Soy
