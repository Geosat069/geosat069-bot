import os, threading, traceback, requests, glob, re, json
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
def home(): return "Geosat069 OK V16 FIX"
def run_web(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

def cargar_pdfs():
    txt=""
    for pdf in glob.glob("docs/*.pdf")[:5]:
        try:
            if fitz:
                doc=fitz.open(pdf)
                for p in doc[:5]: txt+=p.get_text()[:2500]
        except: pass
    return txt[:7000]

def get_datos_reales(lat, lon, years):
    datos={}
    for y in years:
        try:
            date=f"{y}-07-15"
            url=f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={date}&end_date={date}&daily=temperature_2m_max,precipitation_sum,wind_speed_10m_max,relative_humidity_2m_mean&timezone=auto"
            r=requests.get(url,timeout=12).json()['daily']
            datos[y]={"temp": r['temperature_2m_max'][0], "precip": r['precipitation_sum'][0], "viento": r['wind_speed_10m_max'][0], "humedad": r['relative_humidity_2m_mean'][0]}
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
            url = f"https://staticmap.openstreetmap.de/staticmap.php?center={lat},{lon}&zoom=14&size=800x600&markers={lat},{lon},red"
            open(path,'wb').write(requests.get(url,timeout=15).content)
            return path
        plt.figure(figsize=(8,5))
        t=spec.get("type","bar"); labels=spec.get("labels",[])
        for ds in spec.get("datasets",[]):
            if t=="bar": plt.bar(labels, ds["data"], label=ds["label"], alpha=0.85)
            else: plt.plot(labels, ds["data"], marker='o', linewidth=2.5, label=ds["label"])
        plt.title(spec.get("title","Comparativa REAL")); plt.legend(); plt.tight_layout()
        plt.savefig(path, dpi=200); plt.close()
        return path
    except Exception as e:
        print(e); return None

async def start(update, context):
    await update.message.reply_text("Soy GEOSAT el que te sirve. Preguntame normal o pideme con grafica/imagen/mapa y te la hago.")

async def handle_message(update, context):
    texto=update.message.text
    low=texto.lower()
    try:
        quiere_visual = any(k in low for k in ["grafic","imagen","foto","mapa","visual","muestrame","plot","chart"])

        years=[int(y) for y in re.findall(r'\b(20\d{2})\b', texto)]
        if any(k in low for k in ["actual","hoy","ahora"]): years.append(2026)
        years=list(dict.fromkeys(years))[:4]

        lugar_q = re.sub(r'20\d{2}|vs|comparacion|actual|hoy|grafica|imagen|mapa|con|dame','', low).strip()
        if not lugar_q: lugar_q="Pance Cali"
        nombre, lat, lon = geocode(lugar_q[:80])
        datos_reales = get_datos_reales(lat, lon, years) if years else {}
        pdfs = cargar_pdfs()

        # Prompt sin f-string triple para evitar SyntaxError
        prompt_base = (
            "Eres GEOSAT JARVIS, ingeniero topografico 20 anos. Experto QGIS, ArcGIS, Civil3D, LIDAR, ERA5.\n"
            f"Apuntes: {pdfs[:6000]}\n"
            f"Lugar: {nombre} {lat},{lon}\n"
            f"Datos reales: {datos_reales}\n"
            f"Quiere visual? {quiere_visual}\n"
            "Si quiere_visual es False, responde SOLO TEXTO.\n"
            "Si es True, al final anade obligatoriamente: CHART_JSON: {\"type\":\"bar\", \"title\":\"Titulo\", \"labels\":[\"2020\",\"2026\"], \"datasets\":[{\"label\":\"Temp\", \"data\":[21,25]}]}\n"
            "Si pide mapa usa type map.\n"
            f"Pregunta: {texto}"
        )

        comp=client.chat.completions.create(model="openai/gpt-oss-20b", messages=[{"role":"system","content":prompt_base},{"role":"user","content":texto}], temperature=0.7, max_tokens=1900)
        resp=comp.choices[0].message.content

        m=re.search(r'CHART_JSON:\s*(\{.*\})', resp, re.DOTALL)
        if m and quiere_visual:
            try:
                spec=json.loads(m.group(1))
                resp_text=resp.replace(m.group(0),"").strip()
                img_path=crear_imagen_auto(spec, lat, lon)
                if img_path:
                    await update.message.reply_photo(photo=open(img_path,'rb'), caption=resp_text[:1024])
                    return
            except: pass

        await update.message.reply_text(resp.replace("CHART_JSON:","")[:4000])

    except Exception as e:
        traceback.print_exc()
        await update.message.reply_text(f"Error: {e}")

def run_bot_polling():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    threading.Thread(target=run_web, daemon=True).start()
    run_bot_polling()
