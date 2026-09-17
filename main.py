import os, threading, traceback, requests, glob, re, json, datetime, time, urllib.parse
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import Flask
from telegram import Update
from telegram.ext import Application, MessageHandler, filters
from groq import Groq

try: import fitz
except: fitz = None

BOT_TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
app = Flask(__name__)
os.makedirs("docs", exist_ok=True)

@app.route('/')
def home(): return "Geosat V23.1 Hola FIX OK"
def run_web(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

def cargar_pdfs():
    txt=""
    for pdf in glob.glob("docs/*.pdf")[:8]:
        try:
            if fitz:
                doc=fitz.open(pdf)
                for p in doc[:8]: txt+=p.get_text()[:3000]
        except: continue
    return txt[:12000]

def expandir_anos(t):
    low=t.lower(); actual=datetime.datetime.now().year
    m=re.search(r'desde\s+(\d{4}).*?(?:hasta|al|a)\s+(\d{4}|actual)', low)
    if m:
        ini=int(m.group(1)); fin=actual if not m.group(2).isdigit() else int(m.group(2))
        return list(range(max(ini,1940), fin+1))
    if "actual" in low:
        anos=[int(y) for y in re.findall(r'\b(19\d{2}|20\d{2})\b', t)]
        if anos: return list(range(max(anos[0],1940), actual+1))
    return [int(y) for y in re.findall(r'\b(20\d{2})\b', t)]

def get_clima(lat, lon, years):
    if not years: return {}
    ini=max(min(years),1940); fin=max(years)
    try:
        url=f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={ini}-01-01&end_date={fin}-12-31&daily=temperature_2m_max&timezone=auto"
        j=requests.get(url,timeout=25).json()['daily']
        por={}
        for i in range(len(j['time'])):
            try:
                y=int(j['time'][i][:4]); v=j['temperature_2m_max'][i]
                if v is None: continue
                por.setdefault(y,[]).append(v)
            except: continue
        return {y: round(sum(v)/len(v),1) for y,v in por.items() if v}
    except: return {}

def geocode(q):
    if len(q.strip())<3: q="Cali"
    try:
        r=requests.get(f"https://nominatim.openstreetmap.org/search?q={q}&format=json&limit=1", headers={"User-Agent":"GeosatV23"}, timeout=10).json()
        if r: return r[0]['display_name'], float(r[0]['lat']), float(r[0]['lon'])
    except: pass
    return "Cali, Colombia", 3.4419, -76.5287

def crear_grafica(datos, titulo, path="/tmp/g.png"):
    try:
        plt.close('all')
        ys=sorted(datos.keys()); vals=[datos[y] for y in ys]
        plt.figure(figsize=(13,6.5))
        plt.plot([str(y) for y in ys], vals, marker='o', linewidth=2.8, color='#0a58ca')
        plt.title(titulo, fontweight='bold'); plt.xlabel("Año"); plt.ylabel("°C")
        plt.xticks(rotation=45, fontsize=8); plt.grid(True, alpha=0.25, linestyle='--')
        plt.tight_layout(); plt.savefig(path, dpi=250); plt.close('all')
        time.sleep(0.3)
        return path
    except:
        plt.close('all'); return None

async def handle_docs(update, context):
    f=await update.message.document.get_file()
    await f.download_to_drive(f"docs/{update.message.document.file_name}")
    await update.message.reply_text(f"Guardado {update.message.document.file_name}")

async def handle_message(update, context):
    texto=update.message.text
    if not texto: return
    low=texto.lower().strip()

    # FIX HOLA - no llames a Groq para saludos
    if low in ["hola","buenas","hi","hey","ola","holaa"]:
        await update.message.reply_text("¡Hola! Soy Geosat V23. Pregúntame lo que sea y si quieres gráfica dime 'con gráfica' o 'con imagen'. Ej: temperatura de Cali desde 2000 hasta actual con grafica")
        return

    try:
        quiere_visual = any(k in low for k in ["grafic","imagen","foto","visual","mapa","chart","plot"])
        years=expandir_anos(texto)
        if quiere_visual and not years and "cali" in low: years=list(range(2000, datetime.datetime.now().year+1))

        nombre, lat, lon = geocode(re.sub(r'desde|hasta|actual|grafica|con|temperatura','', low))
        datos = get_clima(lat, lon, years) if years else {}
        pdfs = cargar_pdfs()

        # PROMPT BLINDADO - PROHIBIDO HABLAR DE JSON
        sys_prompt=f"""
        Eres GEOSAT, asistente experto en TODO (topografia, ingenieria, qgis, programacion, cualquier tema).
        REGLAS OBLIGATORIAS:
        - Nunca hables de JSON, nunca digas CHART_JSON, nunca pidas formato de grafico.
        - Nunca digas "puedo generar el JSON".
        - Si te piden hola, saluda normal.
        - Si te piden grafica de temperatura, yo la genero con datos reales, tu solo explica el analisis.
        - Responde siempre directo, sin explicar tu funcionamiento interno.
        Datos clima reales: {datos}
        PDFs: {pdfs[:6000]}
        Pregunta usuario: {texto}
        """

        comp=client.chat.completions.create(model="openai/gpt-oss-20b", messages=[{"role":"system","content":sys_prompt}], temperature=0.7, max_tokens=1500)
        resp=comp.choices[0].message.content
        resp=re.sub(r'CHART_JSON.*','', resp, flags=re.DOTALL)
        resp=re.sub(r'```json.*?```','', resp, flags=re.DOTALL).strip()

        if quiere_visual and datos:
            img=crear_grafica(datos, f"Temperatura {nombre} {min(datos)}-{max(datos)}")
            if img:
                with open(img,'rb') as f:
                    await update.message.reply_photo(photo=f.read(), caption=resp[:900])
                return

        await update.message.reply_text(resp[:4000])

    except Exception as e:
        traceback.print_exc()
        await update.message.reply_text(f"Error: {e}")

def run_bot():
    app_bot=Application.builder().token(BOT_TOKEN).build()
    app_bot.add_handler(MessageHandler(filters.Document.ALL, handle_docs))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app_bot.run_polling(drop_pending_updates=True)

if __name__=='__main__':
    threading.Thread(target=run_web, daemon=True).start()
    run_bot()
