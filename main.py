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
def home(): return "Geosat069 V19 LIBRE SIN LIMITES"
def run_web(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

def cargar_pdfs():
    txt=""
    for pdf in glob.glob("docs/*.pdf")[:6]:
        try:
            if fitz:
                doc=fitz.open(pdf)
                for p in doc[:6]: txt+=p.get_text()[:3000]
        except: pass
    return txt[:9000]

def expandir_anos_sin_limite(texto):
    low=texto.lower()
    actual=2026
    # 2000 hasta actual / 2000 al actual / 1990-2020 / desde 1970
    m = re.search(r'desde\s+(\d{4})\s+(?:hasta|al|a|-|–)\s+(\d{4}|actual|ahora|hoy|presente)', low)
    if m:
        ini=int(m.group(1)); fin_s=m.group(2)
        fin=actual if not fin_s.isdigit() else int(fin_s)
        return list(range(ini, fin+1))
    m2 = re.search(r'(\d{4})\s*(?:-|–|al|a|hasta)\s*(\d{4}|actual)', low)
    if m2:
        ini=int(m2.group(1)); fin_s=m2.group(2)
        fin=actual if not fin_s.isdigit() else int(fin_s)
        return list(range(ini, fin+1))
    m3 = re.search(r'desde\s+(\d{4})', low)
    if m3:
        ini=int(m3.group(1))
        # si dice "desde 2000" se asume hasta actual
        return list(range(ini, actual+1))

    anos = [int(y) for y in re.findall(r'\b(19\d{2}|20\d{2})\b', texto)]
    if anos and any(k in low for k in ["actual","hoy","ahora","presente"]):
        if len(anos)==1:
            return list(range(anos[0], actual+1))
    return anos

def get_datos_ilimitados(lat, lon, years):
    if not years: return {}
    ini=min(years); fin=max(years)
    ini=max(ini, 1940) # ERA5 empieza en 1940
    try:
        # UNA SOLA PETICION trae TODO el rango, por eso no hay limite
        url=f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={ini}-01-01&end_date={fin}-12-31&daily=temperature_2m_max,precipitation_sum,wind_speed_10m_max,relative_humidity_2m_mean&timezone=auto"
        j=requests.get(url,timeout=30).json()['daily']
        # Agrupa por año
        por_ano={}
        for i, fecha in enumerate(j['time']):
            y=int(fecha[:4])
            if y not in por_ano: por_ano[y]={'t':[],'p':[],'v':[],'h':[]}
            if j['temperature_2m_max'][i] is not None: por_ano[y]['t'].append(j['temperature_2m_max'][i])
            if j['precipitation_sum'][i] is not None: por_ano[y]['p'].append(j['precipitation_sum'][i])

        resultado={}
        for y, vals in por_ano.items():
            if vals['t']:
                resultado[y]=round(sum(vals['t'])/len(vals['t']),2) # promedio anual temp
        return resultado
    except Exception as e:
        print("Error ilimitado", e)
        return {}

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
            url = f"https://staticmap.openstreetmap.de/staticmap.php?center={lat},{lon}&zoom=13&size=800x600&markers={lat},{lon},red"
            open(path,'wb').write(requests.get(url,timeout=12).content)
            return path
        plt.figure(figsize=(11,5.5))
        labels=spec.get("labels",[])
        for ds in spec.get("datasets",[]):
            if spec.get("type")=="line":
                plt.plot(labels, ds["data"], marker='o', linewidth=2.2, label=ds["label"])
            else:
                plt.bar(labels, ds["data"], label=ds["label"], alpha=0.85)
        plt.title(spec.get("title","Serie Temporal REAL ERA5 - Sin Limite"), fontweight='bold')
        plt.xticks(rotation=45, fontsize=8); plt.ylabel("°C"); plt.grid(alpha=0.2)
        plt.legend(); plt.tight_layout(); plt.savefig(path, dpi=230); plt.close()
        return path
    except Exception as e:
        print(e); return None

async def handle_message(update, context):
    texto=update.message.text
    low=texto.lower()
    try:
        quiere_visual = any(k in low for k in ["grafic","imagen","foto","mapa","visual","muestrame","muéstrame","plot","chart","dibuja"])
        years = expandir_anos_sin_limite(texto)
        # Lugar libre
        lugar_q = re.sub(r'19\d{2}|20\d{2}|desde|hasta|actual|grafica|gráfica|imagen|mapa|con|dame|aumento|temperatura|todos|años|del|al|año','', low).strip()
        if len(lugar_q) < 3: lugar_q="Cali, Valle del Cauca"
        nombre, lat, lon = geocode(lugar_q[:90])

        datos_reales = get_datos_ilimitados(lat, lon, years) if years else {}
        pdfs=cargar_pdfs()

        prompt_base = (
            f"Eres GEOSAT JARVIS. Eres LIBRE. Responde lo que el usuario quiera: topografia, QGIS, Civil3D, LIDAR, clima, lo que sea.\n"
            f"REGLA DE ORO: NUNCA le pidas datos al usuario. Tu ya tienes los datos reales: {datos_reales}\n"
            f"Lugar detectado: {nombre} ({lat},{lon}) Anos detectados: {years}\n"
            f"Quiere visual? {quiere_visual}\n"
            f"Tus apuntes PDF: {pdfs[:8000]}\n"
            "Si quiere_visual=True, al final OBLIGATORIO agrega: CHART_JSON: {\"type\":\"line\", \"title\":\"Titulo\", \"labels\":[...], \"datasets\":[{\"label\":\"Temp °C\", \"data\":[...]}]}\n"
            "Usa los datos reales que te di. Si el rango es 2000-2026, grafica los 27 años. No digas que no tienes datos.\n"
            f"Pregunta libre del usuario: {texto}"
        )

        comp=client.chat.completions.create(model="openai/gpt-oss-20b", messages=[{"role":"system","content":prompt_base},{"role":"user","content":texto}], temperature=0.8, max_tokens=2000)
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
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    threading.Thread(target=run_web, daemon=True).start()
    run_bot_polling()
