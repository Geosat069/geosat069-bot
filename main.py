import os, threading, requests, datetime, urllib.parse, time, asyncio
from flask import Flask
from telegram import Update
from telegram.ext import Application, MessageHandler, filters
from groq import Groq

BOT_TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
GROQ_KEY = os.environ.get("GROQ_API_KEY")
CHAT_ID_ADMIN = os.environ.get("CHAT_ID_ADMIN") or "7732665137"
MODELO_FIJO = "openai/gpt-oss-20b"
ULTIMO_SISMO_ID = None
app_bot_global = None

client = Groq(api_key=GROQ_KEY)
app = Flask(__name__)

@app.route('/')
def home():
    return f"Geosat V39 AUTONOMA VIVA - Modelo {MODELO_FIJO} - Admin {CHAT_ID_ADMIN}"

def tool_clima(lugar="Cali"):
    try:
        g=requests.get(f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(lugar)}&count=1&language=es&format=json",timeout=8).json()
        lat,lon=3.44,-76.52
        if g.get("results"):
            lat=g["results"][0]["latitude"]; lon=g["results"][0]["longitude"]
        j=requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,wind_speed_10m&timezone=auto",timeout=8).json()
        return f"{j['current']['temperature_2m']}°C, viento {j['current']['wind_speed_10m']} km/h"
    except:
        return "Clima no disponible"

def tool_dolar():
    try:
        r=requests.get("https://dolar.wilsono.com/api",timeout=8).json()
        return f"TRM ${r.get('trm','')}"
    except:
        return "Dolar no disponible"

def pensar_autonomo(texto_contexto):
    sys = f"""Eres Geosat V39 AUTONOMA. Vives sola vigilando sismos para Cali.
Contexto: {texto_contexto} Fecha: {datetime.datetime.now()}
Si hay sismo >3.5 cerca Valle/Choco/Cauca genera alerta corta tecnica y tranquilizadora. Si no, responde NADA."""
    try:
        c=client.chat.completions.create(model=MODELO_FIJO,messages=[{"role":"system","content":sys},{"role":"user","content":"Debo alertar?"}],max_tokens=400,temperature=0.3)
        return c.choices[0].message.content
    except:
        return "NADA"

async def enviar_sola(mensaje):
    if app_bot_global and CHAT_ID_ADMIN:
        try:
            await app_bot_global.bot.send_message(chat_id=int(CHAT_ID_ADMIN), text=mensaje[:4000])
        except Exception as e:
            print(f"Error envio: {e}")

def loop_autonomo():
    global ULTIMO_SISMO_ID
    print("IA AUTONOMA DESPERTO - Vigilando cada 10 min")
    time.sleep(5)
    while True:
        try:
            # AQUI VA TU LECTOR REAL DE SGC - por ahora dato de prueba
            sismo_actual = {"mag": 3.8, "lugar": "Istmina - Choco", "prof": 47, "hora": datetime.datetime.now().strftime("%H:%M")}
            sismo_id = f"{sismo_actual['lugar']}-{sismo_actual['hora']}"

            if ULTIMO_SISMO_ID is None:
                ULTIMO_SISMO_ID = "iniciado"
            # Aqui luego pones: if sismo_id!= ULTIMO_SISMO_ID and sismo_actual["mag"] >= 3.5:
            # Por ahora lo dejamos dormido para no spamear

            time.sleep(600)
        except Exception as e:
            print(e); time.sleep(60)

def cerebro(texto):
    contexto = f"Clima Cali: {tool_clima()} | Dolar: {tool_dolar()} | Hora: {datetime.datetime.now().strftime('%d %b %H:%M')}"
    sys_prompt=f"""Eres Geosat V39 AUTONOMA de Cali, paisa, cercana, tecnica. Modelo fijo {MODELO_FIJO}. No inventas.
Contexto real: {contexto}"""
    try:
        c=client.chat.completions.create(model=MODELO_FIJO,messages=[{"role":"system","content":sys_prompt},{"role":"user","content":texto}],max_tokens=800,temperature=0.4)
        return c.choices[0].message.content
    except Exception as e:
        return f"Error {MODELO_FIJO}: {e}"

async def handle_message(update: Update, context):
    txt = update.message.text or ""
    if "mi id" in txt.lower():
        await update.message.reply_text(f"Tu CHAT_ID_ADMIN es: {update.effective_user.id}")
        return
    resp = cerebro(txt)
    await update.message.reply_text(resp[:4000])

def run_bot():
    global app_bot_global
    app_bot_global = Application.builder().token(BOT_TOKEN).build()
    app_bot_global.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    threading.Thread(target=lambda: app.run(host='0.0.0.0',port=int(os.environ.get("PORT",10000))), daemon=True).start()
    threading.Thread(target=loop_autonomo, daemon=True).start()
    print(f"Bot iniciado admin {CHAT_ID_ADMIN}")
    app_bot_global.run_polling(drop_pending_updates=True)

if __name__=='__main__':
    run_bot()
