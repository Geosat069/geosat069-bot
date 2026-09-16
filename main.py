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
def home(): return "Geosat V20.1 FIX GRAFICA OK"
def run_web(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

def cargar_pdfs():
    txt=""
    for pdf in glob.glob("docs/*.pdf")[:8]:
        try:
            if fitz:
                doc=fitz.open(pdf)
                for p in doc[:8]: txt+=f"\n---{pdf}---\n"+p.get_text()[:3000]
        except: pass
    return txt[:12000]

def buscar_web(q):
    try:
        url=f"https://api.duckduckgo.com/?q={q}&format=json&no_html=1"
        r=requests.get(url,timeout=8).json()
        return r.get("AbstractText","")[:2000]
    except: return ""

def expandir_anos(texto):
    low=texto.lower(); actual=datetime.datetime.now().year
    m=re.search(r'desde\s+(\d{4}).*?(?:hasta|al|a)\s+(\d{4}|actual)', low)
    if m:
        ini=int(m.group(1)); fin=actual if not m.group(2).isdigit() else int(m.group(2))
        return list(range(ini, fin+1))
    m2=re.search(r'desde\s+(\d{4})', low)
    if m2: return list(range(int(m2.group(1)), actual+1))
    anos=[int(y) for y in re.findall(r'\b(19\d{2}|20\d{2})\b', texto)]
    if anos and "actual" in low and len(anos)==1:
        return list(range(anos[0], actual+1))
    return anos

def get_datos_clima(lat, lon, years):
    if not years: return {}
    ini=max(min(years),1940); fin=max(years)
    try:
        url=f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={ini}-01-01&end_date={fin}-12-31&daily=temperature_2m_max&timezone=auto"
        j=requests.get(url,timeout=30).json()['daily']
        por_ano={}
        for i,fecha in enumerate(j['time']):
            y=int(fecha[:4])
            por_ano.setdefault(y, []).append(j['temperature_2m_max'][i] or 0)
        return {y: round(sum(v)/len(v),1) for y,v in por_ano.items() if v}
    except: return {}

def geocode(q):
    if len(q.strip())<3: q="Cali, Valle del Cauca"
    try:
        url=f"https://nominatim.openstreetmap.org/search?q={q}&format=json&limit=1"
        r=requests.get(url,headers={"User-Agent":"Geosat069"},timeout=10).json()
        if r: return r[0]['display_name'], float(r[0]['lat']), float(r[0]['lon'])
    except: pass
    return "Cali, Colombia", 3.4419, -76.5287

def crear_visual(spec, path="/tmp/geosat.png"):
    try:
        plt.figure(figsize=(12,6))
        labels=spec.get("labels",[])
        if spec.get("type")=="map":
            # no es grafica, es mapa - no usamos este
            return None
        for ds in spec.get("datasets",[]):
            data=ds["data"]; label=ds.get("label","Dato")
            if spec.get("type")=="line":
                plt.plot(labels, data, marker='o', linewidth=2.5, label=label)
            else:
                plt.bar(labels, data, alpha=0.85, label=label)
        plt.title(spec.get("title","Evolución"), fontweight='bold')
        plt.xticks(rotation=45, fontsize=8); plt.grid(alpha=0.3)
        plt.legend(); plt.tight_layout(); plt.savefig(path, dpi=240); plt.close()
        return path
    except Exception as e:
        print(e); return None

async def handle_docs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        file=await update.message.document.get_file()
        fname=update.message.document.file_name
        await file.download_to_drive(f"docs/{fname}")
        await update.message.reply_text(f"Listo, aprendí {fname}. Ya está en mi memoria.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto=update.message.text; low=texto.lower()
    try:
        if low.strip() in ["hola","buenas","hello","hi"]:
            await update.message.reply_text("Hola! Soy GEOSAT V20.1. Pídeme lo que sea, de cualquier año (desde 1940 hasta hoy). Si quieres gráfica di 'con gráfica'.")
            return

        quiere_visual = any(k in low for k in ["grafic","imagen","foto","mapa","visual","plot","chart"])
        years=expandir_anos(texto)
        lugar_q=re.sub(r'19\d{2}|20\d{2}|desde|hasta|actual|grafica|imagen|mapa|con|dame','', low).strip()
        nombre, lat, lon = geocode(lugar_q)
        datos=get_datos_clima(lat, lon, years) if years else {}
        pdfs=cargar_pdfs()
        web=buscar_web(texto[:100])

        prompt=f"""
Eres GEOSAT JARVIS V20.1. Responde de CUALQUIER tema, sin limite de año (ERA5 desde 1940 hasta 2026). Prefiere info actual.
Tienes datos reales: {datos}
Lugar: {nombre} ({lat},{lon})
PDFs: {pdfs[:9000]}
Web: {web[:1500]}
Si quiere_visual={quiere_visual}, al final OBLIGATORIO genera:
CHART_JSON: {{"type":"line", "title":"Titulo", "labels":["2000",...], "datasets":[{{"label":"Temp °C","data":[...]}}]}}
Pregunta: {texto}
"""
        comp=client.chat.completions.create(model="openai/gpt-oss-20b", messages=[{"role":"system","content":prompt}], temperature=0.8, max_tokens=2200)
        resp=comp.choices[0].message.content

        # FIX DE TU CAPTURA: detecta JSON aunque venga sin CHART_JSON:
        json_match = re.search(r'CHART_JSON:\s*(\{.*\})', resp, re.DOTALL)
        if not json_match:
            # busca el JSON suelto tipo {"type":"line"... como en tu captura
            json_match = re.search(r'(\{\s*"type"\s*:\s*".*?"\s*,.*\})', resp, re.DOTALL)

        if json_match and quiere_visual:
            try:
                # Limpia saltos de linea
                raw = json_match.group(1).replace("'",'"')
                spec = json.loads(raw)
                txt = resp.replace(json_match.group(0),"").strip()
                img = crear_visual(spec)
                if img:
                    await update.message.reply_photo(photo=open(img,'rb'), caption=txt[:1024])
                    return
            except Exception as e:
                print("Error parse JSON", e, traceback.format_exc())

        await update.message.reply_text(resp[:4000])
    except Exception as e:
        traceback.print_exc()
        await update.message.reply_text(f"Error: {e}")

def run_bot():
    application=Application.builder().token(BOT_TOKEN).build()
    application.add_handler(MessageHandler(filters.Document.ALL, handle_docs))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling(drop_pending_updates=True)

if __name__=='__main__':
    threading.Thread(target=run_web, daemon=True).start()
    run_bot()
