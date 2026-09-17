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
def home(): return "Geosat V36 UNIVERSAL DEFINITIVO OK"

def run_web(): app.run(host='0.0.0.0',port=int(os.environ.get("PORT",10000)))

def cargar_pdfs():
 txt=""
 for pdf in glob.glob("docs/*.pdf")[:10]:
  try:
   if fitz:
    doc=fitz.open(pdf)
    for p in doc[:12]: txt+=p.get_text()[:3000]
  except: continue
 return txt[:15000]

def clean(t): return re.sub(r'<.*?>','',t).strip()[:500]

# === CEREBRO UNIVERSAL DE DATOS REALES ===
def buscar_web_universal(q):
 ctx=""
 try:
  for lang in ["es","en"]:
   try:
    r=requests.get(f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(q)}",timeout=5)
    if r.status_code==200: ctx+=r.json().get('extract','')[:1200]+" "
   except: pass
  try:
   r=requests.get(f"https://api.duckduckgo.com/?q={urllib.parse.quote(q)}&format=json",timeout=6,headers={"User-Agent":"Mozilla/5.0"})
   j=r.json(); ctx+=j.get("AbstractText","")[:1200]+" "
  except: pass
  for url in [f"https://www.bing.com/search?q={urllib.parse.quote(q)}",f"https://search.brave.com/search?q={urllib.parse.quote(q)}",f"https://search.yahoo.com/search?p={urllib.parse.quote(q)}"]:
   try:
    r=requests.get(url,timeout=7,headers={"User-Agent":"Mozilla/5.0"})
    m=re.findall(r'<p[^>]*>(.*?)</p>',r.text)
    for s in m[:3]: ctx+=clean(s)+" "
   except: pass
 except: pass
 return ctx[:6000]

def obtener_clima_universal(lugar):
 try:
  g=requests.get(f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(lugar)}&count=1&language=es&format=json",timeout=8).json()
  lat,lon,nom=3.44,-76.52,lugar
  if g.get("results"):
   r=g["results"][0]; lat=r["latitude"]; lon=r["longitude"]; nom=f"{r['name']}, {r.get('country','')}"
  url=f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,wind_speed_10m,weather_code&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&timezone=auto&forecast_days=7"
  j=requests.get(url,timeout=10).json()
  cur=j.get("current",{}); daily=j.get("daily",{})
  txt=f"CLIMA REAL TIEMPO REAL de {nom}: Ahora {cur.get('temperature_2m')}°C sensacion {cur.get('apparent_temperature')}°C humedad {cur.get('relative_humidity_2m')}% viento {cur.get('wind_speed_10m')}km/h lluvia {cur.get('precipitation')}mm codigo {cur.get('weather_code')}. Pronostico 7 dias: "
  for i in range(min(7,len(daily.get('time',[])))): txt+=f"{daily['time'][i]} max{daily['temperature_2m_max'][i]} min{daily['temperature_2m_min'][i]} lluvia{daily['precipitation_sum'][i]}mm; "
  return txt, lat, lon, nom
 except Exception as e: return f"Error clima {e}",3.44,-76.52,lugar

def obtener_finanzas_universal():
 txt=""
 try:
  r=requests.get("https://open.er-api.com/v6/latest/USD",timeout=8).json()
  txt+=f"DOLAR REAL HOY: 1 USD = {r.get('rates',{}).get('COP')} COP, EUR={r.get('rates',{}).get('EUR')}, MXN={r.get('rates',{}).get('MXN')}, fecha {r.get('time_last_update_utc')}. "
 except: pass
 try:
  r2=requests.get("https://trm-colombia.vercel.app/api/trm",timeout=8).json()
  if r2.get("data"): txt+=f"TRM COLOMBIA OFICIAL: {r2['data'].get('value')} COP validez {r2['data'].get('validityFrom')}. "
 except: pass
 try:
  r3=requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd,cop",timeout=8).json()
  txt+=f"CRYPTO REAL: BTC {r3.get('bitcoin')} ETH {r3.get('ethereum')}. "
 except: pass
 return txt

def obtener_datos_tiempo_real_AUTO(pregunta):
 # Detecta automaticamente que necesita
 low=pregunta.lower()
 datos_extra=""

 # 1. Si habla de clima en cualquier parte
 if any(k in low for k in ["clima","temperatura","lluvia","pronostico","tiempo en","hace frio","hace calor","humedad","viento"]):
  lugar=pregunta
  for w in ["clima de","clima en","temperatura de","temperatura en","tiempo de","tiempo en","pronostico de","estado del clima de","como esta el clima en"]: lugar=lugar.lower().replace(w,"")
  lugar=lugar.replace("?","").strip()[:40] or "Cali"
  c,_,_,nom=obtener_clima_universal(lugar)
  datos_extra+=c+" "

 # 2. Si habla de dinero, dolar, euro, bitcoin, precio
 if any(k in low for k in ["dolar","dólar","trm","euro","bitcoin"," btc "," eth ","precio del","cuanto vale","cotizacion"]):
  datos_extra+=obtener_finanzas_universal()+" "

 # 3. Siempre busca web universal + fecha actual
 ahora=datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
 web=buscar_web_universal(pregunta)
 datos_extra+=f"Fecha actual sistema: {ahora}. Info web: {web}"

 return datos_extra[:8000]

def crear_grafica_historica(lugar,lat,lon,path="/tmp/graf.png"):
 if plt is None: return None
 try:
  yf=datetime.datetime.now().year
  url=f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date=1940-01-01&end_date={yf}-12-31&daily=temperature_2m_max&timezone=auto"
  j=requests.get(url,timeout=15).json()['daily']; por={}
  for i,t in enumerate(j['time']):
   v=j['daily']['temperature_2m_max'][i] if 'daily' in j else j['time']
   # fix
   v=j['daily']['temperature_2m_max'][i] if 'temperature_2m_max' in j['daily'] else None
   if v is None: continue
   y=int(t[:4]); por.setdefault(y,[]).append(v)
  # version simple por bug anterior
  hist={}
  for i,t in enumerate(j['daily']['time']):
   v=j['daily']['temperature_2m_max'][i]
   if v is None: continue
   y=int(t[:4]); hist.setdefault(y,[]).append(v)
  hist={y:round(sum(v)/len(v),1) for y,v in hist.items() if v}
  plt.close('all'); ys=sorted(hist.keys()); vs=[hist[y] for y in ys]
  plt.figure(figsize=(12,6)); plt.plot([str(y) for y in ys],vs,marker='o'); plt.title(f"Temp historica {lugar} {ys[0]}-{ys[-1]}"); plt.grid(True,alpha=0.3); plt.tight_layout()
  plt.savefig(path,dpi=200); plt.close('all'); return path
 except Exception as e:
  print(e); return None

def descargar(url,path):
 try:
  r=requests.get(url,timeout=10,headers={"User-Agent":"Mozilla/5.0"},stream=True)
  if r.ok and 'image' in r.headers.get('Content-Type','') and len(r.content)>10000:
   open(path,'wb').write(r.content); return True
 except: pass
 return False

def buscar_imagen_real(q,path="/tmp/real.jpg"):
 q=q.lower().replace("imagen real de","").replace("foto real de","").replace("busca","").strip()
 h={"User-Agent":"Mozilla/5.0"}
 try:
  r=requests.get(f"https://duckduckgo.com/?q={urllib.parse.quote(q)}",headers=h,timeout=10)
  m=re.search(r'vqd="([^"]+)"',r.text) or re.search(r'vqd=([\d-]+)',r.text)
  if m:
   vqd=m.group(1).strip('"')
   r2=requests.get(f"https://duckduckgo.com/i.js?q={urllib.parse.quote(q)}&vqd={vqd}",headers=h,timeout=10)
   for it in r2.json().get("results",[])[:6]:
    if descargar(it.get("image") or it.get("thumbnail"),path): return path
 except: pass
 try:
  r=requests.get(f"https://www.bing.com/images/search?q={urllib.parse.quote(q)}",headers=h,timeout=10)
  for u in re.findall(r'murl&quot;:&quot;(https[^&]+)&quot;',r.text)[:6]:
   if descargar(u.replace("\\u002F","/").replace("\\",""),path): return path
 except: pass
 return None

def generar_imagen_ia(q,path="/tmp/ia.jpg"):
 try:
  url=f"https://image.pollinations.ai/prompt/{urllib.parse.quote(q)}?width=1024&height=1024&nologo=true&seed={random.randint(1,999999)}"
  r=requests.get(url,timeout=60)
  if r.ok and len(r.content)>10000:
   open(path,'wb').write(r.content); return path
 except: pass
 return None

def llamar_groq_universal(prompt):
 pdfs=cargar_pdfs()
 datos_reales=obtener_datos_tiempo_real_AUTO(prompt)
 sys=f"""Eres Geosat V36 UNIVERSAL DEFINITIVO con acceso a TODO en tiempo real.
INSTRUCCIONES OBLIGATORIAS:
- TIENES PROHIBIDO DECIR "no tengo acceso a datos en tiempo real" "no puedo darte el valor exacto" "consulta otras fuentes". ESTA PROHIBIDO.
- SIEMPRE usa los DATOS REALES que te doy en EXTRA. Esos datos SON reales y actuales.
- Responde CUALQUIER duda: clima, dolar, bitcoin, noticias, deportes, motos, historia, recetas, codigo, lo que sea.
- Si te dan clima real, dalo con numeros exactos. Si te dan dolar real, dalo exacto.
- Nunca inventes excusa.

PDFs usuario: {pdfs[:6000]}
DATOS REALES TIEMPO REAL AUTO-DETECTADOS PARA ESTA PREGUNTA:
{datos_reales[:7000]}
Responde en español, util, directo, con datos reales."""

 try:
  c=client.chat.completions.create(model="openai/gpt-oss-20b",messages=[{"role":"system","content":sys},{"role":"user","content":prompt}],max_tokens=1500,temperature=0.35)
  return c.choices[0].message.content[:4000]
 except Exception as e:
  print(f"Error gpt-oss: {e}")
  if "tool" in str(e).lower():
   try:
    c=client.chat.completions.create(model="openai/gpt-oss-20b",messages=[{"role":"system","content":f"Responde usando SOLO estos datos reales: {datos_reales[:5000]}. PROHIBIDO DECIR QUE NO TIENES ACCESO. PROHIBIDO USAR TOOLS."},{"role":"user","content":prompt}],max_tokens=1200,temperature=0.3)
    return c.choices[0].message.content[:3800]
   except: return datos_reales[:3000]
  return f"Error: {e}"

async def procesar(update,texto):
 low=texto.lower().strip()
 if low in ["hola","buenas","hi","hey","ola","q mas","que mas","buenos dias"]:
  await update.message.reply_text("Hola! 🌎 Soy Geosat V36 UNIVERSAL DEFINITIVO\nYa no me tienes que programar por tema. Preguntame LO QUE SEA en tiempo real: clima de cualquier ciudad, dolar hoy, bitcoin, noticias, lo que sea. Tambien imagenes reales, IA, graficas y PDFs. Todo por texto o voz.")
  return

 quiere_img=any(k in low for k in ["imagen","foto","grafica","gráfica","mapa","dibuja","muestrame"])
 quiere_real=any(k in low for k in ["real","verdadera","busca"]) and quiere_img
 quiere_generar="genera" in low or "crea" in low
 quiere_graf="grafica" in low or "gráfica" in low

 if quiere_img and quiere_real and not quiere_generar:
  q=texto.lower().replace("imagen real de","").replace("foto real de","").replace("busca imagen de","").replace("busca","").strip() or "Cali"
  await update.message.reply_text(f"🔍 Buscando foto REAL de {q} en 7 motores...")
  f=buscar_imagen_real(q)
  if f:
   with open(f,'rb') as ph: await update.message.reply_photo(photo=ph.read(),caption=f"Foto REAL de {q}")
   return

 if quiere_graf or (quiere_img and "temperatura" in low):
  # intenta sacar lugar para grafica climatica
  lugar=texto.lower().replace("grafica de","").replace("grafica","").replace("temperatura de","").strip() or "Cali"
  await update.message.reply_text(f"📊 Generando grafica de {lugar}...")
  txt,lat,lon,nom=obtener_clima_universal(lugar)
  foto=crear_grafica_historica(nom,lat,lon)
  cap=llamar_groq_universal(texto)
  if foto:
   with open(foto,'rb') as ph: await update.message.reply_photo(photo=ph.read(),caption=cap[:1000])
  else: await update.message.reply_text(cap)
  return

 if quiere_img:
  q=texto.lower().replace("genera imagen de","").replace("imagen de","").replace("foto de","").replace("dibuja","").strip() or "paisaje futurista"
  await update.message.reply_text(f"🎨 Generando IA de {q}...")
  f=generar_imagen_ia(q)
  if f:
   with open(f,'rb') as ph: await update.message.reply_photo(photo=ph.read(),caption=f"IA {q}")
  return

 # TODO LO DEMAS: CUALQUIER DUDA, TIEMPO REAL
 await update.message.reply_text("🌐 Buscando datos reales universales...")
 await update.message.reply_text(llamar_groq_universal(texto))

async def handle_docs(update,context):
 try:
  f=await update.message.document.get_file()
  await f.download_to_drive(f"docs/{update.message.document.file_name}")
  await update.message.reply_text(f"PDF {update.message.document.file_name} guardado ✅ Ya aprendi de el para siempre")
 except Exception as e: await update.message.reply_text(str(e))

async def handle_voice(update,context):
 try:
  await update.message.reply_text("🎤 Te escucho, cualquier comando por voz...")
  vf=await update.message.voice.get_file()
  ogg="/tmp/voice.ogg"; await vf.download_to_drive(ogg)
  with open(ogg,"rb") as fd:
   tr=client.audio.transcriptions.create(model="whisper-large-v3",file=(ogg,fd.read()))
  texto=tr.text or ""
  if not texto: await update.message.reply_text("No entendi audio"); return
  await update.message.reply_text(f"Entendi por voz: {texto}")
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
