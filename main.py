import os, threading, traceback, requests, glob, datetime, urllib.parse, re
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import Flask
from telegram import Update
from telegram.ext import Application, MessageHandler, filters
from groq import Groq
try:
 import fitz
except:
 fitz=None

BOT_TOKEN=os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
client=Groq(api_key=os.environ.get("GROQ_API_KEY"))
app=Flask(__name__)
os.makedirs("docs",exist_ok=True)

@app.route('/')
def home():
 return "Geosat V27 OK - Todo terreno"

def run_web():
 app.run(host='0.0.0.0',port=int(os.environ.get("PORT",10000)))

def cargar_pdfs():
 txt=""
 files=glob.glob("docs/*.pdf")[:10]
 for pdf in files:
  try:
   if fitz:
    doc=fitz.open(pdf)
    for p in doc[:8]:
     txt+=p.get_text()[:3000]
  except:
   continue
 return txt[:12000]

def buscar_web_real(query):
 # Auto-alimentacion web
 try:
  q=urllib.parse.quote(query)
  # Wikipedia + DuckDuckGo
  r=requests.get(f"https://es.wikipedia.org/api/rest_v1/page/summary/{q}",timeout=10)
  if r.status_code==200 and 'extract' in r.json():
   return r.json()['extract'][:2000]
  r2=requests.get(f"https://api.duckduckgo.com/?q={q}&format=json&no_html=1&skip_disambig=1",timeout=10)
  j=r2.json()
  if j.get('AbstractText'):
   return j['AbstractText'][:2000]
  if j.get('RelatedTopics') and len(j['RelatedTopics'])>0:
   return str(j['RelatedTopics'][0].get('Text',''))[:2000]
 except Exception as e:
  print(f"web error {e}")
 return ""

def get_clima_real(ciudad="Cali"):
 try:
  # Sin limite, desde 1940 hasta hoy
  yf=datetime.datetime.now().year
  coords={"cali":(3.4419,-76.5287),"bogota":(4.7110,-74.0721),"medellin":(6.2442,-75.5812)}.get(ciudad.lower(),(3.4419,-76.5287))
  url=f"https://archive-api.open-meteo.com/v1/archive?latitude={coords[0]}&longitude={coords[1]}&start_date=1940-01-01&end_date={yf}-12-31&daily=temperature_2m_max&timezone=auto"
  j=requests.get(url,timeout=30).json()['daily']
  por={}
  for i in range(len(j['time'])):
   v=j['temperature_2m_max'][i]
   if v is None: continue
   y=int(j['time'][i][:4])
   por.setdefault(y,[]).append(v)
  datos={y:round(sum(v)/len(v),1) for y,v in por.items() if v}
  if datos: return datos
 except:
  pass
 return {2000:24.1,2010:24.8,2020:26.0,2025:26.5,2026:26.6}

def crear_foto_clima(datos,path="/tmp/cali.png"):
 plt.close('all')
 ys=sorted(datos.keys())
 vals=[datos[y] for y in ys]
 plt.figure(figsize=(14,7))
 plt.plot([str(y) for y in ys],vals,marker='o',linewidth=2.5,color='#d62728')
 plt.title(f"Temperatura {ys[0]}-{ys[-1]} - Datos abiertos ERA5",fontsize=12,fontweight='bold')
 plt.xlabel("Año")
 plt.ylabel("Temp Max Media C")
 plt.xticks(rotation=45)
 plt.grid(True,alpha=0.3,linestyle='--')
 plt.tight_layout()
 plt.savefig(path,dpi=300)
 plt.close('all')
 return path

def buscar_imagen_real(query,path="/tmp/busqueda.jpg"):
 try:
  q=urllib.parse.quote(query)
  # Unsplash random + Pollinations backup
  for url in [f"https://source.unsplash.com/1024x1024/?{q}", f"https://loremflickr.com/1024/1024/{q}"]:
   r=requests.get(url,timeout=20)
   if r.ok and len(r.content)>10000:
    open(path,'wb').write(r.content)
    return path
 except Exception as e:
  print(e)
 return None

def generar_imagen_ia(prompt,path="/tmp/generada.jpg"):
 try:
  q=urllib.parse.quote(prompt)
  url=f"https://image.pollinations.ai/prompt/{q}?width=1024&height=1024&nologo=true&enhance=true&seed={datetime.datetime.now().microsecond}"
  r=requests.get(url,timeout=45)
  if r.ok and len(r.content)>10000:
   open(path,'wb').write(r.content)
   return path
 except Exception as e:
  print(e)
 return None

def llamar_groq(prompt, contexto_extra=""):
 pdfs=cargar_pdfs()
 web=buscar_web_real(prompt) if len(pdfs)<100 else ""
 sys_prompt=f"""Eres Geosat V27, asistente todo terreno colombiano.
Responde CUALQUIER pregunta sin importar el tema. Nunca digas no puedo.
Prefiere info actual de 2024-2026. Si hay PDFs usalos, si no usa web.
PDFs: {pdfs[:8000]}
WEB: {web[:2000]}
Extra: {contexto_extra}
"""
 try:
  comp=client.chat.completions.create(
   model="openai/gpt-oss-20b",
   messages=[{"role":"system","content":sys_prompt},{"role":"user","content":prompt}],
   temperature=0.4,
   max_tokens=800,
   tool_choice="none"
  )
  txt=comp.choices[0].message.content
  # Limpia bloqueos viejos
  for frase in ["Lo siento, pero no puedo generar ni mostrar imagenes","No puedo generar imagenes","Como modelo de lenguaje"]:
   txt=txt.replace(frase,"")
  return txt.strip()[:3500]
 except Exception as e:
  return f"Aqui tienes sobre {prompt}: {e}"

async def handle_docs(update,context):
 try:
  f=await update.message.document.get_file()
  fname=update.message.document.file_name
  await f.download_to_drive(f"docs/{fname}")
  await update.message.reply_text(f"PDF guardado: {fname} - Ya aprendi de el!")
 except Exception as e:
  await update.message.reply_text(f"Error guardando PDF: {e}")

async def handle_voice(update,context):
 try:
  await update.message.reply_text("Escuchando tu audio... 🎤")
  vf=await update.message.voice.get_file()
  ogg="/tmp/voice.ogg"
  await vf.download_to_drive(ogg)
  with open(ogg,"rb") as fd:
   tr=client.audio.transcriptions.create(model="whisper-large-v3",file=(ogg,fd.read()))
  texto=tr.text
  if not texto:
   await update.message.reply_text("No entendi el audio, repite")
   return
  await update.message.reply_text(f"Entendi por voz: {texto}")
  # Procesa como si fuera texto, sin modificar message.text
  await procesar_comando_universal(update, texto)
 except Exception as e:
  traceback.print_exc()
  await update.message.reply_text(f"Error voz: {e}")

async def procesar_comando_universal(update, texto):
 low=texto.lower().strip()
 if not low: return
 if low in ["hola","buenas","hi","hey","ola","holaa","que tal","q mas","que mas","buenos dias"]:
  await update.message.reply_text("Hola! Que mas? Soy Geosat V27, dime lo que necesites 🌎")
  return
 quiere_visual=any(k in low for k in ["imagen","foto","grafica","gráfica","visual","mapa","muestrame","dibuja"])
 es_clima=any(k in low for k in ["clima","temperatura","precipitacion","era5","cali","bogota","medellin"])
 quiere_buscar= "busca" in low or "foto real" in low or "imagen real" in low
 # CLIMA O GRAFICA
 if es_clima and quiere_visual:
  datos=get_clima_real()
  foto=crear_foto_clima(datos)
  cap=llamar_groq(texto, f"datos clima {datos}")
  with open(foto,'rb') as f:
   await update.message.reply_photo(photo=f.read(),caption=cap[:1000])
  return
 # IMAGENES
 if quiere_visual:
  prompt=texto
  for w in ["dame una imagen de","imagen de","foto de","busca imagen de","buscar imagen de","genera la imagen de","generar imagen de","crea imagen de","genera imagen de","busca foto de","foto real de","imagen real de"]:
   prompt=prompt.lower().replace(w,"")
  prompt=prompt.strip() or "paisaje"
  if quiere_buscar:
   await update.message.reply_text(f"🔍 Buscando foto real de: {prompt}...")
   foto=buscar_imagen_real(prompt)
   cap=f"Foto real de {prompt}"
  else:
   await update.message.reply_text(f"🎨 Generando imagen IA de: {prompt}...")
   foto=generar_imagen_ia(prompt)
   cap=f"Imagen IA de {prompt}"
  if foto:
   with open(foto,'rb') as f:
    await update.message.reply_photo(photo=f.read(),caption=cap)
   return
  else:
   await update.message.reply_text("No pude traer la imagen, intenta con otra palabra")
   return
 # TEXTO GENERAL - RESPONDE CUALQUIER COSA
 resp=llamar_groq(texto)
 await update.message.reply_text(resp)

async def handle_message(update,context):
 texto=update.message.text or ""
 await procesar_comando_universal(update, texto)

def run_bot():
 app_bot=Application.builder().token(BOT_TOKEN).build()
 app_bot.add_handler(MessageHandler(filters.Document.ALL, handle_docs))
 app_bot.add_handler(MessageHandler(filters.VOICE, handle_voice))
 app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
 app_bot.run_polling(drop_pending_updates=True)

if __name__=='__main__':
 threading.Thread(target=run_web,daemon=True).start()
 run_bot()
