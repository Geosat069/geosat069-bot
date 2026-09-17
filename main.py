import os, threading, traceback, requests, glob, re, json, datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq
try:
    import fitz
except:
    fitz = None

BOT_TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY)
app = Flask(__name__)
os.makedirs("docs", exist_ok=True)

@app.route('/')
def home(): return "Geosat V21.2 OK"

def run_web(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

def cargar_pdfs():
    txt=""
    for pdf in glob.glob("docs/*.pdf")[:8]:
        try:
            if fitz:
                doc=fitz.open(pdf)
                for p in doc[:8]: txt+=f"\n---{pdf}---\n"+p.get_text()[:3000]
        except: continue
    return txt[:12000]

def buscar_web(q):
    try:
        r=requests.get(f"https://api.duckduckgo.com/?q={q}&format=json&no_html=1",timeout=8).json()
        return r.get("AbstractText","")[:2000]
    except: return ""

def expandir_anos(texto):
    low=texto.lower(); actual=datetime.datetime.now().year
    m=re.search(r'desde\s+(\d{4}).*?(?:hasta|al|a)\s+(\d{4}|actual)', low)
    if m:
        ini=int(m.group(1)); fin=actual if not m.group(2).isdigit() else int(m.group(2))
        return list(range(ini, fin+1))
    m2=re.search(r'(\d{4})\s*-\s*(\d{4}|actual)', low)
    if m2:
        ini=int(m2.group(1)); fin=actual if not m2.group(2).isdigit() else int(m2.group(2))
        return list(range(ini, fin+1))
    m3=re.search(r'desde\s+(\d{4})', low)
    if m3: return list(range(int(m3.group(1)), actual+1))
    anos=[int(y) for y in re.findall(r'\b(19\d{2}|20\d{2})\b', texto)]
    if anos and "actual" in low and len(anos)==1: return list(range(anos[0], actual+1))
    return anos

def get_datos_clima(lat, lon, years):
    if not years: return {}
    ini=max(min(years),1940); fin=max(years)
    try:
        url=f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={ini}-01-01&end_date={fin}-12-31&daily=temperature_2m_max&timezone=auto"
        j=requests.get(url,timeout=30).json()['daily']
        por_ano={}
        for i in range(len(j['time'])):
            try:
                y=int(j['time'][i][:4]); v=j['temperature_2m_max'][i]
                if v is None: continue
                por_ano.setdefault(y,[]).append(v)
            except: continue
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

def crear_visual(spec, lat, lon, path="/tmp/geosat.png"):
    try:
        if spec.get("type")=="map":
            url=f"https://staticmap.openstreetmap.de/staticmap.php?center={lat},{lon}&zoom=13&size=900x700&markers={lat},{lon},red"
            open(path,'wb').write(requests.get(url,timeout=15).content)
            return path
        plt.figure(figsize=(13,6.5))
        labels=spec.get("labels",[])
        for ds in spec.get("datasets",[]):
            data=ds["data"]; label=ds.get("label","Temp C")
            if spec.get("type")=="bar": plt.bar(labels, data, alpha=0.85, label=label, color='#0a58ca')
            else: plt.plot(labels, data, marker='o', linewidth=2.8, label=label, color='#0a58ca')
        plt.title(spec.get("title","Temperatura"), fontweight='bold', fontsize=13)
        plt.xlabel("Ano"); plt.ylabel("C"); plt.xticks(rotation=45, fontsize=9)
        plt.grid(True, alpha=0.25, linestyle='--'); plt.legend(); plt.tight_layout()
        plt.savefig(path, dpi=300); plt.close()
        return path
    except Exception as e:
        print(e); return None

async def start(update, context): await update.message.reply_text("GEOSAT V21.2 listo")

async def handle_docs(update, context):
    try:
        file=await update.message.document.get_file()
        await file.download_to_drive(f"docs/{update.message.document.file_name}")
        await update.message.reply_text(f"Guardado {update.message.document.file_name}")
    except Exception as e:
        await update.message.reply_text(f"Error {e}")

async def handle_message(update, context):
    texto=update.message.text; low=texto.lower()
    try:
        if low.strip() in ["hola","buenas","hi","hey","ola"]:
            await update.message.reply_text("Hola! V21.2 sin limite. Di con grafica / imagen / mapa"); return
        quiere_visual=any(k in low for k in ["grafic","imagen","foto","mapa","visual"])
        years=expandir_anos(texto)
        lugar_q=re.sub(r'19\d{2}|20\d{2}|desde|hasta|actual|grafica|imagen|mapa|con|dame|temperatura|anos|ano|media|anual','', low).strip()
        nombre, lat, lon=geocode(lugar_q)
        datos=get_datos_clima(lat, lon, years) if years else {}
        pdfs=cargar_pdfs(); web=buscar_web(texto[:120])
        prompt=f"Eres GEOSAT V21.2. Datos:{datos} Lugar:{nombre} PDFs:{pdfs[:8000]} Web:{web[:1500]} Visual:{quiere_visual} Pregunta:{texto} Si visual True agrega CHART_JSON: {{\"type\":\"line\",\"title\":\"Temp Cali\",\"labels\":[...],\"datasets\":[{{\"label\":\"Temp C\",\"data\":[...]}}]}}"
        comp=client.chat.completions.create(model="openai/gpt-oss-20b", messages=[{"role":"system","content":prompt}], temperature=0.8, max_tokens=2200)
        resp=comp.choices[0].message.content
        jm=re.search(r'CHART_JSON:\s*(\{.*\})', resp, re.DOTALL)
        if not jm: jm=re.search(r'(\{\s*"type"\s*:.*\})', resp, re.DOTALL)
        if jm and quiere_visual:
            try:
                raw=re.sub(r'```json|```','', jm.group(1)).replace("'",'"')
                spec=json.loads(raw)
                clean=re.sub(r'CHART_JSON:.*','', resp, flags=re.DOTALL).strip()
                clean=re.sub(r'```json.*?```','', clean, flags=re.DOTALL).strip()
                img=crear_visual(spec, lat, lon)
                if img:
                    await update.message.reply_photo(photo=open(img,'rb'), caption=clean[:1024]); return
            except Exception as e:
                print(f"visual error {e}")
        final=re.sub(r'CHART_JSON:.*','', resp, flags=re.DOTALL).strip()
        await update.message.reply_text(final[:4000])
    except Exception as e:
        await update.message.reply_text(f"Error {e}")

def run_bot():
    application=Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_docs))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling(drop_pending_updates=True)

if __name__=='__main__':
    threading.Thread(target=run_web, daemon=True).start()
    run_bot()
