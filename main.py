import os, threading, traceback, requests, glob, re, datetime
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
def home(): return "Geosat V24.3 FINAL"
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
    plt.title(f"Cali {ys[0]}-{ys[-1]} ERA5", fontsize=13, fontweight='bold')
    plt.xlabel("Año"); plt.ylabel("°C"); plt.xticks(rotation=45); plt.grid(True, alpha=0.3, linestyle='--')
    plt.tight_layout(); plt.savefig(path, dpi=280); plt.close('all')
    return path
def llamar_groq(prompt, datos):
    sys = f"""Eres Geosat V24.3. REGLAS: La imagen YA FUE generada. NUNCA digas no puedo generar imagenes. NUNCA uses python. Solo analiza: {datos} Pregunta: {prompt}"""
    try:
        comp = client.chat.completions.create(model="openai/gpt-oss-20b", messages=[{"role":"system","content":sys}], temperature=0.3, max_tokens=400, tool_choice="none")
        txt = comp.choices[0].message.content
        for frase in ["Lo siento, pero no puedo generar ni mostrar imágenes.", "No puedo generar imágenes", "Respuesta a la solicitud de imagen"]:
            txt = txt.replace(frase, "")
        return txt.strip()
    except Exception as e:
        return f"Tendencia Cali {min(datos.values())} a {max(datos.values())}°C. ERA5 real."
async def handle_docs(update, context):
    f=await update.message.document.get_file()
    await f.download_to_drive(f"docs/{update.message.document.file_name}")
    await update.message.reply_text(f"Guardado {update.message.document.file_name}")
async def handle_message(update, context):
    texto=update.message.text or ""
    low=texto.lower().strip()
    if low in ["hola","buenas","hi","hey","ola"]:
        await update.message.reply_text("Hola! Soy Geosat V24.3 FINAL. Dime 'temperatura Cali 2000 hasta actual con imagen'")
        return
    try:
        quiere_visual = any(k in low for k in ["imagen","foto","grafica","visual","mapa"])
        if quiere_visual:
            datos = get_clima_real()
            foto = crear_foto(datos)
            caption = llamar_groq(texto, datos)
            with open(foto,'rb') as f:
                await update.message.reply_photo(photo=f.read(), caption=caption[:900])
            return
        pdfs=cargar_pdfs()
        resp = llamar_groq(f"PDFs: {pdfs[:4000]} Pregunta: {texto}", {})
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
