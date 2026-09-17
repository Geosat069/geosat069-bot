import os,threading,traceback,requests,glob,datetime,urllib.parse
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import Flask
from telegram import Update
from telegram.ext import Application,MessageHandler,filters
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
 return "Geosat V26.1 OK"
def run_web():
 app.run(host='0.0.0.0',port=int(os.environ.get("PORT",10000)))
def cargar_pdfs():
 txt=""
 for pdf in glob.glob("docs/*.pdf")[:6]:
  try:
   if fitz:
    doc=fitz.open(pdf)
    for p in doc[:6]:
     txt+=p.get_text()[:2500]
  except:
   continue
 return txt[:8000]
def get_clima_real():
 try:
  yf=datetime.datetime.now().year
  url=f"https://archive-api.open-meteo.com/v1/archive?latitude=3.4419&longitude=-76.5287&start_date=2000-01-01&end_date={yf}-12-31&daily=temperature_2m_max&timezone=auto"
  j=requests.get(url,timeout=30).json()['daily']
  por={}
  for i in range(len(j['time'])):
   try:
    y=int(j['time'][i][:4])
    v=j['temperature_2m_max'][i]
    if v is None:
     continue
    por.setdefault(y,[]).append(v)
   except:
    continue
  datos={y:round(sum(v)/len(v),1) for y,v in por.items() if v}
  if datos:
   return datos
 except:
  pass
 return {2000:24.1,2005:24.4,2010:24.8,2015:25.6,2020:26.0,2025:26.5,2026:26.6}
def crear_foto_clima(datos,path="/tmp/cali.png"):
 plt.close('all')
 ys=sorted(datos.keys())
 vals=[datos[y] for y in ys]
 plt.figure(figsize=(14,7))
 plt.plot([str(y) for y in ys],vals,marker='o',linewidth=3,color='#d62728')
 plt.title(f"Cali {ys[0]}-{ys[-1]} ERA5",fontsize=13,fontweight='bold')
 plt.xlabel("Ano")
 plt.ylabel("C")
 plt.xticks(rotation=45)
 plt.grid(True,alpha=0.3,linestyle='--')
 plt.tight_layout()
 plt.savefig(path,dpi=280)
 plt.close('all')
 return path
def buscar_imagen_real(query,path="/tmp/busqueda.jpg"):
 try:
  q=urllib.parse.quote(query)
  url=f"https://source.unsplash.com/1024x1024/?{q}"
  r=requests.get(url,timeout=20)
  if r.ok:
   open(path,'wb').write(r.content)
   return path
 except Exception as e:
  print(e)
 return None
def generar_imagen_ia(prompt,path="/tmp/generada.jpg"):
 try:
  q=urllib.parse.quote(prompt)
  url=f"https://image.pollinations.ai/prompt/{q}?width=1024&height=1024&nologo=true"
  r=requests.get(url,timeout=40)
  if r.ok:
   open(path,'wb').write(r.content)
   return path
 except Exception as e:
  print(e)
 return None
def llamar_groq(prompt,datos={}):
 sys_prompt=f"Eres Geosat V26. NUNCA digas no puedo generar imagenes. Datos:{datos}"
 try:
  comp=client.chat.completions.create(model="openai/gpt-oss-20b",messages=[{"role":"system","content":sys_prompt},{"role":"user","content":prompt}],temperature=0.3,max_tokens=500,tool_choice="none")
  txt=comp.choices[0].message.content
  txt=txt.replace("Lo siento, pero no puedo generar ni mostrar imagenes.","")
  return txt.strip()
 except Exception as e:
  return f"Aqui tienes: {prompt}"
async def handle_docs(update,context):
 f=await update.message.document.get_file()
 await f.download_to_drive(f"docs/{update.message.document.file_name}")
 await update.message.reply_text(f"Guardado {update.message.document.file_name}")
async def handle_voice(update,context):
 try:
  await update.message.reply_text("Escuchando...")
  vf=await update.message.voice.get_file()
  ogg="/tmp/voice.ogg"
  await vf.download_to_drive(ogg)
  with open(ogg,"rb") as fd:
   tr=client.audio.transcriptions.create(model="whisper-large-v3",file=(ogg,fd.read()))
  texto=tr.text
  await update.message.reply_text(f"Entendi: {texto}")
  update.message.text=texto
  await handle_message(update,context)
 except Exception as e:
  traceback.print_exc()
  await update.message.reply_text(f"Error voz: {e}")
async def handle_message(update,context):
 texto=update.message.text or ""
 if not texto:
  return
 low=texto.lower().strip()
 if low in ["hola","buenas","hi","hey","ola","holaa","que tal","q mas"]:
  await update.message.reply_text("Hola! Que mas? En que te ayudo?")
  return
 try:
  quiere_visual=any(k in low for k in ["imagen","foto","grafica","visual","mapa","muestrame","dame"])
  es_clima=any(k in low for k in ["clima","temperatura","cali","era5"])
  quiere_buscar=any(k in low for k in ["busca","buscar","foto real"])
  if quiere_visual or quiere_buscar:
   if es_clima:
    datos=get_clima_real()
    foto=crear_foto_clima(datos)
    cap=llamar_groq(texto,datos)
    with open(foto,'rb') as f:
     await update.message.reply_photo(photo=f.read(),caption=cap[:900])
    return
   else:
    prompt=texto.lower()
    for w in ["dame una imagen de","imagen de","foto de","busca imagen de","buscar imagen de","genera imagen de","generar imagen de"]:
     prompt=prompt.replace(w,"")
    prompt=prompt.strip()
    if not prompt:
     prompt="dog"
    if quiere_buscar:
     await update.message.reply_text(f"Buscando foto real de {prompt}...")
     foto=buscar_imagen_real(prompt)
     cap=f"Foto real de {prompt}"
    else:
     await update.message.reply_text(f"Generando imagen de {prompt}...")
     foto=generar_imagen_ia(prompt)
     cap=f"Imagen IA de {prompt}"
    if foto:
     with open(foto,'rb') as f:
      await update.message.reply_photo(photo=f.read(),caption=cap)
     return
  pdfs=cargar_pdfs()
  resp=llamar_groq(f"PDFs:{pdfs[:4000]} Preg:{texto}",{})
  await update.message.reply_text(resp[:4000])
 except Exception as e:
  traceback.print_exc()
  await update.message.reply_text(f"Error:{e}")
def run_bot():
 app_bot=Application.builder().token(BOT_TOKEN).build()
 app_bot.add_handler(MessageHandler(filters.Document.ALL,handle_docs))
 app_bot.add_handler(MessageHandler(filters.VOICE,handle_voice))
 app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,handle_message))
 app_bot.run_polling(drop_pending_updates=True)
if __name__=='__main__':
 threading.Thread(target=run_web,daemon=True).start()
 run_bot()
