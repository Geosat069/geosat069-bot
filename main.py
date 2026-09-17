import os, threading, traceback, requests, glob, datetime, urllib.parse
try:
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
except Exception as e:
 print(f"matplotlib no cargó: {e}")
 plt=None

from flask import Flask
from telegram import Update
from telegram.ext import Application, MessageHandler, filters
from groq import Groq
try:
 import fitz
except:
 fitz=None

BOT_TOKEN=os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
GROQ_KEY=os.environ.get("GROQ_API_KEY")

if not BOT_TOKEN:
 print("ERROR FATAL: No hay BOT_TOKEN en Render")
if not GROQ_KEY:
 print("ERROR FATAL: No hay GROQ_API_KEY en Render")

client=Groq(api_key=GROQ_KEY) if GROQ_KEY else None
app=Flask(__name__)
os.makedirs("docs",exist_ok=True)

@app.route('/')
def home():
 return "Geosat V28.1 OK"

def run_web():
 app.run(host='0.0.0.0',port=int(os.environ.get("PORT",10000)))

def cargar_pdfs():
 txt=""
 for pdf in glob.glob("docs/*.pdf")[:10]:
  try:
   if fitz:
    doc=fitz.open(pdf)
    for p in doc[:8]:
     txt+=p.get_text()[:3000]
  except: continue
 return txt[:12000]

def buscar_web_real(q):
 info=""
 try:
  qq=urllib.parse.quote(q)
  r=requests.get(f"https://es.wikipedia.org/api/rest_v1/page/summary/{qq}",timeout=8)
  if r.status_code==200:
   info+=r.json().get('extract','')
 except: pass
 return info[:2500]

def get_clima_real():
 try:
  yf=datetime.datetime.now().year
  url=f"https://archive-api.open-meteo.com/v1/archive?latitude=3.4419&longitude=-76.5287&start_date=1940-01-01&end_date={yf}-12-31&daily=temperature_2m_max&timezone=auto"
  j=requests.get(url,timeout=25).json()['daily']
  por={}
  for i,t in enumerate(j['time']):
   v=j['temperature_2m_max'][i]
   if v is None: continue
   y=int(t[:4])
   por.setdefault(y,[]).append(v)
  return {y:round(sum(v)/len(v),1) for y,v in por.items() if v}
 except: return {2020:26.0,2025:26.5}

def crear_foto_clima(datos,path="/tmp/cali.png"):
 if plt is None: return None
 plt.close('all')
 ys=sorted(datos.keys())
 vals=[datos[y] for y in ys]
 plt.figure(figsize=(12,6))
 plt.plot([str(y) for y in ys],vals,marker='o',color='#d62728')
 plt.title(f"Temperatura {ys[0]}-{ys[-1]}")
 plt.grid(True,alpha=0.3)
 plt.tight_layout()
 plt.savefig(path,dpi=200)
 plt.close('all')
 return path

def buscar_imagen_real(q,path="/tmp/busqueda.jpg"):
 try:
  qq=urllib.parse.quote(q)
  r=requests.get(f"https://source.unsplash.com/1024x1024/?{qq}",timeout=20,allow_redirects=True)
  if r.ok and len(r.content)>10000:
   open(path,'wb').write(r.content)
   return path
 except: pass
 return None

def generar_imagen_ia(q,path="/tmp/generada.jpg"):
 try:
  qq=urllib.parse.quote(q)
  url=f"https://image.pollinations.ai/prompt/{qq}?width=1024&height=1024&nologo=true&seed={datetime.datetime.now().microsecond}"
  r=requests.get(url,timeout=60)
  if r.ok and len(r.content)>15000:
   open(path,'wb').write(r.content)
   return path
 except: pass
 return None

def llamar_groq(prompt, extra=""):
 pdfs=cargar_pdfs()
 web=buscar_web_real(prompt)
 sys=f"Eres Geosat V28.1 modelo openai/gpt-oss-20b, responde TODO tema, prefiere info 2024-2026. PDFs:{pdfs[:6000]} WEB:{web[:2000]} Extra:{extra}"
 try:
  c=client.chat.completions.create(model="openai/gpt-oss-20b",messages=[{"role":"system","content":sys},{"role":"user","content":prompt}],max_tokens=1000,temperature=0.45)
  return c.choices[0].message.content[:3800]
 except Exception as e:
  traceback.print_exc()
  return f"Error Groq: {e}"

async def procesar_comando_universal(update, texto):
 low=texto.lower().strip()
 if low in ["hola","buenas","hi","hey","ola","q mas","que mas"]:
  await update.message.reply_text("Hola! Que mas? En que te ayudo? 🌎")
  return
 quiere_visual=any(k in low for k in ["imagen","foto","grafica","gráfica","mapa","muestrame","dibuja","foto real","imagen real"])
 quiere_buscar="busca" in low or "foto real" in low
 es_clima="temperatura" in low or "era5" in low or low=="cali"

 if quiere_buscar and quiere_visual:
  prompt=texto.lower().replace("busca imagen real de","").replace("busca imagen de","").replace("busca foto de","").replace("busca","").strip() or "Cali"
  await update.message.reply_text(f"🔍 Buscando foto real de {prompt}...")
  foto=buscar_imagen_real(prompt)
  if foto:
   with open(foto,'rb') as f: await update.message.reply_photo(photo=f.read(),caption=f"Foto real de {prompt}")
   return

 if es_clima and quiere_visual:
  datos=get_clima_real()
  foto=crear_foto_clima(datos)
  cap=llamar_groq(texto,str(datos))
  if foto:
   with open(foto,'rb') as f: await update.message.reply_photo(photo=f.read(),caption=cap[:1000])
  else: await update.message.reply_text(cap)
  return

 if quiere_visual:
  prompt=texto.lower().replace("genera imagen de","").replace("imagen de","").replace("foto de","").strip() or "paisaje"
  await update.message.reply_text(f"🎨 Generando IA: {prompt}...")
  foto=generar_imagen_ia(prompt)
  if foto:
   with open(foto,'rb') as f: await update.message.reply_photo(photo=f.read(),caption=f"Imagen IA de {prompt}")
   return

 await update.message.reply_text(llamar_groq(texto))

async def handle_docs(update,context):
 try:
  f=await update.message.document.get_file()
  await f.download_to_drive(f"docs/{update.message.document.file_name}")
  await update.message.reply_text("PDF guardado ✅")
 except Exception as e: await update.message.reply_text(str(e))

async def handle_voice(update,context):
 try:
  await update.message.reply_text("Escuchando... 🎤")
  vf=await update.message.voice.get_file()
  ogg="/tmp/voice.ogg"
  await vf.download_to_drive(ogg)
  with open(ogg,"rb") as fd:
   tr=client.audio.transcriptions.create(model="whisper-large-v3",file=(ogg,fd.read()))
  texto=tr.text or ""
  await update.message.reply_text(f"Entendi: {texto}")
  await procesar_comando_universal(update, texto)
 except Exception as e:
  traceback.print_exc()
  await update.message.reply_text(f"Error voz: {e}")

async def handle_message(update,context):
 await procesar_comando_universal(update, update.message.text or "")

def run_bot():
 app_bot=Application.builder().token(BOT_TOKEN).build()
 app_bot.add_handler(MessageHandler(filters.Document.ALL, handle_docs))
 app_bot.add_handler(MessageHandler(filters.VOICE, handle_voice))
 app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
 app_bot.run_polling(drop_pending_updates=True)

if __name__=='__main__':
 threading.Thread(target=run_web,daemon=True).start()
 run_bot()
