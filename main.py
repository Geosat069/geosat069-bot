import os, threading, requests, datetime, urllib.parse, time, asyncio
from flask import Flask
from telegram import Update
from telegram.ext import Application, MessageHandler, filters
from groq import Groq
import pytz

# --- CONFIG FIJA ---
BOT_TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
GROQ_KEY = os.environ.get("GROQ_API_KEY")
CHAT_ID_ADMIN = os.environ.get("CHAT_ID_ADMIN") or "7732665137"
MODELO_FIJO = "openai/gpt-oss-20b"
SUPA_URL = os.environ.get("SUPABASE_URL")
SUPA_KEY = os.environ.get("SUPABASE_KEY")

ULTIMO_SISMO_ID = None
ULTIMO_BRIEFING = None
app_bot_global = None

client = Groq(api_key=GROQ_KEY)
app = Flask(__name__)

@app.route('/')
def home():
    return f"Geosat V43 JARVIS SUPABASE VIVA - Modelo {MODELO_FIJO} - Admin {CHAT_ID_ADMIN}"

# --- SUPABASE MEMORIA ETERNA CORREGIDA PARA memoria_geosat ---
def supa_guardar(nota, usuario_id=None):
    if not SUPA_URL or not SUPA_KEY:
        print("Falta SUPABASE_URL o KEY")
        return
    try:
        uid = str(usuario_id or CHAT_ID_ADMIN)
        headers = {"apikey": SUPA_KEY, "Authorization": f"Bearer {SUPA_KEY}", "Content-Type": "application/json", "Prefer": "return=representation"}
        data = {
            "usuario_id": uid,
            "mensaje": str(nota)[:1000],
            "respuesta": "guardado auto"
        }
        r = requests.post(f"{SUPA_URL}/rest/v1/memoria_geosat", headers=headers, json=data, timeout=15)
        print(f"INSERT REAL memoria_geosat: Status {r.status_code} Body {r.text[:300]} | Nota: {nota[:50]}")
    except Exception as e:
        print(f"Error guardando memoria: {e}")

def supa_leer():
    if not SUPA_URL or not SUPA_KEY:
        return "Memoria local, sin Supabase"
    try:
        headers = {"apikey": SUPA_KEY, "Authorization": f"Bearer {SUPA_KEY}"}
        url = f"{SUPA_URL}/rest/v1/memoria_geosat?select=mensaje&order=id.desc&limit=10"
        resp = requests.get(url, headers=headers, timeout=15)
        print(f"LEER memoria_geosat: {resp.status_code} {resp.text[:300]}")
        r = resp.json()
        if isinstance(r, list) and len(r) > 0:
            return " | ".join([x.get("mensaje","") for x in r])
        return "Sin recuerdos aun"
    except Exception as e:
        print(f"Error leyendo memoria: {e}")
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
    try:
        r = requests.get("https://trm-colombia.vercel.app/?date=today", timeout=10).json()
        if r.get("data",{}).get("value"):
            return f"TRM ${r['data']['value']} COP"
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

def pensar(contexto, es_briefing=False):
    memoria = supa_leer()
    sys_prompt = f"""Eres JARVIS V43 de Cali, asistente personal autonomo. Vives sola.
MEMORIA ETERNA DE TU JEFE (Supabase): {memoria}
CONTEXTO REAL: {contexto}
Hora Bogota: {datetime.datetime.now(pytz.timezone('America/Bogota')).strftime('%d %B %Y %H:%M')}
MODELO FIJO OBLIGATORIO: {MODELO_FIJO}
Instrucciones: {'Genera briefing 6am proactivo, cariñoso, tecnico, 4 lineas' if es_briefing else 'Responde paisa, tecnico, corto. Si es sismo genera alerta. Nunca digas no tengo datos, usa el contexto real'}
"""
    try:
        c = client.chat.completions.create(model=MODELO_FIJO, messages=[{"role":"system","content":sys_prompt},{"role":"user","content":contexto}], max_tokens=800, temperature=0.4)
        return c.choices[0].message.content
    except Exception as e:
        return f"Error Groq {MODELO_FIJO}: {e} | Clima {tool_clima()} Dolar {tool_dolar()}"

async def enviar_sola(mensaje):
    if app_bot_global and CHAT_ID_ADMIN:
        try:
            await app_bot_global.bot.send_message(chat_id=int(CHAT_ID_ADMIN), text=mensaje[:4000])
        except Exception as e:
            print(f"Error envio sola: {e}")

# --- LOOP JARVIS AUTONOMO ---
def loop_autonomo():
    global ULTIMO_SISMO_ID, ULTIMO_BRIEFING
    print("JARVIS V43 DESPERTO - Esperando 6am y sismos")
    tz = pytz.timezone('America/Bogota')
    time.sleep(10)
    while True:
        try:
            ahora = datetime.datetime.now(tz)
            if ahora.hour == 6 and ahora.minute < 5 and ULTIMO_BRIEFING!= ahora.date():
                datos = f"Briefing 6am. Clima: {tool_clima()} Dolar: {tool_dolar()} Sismo ultimo: {get_sismo_real()} Memoria: {supa_leer()}"
                texto = pensar(datos, es_briefing=True)
                msg = f"☀️ BUENOS DIAS JEFE - BRIEFING 6AM JARVIS\n\n{texto}\n\nEstoy vigilando sola."
                loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
                loop.run_until_complete(enviar_sola(msg))
                ULTIMO_BRIEFING = ahora.date()

            s = get_sismo_real()
            if s:
                if ULTIMO_SISMO_ID is None:
                    ULTIMO_SISMO_ID = s["id"]
                elif s["id"]!= ULTIMO_SISMO_ID and s["mag"] >= 3.0:
                    ULTIMO_SISMO_ID = s["id"]
                    supa_guardar(f"Sismo Mag {s['mag']} en {s['lugar']} a las {s['hora']}")
                    analisis = pensar(f"ALERTA SISMO NUEVO Mag {s['mag']} {s['lugar']} {s['hora']} Clima {tool_clima()}")
                    if "NADA" not in analisis.upper()[:10]:
                        loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
                        loop.run_until_complete(enviar_sola(f"🚨 ALERTA AUTONOMA JARVIS\n📍 {s['lugar']}\n📏 Mag {s['mag']} 🕒 {s['hora']}\n\n{analisis}"))
            time.sleep(60)
        except Exception as e:
            print(f"Error loop: {e}"); time.sleep(60)

def cerebro(texto, user_id=None):
    if "recuerda" in texto.lower():
        supa_guardar(texto, usuario_id=user_id)
        return f"Listo jefe, guardado para siempre en Supabase: '{texto}'"
    contexto = f"Clima {tool_clima()} Dolar {tool_dolar()} Memoria {supa_leer()} Usuario dijo: {texto}"
    return pensar(contexto)

async def handle_message(update: Update, context):
    txt = update.message.text or ""
    uid = update.effective_user.id
    if "mi id" in txt.lower():
        await update.message.reply_text(f"Tu ID es {uid}")
        return
    if "memoria" in txt.lower() or "que recuerdas" in txt.lower():
        await update.message.reply_text(f"🧠 Lo que recuerdo:\n{supa_leer()[:3500]}")
        return
    resp = cerebro(txt, user_id=uid)
    await update.message.reply_text(resp[:4000])

def run_bot():
    global app_bot_global
    app_bot_global = Application.builder().token(BOT_TOKEN).build()
    app_bot_global.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000))), daemon=True).start()
    threading.Thread(target=loop_autonomo, daemon=True).start()
    print(f"Bot V43 JARVIS iniciado admin {CHAT_ID_ADMIN} modelo {MODELO_FIJO}")
    app_bot_global.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    run_bot()
