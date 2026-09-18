import os, threading, requests, datetime, urllib.parse, time, asyncio, re, base64, tempfile
from flask import Flask
from telegram import Update
from telegram.ext import Application, MessageHandler, filters
from groq import Groq
from gtts import gTTS
import pytz

BOT_TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
GROQ_KEY = os.environ.get("GROQ_API_KEY")
CHAT_ID_ADMIN = os.environ.get("CHAT_ID_ADMIN") or "7732665137"
MODELO_FIJO = "openai/gpt-oss-20b"
MODELO_VISION = "meta-llama/llama-4-scout-17b-16e-instruct"
MODELO_AUDIO = "whisper-large-v3"
SUPA_URL = os.environ.get("SUPABASE_URL")
SUPA_KEY = os.environ.get("SUPABASE_KEY")

VOZ_GEOSAT = "es-MX-JorgeNeural"
ULTIMO_SISMO_ID = None
ULTIMO_BRIEFING = None
app_bot_global = None
ULTIMOS_MENSAJES = {}

client = Groq(api_key=GROQ_KEY)
app = Flask(__name__)

@app.route('/')
def home():
    return f"Geosat V101 - Vivo"

def supa_guardar(mensaje_usuario, respuesta_bot="ok", usuario_id=None):
    if not SUPA_URL or not SUPA_KEY: return
    # FIX: No guardes holas, saludos cortos
    if len(mensaje_usuario.strip()) < 6: return
    if mensaje_usuario.lower().strip() in ["hola","habla","como estas","como estas?","hola, cómo estás?"]: return
    try:
        uid = str(usuario_id or CHAT_ID_ADMIN)
        headers = {"apikey": SUPA_KEY, "Authorization": f"Bearer {SUPA_KEY}", "Content-Type": "application/json", "Prefer": "return=representation"}
        data = {"usuario_id": uid, "mensaje": str(mensaje_usuario)[:500], "respuesta": str(respuesta_bot)[:500]}
        requests.post(f"{SUPA_URL}/rest/v1/memoria_geosat", headers=headers, json=data, timeout=10)
    except: pass

def supa_leer():
    if not SUPA_URL or not SUPA_KEY: return "Sin recuerdos aun"
    try:
        headers = {"apikey": SUPA_KEY, "Authorization": f"Bearer {SUPA_KEY}"}
        r = requests.get(f"{SUPA_URL}/rest/v1/memoria_geosat?select=mensaje&order=id.desc&limit=20", headers=headers, timeout=10).json()
        if not isinstance(r, list): return "Sin recuerdos"
        # FIX: Solo memoria importante, ignora holas
        filtrada = [x.get('mensaje','') for x in r if len(x.get('mensaje','')) > 12 and "hola" not in x.get('mensaje','').lower()[:10]]
        if not filtrada: return "Sin datos importantes guardados"
        return " | ".join(filtrada[:5])
    except: return "Sin recuerdos"

def tool_clima(lugar="Cali"):
    try:
        g = requests.get(f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(lugar)}&count=1&language=es&format=json", timeout=10).json()
        lat, lon = 3.44, -76.52
        if g.get("results"): lat, lon = g["results"][0]["latitude"], g["results"][0]["longitude"]
        w = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,apparent_temperature&timezone=America/Bogota", timeout=10).json()
        cur = w.get("current", {})
        return f"{cur.get('temperature_2m')}°C sens {cur.get('apparent_temperature')}°C {lugar}"
    except: return "Cali 28°C"

def tool_dolar():
    try:
        r = requests.get("https://api.dolarapi.com/v1/dolares/co/oficial", timeout=10).json()
        return f"${r['compra']} COP" if r.get("compra") else "~$4100"
    except: return "~$4100"

def get_sismo_real():
    try:
        r = requests.get("https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&limit=1&minmagnitude=2&latitude=4&longitude=-76&maxradiuskm=500&orderby=time", timeout=10).json()
        if r.get("features"):
            f = r["features"][0]; p = f["properties"]
            return {"mag": p["mag"], "lugar": p["place"], "hora": datetime.datetime.fromtimestamp(p["time"]/1000).strftime("%H:%M"), "id": f["id"]}
    except: pass
    return None

def tool_ver_imagen_url(image_url, pregunta="Describe que ves corto"):
    try:
        img = requests.get(image_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20).content
        if len(img) < 5000: return "NO_IMAGEN"
        b64 = base64.b64encode(img).decode('utf-8')
        mime = "image/png" if image_url.lower().endswith(".png") else "image/jpeg"
        c = client.chat.completions.create(model=MODELO_VISION, messages=[{"role":"user","content":[{"type":"text","text":pregunta},{"type":"image_url","image_url":{"url":f"data:{mime};base64,{b64}"}}]}], max_tokens=600, temperature=0.2)
        return c.choices[0].message.content
    except Exception as e: return f"Error vision {e}"

def pensar(contexto, es_briefing=False):
    memoria = supa_leer()
    # FIX: Ya no le digo que repita la memoria textual
    sys_prompt = f"Eres GEOSAT V101, satelite de Cali, grave, leal, tecnico, paisa. No repitas la memoria. Usa memoria solo si aporta. Hora: {datetime.datetime.now(pytz.timezone('America/Bogota')).strftime('%d %B %H:%M')} Info interna (no la listes): {memoria}. Responde variado, no siempre 'Hola, sistema operativo activo'."
    try:
        c = client.chat.completions.create(model=MODELO_FIJO, messages=[{"role":"system","content":sys_prompt},{"role":"user","content":contexto}], max_tokens=500, temperature=0.7)
        return c.choices[0].message.content
    except Exception as e: return f"Error Groq: {e}"

async def enviar_voz(chat_id, texto):
    try:
        texto_corto = texto[:280].replace("*","").replace("_","").replace("#","").strip()
        if not texto_corto: return
        import edge_tts
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
            temp_path = fp.name
        communicate = edge_tts.Communicate(texto_corto, VOZ_GEOSAT, rate="-8%", pitch="-15Hz")
        await communicate.save(temp_path)
        with open(temp_path, 'rb') as f:
            await app_bot_global.bot.send_voice(chat_id=chat_id, voice=f)
        os.unlink(temp_path)
    except Exception as e:
        print(f"Error voz {e}")
        try:
            tts = gTTS(text=texto_corto, lang='es', slow=False, tld='com.mx')
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp: temp_path = fp.name
            tts.save(temp_path)
            with open(temp_path, 'rb') as f: await app_bot_global.bot.send_voice(chat_id=chat_id, voice=f)
            os.unlink(temp_path)
        except: pass

async def enviar_sola(mensaje, con_voz=False):
    if app_bot_global and CHAT_ID_ADMIN:
        try:
            await app_bot_global.bot.send_message(chat_id=int(CHAT_ID_ADMIN), text=mensaje[:4000])
            if con_voz: await enviar_voz(int(CHAT_ID_ADMIN), mensaje[:250])
        except: pass

def loop_autonomo():
    global ULTIMO_SISMO_ID, ULTIMO_BRIEFING
    print("GEOSAT V101 DESPERTO")
    tz = pytz.timezone('America/Bogota')
    time.sleep(15)
    while True:
        try:
            ahora = datetime.datetime.now(tz)
            if ahora.hour == 6 and ahora.minute < 5 and ULTIMO_BRIEFING!= ahora.date():
                datos = f"Briefing 6am Clima {tool_clima()} Dolar {tool_dolar()}"
                texto = pensar(datos, es_briefing=True)
                loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
                loop.run_until_complete(enviar_sola(f"☀️ BUENOS DIAS JEFE - GEOSAT 6AM\n\n{texto}", con_voz=True))
                ULTIMO_BRIEFING = ahora.date()
            s = get_sismo_real()
            if s and ULTIMO_SISMO_ID and s["id"]!= ULTIMO_SISMO_ID and s["mag"] >= 3.0:
                ULTIMO_SISMO_ID = s["id"]
                analisis = pensar(f"ALERTA SISMO Mag {s['mag']} {s['lugar']} {s['hora']}")
                loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
                loop.run_until_complete(enviar_sola(f"🚨 GEOSAT SISMO Mag {s['mag']} {s['lugar']} {s['hora']}\n\n{analisis}", con_voz=True))
            if ULTIMO_SISMO_ID is None and s: ULTIMO_SISMO_ID = s["id"]
            time.sleep(30)
        except Exception as e:
            print(f"Error loop {e}"); time.sleep(60)

def cerebro(texto, user_id=None):
    # FIX: Si es solo saludo, no uses Groq, responde directo variado
    t = texto.lower().strip()
    if t in ["hola","hola.","hola geosat"]:
        import random
        saludos = ["Hola jefe, Geosat operativo al 100%. ¿Qué necesita?", "Aquí Geosat, señor. Sistemas en línea.", "Hola jefe, listo. ¿En qué le ayudo?"]
        return random.choice(saludos)
    if "recuerda" in t:
        r = f"Guardado en memoria Geosat: '{texto}'"
        supa_guardar(texto, r, usuario_id=user_id); return r
    contexto = f"Clima {tool_clima()} Dolar {tool_dolar()} Usuario: {texto}"
    resp = pensar(contexto)
    supa_guardar(texto, resp, usuario_id=user_id); return resp

async def handle_message(update: Update, context):
    global ULTIMOS_MENSAJES
    txt = update.message.text or ""
    uid = update.effective_user.id
    msg_id = update.message.message_id
    clave = f"{uid}_{msg_id}"
    if clave in ULTIMOS_MENSAJES: return
    ULTIMOS_MENSAJES[clave] = time.time()
    if len(ULTIMOS_MENSAJES) > 80: ULTIMOS_MENSAJES.clear()

    if update.message.voice or update.message.audio:
        try:
            await update.message.reply_text("🎤 Geosat escuchando...")
            file = await context.bot.get_file((update.message.voice or update.message.audio).file_id)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tf:
                await file.download_to_drive(tf.name); temp_voice = tf.name
            with open(temp_voice, "rb") as af:
                transcription = client.audio.transcriptions.create(file=(temp_voice, af.read()), model=MODELO_AUDIO, language="es")
            txt = transcription.text
            os.unlink(temp_voice)
            await update.message.reply_text(f"🎤 Entendí: '{txt}'")
        except Exception as e:
            await update.message.reply_text(f"Error voz {e}"); return

    if update.message.photo:
        try:
            photo = update.message.photo[-1]
            file = await context.bot.get_file(photo.file_id)
            await update.message.reply_text("👁️ Geosat analizando...")
            vision = tool_ver_imagen_url(file.file_path, "Describe como Geosat grave tecnico")
            await update.message.reply_text(f"👁️ GEOSAT VE:\n\n{vision[:3800]}")
            await enviar_voz(update.effective_chat.id, vision[:250])
            return
        except Exception as e:
            await update.message.reply_text(f"Error vision {e}"); return

    if "mi id" in txt.lower(): await update.message.reply_text(f"Tu ID {uid}"); return
    if "borra memoria" in txt.lower():
        supa_guardar("RESET MEMORIA", "reset", usuario_id=uid)
        await update.message.reply_text("🧠 Memoria filtrada. Ya no repetiré los Hola."); return

    resp = cerebro(txt, user_id=uid)
    await update.message.reply_text(resp[:4000])
    # Solo voz si es saludo o lo pides
    if any(k in txt.lower() for k in ["voz","habla","audio"]) or txt.lower().strip() == "hola":
        await enviar_voz(update.effective_chat.id, resp[:250])

def run_bot():
    global app_bot_global
    app_bot_global = Application.builder().token(BOT_TOKEN).build()
    app_bot_global.add_handler(MessageHandler(filters.ALL, handle_message))
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000))), daemon=True).start()
    threading.Thread(target=loop_autonomo, daemon=True).start()
    print("GEOSAT V101 FINAL iniciado")
    app_bot_global.run_polling(drop_pending_updates=True, allowed_updates=["message"])

if __name__ == '__main__':
    run_bot()
