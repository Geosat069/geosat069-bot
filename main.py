import os, threading, traceback, requests, glob, re, json, datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

try: import fitz
except: fitz = None

BOT_TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY)
app = Flask(__name__)
os.makedirs("docs", exist_ok=True)

@app.route('/')
def home(): return "Geosat069 FUNCIONANDO V16"
def run_web(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

def cargar_pdfs():
    txt=""
    for pdf in glob.glob("docs/*.pdf")[:5]:
        try:
            if fitz:
                doc=fitz.open(pdf)
                for p in doc[:5]: txt+=p.get_text()[:2500]
        except: pass
    return txt[:8000]

def get_datos_reales(lat, lon, years):
    datos={}
    for y in years:
        try:
            date=f"{y}-07-15"
            url=f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={date}&end_date={date}&daily=temperature_2m_max,precipitation_sum,wind_speed_10m_max,relative_humidity_2m_mean,shortwave_radiation_sum&timezone=auto"
            r=requests.get(url,timeout=12).json()['daily']
            datos[y]={
                "temp": r['temperature_2m_max'][0],
                "precip": r['precipitation_sum'][0],
                "viento": r['wind_speed_10m_max'][0],
                "humedad": r['relative_humidity_2m_mean'][0],
                "radiacion": r['shortwave_radiation_sum'][0]
            }
        except: pass
    return datos

def geocode(q):
    try:
        url=f"https://nominatim.openstreetmap.org/search?q={q}, Cali, Colombia&format=json&limit=1"
        r=requests.get(url,headers={"User-Agent":"Geosat069"},timeout=10).json()
        if r: return r[0]['display_name'], float(r[0]['lat']), float(r[0]['lon'])
    except: pass
    return q, 3.4419, -76.55

def crear_imagen_auto(spec, lat, lon, path="/tmp/geosat.png"):
    try:
        if spec.get("type") == "map":
            # Mapa satelital real
            url = f"https://staticmap.openstreetmap.de/staticmap.php?center={lat},{lon}&zoom=14&size=800x600&markers={lat},{lon},red"
            img_data = requests.get(url, timeout=15).content
            open(path,'wb').write(img_data)
            return path

        plt.figure(figsize=(8,5))
        t=spec.get("type","bar")
        labels=spec.get("labels",[])
        if t=="bar":
            for ds in spec.get("datasets",[]):
                plt.bar(labels, ds["data"], label=ds["label"], alpha=0.85)
        elif t=="line":
            for ds in spec.get("datasets",[]):
                plt.plot(labels, ds["data"], marker='o', linewidth=2.5, label=ds["label"])
        elif t=="pie":
            plt.pie(spec["datasets"][0]["data"], labels=labels, autopct='%1.1f%%')

        plt.title(spec.get("title","Comparativa Ambiental REAL"), fontweight='bold', fontsize=11)
        plt.legend(); plt.tight_layout(); plt.savefig(path, dpi=220); plt.close()
        return path
    except Exception as e:
        print("Error imagen", e)
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Soy GEOSAT el que te sirve. Pregúntame normal o pídeme con gráfica/imagen/mapa y te la hago.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto=update.message.text
    low=texto.lower()
    try:
        quiere_visual = any(k in low for k in ["grafic","grafico","imagen","foto","mapa","visual","muestrame","muéstrame","plot","chart","dibuja"])

        years=[int(y) for y in re.findall(r'\b(20\d{2})\b', texto)]
        if any(k in low for k in ["actual","hoy","ahora","este año"]): years.append(2026)
        years=list(dict.fromkeys(years))[:4]

        # Lugar
        lugar_q = re.sub(r'20\d{2}|vs|comparacion|actual|hoy|grafica|imagen|mapa|con|dame|la|del|año', '', low).strip()
        if not lugar_q: lugar_q="Pance, Cali"
        nombre, lat, lon = geocode(lugar_q[:80])

        datos_reales = get_datos_reales(lat, lon, years) if years else {}
        pdfs = cargar_pdfs()

        prompt = f"""
        Eres GEOSAT JARVIS, ingeniero topográfico y geomático con 20 años de experiencia.
        Experto en QGIS, ArcGIS Pro, Civil 3D, LIDAR, Sentinel,
