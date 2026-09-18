import os, threading, requests, datetime, urllib.parse, time, asyncio, re, base64, tempfile
from flask import Flask
from telegram import Update
from telegram.ext import Application, MessageHandler, filters
from groq import Groq
from gtts import gTTS
import pytz

# --- CONFIG ---
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
CAMARAS_VIGILADAS = {}
app_bot_global = None
ULTIMOS_MENSAJES = {} # Anti spam

client = Groq(api_key=GROQ_KEY)
app = Flask(__name__)

@app.route('/')
def home():
    return f"Geosat V100 LATINO GRATIS - Vivo - {len(CAMARAS_VIGILADAS)} camaras"

def supa_guardar(mensaje_usuario, respuesta_bot="guardado auto", usuario_id=None):
    if not SUPA_URL or not SUPA_KEY: return
    try:
        uid = str(usuario_id or CHAT_ID_ADMIN)
        headers = {"apikey": SUPA_KEY, "Authorization": f"Bearer {SUPA_KEY}", "Content-Type": "application/json", "Prefer": "return=representation"}
        data = {"usuario_id": uid, "mensaje": str(mensaje_usuario)[:1000], "respuesta": str(respuesta_bot)[:1000]}
        requests.post(f"{SUPA_URL}/rest/v1/memoria_geosat", headers=headers, json=data, timeout=15)
    except: pass

def supa_leer():
    if not SUPA_URL or not SUPA_KEY: return "Sin Supabase"
    try:
        headers = {"apikey": SUPA_KEY, "Authorization": f"Bearer {SUPA_KEY}"}
        r = requests.get(f"{SUPA_URL}/rest/v1/memoria_geosat?select=mensaje&order=id.desc&limit=15", headers=headers, timeout=15).json()
        if isinstance(r, list) and r:
            imp = [f"[IMPORTANTE] {x.get('mensaje','')}" for x in r if any(k in x.get('mensaje','').lower() for k in ["recuerda","jefe","soy","importante"])]
            if imp: return " | ".join(imp[:8])
            return " | ".join([x.get('mensaje','')[:80] for x in r[:6]])
        return "Sin recuerdos"
    except: return "Error memoria"

def tool_clima(lugar="Cali"):
    try:
        g = requests.get(f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(lugar)}&count=1&language=es&format=json", timeout=10).json()
        lat, lon = 3.44, -76.52
        if g.get("results"): lat, lon = g["results"][0]["latitude"], g["results"][0]["longitude"]
        w = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,precipitation&daily=precipitation_probability_max&timezone=America/Bogota", timeout=10).json()
        cur = w.get("current", {}); daily = w.get("daily", {})
        prob = daily.get("precipitation_probability_max",[0])[0] if daily.get("precipitation_probability_max") else 0
        return f"{cur.get('temperature_2m')}°C sens {cur.get('apparent_temperature')}°C Hum {cur.get('relative_humidity_2m')}% Prob {prob}% Viento {cur.get('wind_speed_10m')}km/h {lugar}"
    except: return "Cali 28°C"

def tool_dolar():
    try:
        r = requests.get("https://api.dolarapi.com/v1/dolares/co/oficial", timeout=10).json()
        if r.get("compra"): return f"${r['compra']} COP"
    except: pass
    return "~$4100"

def get_sismo_real():
    try:
        r = requests.get("https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&limit=1&minmagnitude=2&latitude=4&longitude=-76&maxradiuskm=500&orderby=time", timeout=10).json()
        if r.get("features"):
            f = r["features"][0]; p = f["properties"]
            return {"mag": p["mag"], "lugar": p["place"], "hora": datetime.datetime.fromtimestamp(p["time"]/1000).strftime("%H:%M"), "id": f["id"]}
    except: pass
    return None

def tool_ver_imagen_url(image_url, pregunta="Describe que ves, tecnico, corto"):
    try:
        img = requests.get(image_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20).content
        if len(img) < 5000: return "NO_IMAGEN"
        b64 = base64.b64encode(img).decode('utf-8')
        mime = "image/png" if image_url.lower().endswith(".png") else "image/jpeg"
        c = client.chat.completions.create(model=MODELO_VISION, messages=[{"role":"user","content":[{"type":"text","text":pregunta},{"type":"image_url","image_url":{"url":f"data:{mime};base64,{b64}"}}]}], max_tokens=700, temperature=0.2)
        return c.choices[0].message.content
    except Exception as e: return f"Error vision {e}"

def pensar(contexto, es_briefing=False):
    memoria = supa_leer()
    sys_prompt = f"Eres GEOSAT V100, asistente satelital de Cali, voz latina grave, serio, leal, tecnico, paisa. Habla como sistema. MEMORIA: {memoria} Hora: {datetime.datetime.now(pytz.timezone('America/Bogota')).strftime('%d %B %Y %H:%M')} {'Briefing 6am 4 lineas' if es_briefing else 'Responde corto, tecnico, usa memoria, 1 sola respuesta'}"
    try:
        c = client.chat.completions.create(model=MODELO_FIJO, messages=[{"role":"system","content":sys_prompt},{"role":"user","content":contexto}], max_tokens=600, temperature=0.4)
        return c.choices[0].message.content
    except Exception as e: return f"Error Groq: {e}"

# --- VOZ GEOSAT LATINO GRATIS - CORREGIDA ---
async def enviar_voz(chat_id, texto):
    try:
        texto_corto = texto[:350].replace("*","").replace("_","").replace("#","").strip()
        if not texto_corto: return
        try:
            import edge_tts
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
                temp_path = fp.name
            communicate = edge_tts.Communicate(texto_corto, VOZ_GEOSAT, rate="-8%", pitch="-15Hz")
            await communicate.save(temp_path)
            with open(temp_path, 'rb') as f:
                await app_bot_global.bot.send_voice(chat_id=chat_id, voice=f)
            os.unlink(temp_path)
            print(f"Voz Geosat enviada {VOZ_GEOSAT}")
            return
        except Exception as e:
            print(f"Error edge-tts {e}, fallback gTTS")
            tts = gTTS(text=texto_corto, lang='es', slow=False, tld='com.mx')
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
                temp_path = fp.name
            tts.save(temp_path)
            with open(temp_path, 'rb') as f:
                await app_bot_global.bot.send_voice(chat_id=chat_id, voice=f)
            os.unlink(temp_path)
    except Exception as e:
        print(f"Error voz final: {e}")

async def enviar_sola(mensaje, con_voz=False):
    if app_bot_global and CHAT_ID_ADMIN:
        try:
            await app_bot_global.bot.send_message(chat_id=int(CHAT_ID_ADMIN), text=mensaje[:4000])
            if con_voz: await enviar_voz(int(CHAT_ID_ADMIN), mensaje[:300])
        except: pass

def loop_autonomo():
    global ULTIMO_SISMO_ID, ULTIMO_BRIEFING
    print("GEOSAT V100 DESPERTO")
    tz = pytz.timezone('America/Bogota')
    time.sleep(15)
    while True:
        try:
            ahora = datetime.datetime.now(tz)
            if ahora.hour == 6 and ahora.minute < 5 and ULTIMO_BRIEFING!= ahora.date():
                datos = f"Briefing 6am Clima {tool_clima()} Dolar {tool_dolar()} Memoria {supa_leer()}"
                texto = pensar(datos, es_briefing=True)
                loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
                loop.run_until_complete(enviar_sola(f"☀️ BUENOS DIAS JEFE - BRIEFING GEOSAT 6AM\n\n{texto}", con_voz=True))
                ULTIMO_BRIEFING = ahora.date()

            s = get_sismo_real()
            if s:
                if ULTIMO_SISMO_ID is None: ULTIMO_SISMO_ID = s["id"]
                elif s["id"]!= ULTIMO_SISMO_ID and s["mag"] >= 3.0:
                    ULTIMO_SISMO_ID = s["id"]
                    supa_guardar(f"Sismo Mag {s['mag']} {s['lugar']}", "alerta")
                    analisis = pensar(f"ALERTA SISMO Mag {s['mag']} {s['lugar']} {s['hora']}")
                    loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
                    loop.run_until_complete(enviar_sola(f"🚨 GEOSAT SISMO Mag {s['mag']} {s['lugar']} {s['hora']}\n\n{analisis}", con_voz=True))
            time.sleep(30)
        except Exception as e:
            print(f"Error loop {e}"); time.sleep(60)

def cerebro(texto, user_id=None):
    if "recuerda" in texto.lower():
        r = f"Listo jefe, guardado para siempre en Geosat: '{texto}'"
        supa_guardar(texto, r, usuario_id=user_id); return r
    contexto = f"Clima {tool_clima()} Dolar {tool_dolar()} Memoria {supa_leer()} Usuario: {texto}"
    resp = pensar(contexto)
    supa_guardar(texto, resp, usuario_id=user_id); return resp

async def handle_message(update: Update, context):
    global ULTIMOS_MENSAJES
    txt = update.message.text or ""
    uid = update.effective_user.id
    msg_id = update.message.message_id

    # ANTI-DUPLICADO: si el mismo mensaje id ya se proceso, ignorar
    clave = f"{uid}_{msg_id}"
    if clave in ULTIMOS_MENSAJES: return
    ULTIMOS_MENSAJES[clave] = time.time()
    # Limpia viejos
    if len(ULTIMOS_MENSAJES) > 100: ULTIMOS_MENSAJES.clear()

    if update.message.voice or update.message.audio:
        try:
            await update.message.reply_text("🎤 Geosat escuchando...")
            file_obj = update.message.voice or update.message.audio
            file = await context.bot.get_file(file_obj.file_id)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tf:
                await file.download_to_drive(tf.name)
                temp_voice = tf.name
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
            vision = tool_ver_imagen_url(file.file_path, "Describe como Geosat grave tecnico paisa")
            await update.message.reply_text(f"👁️ GEOSAT VE:\n\n{vision[:3800]}")
            await enviar_voz(update.effective_chat.id, vision[:280])
            supa_guardar("Foto analizada", vision, usuario_id=uid); return
        except Exception as e:
            await update.message.reply_text(f"Error vision {e}"); return

    low = txt.lower()

    if "vigilar" in low and "http" in low:
        urls = re.findall(r'https?://\S+', txt)
        if urls:
            CAMARAS_VIGILADAS[urls[0]] = {}
            await update.message.reply_text(f"✅ GEOSAT VIGILANCIA ACTIVADA\n📹 {urls[0][:100]}")
            await enviar_voz(update.effective_chat.id, "Vigilancia Geosat activada, señor.")
            return

    if "deja de vigilar" in low or "para de vigilar" in low:
        CAMARAS_VIGILADAS.clear()
        await update.message.reply_text("🛑 Vigilancia Geosat detenida."); return

    if "mi id" in low: await update.message.reply_text(f"Tu ID {uid}"); return
    if "memoria" in low or "que recuerdas" in low: await update.message.reply_text(f"🧠 GEOSAT MEMORIA:\n{supa_leer()[:3500]}"); return

    # CEREBRO PRINCIPAL - 1 SOLA RESPUESTA
    resp = cerebro(txt, user_id=uid)
    await update.message.reply_text(resp[:4000])

    # Solo manda voz si lo pides o si es corto
    if any(k in low for k in ["voz","habla","audio","habla geosat","dime"]) or ("hola" in low and len(low) < 10):
        await enviar_voz(update.effective_chat.id, resp[:300])

def run_bot():
    global app_bot_global
    app_bot_global = Application.builder().token(BOT_TOKEN).build()
    app_bot_global.add_handler(MessageHandler(filters.ALL, handle_message))
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000))), daemon=True).start()
    threading.Thread(target=loop_autonomo, daemon=True).start()
    print("Bot GEOSAT V100 iniciado FINAL")
    # drop_pending_updates evita duplicados al reiniciar Render
    app_bot_global.run_polling(drop_pending_updates=True, allowed_updates=["message"], poll_interval=2.0)

if __name__ == '__main__':
    run_bot()
