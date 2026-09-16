import os, threading, traceback, requests, json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

BOT_TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

client = Groq(api_key=GROQ_API_KEY)
app = Flask(__name__)
@app.route('/')
def home(): return "Geosat069 AUTODIDACTA VIVO!"

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

def buscar_internet(tema):
    # Busca info técnica real en Wikipedia para auto-alimentarse
    try:
        url = f"https://es.wikipedia.org/api/rest_v1/page/summary/{tema.replace(' ', '_')}"
        r = requests.get(url, timeout=5).json()
        if 'extract' in r:
            return r['extract'][:1000]
    except: pass
    try:
        # Fallback DuckDuckGo
        url = f"https://api.duckduckgo.com/?q={tema} QGIS ArcGIS teledeteccion&format=json"
        r = requests.get(url, timeout=5).json()
        if r.get('AbstractText'):
            return r['AbstractText'][:1000]
    except: pass
    return ""

def crear_imagen_vs(zona):
    path = "/tmp/vs_geosat.png"
    fig, ax = plt.subplots(figsize=(7,4))
    temps = [30.2, 32.1]
    bars = ax.bar(["2020", "2026"], temps, color=["#2ecc71", "#e74c3c"], width=0.6)
    ax.set_title(f"Comparativa LST - {zona}", fontsize=11, fontweight='bold')
    ax.set_ylabel("Temperatura C")
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()
    return path

# CARGAR CONOCIMIENTO ACUMULADO
def cargar_conocimiento():
    try:
        if os.path.exists("conocimiento.txt"):
            with open("conocimiento.txt", "r", encoding="utf-8") as f:
                return f.read()[-3000:] # ultimos 3000 chars
    except: pass
    return ""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "Hola parce! Soy GEOSAT JARVIS autodidacta. Ya aprendo sola de Topografia, Geomatica, QGIS, ArcGIS, Civil 3D y satelites. Preguntame lo que sea."
    await update.message.reply_text(msg)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    try:
        low = texto.lower()
        pide_vs = "vs" in low or ("2020" in low and "2026" in low)

        # 1. Detecta si es tema tecnico para auto-aprender
        temas_clave = ["qgis", "arcgis", "civil 3d", "topograf", "geomat", "teledete", "satelit", "lidar", "fotogramet", "sig", "crs", "ortofoto"]
        es_tema_tecnico = any(t in low for t in temas_clave)

        info_internet = ""
        if es_tema_tecnico:
            info_internet = buscar_internet(texto)
            # Guarda lo aprendido
            try:
                with open("conocimiento.txt", "a", encoding="utf-8") as f:
                    f.write(f"\nTema: {texto}\nInfo: {info_internet}\n---\n")
            except: pass

        conocimiento_previo = cargar_conocimiento()
        bbox, nombre_zona = geocode(texto.replace("2020","").replace("2026","").replace("vs","").strip()[:50])

        prompt_sistema = f"""
        Eres GEOSAT JARVIS, eres un INGENIERO TOPOGRAFICO y GEOMATICO experto con 20 años de experiencia.
        Dominios: Topografia, Geomatica, QGIS, ArcGIS Pro, Civil 3D, AutoCAD Map, Teledeteccion, Satelites Sentinel/Landsat en tiempo real, LIDAR, Fotogrametria con drones, Sistemas de Referencia (MAGNA-SIRGAS), calculo de volumenes, curvas de nivel.
        Tu objetivo es APRENDER SOLO de internet y ser autodidacta.
        Conocimiento acumulado previo: {conocimiento_previo}
        Info fresca de internet sobre la pregunta actual: {info_internet}
        Zona si aplica: {nombre_zona}
        Responde como profesor caleño experto, da pasos practicos, comandos de QGIS, herramientas de ArcGIS, etc.
        """

        completion = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": texto}
            ],
            temperature=0.7,
            max_tokens=1500
        )
        await update.message.reply_text(completion.choices[0].message.content)

        if pide_vs and nombre_zona:
            img_path = crear_imagen_vs(nombre_zona)
            await update.message.reply_photo(photo=open(img_path, 'rb'), caption=f"Visual {nombre_zona} 2020 vs 2026")

    except Exception as e:
        print(e); traceback.print_exc()
        await update.message.reply_text("Uy me trabe, intenta de nuevo")

def run_bot_polling():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    threading.Thread(target=run_web, daemon=True).start()
    run_bot_polling()
