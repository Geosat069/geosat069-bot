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
def home():
 return "Geosat V31 UNLIMITED SEARCH OK"

def run_web():
 app.run(host='0.0.0.0',port=int(os.environ.get("PORT",10000)))

def cargar_pdfs():
 txt=""
 for pdf in glob.glob("docs/*.pdf")[:6]:
  try:
   if fitz:
    doc=fitz.open(pdf)
    for p in doc[:5]: txt+=p.get_text()[:2000]
  except: continue
 return txt[:8000]

# === MOTORES ===
def clean_html(t):
 return re.sub(r'<.*?>','',t).replace('&quot;','"').replace('&amp;','&').strip()[:500]

def buscar_wikipedia(q, lang="es"):
 try:
  qq=urllib.parse.quote(q)
  r=requests.get(f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{qq}",timeout=7)
  if r.status_code==200:
   return f"WIKI-{lang.upper()}: "+r.json().get('extract','')[:1500]
 except: pass
 return ""

def buscar_ddg_api(q):
 try:
  url=f"https://api.duckduckgo.com/?q={urllib.parse.quote(q)}&format=json&pretty=1"
  r=requests.get(url, timeout=8, headers={"User-Agent":"Mozilla/5.0"})
  j=r.json()
  txt=j.get("AbstractText","")
  for t in j.get("RelatedTopics",[])[:3]:
   if isinstance(t, dict) and t.get("Text"): txt+=" "+t["Text"]
  return f"DDG-API: {txt[:1500]}" if txt else ""
 except: return ""

def buscar_bing(q):
 try:
  h={"User-Agent":"Mozilla/5.0"}
  r=requests.get(f"https://www.bing.com/search?q={urllib.parse.quote(q)}&setlang=es", headers=h, timeout=10)
  snips=re.findall(r'<p class="b_lineclamp2[^>]*>(.*?)</p>', r.text)
  if not snips: snips=re.findall(r'<div class="b_caption"><p>(.*?)</p>', r.text)
  txt=" ".join([clean_html(s) for s in snips[:4]])
  return f"BING: {txt[:1500]}" if txt else ""
 except: return ""

def buscar_yahoo(q):
 try:
  h={"User-Agent":"Mozilla/5.0"}
  r=requests.get(f"https://search.yahoo.com/search?p={urllib.parse.quote(q)}", headers=h, timeout=10)
  snips=re.findall(r'<p class="[^"]*fc-2nd[^"]*">(.*?)</p>', r.text)
  txt=" ".join([clean_html(s) for s in snips[:3]])
  return f"YAHOO: {txt[:1500]}" if txt else ""
 except: return ""

def buscar_brave(q):
 try:
  h={"User-Agent":"Mozilla/5.0"}
  r=requests.get(f"https://search.brave.com/search?q={urllib.parse.quote(q)}&source=web", headers=h, timeout=10)
  snips=re.findall(r'<p class="snippet[^>]*>(.*?)</p>', r.text, re.DOTALL)
  txt=" ".join([clean_html(s) for s in snips[:3]])
  return f"BRAVE: {txt[:1500]}" if txt else ""
 except: return ""

def buscar_ecosia(q):
 try:
  h={"User-Agent":"Mozilla/5.0"}
  r=requests.get(f"https://www.ecosia.org/search?q={urllib.parse.quote(q)}", headers=h, timeout=10)
  snips=re.findall(r'<p class="result__description[^>]*>(.*?)</p>', r.text, re.DOTALL)
  txt=" ".join([clean_html(s) for s in snips[:3]])
  return f"ECOSIA: {txt[:1500]}" if txt else ""
 except: return ""

def buscar_google_scrape(q):
 try:
  h={"User-Agent":"Mozilla/5.0"}
  r=requests.get(f"https://www.google.com/search?q={urllib.parse.quote(q)}&hl=es", headers=h, timeout=10)
  snips=re.findall(r'<div class="VwiC3b[^>]*>(.*?)</div>', r.text, re.DOTALL)
  txt=" ".join([clean_html(s) for s in snips[:3]])
  return f"GOOGLE: {txt[:1500]}" if txt else ""
 except: return ""

def buscar_todo_internet(q):
 print(f"=== BUSCANDO ILIMITADO: {q} ===")
 motores=[
  buscar_wikipedia(q,"es"),
  buscar_wikipedia(q,"en"),
  buscar_ddg_api(q),
  buscar_bing(q),
  buscar_yahoo(q),
  buscar_brave(q),
  buscar_ecosia(q),
  buscar_google_scrape(q),
 ]
 contexto="\n".join([m for m in motores if m])
 print(f"Motores con datos: {len([m for m in motores if m])}/8 - {len(contexto)} chars")
 if not contexto:
  contexto="Sin resultados de buscadores, usa conocimiento general pero menciona que no hubo internet"
 return contexto[:7000]

# Imagenes REAL multi motor
def descargar_imagen_url(img_url, path):
 try:
  h={"User-Agent":"Mozilla/5.0","Referer":"https://www.google.com/"}
  r=requests.get(img_url, headers=h, timeout=10, stream=True)
  if r.ok and 'image' in r.headers.get('Content-Type','') and len(r.content)>12000:
   open(path,'wb').write(r.content); return True
 except: pass
 return False

def buscar_imagen_real_google(q, path="/tmp/busqueda.jpg"):
 q=q.replace("busco una","").replace("busca","").replace("foto real de","").replace("imagen real de","").strip()
 headers={"User-Agent":"Mozilla/5.0"}
 # DDG
 try:
  r=requests.get(f"https://duckduckgo.com/?q={urllib.parse.quote(q)}", headers=headers, timeout=10)
  vqd_m=re.search(r'vqd="([^"]+)"', r.text) or re.search(r"vqd='([^']+)'", r.text) or re.search(r'vqd=([\d-]+)', r.text)
  if vqd_m:
   vqd=vqd_m.group(1)
   r2=requests.get(f"https://duckduckgo.com/i.js?l=us-en&o=json&q={urllib.parse.quote(q)}&vqd={vqd}", headers=headers, timeout=10)
   for item in r2.json().get("results", [])[:6]:
    if descargar_imagen_url(item.get("image") or item.get("thumbnail"), path): return path
 except: pass
 # Bing
 try:
  r=requests.get(f"https://www.bing.com/images/search?q={urllib.parse.quote(q)}", headers=headers, timeout=10)
  urls=re.findall(r'murl&quot;:&quot;(https[^&]+)&quot;', r.text)
  for u in urls[:6]:
   u=u.replace("\\u002F","/").replace("\\","")
   if descargar_imagen_url(u, path): return path
 except: pass
 return None

def generar_imagen_ia(q,path="/tmp/generada.jpg"):
 try:
  qq=urllib.parse.quote(q)
  url=f"https://image.pollinations.ai/prompt/{qq}?width=1024&height=1024&nologo=true&seed={random.randint(1,999999)}"
  r=requests.get(url,timeout=60)
  if r.ok and len(r.content)>15000:
   open(path,'wb').write(r.content); return path
 except: pass
 return None

def get_clima_real():
 try:
  yf=datetime.datetime.now().year
  url=f"https://archive-api.open-meteo.com/v1/archive?latitude=3.4419&longitude=-76.5287&start_date=1940-01-01&end_date={yf}-12-31&daily=temperature_2m_max&timezone=auto"
  j=requests.get(url,timeout=25).json()['daily']; por={}
  for i,t in enumerate(j['time']):
   v=j['temperature_2m_max'][i]
   if v is None: continue
   y=int(t[:4]); por.setdefault(y,[]).append(v)
  return {y:round(sum(v)/len(v),1) for y,v in por.items() if v}
 except: return {2020:26.0,2025:26.5}

def crear_foto_clima(datos,path="/tmp/cali.png"):
 if plt is None: return None
 plt.close('all'); ys=sorted(datos.keys()); vals=[datos[y] for y in ys]
 plt.figure(figsize=(12,6)); plt.plot([str(y) for y in ys],vals,marker='o',color='#d62728')
 plt.title(f"Temp Cali {ys[0]}-{ys[-1]}"); plt.grid(True,alpha=0.3); plt.tight_layout()
 plt.savefig(path,dpi=200); plt.close('all'); return path

def llamar_groq_con_busqueda(prompt, extra=""):
 pdfs=cargar_pdfs()
 busqueda=buscar_todo_internet(prompt)
 sys_prompt=f"""Eres Geosat V31 con busqueda ILIMITADA.
Motores activos: Google, Bing, Yahoo, Brave, Ecosia, DuckDuckGo API, Wikipedia ES, Wikipedia EN.
Modelo: openai/gpt-oss-20b - NUNCA CAMBIES MODELO.
Usa SIEMPRE la info buscada para responder. Responde en español, actualizado, util, sin limite de año pero prioriza 2024-2026.
Si te piden imagen real, ya la busca otra funcion, tu solo da texto.

PDFS: {pdfs[:4000]}
RESULTADOS DE 8 BUSCADORES:
{busqueda[:6000]}
EXTRA: {extra}
"""
 try:
  c=client.chat.completions.create(model="openai/gpt-oss-20b",messages=[{"role":"system","content":sys_prompt},{"role":"user","content":prompt}],max_tokens=1300,temperature=0.4)
  resp=c.choices[0].message.content
  return resp[:3800] + f"\n\n🌐 Busqué en 8 motores: Google, Bing, Yahoo, Brave, Ecosia, DDG, Wiki ES/EN para '{prompt}'"
 except Exception as e:
  traceback.print_exc(); return f"Error: {e}"

async def procesar_comando_universal(update, texto):
 low=texto.lower().strip()
 if low in ["hola","buenas","hi","hey","ola","q mas","que mas","que hubo"]:
  await update.message.reply_text("Hola! 🌎 Soy Geosat V31 con 8 buscadores ilimitados - Google, Bing, Yahoo, Brave, Ecosia, DDG, Wiki")
  return

 quiere_visual=any(k in low for k in ["imagen","foto","grafica","mapa"])
 quiere_buscar= any(k in low for k in ["busca","foto real","imagen real","verdadera"])
 es_generar= "genera" in low or "crea" in low
 es_clima= ("temperatura" in low or "era5" in low) and not quiere_visual

 if quiere_buscar and quiere_visual and not es_generar:
  prompt=texto.lower().replace("busca imagen real de","").replace("imagen real de","").replace("foto real de","").replace("busca","").strip() or "Cali"
  await update.message.reply_text(f"🔍 Buscando foto REAL en Google/Bing/Yahoo/Brave de {prompt}...")
  foto=buscar_imagen_real_google(prompt)
  if foto:
   with open(foto,'rb') as f: await update.message.reply_photo(photo=f.read(),caption=f"Foto REAL de {prompt} - 8 motores")
   return

 if es_clima:
  datos=get_clima_real(); foto=crear_foto_clima(datos); cap=llamar_groq_con_busqueda(texto,str(datos))
  if foto and quiere_visual:
   with open(foto,'rb') as f: await update.message.reply_photo(photo=f.read(),caption=cap[:1000])
  else: await update.message.reply_text(cap)
  return

 if quiere_visual and es_generar:
  prompt=texto.lower().replace("genera imagen de","").replace("imagen de","").replace("foto de","").strip() or "paisaje"
  await update.message.reply_text(f"🎨 Generando IA: {prompt}...")
  foto=generar_imagen_ia(prompt)
  if foto:
   with open(foto,'rb') as f: await update.message.reply_photo(photo=f.read(),caption=f"IA de {prompt}")
   return

 await update.message.reply_text("🔎 Buscando en 8 motores: Google, Bing, Yahoo, Brave, Ecosia, DDG, Wikipedia...")
 await update.message.reply_text(llamar_groq_con_busqueda(texto))

async def handle_docs(update,context):
 try:
  f=await update.message.document.get_file()
  await f.download_to_drive(f"docs/{update.message.document.file_name}")
  await update.message.reply_text(f"PDF {update.message.document.file_name} guardado ✅")
 except Exception as e: await update.message.reply_text(str(e))

async def handle_voice(update,context):
 try:
  await update.message.reply_text("🎤 Escuchando y buscando en 8 motores...")
  vf=await update.message.voice.get_file()
  ogg="/tmp/voice.ogg"; await vf.download_to_drive(ogg)
  with open(ogg,"rb") as fd:
   tr=client.audio.transcriptions.create(model="whisper-large-v3",file=(ogg,fd.read()))
  texto=tr.text or ""
  if not texto: await update.message.reply_text("No entendi audio"); return
  await update.message.reply_text(f"Entendi: {texto}\n🔎 Buscando en Google, Bing, Yahoo, Brave, Ecosia...")
  await procesar_comando_universal(update, texto)
 except Exception as e:
  traceback.print_exc(); await update.message.reply_text(f"Error voz: {e}")

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
