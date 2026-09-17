import os, threading, traceback, requests, glob, re, datetime, time
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
def home(): return "Geosat V24 REAL ERA5 OK"
def run_web(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

def cargar_pdfs():
    txt=""
    for pdf in glob.glob("docs/*.pdf")[:6]:
        try:
            if fitz:
                doc=fitz.open(pdf)
                for p in doc[:6]: txt+=p.get_text()[:2500]
        except: continue
    return txt[:10000]

def expandir_anos(t):
    actual=datetime.datetime.now().year
    m=re.search(r'2000.*?(?:hasta|actual)', t.lower())
    if m: return list(range(2000, actual+1))
    anos=[int(y) for y in re.findall(r'\b(20\d{2})\b', t)]
    if anos and "actual" in t.lower(): return list(range(min(anos), actual+1))
    if anos: return anos
    return list(range(2000, actual+1))

def get_clima_real(lat, lon, years):
    ini=max(min(years),1940); fin=max(years)
    try:
        url=f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={ini}-01-01&end_date={fin}-12-31&daily=temperature_2m_max&timezone=auto"
        j=requests.get(url,timeout=30).json()['daily']
        por={}
        for i in range(len(j['time'])):
            try:
                y=int(j['time'][i][:4]); v=j['temperature_2m_max'][i]
                if v is None: continue
                por.setdefault(y,[]).append(v)
            except: continue
        return {y: round(sum(v)/len(v),1) for y,v in por.items() if v}
    except Exception as e:
        print(f"Clima error {e}")
        return {}

def crear_foto_real(datos, titulo, path="/tmp/cali.png"):
    plt.close('all')
    ys=sorted(datos.keys()); vals=[datos[y] for y in ys]
    plt.figure(figsize=(14,7))
    plt.plot([str(y) for y in ys], vals, marker='o', linewidth=3, color='#d62728')
    plt.title(titulo, fontsize=14, fontweight='bold')
    plt.xlabel("Año"); plt.ylabel("Temp media anual °C")
    plt.xticks(rotation=45); plt.grid(True, alpha=0.3, linestyle='--')
    # Anota el valor real encima
    for x,y in zip([str(y) for y in ys], vals):
        plt.text(x, y, str(y), fontsize=7, ha='center', va='bottom')
    plt.tight_layout(); plt.savefig(path, dpi=280); plt.close('all')
    return path

async def handle_docs(update, context):
    f=await update.message.document.get_file()
    await f.download_to_drive(f"docs/{update.message.document.file_name}")
    await update.message.reply_text(f"Guardado {update.message.document.file_name}")

async def handle_message(update, context):
    texto=update.message.text or ""
    low=texto.lower()
    if low in ["hola","buenas","hi"]:
        await update.message.reply_text("Hola! Soy Geosat V24. Dime 'temperatura Cali 2000 hasta actual con imagen' y te mando la foto real ERA5.")
        return

    try:
        quiere_visual = any(k in low for k in ["imagen","foto","grafica","gráfica","visual"])
        years = expandir_anos(texto)
        print(f"Years detectados: {years}")

        # 1. PRIMERO saca datos reales, sin llamar al LLM
        datos_reales = get_clima_real(3.4419, -76.5287, years)
        print(f"Datos reales: {datos_reales}")

        # 2. Si pide imagen y tenemos datos, MANDA FOTO DIRECTO
        if quiere_visual and datos_reales:
            foto = crear_foto_real(datos_reales, f"Temperatura media anual Cali {min(datos_reales)}-{max(datos_reales)} - ERA5 Real")
            pdfs = cargar_pdfs()
            # Ahora si llama al LLM solo para el texto que acompaña la foto
            prompt = f"Eres GEOSAT. Analiza estos datos REALES de Cali ERA5: {datos_reales}. No inventes otros. Tendencia: {datos_reales}. PDFs: {pdfs[:3000]}. Pregunta: {texto}. Explica tendencia en 3 lineas, sin tabla."
            comp = client.chat.completions.create(model="openai/gpt-oss-20b", messages=[{"role":"system","content":prompt}], temperature=0.5, max_tokens=600)
            caption = comp.choices[0].message.content[:900]

            with open(foto,'rb') as f:
                await update.message.reply_photo(photo=f.read(), caption=caption)
            return

        # Si no pide visual, respuesta normal
        pdfs=cargar_pdfs()
        prompt=f"Eres Geosat. Responde cualquier tema. Datos reales: {datos_reales} PDFs: {pdfs[:5000]} Pregunta: {texto}"
        comp=client.chat.completions.create(model="openai/gpt-oss-20b", messages=[{"role":"system","content":prompt}], temperature=0.7, max_tokens=1500)
        await update.message.reply_text(comp.choices[0].message.content[:4000])

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
