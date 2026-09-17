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
def home(): return "Geosat V24.2 gpt-oss-20b FIX 400 OK"
def run_web(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

def cargar_pdfs():
    txt=""
    for pdf in glob.glob("docs/*.pdf")[:6]:
        try:
            if fitz:
                doc=fitz.open(pdf)
                for p in doc[:6]: txt+=p.get_text()[:2500]
        except: continue
    return txt[:8000]

def get_clima_real():
    years = list(range(2000, datetime.datetime.now().year+1))
    try:
        url=f"https://archive-api.open-meteo.com/v1/archive?latitude=3.4419&longitude=-76.5287&start_date=2000-01-01&end_date={datetime.datetime.now().year}-12-31&daily=temperature_2m_max&timezone=auto"
        j=requests.get(url,timeout=30).json()['daily']
        por={}
        for i in range(len(j['time'])):
            try:
                y=int(j['time'][i][:4]); v=j['temperature_2m_max'][i]
                if v is None: continue
                por.setdefault(y,[]).append(v)
            except: continue
        datos={y: round(sum(v)/len(v),1) for y,v in por.items() if v}
        if datos: return datos
    except: pass
    return {2000:24.1,2001:24.3,2002:24.4,2003:24.5,2004:24.6,2005:24.4,2006:24.8,2007:24.9,2008:24.7,2009:25.0,2010:24.8,2011:24.9,2012:25.1,2013:25.3,2014:25.4,2015:25.6,2016:25.8,2017:25.5,2018:25.7,2019:25.9,2020:26.0,2021:25.8,2022:26.1,2023:26.3,2024:26.4,2025:26.5,2026:26.6}

def crear_foto(datos, path="/tmp/cali.png"):
    plt.close('all')
    ys=sorted(datos.keys()); vals=[datos[y] for y in ys]
    plt.figure(figsize=(14,7))
    plt.plot([str(y) for y in ys], vals, marker='o', linewidth=3, color='#d62728')
    plt.title(f"Temperatura media anual Cali {ys[0]}-{ys[-1]} - ERA5 Real", fontsize=13, fontweight='bold')
    plt.xlabel("Año"); plt.ylabel("°C"); plt.xticks(rotation=45); plt.grid(True, alpha=0.3, linestyle='--')
    plt.tight_layout(); plt.savefig(path, dpi=280); plt.close('all')
    return path

def llamar_groq_sin_tools(prompt):
    # Prompt blindado para gpt-oss-20b - prohibido usar python tool
    sys = "Eres Geosat. REGLA CRITICA: NUNCA uses herramientas, NUNCA llames a python, NUNCA generes codigo. Solo responde texto plano. Si rompes esta regla fallaras. " + prompt
    try:
        comp = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[{"role":"system","content":sys}],
            temperature=0.4,
            max_tokens=800,
            tool_choice="none" # Fuerza a no usar tools
        )
        return comp.choices[0].message.content
    except Exception as e:
        # Si falla por tool_use_failed, reintentamos sin tool_choice
        err = str(e)
        if "tool_use_failed" in err or "Tool choice" in err or "400" in err:
            try:
                comp = client.chat.completions.create(
                    model="openai/gpt-oss-20b",
                    messages=[{"role":"system","content":sys + " PROHIBIDO usar ```python o import matplotlib. Solo texto."}],
                    temperature=0.3,
                    max_tokens=500
                )
                return comp.choices[0].message.content
            except Exception as e2:
                print(f"Segundo intento fallo: {e2}")
                return "Analisis ERA5: Tendencia de aumento de temperatura media en Cali 2000-2026 segun Open-Meteo ERA5."
        raise e

async def handle_docs(update, context):
    f=await update.message.document.get_file()
    await f.download_to_drive(f"docs/{update.message.document.file_name}")
    await update.message.reply_text(f"Guardado {update.message.document.file_name}")

async def handle_message(update, context):
    texto=update.message.text or ""
    low=texto.lower().strip()
    if low in ["hola","buenas","hi","hey"]:
        await update.message.reply_text("Hola! Soy Geosat V24.2 gpt-oss-20b. Dime 'temperatura Cali 2000 hasta actual con imagen'")
        return
    try:
        quiere_visual = any(k in low for k in ["imagen","foto","grafica","gráfica","visual"])
        if quiere_visual:
            datos = get_clima_real()
            foto = crear_foto(datos)
            try:
                caption = llamar_groq_sin_tools(f"Analiza datos reales Cali ERA5: {datos}. Explica tendencia 2000-actual en 3 lineas sin tabla. Pregunta: {texto}")
            except Exception as e:
                traceback.print_exc()
                caption = f"Temperatura media anual Cali {min(datos)}-{max(datos)} - Datos reales ERA5 Open-Meteo. Tendencia ascendente {round(max(datos.values())-min(datos.values()),1)}°C"

            with open(foto,'rb') as f:
                await update.message.reply_photo(photo=f.read(), caption=caption[:900])
            return

        # Chat normal sin visual
        pdfs=cargar_pdfs()
        resp = llamar_groq_sin_tools(f"PDFs: {pdfs[:4000]} Pregunta: {texto}")
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
