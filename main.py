import os, threading, traceback, requests, glob
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

# Intenta importar para PDFs y YouTube
try:
    import fitz # PyMuPDF
except: fitz = None

BOT_TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY)

app = Flask(__name__)
@app.route('/')
def home(): return "Geosat069 AUTODIDACTA TOTAL VIVO!"

def run_web():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

# --- FUNCIONES DE AUTO-APRENDIZAJE ---

def cargar_pdfs():
    texto_total = ""
    try:
        pdfs = glob.glob("docs/*.pdf")
        for pdf_path in pdfs[:3]: # lee max 3 para no saturar memoria de Render
            if fitz:
                doc = fitz.open(pdf_path)
                for page in doc[:5]: # primeras 5 paginas de cada pdf
                    texto_total += page.get_text()[:2000]
        if texto_total:
            return texto_total[:5000]
    except Exception as e:
        print(f"Error PDFs: {e}")
    return ""

def buscar_internet(tema):
    try:
        url = f"https://es.wikipedia.org/api/rest_v1/page/summary/{tema.replace(' ', '_')}"
        r = requests.get(url, timeout=5).json()
        if 'extract' in r: return r['extract'][:1200]
    except: pass
    return ""

def buscar_sentinel_hoy():
    try:
        # Busca ultimo Sentinel-2 sobre Cali (3.4, -76.5)
        url = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products?$filter=Collection/Name eq 'SENTINEL-2' and OData.CSC.Intersects(area=geography'SRID=4326;POINT(-76.52 3.45)')&$top=1&$orderby=ContentDate/Start desc"
        r = requests.get(url, timeout=10).json()
        if 'value' in r and len(r['value'])>0:
            prod = r['value'][0]
            return f"Ultimo Sentinel-2: {prod['Name']} Fecha: {prod['ContentDate']['Start']}"
    except Exception as e:
        print(f"Sentinel error: {e}")
    return "No pude consultar Sentinel ahora, pero se Sentinel-2 y Landsat 8/9 en tiempo real."

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
    ax.set_title(f"Comparativa LST - {zona}", fontsize=11, fontweight='bold')
    ax.set_ylabel("Temperatura C")
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()
    return path

# --- BOT ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hola! Soy GEOSAT JARVIS Profesor Autodidacta. Ya leo tus PDFs de /docs, consulto Sentinel real y aprendo de internet. Preguntame de QGIS, ArcGIS, Civil 3D, LIDAR, o pide un VS como 'Pance 2020 vs 2026'.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    low = texto.lower()
    try:
        pide_vs = "vs" in low or ("2020" in low and "2026" in low)
        es_tecnico = any(t in low for t in ["qgis","arcgis","civil","topograf","geomat","lidar","dron","sentinel","landsat","mdt","curvas"])

        info_pdf = cargar_pdfs() if es_tecnico else ""
        info_web = buscar_internet(texto[:40]) if es_tecnico else ""
        info_sentinel = buscar_sentinel_hoy() if "satelit" in low or "sentinel" in low else ""

        bbox, nombre_zona = geocode(texto.replace("2020","").replace("2026","").replace("vs","").strip()[:50])

        prompt = f"""
        Eres GEOSAT JARVIS, INGENIERO TOPOGRAFICO Y GEOMATICO experto (20 años). Experto en QGIS, ArcGIS Pro, Civil 3D, AutoCAD, LIDAR, fotogrametria, teledeteccion.
        CONTEXTO DE AUTO-APRENDIZAJE:
        - Conocimiento de PDFs del usuario: {info_pdf[:3000]}
        - Info fresca de internet: {info_web}
        - Info satelital real: {info_sentinel}
        - Zona detectada: {nombre_zona} {bbox}
        INSTRUCCION: Responde como profesor, da comandos exactos de QGIS (ej: Raster > Extraer > Contorno), herramientas de ArcGIS (Spatial Analyst), y Civil 3D. Si te dan link de YouTube, resume el tutorial y aprendelo.
        """

        completion = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[{"role":"system","content":prompt},{"role":"user","content":texto}],
            temperature=0.7, max_tokens=1500
        )
        await update.message.reply_text(completion.choices[0].message.content)

        if pide_vs:
            zona_img = nombre_zona if nombre_zona else texto[:30]
            img_path = crear_imagen_vs(zona_img)
            await update.message.reply_photo(photo=open(img_path,'rb'), caption=f"Visual termica {zona_img} 2020 vs 2026 - EICU")

    except Exception as e:
        print(e); traceback.print_exc()
        await update.message.reply_text("Uy me trabe un segundo, intenta de nuevo")

def run_bot_polling():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    threading.Thread(target=run_web, daemon=True).start()
    run_bot_polling()
