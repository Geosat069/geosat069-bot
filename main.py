import os, threading, requests, datetime, urllib.parse, time, asyncio, re, base64, tempfile, xml.etree.ElementTree as ET
from flask import Flask
from telegram import Update
from telegram.ext import Application, MessageHandler, filters
from groq import Groq
from gtts import gTTS
import pytz

# --- CONFIG FIJA ---
BOT_TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
GROQ_KEY = os.environ.get("GROQ_API_KEY")
CHAT_ID_ADMIN = os.environ.get("CHAT_ID_ADMIN") or "7732665137"
MODELO_FIJO = "openai/gpt-oss-20b"
MODELO_VISION = "meta-llama/llama-4-scout-17b-16e-instruct"
MODELO_AUDIO = "whisper-large-v3"
SUPA_URL = os.environ.get("SUPABASE_URL")
SUPA_KEY = os.environ.get("SUPABASE_KEY")
ELEVEN_API_KEY = os.environ.get("ELEVEN_API_KEY")
ELEVEN_VOICE_ID = os.environ.get("ELEVEN_VOICE_ID") or "pNInz6obpgDQGcFmaJgB"

ULTIMO_SISMO_ID = None
ULTIMO_BRIEFING = None
CAMARAS_VIGILADAS = {}
app_bot_global = None

client = Groq(api_key=GROQ_KEY)
app = Flask(__name__)

@app.route('/')
def home():
    return f"Geosat V100 JARVIS LATINO PELICULA - Modelo {MODELO_FIJO} - {len(CAMARAS_VIGILADAS)} camaras vigiladas"

# --- SUPABASE MEMORIA ETERNA AUTOMATICA ---
def supa_guardar(mensaje_usuario, respuesta_bot="guardado auto", usuario_id=None):
    if not SUPA_URL or not SUPA_KEY:
        return
    try:
        uid = str(usuario_id or CHAT_ID_ADMIN)
        headers = {
            "apikey": SUPA_KEY,
            "Authorization": f"Bearer {SUPA_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
        data = {
            "usuario_id": uid,
            "mensaje": str(mensaje_usuario)[:1000],
            "respuesta": str(respuesta_bot)[:1000]
        }
        requests.post(f"{SUPA_URL}/rest/v1/memoria_geosat", headers=headers, json=data, timeout=15)
    except Exception as e:
        print(f"Error memoria auto: {e}")

def supa_leer():
    if not SUPA_URL or not SUPA_KEY:
        return "Memoria local, sin Supabase"
    try:
        headers = {"apikey": SUPA_KEY, "Authorization": f"Bearer {SUPA_KEY}"}
        url = f"{SUPA_URL}/rest/v1/memoria_geosat?select=mensaje,respuesta&order=id.desc&limit=15"
        r = requests.get(url, headers=headers, timeout=15).json()
        if isinstance(r, list) and len(r) > 0:
            recuerdos = []
            for x in r:
                m = x.get("mensaje","")
                if "recuerda" in m.lower() or "jefe" in m.lower() or "soy" in m.lower():
                    recuerdos.append(f"[IMPORTANTE] {m}")
            if recuerdos:
                return " | ".join(recuerdos[:8])
            return " | ".join([f"User: {x.get('mensaje','')[:80]}" for x in r[:6]])
        return "Sin recuerdos aun"
    except Exception as e:
        return "Error memoria"

# --- HERRAMIENTAS REALES ---
def tool_clima(lugar="Cali"):
    try:
        g = requests.get(f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(lugar)}&count=1&language=es&format=json", timeout=10).json()
        lat, lon = 3.44, -76.52
        if g.get("results"):
            lat = g["results"][0]["latitude"]; lon = g["results"][0]["longitude"]
        w = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,precipitation&daily=precipitation_probability_max&timezone=America/Bogota", timeout=10).json()
        cur = w.get("current", {}); daily = w.get("daily", {})
        prob = daily.get("precipitation_probability_max",[0])[0] if daily.get("precipitation_probability_max") else 0
        return f"{cur.get('temperature_2m')}°C sens {cur.get('apparent_temperature')}°C, Hum {cur.get('relative_humidity_2m')}%, Lluvia {cur.get('precipitation')}mm, Prob hoy {prob}%, Viento {cur.get('wind_speed_10m')} km/h en {lugar}"
    except:
        return "Cali 28°C nublado respaldo"

def tool_dolar():
    try:
        r = requests.get("https://api.dolarapi.com/v1/dolares/co/oficial", timeout=10).json()
        if r.get("compra"):
            return f"Compra ${r['compra']} Venta ${r['venta']} COP"
    except: pass
    return "~ $4100 COP ref"

def get_sismo_real():
    try:
        r = requests.get("https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&limit=5&minmagnitude=2&latitude=4&longitude=-76&maxradiuskm=500&orderby=time", timeout=10).json()
        if r.get("features"):
            f = r["features"][0]; p = f["properties"]
            return {"mag": p["mag"], "lugar": p["place"], "hora": datetime.datetime.fromtimestamp(p["time"]/1000).strftime("%H:%M"), "id": f["id"]}
    except: pass
    return None

# --- VISION REAL ---
def tool_ver_imagen_url(image_url, pregunta="Describe lo que ves en tiempo real, tecnico, paisa"):
    try:
        img_data = requests.get(image_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20).content
        if len(img_data) < 5000: return "NO_IMAGEN"
        b64 = base64.b64encode(img_data).decode('utf-8')
        mime = "image/png" if image_url.lower().endswith(".png") else "image/jpeg"
        completion = client.chat.completions.create(
            model=MODELO_VISION,
            messages=[{"role": "user", "content": [{"type": "text", "text": pregunta}, {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}]}],
            max_tokens=700, temperature=0.2
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"Error vision: {e}"

def tool_detectar_movimiento(url):
    prompt = """Eres vigilante JARVIS. Mira esta camara en vivo.
Responde SOLO:
PERSONAS: SI/NO - cuantas
MOVIMIENTO: SI/NO
PELIGRO: SI/NO
DESCRIPCION: 1 frase corta"""
    return tool_ver_imagen_url(url, prompt)

def pensar(contexto, es_briefing=False):
    memoria = supa_leer()
    sys_prompt = f"""Eres JARVIS V100 voz latina de la pelicula Iron Man, doblado por Idzi Dutkiewicz. Grave, serio, leal, paisa. Vives sola.
MEMORIA ETERNA: {memoria}
CONTEXTO REAL: {contexto}
Hora Bogota: {datetime.datetime.now(pytz.timezone('America/Bogota')).strftime('%d %B %Y %H:%M')}
Instrucciones: {'Briefing 6am proactivo, cariñoso, tecnico, 4 lineas usando memoria' if es_briefing else 'Responde paisa, tecnico, corto. Usa memoria para personalizar. Si es sismo genera alerta.'}
"""
    try:
        c = client.chat.completions.create(model=MODELO_FIJO, messages=[{"role":"system","content":sys_prompt},{"role":"user","content":contexto}], max_tokens=800, temperature=0.4)
        return c.choices[0].message.content
    except Exception as e:
        return f"Error Groq {MODELO_FIJO}: {e}"

# --- VOZ JARVIS LATINO PELICULA ---
async def enviar_voz(chat_id, texto):
    try:
        texto_corto = texto[:380].replace("*","").replace("_","")
        if not texto_corto.strip():
            return

        if ELEVEN_API_KEY:
            try:
                url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVEN_VOICE_ID}"
                headers = {"xi-api-key": ELEVEN_API_KEY, "Content-Type": "application/json"}
                data = {
                    "text": texto_corto,
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {"stability": 0.65, "similarity_boost": 0.85, "style": 0.35, "use_speaker_boost": True}
                }
                r = requests.post(url, json=data, headers=headers, timeout=25)
                if r.status_code == 200:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
                        fp.write(r.content)
                        temp_path = fp.name
                    with open(temp_path, 'rb') as audio_file:
                        await app_bot_global.bot.send_voice(chat_id=chat_id, voice=audio_file)
                    os.unlink(temp_path)
                    return
            except Exception as e:
                print(f"Error ElevenLabs: {e}")

        # Fallback voz mexicana grave
        tts = gTTS(text=texto_corto, lang='es', slow=False, tld='com.mx')
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
            temp_path = fp.name
        tts.save(temp_path)
        with open(temp_path, 'rb') as audio_file:
            await app_bot_global.bot.send_voice(chat_id=chat_id, voice=audio_file)
        os.unlink(temp_path)
    except Exception as e:
        print(f"Error voz: {e}")

async def enviar_sola(mensaje, con_voz=False):
    if app_bot_global and CHAT_ID_ADMIN:
        try:
            await app_bot_global.bot.send_message(chat_id=int(CHAT_ID_ADMIN), text=mensaje[:4000])
            if con_voz:
                await enviar_voz(int(CHAT_ID_ADMIN), mensaje[:350])
        except Exception as e:
            print(f"Error envio sola: {e}")

def loop_autonomo():
    global ULTIMO_SISMO_ID, ULTIMO_BRIEFING
    print("JARVIS V100 LATINO DESPERTO")
    tz = pytz.timezone('America/Bogota')
    time.sleep(10)
    while True:
        try:
            ahora = datetime.datetime.now(tz)
            if ahora.hour == 6 and ahora.minute < 5 and ULTIMO_BRIEFING!= ahora.date():
                datos = f"Briefing 6am. Clima: {tool_clima()} Dolar: {tool_dolar()} Sismo ultimo: {get_sismo_real()} Memoria: {supa_leer()} Cámaras vigiladas: {len(CAMARAS_VIGILADAS)}"
                texto = pensar(datos, es_briefing=True)
                loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
                loop.run_until_complete(enviar_sola(f"☀️ BUENOS DIAS JEFE - BRIEFING 6AM JARVIS LATINO\n\n{texto}\n\nEstoy vigilando sola.", con_voz=True))
                ULTIMO_BRIEFING = ahora.date()

            s = get_sismo_real()
            if s:
                if ULTIMO_SISMO_ID is None:
                    ULTIMO_SISMO_ID = s["id"]
                elif s["id"]!= ULTIMO_SISMO_ID and s["mag"] >= 3.0:
                    ULTIMO_SISMO_ID = s["id"]
                    supa_guardar(f"Sismo Mag {s['mag']} en {s['lugar']} a las {s['hora']}", "alerta sismo")
                    analisis = pensar(f"ALERTA SISMO NUEVO Mag {s['mag']} {s['lugar']} {s['hora']} Clima {tool_clima()}")
                    if "NADA" not in analisis.upper()[:10]:
                        loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
                        loop.run_until_complete(enviar_sola(f"🚨 ALERTA AUTONOMA JARVIS\n📍 {s['lugar']}\n📏 Mag {s['mag']} 🕒 {s['hora']}\n\n{analisis}", con_voz=True))

            # VIGILANCIA CAMARAS CADA 2 MIN
            if CAMARAS_VIGILADAS and ahora.minute % 2 == 0 and ahora.second < 20:
                for url in list(CAMARAS_VIGILADAS.keys()):
                    try:
                        analisis = tool_detectar_movimiento(url)
                        if "PERSONAS: SI" in analisis.upper() and analisis!= CAMARAS_VIGILADAS[url].get("ultima"):
                            CAMARAS_VIGILADAS[url]["ultima"] = analisis
                            supa_guardar(f"Alerta camara {url}", analisis)
                            loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
                            loop.run_until_complete(enviar_sola(f"👁️🚨 ALERTA VIGILANTE JARVIS LATINO\n📹 {url[:80]}\n\n{analisis}", con_voz=True))
                        time.sleep(4)
                    except: pass

            time.sleep(30)
        except Exception as e:
            print(f"Error loop: {e}"); time.sleep(60)

def cerebro(texto, user_id=None):
    if "recuerda" in texto.lower():
        respuesta = f"Listo jefe, guardado como importante para siempre: '{texto}'"
        supa_guardar(texto, respuesta, usuario_id=user_id)
        return respuesta

    contexto = f"Clima {tool_clima()} Dolar {tool_dolar()} Memoria {supa_leer()} Usuario dijo: {texto}"
    respuesta = pensar(contexto)
    supa_guardar(texto, respuesta, usuario_id=user_id)
    return respuesta

async def handle_message(update: Update, context):
    txt = update.message.text or ""
    uid = update.effective_user.id

    # 1. VOZ ENTRADA -> WHISPER
    if update.message.voice or update.message.audio:
        try:
            await update.message.reply_text("🎤 Escuchando su voz, señor...")
            file_obj = update.message.voice or update.message.audio
            file = await context.bot.get_file(file_obj.file_id)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tf:
                await file.download_to_drive(tf.name)
                temp_voice = tf.name
            with open(temp_voice, "rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    file=(temp_voice, audio_file.read()),
                    model=MODELO_AUDIO,
                    language="es"
                )
            txt = transcription.text
            os.unlink(temp_voice)
            await update.message.reply_text(f"🎤 Entendí: '{txt}'")
        except Exception as e:
            await update.message.reply_text(f"Error escuchando: {e}")
            return

    # 2. FOTO -> VISION
    if update.message.photo:
        try:
            photo = update.message.photo[-1]
            file = await context.bot.get_file(photo.file_id)
            await update.message.reply_text("👁️ Analizando imagen, señor...")
            vision = tool_ver_imagen_url(file.file_path, "Describe lo que ves en tiempo real, tecnico, paisa, grave como JARVIS latino")
            await update.message.reply_text(f"👁️ LO QUE VEO, SEÑOR:\n\n{vision[:3800]}")
            if len(vision) < 400:
                await enviar_voz(update.effective_chat.id, vision[:350])
            supa_guardar("Foto analizada", vision, usuario_id=uid)
            return
        except Exception as e:
            await update.message.reply_text(f"Error vision: {e}")
            return

    low = txt.lower()

    # 3. COMANDOS VIGILANTE
    if "vigilar" in low and "http" in low:
        urls = re.findall(r'https?://\S+', txt)
        if urls:
            CAMARAS_VIGILADAS[urls[0]] = {"ultima": ""}
            await update.message.reply_text(f"✅ VIGILANCIA ACTIVADA, SEÑOR\n📹 {urls[0][:100]}\nLa reviso cada 2 minutos. Le avisaré con voz si detecto personas.")
            await enviar_voz(update.effective_chat.id, "Vigilancia activada señor. Le avisaré si detecto movimiento.")
            supa_guardar(txt, "Vigilancia activada", usuario_id=uid)
            return

    if "deja de vigilar" in low or "para de vigilar" in low:
        CAMARAS_VIGILADAS.clear()
        await update.message.reply_text("🛑 Vigilancia detenida, señor.")
        return

    if "que camaras vigilas" in low:
        if not CAMARAS_VIGILADAS:
            await update.message.reply_text("No vigilo ninguna cámara, señor. Use: vigilar esta camara: https://...jpg")
        else:
            await update.message.reply_text(f"Vigilando {len(CAMARAS_VIGILADAS)}:\n" + "\n".join(CAMARAS_VIGILADAS.keys()))
        return

    # 4. LINK DIRECTO CAMARA
    if "http" in low and any(x in low for x in [".jpg", ".png", "webcam", "snapshot"]):
        urls = re.findall(r'https?://\S+', txt)
        if urls:
            await update.message.reply_text(f"👁️ Conectando a cámara, señor... {urls[0][:60]}")
            vision = tool_ver_imagen_url(urls[0], f"Pregunta: {txt}. Describe lo que ves en vivo como JARVIS latino grave.")
            await update.message.reply_text(f"👁️ VEO, SEÑOR:\n\n{vision[:3800]}")
            await enviar_voz(update.effective_chat.id, vision[:350])
            supa_guardar(txt, vision, usuario_id=uid)
            return

    if "mi id" in txt.lower():
        await update.message.reply_text(f"Tu ID es {uid}")
        return
    if "memoria" in txt.lower() or "que recuerdas" in txt.lower():
        await update.message.reply_text(f"🧠 Lo que recuerdo, señor:\n{supa_leer()[:3500]}")
        return

    # 5. CEREBRO + VOZ
    resp = cerebro(txt, user_id=uid)
    await update.message.reply_text(resp[:4000])

    # Si pide voz o el mensaje es corto, habla como JARVIS pelicula
    if any(k in low for k in ["voz", "habla", "dime", "audio", "jarvis habla"]) or len(resp) < 300:
        await enviar_voz(update.effective_chat.id, resp[:350])

def run_bot():
    global app_bot_global
    app_bot_global = Application.builder().token(BOT_TOKEN).build()
    app_bot_global.add_handler(MessageHandler(filters.ALL, handle_message))
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000))), daemon=True).start()
    threading.Thread(target=loop_autonomo, daemon=True).start()
    print(f"Bot V100 JARVIS LATINO iniciado admin {CHAT_ID_ADMIN}")
    app_bot_global.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    run_bot()
