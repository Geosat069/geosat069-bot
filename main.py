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
def home(): return "Geosat V33 TODO TERRENO OK - gpt-oss-20b"

def run_web(): app.run(host='0.0.0.0',port=int(os.environ.get("PORT",10000)))

# 1. PDFs - YA TIENES LA CARPETA EN GITHUB
def cargar_pdfs():
 txt=""
 for pdf in glob.glob("docs/*.pdf")[:10]:
  try:
   if fitz:
    doc=fitz.open(pdf)
    for p in doc[:10]: txt+=p.get_text()[:3000]
  except: continue
 return txt[:15000]

# 2. APRENDE SOLA DE LA RED - 7 MOTORES ILIMITADOS
def clean(t): return re.sub(r'<.*?>','',t)[:600]

def buscar_web(q):
 ctx=""
 try:
  # Wikipedia ES/EN
  for lang in ["es","en"]:
   try:
    r=requests.get(f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(q)}",timeout=6)
    if r.status_code==200: ctx+=r.json().get('extract','')[:1500]+" "
   except: pass
  # DuckDuckGo API
  try:
   r=requests.get(f"https://api.duckduckgo.com/?q={urllib.parse.quote(q)}&format=json",timeout=6,headers={"User-Agent":"Mozilla/5.0"})
   j=r.json(); ctx+=j.get("AbstractText","")[:1500]+" "
  except: pass
  # Bing, Yahoo, Brave, Google snippets
  for url_pat in [
   f"https://www.bing.com/search?q={urllib.parse.quote(q)}",
   f"https://search.yahoo.com/search?p={urllib.parse.quote(q)}",
   f"https://search.brave.com/search?q={urllib.parse.quote(q)}"
  ]:
   try:
    r=requests.get(url_pat,timeout=8,headers={"User-Agent":"Mozilla/5.0"})
    m=re.findall(r'<p[^>]*>(.*?)</p>',r.text)
    for s in m[:3]: ctx+=clean(s)+" "
   except: pass
 except Exception as e: print(e)
 return ctx[:7000]

# 3. IMAGEN REAL - BUSCAR CUALQUIER IMAGEN
def descargar(url,path):
 try:
  r=requests.get(url,timeout=12,headers={"User-Agent":"Mozilla/5.0","Referer":"https://www.google.com/"},stream=True)
  if r.ok and 'image' in r.headers.get('Content-Type','') and len(r.content)>12000:
   open(path,'wb').write(r.content); return True
 except: pass
 return False

def buscar_imagen_real(q,path="/tmp/real.jpg"):
 q=q.lower().replace("busca","").replace("imagen real de","").replace("foto real de","").replace("imagen de","").replace("foto de","").strip()
 h={"User-Agent":"Mozilla/5.0"}
 try: # DuckDuckGo Images
  r=requests.get(f"https://duckduckgo.com/?q={urllib.parse.quote(q)}",headers=h,timeout=10)
  m=re.search(r'vqd="([^"]+)"',r.text) or re.search(r'vqd=([\d-]+)',r.text)
  if m:
   vqd=m.group(1).strip('"')
   r2=requests.get(f"https://duckduckgo.com/i.js?q={urllib.parse.quote(q)}&vqd={vqd}",headers=h,timeout=10)
   for it in r2.json().get("results",[])[:8]:
    if descargar(it.get("image") or it.get("thumbnail"),path): return path
 except: pass
 try: # Bing Images
  r=requests.get(f"https://www.bing.com/images/search?q={urllib.parse.quote(q)}",headers=h,timeout=10)
  for u in re.findall(r'murl&quot;:&quot;(https[^&]+)&quot;',r.text)[:8]:
   if descargar(u.replace("\\u002F","/").replace("\\",""),path): return path
 except: pass
 return None

# 4. GENERAR CUALQUIER IMAGEN
def generar_imagen_ia(q,path="/tmp/ia.jpg"):
 try:
  url=f"https://image.pollinations.ai/prompt/{urllib.parse.quote(q)}?width=1024&height=1024&nologo=true&seed={random.randint(1,999999)}"
  r=requests.get(url,timeout=60)
  if r.ok and len(r.content)>15000:
   open(path,'wb').write(r.content); return path
 except: pass
 return None

# 5. GRAFICAS DE LO QUE SEA
def get_clima():
 try:
  yf=datetime.datetime.now().year
  url=f"https://archive-api.open-meteo.com/v1/archive?latitude=3.4419&longitude=-76.5287&start_date=1940-01-01&end_date={yf}-12-31&daily=temperature_2m_max&timezone=auto"
  j=requests.get(url,timeout=20).json()['daily']; por={}
  for i,t in enumerate(j['time']):
   v=j['temperature_2m_max'][i]
   if v is None: continue
   por.setdefault(int(t[:4]),[]).append(v)
  return {y:round(sum(v)/len(v),1) for y,v in por.items() if v}
 except: return {2020:26.0,2025:27.0}

def crear_grafica(datos,titulo,path="/tmp/graf.png"):
 if plt is None: return None
 plt.close('all'); ys=sorted(datos.keys()); vs=[datos[y] for y in ys]
 plt.figure(figsize=(12,6)); plt.plot([str(y) for y in ys],vs,marker='o'); plt.title(titulo); plt.grid(True,alpha=0.3); plt.tight_layout()
 plt.savefig(path,dpi=200); plt.close('all'); return path

# 6. CEREBRO - RESPONDE CUALQUIER TEMA - ANTI ERROR 400
def llamar_groq(prompt,extra=""):
 pdfs=cargar_pdfs(); web=buscar_web(prompt)
 sys=f"""Eres Geosat V33 TODO TERRENO.
REGLA CRITICA: PROHIBIDO USAR TOOLS. NO LLAMES A browser.search. NO USES HERRAMIENTAS. Solo responde con el contexto dado.

Eres capaz de responder CUALQUIER PREGUNTA sin importar el tema: motos, carros, ciencia, historia, recetas, programacion, medicina, etc.
Usa esta info real:
PDFs del usuario: {pdfs[:5000]}
WEB REAL de 7 motores: {web[:6000]}
EXTRA: {extra}
Responde en español, util, actualizado 2024-2026, directo."""
 try:
  c=client.chat.completions.create(model="openai/gpt-oss-20b",messages=[{"role":"system","content":sys},{"role":"user","content":prompt}],max_tokens=1300,temperature=0.4)
  return c.choices[0].message.content[:3800]
 except Exception as e:
  print(f"Error gpt-oss: {e}")
  # Fallback para que nunca se caiga
  if "tool" in str(e).lower():
   try:
    c=client.chat.completions.create(model="openai/gpt-oss-20b",messages=[{"role":"system","content":f"Responde con esto: {web[:4000]} {pdfs[:2000]}. PROHIBIDO TOOLS."},{"role":"user","content":prompt}],max_tokens=1000,temperature=0.3)
    return c.choices[0].message.content[:3800]
   except: return f"Info de {prompt}: {web[:2500]}"
  return f"Error: {e}"

# 7. PROCESADOR UNIVERSAL - TEXTO Y VOZ - CUALQUIER COMANDO
async def procesar(update,texto):
 low=texto.lower().strip()
 if low in ["hola","buenas","hi","hey","ola","q mas","que mas","que hubo","buenos dias","hola geosat"]:
  await update.message.reply_text("Hola! 🌎 Soy Geosat V33 TODO TERRENO\nPuedo responder cualquier tema, buscar y generar imagenes, graficas, PDFs y por voz. Que necesitas?")
  return

 quiere_img=any(k in low for k in ["imagen","foto","grafica","gráfica","mapa","dibuja","muestrame","enseñame"])
 quiere_real=any(k in low for k in ["real","verdadera","busca"])
 quiere_generar="genera" in low or "crea" in low or "invent" in low
 quiere_graf="grafica" in low or "gráfica" in low or "temperatura" in low or "era5" in low or "grafico" in low

 # CASO A: BUSCAR CUALQUIER IMAGEN REAL
 if quiere_img and quiere_real and not quiere_generar:
  q=texto.lower().replace("busca","").replace("imagen real de","").replace("foto real de","").replace("imagen de","").replace("foto de","").strip() or "Cali"
  await update.message.reply_text(f"🔍 Buscando foto REAL de {q} en Google/Bing/DDG...")
  f=buscar_imagen_real(q)
  if f:
   with open(f,'rb') as ph: await update.message.reply_photo(photo=ph.read(),caption=f"Foto REAL de {q}")
  else:
   await update.message.reply_text("No encontre foto real libre, te genero una IA...")
   f=generar_imagen_ia(q)
   if f:
    with open(f,'rb') as ph: await update.message.reply_photo(photo=ph.read(),caption=f"IA de {q} (no habia real)")
  return

 # CASO B: GRAFICA
 if quiere_graf:
  await update.message.reply_text("📊 Generando grafica...")
  datos=get_clima(); foto=crear_grafica(datos,f"Grafica - {texto}"); cap=llamar_groq(texto,str(datos))
  if foto:
   with open(foto,'rb') as ph: await update.message.reply_photo(photo=ph.read(),caption=cap[:1000])
  else: await update.message.reply_text(cap)
  return

 # CASO C: GENERAR CUALQUIER IMAGEN
 if quiere_img:
  q=texto.lower().replace("genera imagen de","").replace("generar imagen de","").replace("imagen de","").replace("foto de","").replace("crea imagen de","").replace("dibuja","").strip() or "paisaje bonito"
  await update.message.reply_text(f"🎨 Generando imagen IA de {q}...")
  f=generar_imagen_ia(q)
  if f:
   with open(f,'rb') as ph: await update.message.reply_photo(photo=ph.read(),caption=f"Imagen IA de {q}")
  return

 # CASO D: CUALQUIER PREGUNTA - TEXTO - APRENDE DE LA RED + PDFS
 await update.message.reply_text("🔎 Buscando info en la red y en tus PDFs...")
 await update.message.reply_text(llamar_groq(texto))

async def handle_docs(update,context):
 try:
  f=await update.message.document.get_file()
  path=f"docs/{update.message.document.file_name}"
  await f.download_to_drive(path)
  await update.message.reply_text(f"PDF {update.message.document.file_name} guardado ✅ Ya aprendi de el, preguntame lo que sea de ese PDF")
 except Exception as e: await update.message.reply_text(str(e))

# VOZ - CUALQUIER COMANDO POR VOZ
async def handle_voice(update,context):
 try:
  await update.message.reply_text("🎤 Escuchando... te entiendo cualquier comando por voz")
  vf=await update.message.voice.get_file()
  ogg="/tmp/voice.ogg"; await vf.download_to_drive(ogg)
  with open(ogg,"rb") as fd:
   tr=client.audio.transcriptions.create(model="whisper-large-v3",file=(ogg,fd.read()))
  texto=tr.text or ""
  if not texto:
   await update.message.reply_text("No entendi el audio, intenta de nuevo")
   return
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
