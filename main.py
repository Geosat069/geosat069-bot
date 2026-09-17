import os, threading, traceback, requests, glob, datetime, urllib.parse, re, random
try:
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
except:
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
client=Groq(api_key=GROQ_KEY) if GROQ_KEY else None
app=Flask(__name__)
os.makedirs("docs",exist_ok=True)

@app.route('/')
def home(): return "Geosat V34 CLIMA REAL MUNDIAL OK"

def run_web(): app.run(host='0.0.0.0',port=int(os.environ.get("PORT",10000)))

def cargar_pdfs():
 txt=""
 for pdf in glob.glob("docs/*.pdf")[:10]:
  try:
   if fitz:
    doc=fitz.open(pdf)
    for p in doc[:10]: txt+=p.get_text()[:3000]
  except: continue
 return txt[:15000]

def clean(t): return re.sub(r'<.*?>','',t)[:600]

def buscar_web(q):
 ctx=""
 try:
  for lang in ["es","en"]:
   try:
    r=requests.get(f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(q)}",timeout=6)
    if r.status_code==200: ctx+=r.json().get('extract','')[:1200]+" "
   except: pass
  try:
   r=requests.get(f"https://api.duckduckgo.com/?q={urllib.parse.quote(q)}&format=json",timeout=6,headers={"User-Agent":"Mozilla/5.0"})
   j=r.json(); ctx+=j.get("AbstractText","")[:1200]+" "
  except: pass
  for url_pat in [f"https://www.bing.com/search?q={urllib.parse.quote(q)}",f"https://search.brave.com/search?q={urllib.parse.quote(q)}"]:
   try:
    r=requests.get(url_pat,timeout=8,headers={"User-Agent":"Mozilla/5.0"})
    m=re.findall(r'<p[^>]*>(.*?)</p>',r.text)
    for s in m[:3]: ctx+=clean(s)+" "
   except: pass
 except: pass
 return ctx[:6000]

# === NUEVO: CLIMA REAL DE CUALQUIER LUGAR DEL MUNDO ===
def obtener_coordenadas(lugar):
 try:
  url=f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(lugar)}&count=1&language=es&format=json"
  r=requests.get(url,timeout=10).json()
  if r.get("results"):
   res=r["results"][0]
   return res["latitude"], res["longitude"], f"{res['name']}, {res.get('country','')}"
 except: pass
 # fallback Cali
 return 3.44, -76.52, lugar

def obtener_clima_real_mundial(lugar):
 try:
  lat,lon,nombre = obtener_coordenadas(lugar)
  # Clima actual + pronostico 7 dias
  url=f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,rain,wind_speed_10m,weather_code&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max&timezone=auto&forecast_days=7"
  j=requests.get(url,timeout=15).json()
  cur=j.get("current",{}); daily=j.get("daily",{})

  texto=f"CLIMA REAL ACTUAL DE {nombre.upper()}:\n"
  texto+=f"Temp actual: {cur.get('temperature_2m')}°C Sensacion: {cur.get('apparent_temperature')}°C\n"
  texto+=f"Humedad: {cur.get('relative_humidity_2m')}% Viento: {cur.get('wind_speed_10m')} km/h\n"
  texto+=f"Lluvia ahora: {cur.get('precipitation')}mm Codigo clima: {cur.get('weather_code')}\n"
  texto+="Pronostico 7 dias:\n"
  for i in range(min(7,len(daily.get('time',[])))):
   texto+=f"{daily['time'][i]}: Max {daily['temperature_2m_max'][i]}°C Min {daily['temperature_2m_min'][i]}°C Lluvia {daily['precipitation_sum'][i]}mm\n"

  # Datos para grafica
  datos_hist={}
  try:
   yf=datetime.datetime.now().year
   url2=f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date=1940-01-01&end_date={yf}-12-31&daily=temperature_2m_max&timezone=auto"
   j2=requests.get(url2,timeout=20).json()['daily']
   for i,t in enumerate(j2['time']):
    v=j2['temperature_2m_max'][i]
    if v is None: continue
    y=int(t[:4]); datos_hist.setdefault(y,[]).append(v)
   datos_hist={y:round(sum(v)/len(v),1) for y,v in datos_hist.items() if v}
  except: datos_hist={2020:26,2025:27}

  return texto, datos_hist, nombre, lat, lon
 except Exception as e:
  print(f"Error clima: {e}"); return f"Error clima {lugar}: {e}", {2020:26,2025:27}, lugar, 3.44, -76.52

def crear_grafica_clima(datos,titulo,path="/tmp/clima.png"):
 if plt is None: return None
 try:
  plt.close('all'); ys=sorted(datos.keys()); vs=[datos[y] for y in ys]
  plt.figure(figsize=(12,6)); plt.plot([str(y) for y in ys],vs,marker='o',color='#1f77b4')
  plt.title(f"Temperatura historica {titulo} {ys[0]}-{ys[-1]}"); plt.grid(True,alpha=0.3); plt.tight_layout()
  plt.savefig(path,dpi=200); plt.close('all'); return path
 except: return None

def descargar(url,path):
 try:
  r=requests.get(url,timeout=12,headers={"User-Agent":"Mozilla/5.0"},stream=True)
  if r.ok and 'image' in r.headers.get('Content-Type','') and len(r.content)>12000:
   open(path,'wb').write(r.content); return True
 except: pass
 return False

def buscar_imagen_real(q,path="/tmp/real.jpg"):
 q=q.lower().replace("busca","").replace("imagen real de","").replace("foto real de","").strip()
 h={"User-Agent":"Mozilla/5.0"}
 try:
  r=requests.get(f"https://duckduckgo.com/?q={urllib.parse.quote(q)}",headers=h,timeout=10)
  m=re.search(r'vqd="([^"]+)"',r.text) or re.search(r'vqd=([\d-]+)',r.text)
  if m:
   vqd=m.group(1).strip('"')
   r2=requests.get(f"https://duckduckgo.com/i.js?q={urllib.parse.quote(q)}&vqd={vqd}",headers=h,timeout=10)
   for it in r2.json().get("results",[])[:8]:
    if descargar(it.get("image") or it.get("thumbnail"),path): return path
 except: pass
 try:
  r=requests.get(f"https://www.bing.com/images/search?q={urllib.parse.quote(q)}",headers=h,timeout=10)
  for u in re.findall(r'murl&quot;:&quot;(https[^&]+)&quot;',r.text)[:8]:
   if descargar(u.replace("\\u002F","/").replace("\\",""),path): return path
 except: pass
 return None

def generar_imagen_ia(q,path="/tmp/ia.jpg"):
 try:
  url=f"https://image.pollinations.ai/prompt/{urllib.parse.quote(q)}?width=1024&height=1024&nologo=true&seed={random.randint(1,999999)}"
  r=requests.get(url,timeout=60)
  if r.ok and len(r.content)>15000:
   open(path,'wb').write(r.content); return path
 except: pass
 return None

def llamar_groq(prompt,extra="",web_extra=""):
 pdfs=cargar_pdfs(); web=buscar_web(prompt)
 if web_extra: web = web_extra + "\n" + web
 sys=f"""Eres Geosat V34 CLIMA REAL MUNDIAL.
REGLA: PROHIBIDO USAR TOOLS. NO LLAMES A browser.search. Responde solo con contexto dado.
Puedes responder CUALQUIER tema. Si es clima, USA LOS DATOS REALES DE LA API que te doy en EXTRA, no inventes tabla tipica.
PDFs: {pdfs[:5000]}
WEB: {web[:5000]}
DATOS REALES CLIMA/OTROS: {extra[:6000]}
Responde español util, con datos reales actuales si es clima."""
 try:
  c=client.chat.completions.create(model="openai/gpt-oss-20b",messages=[{"role":"system","content":sys},{"role":"user","content":prompt}],max_tokens=1400,temperature=0.35)
  return c.choices[0].message.content[:4000]
 except Exception as e:
  print(e)
  if "tool" in str(e).lower():
   try:
    c=client.chat.completions.create(model="openai/gpt-oss-20b",messages=[{"role":"system","content":f"Usa esto: {extra[:5000]} {web[:3000]} PROHIBIDO TOOLS"},{"role":"user","content":prompt}],max_tokens=1200,temperature=0.3)
    return c.choices[0].message.content[:3800]
   except: return f"{extra[:3000]}"
  return f"Error: {e}"

async def procesar(update,texto):
 low=texto.lower().strip()
 if low in ["hola","buenas","hi","hey","ola","q mas","que mas","que hubo","buenos dias"]:
  await update.message.reply_text("Hola! 🌎 Geosat V34 con clima REAL mundial, imagenes reales, IA, PDFs y voz. Preguntame clima de cualquier ciudad del mundo!")
  return

 es_clima=any(k in low for k in ["clima","tiempo","temperatura","lluvia","pronostico","pronóstico","humedad","viento","era5","estado del clima"])
 quiere_img=any(k in low for k in ["imagen","foto","grafica","gráfica","mapa","dibuja"])
 quiere_real=any(k in low for k in ["real","verdadera","busca"])
 quiere_generar="genera" in low or "crea" in low

 # CLIMA REAL MUNDIAL - PRIORIDAD
 if es_clima:
  # extrae lugar
  lugar=texto.lower().replace("estado del clima de","").replace("clima de","").replace("tiempo de","").replace("temperatura de","").replace("pronostico de","").replace("clima en","").replace("estado del clima","").strip() or "Cali"
  lugar=lugar.replace("?","").strip()
  if len(lugar)<2: lugar="Cali"
  await update.message.reply_text(f"🌦️ Consultando clima REAL de {lugar} con satelite...")
  clima_txt, hist, nombre, lat, lon = obtener_clima_real_mundial(lugar)
  foto=crear_grafica_clima(hist,nombre) if quiere_img or "grafica" in low or True else None
  cap=llamar_groq(texto, extra=clima_txt, web_extra=f"Coordenadas {nombre} {lat},{lon}")
  if foto and quiere_img:
   with open(foto,'rb') as ph: await update.message.reply_photo(photo=ph.read(),caption=cap[:1000])
  else:
   # si pide grafica o si no, manda grafica + texto siempre para clima
   if foto:
    with open(foto,'rb') as ph: await update.message.reply_photo(photo=ph.read(),caption=f"Historico {nombre}")
   await update.message.reply_text(cap)
  return

 if quiere_img and quiere_real and not quiere_generar:
  q=texto.lower().replace("imagen real de","").replace("foto real de","").replace("busca","").strip() or "Cali"
  await update.message.reply_text(f"🔍 Buscando foto REAL de {q}...")
  f=buscar_imagen_real(q)
  if f:
   with open(f,'rb') as ph: await update.message.reply_photo(photo=ph.read(),caption=f"Foto REAL de {q}")
  else:
   f=generar_imagen_ia(q)
   if f:
    with open(f,'rb') as ph: await update.message.reply_photo(photo=ph.read(),caption=f"IA de {q}")
  return

 if quiere_img:
  q=texto.lower().replace("genera imagen de","").replace("imagen de","").replace("foto de","").strip() or "paisaje"
  await update.message.reply_text(f"🎨 Generando {q}...")
  f=generar_imagen_ia(q)
  if f:
   with open(f,'rb') as ph: await update.message.reply_photo(photo=ph.read(),caption=f"IA {q}")
  return

 await update.message.reply_text("🔎 Buscando en red y PDFs...")
 await update.message.reply_text(llamar_groq(texto))

async def handle_docs(update,context):
 try:
  f=await update.message.document.get_file()
  await f.download_to_drive(f"docs/{update.message.document.file_name}")
  await update.message.reply_text(f"PDF {update.message.document.file_name} guardado ✅ Ya aprendi")
 except Exception as e: await update.message.reply_text(str(e))

async def handle_voice(update,context):
 try:
  await update.message.reply_text("🎤 Escuchando comando por voz...")
  vf=await update.message.voice.get_file()
  ogg="/tmp/voice.ogg"; await vf.download_to_drive(ogg)
  with open(ogg,"rb") as fd:
   tr=client.audio.transcriptions.create(model="whisper-large-v3",file=(ogg,fd.read()))
  texto=tr.text or ""
  if not texto: return
  await update.message.reply_text(f"Entendi: {texto}")
  await procesar(update,texto)
 except Exception as e:
  traceback.print_exc(); await update.message.reply_text(f"Error voz: {e}")

async def handle_message(update,context):
 await procesar(update, update.message.text or "")

def run_bot():
 app_bot=Application.builder().token(BOT_TOKEN).build()
 app_bot.add_handler(MessageHandler(filters.Document.ALL, handle_docs))
 app_bot.add_handler(MessageHandler(filters.VOICE, handle_voice))
 app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
 app_bot.run_polling(drop_pending_updates=True)

if __name__=='__main__':
 threading.Thread(target=run_web,daemon=True).start()
 run_bot()
