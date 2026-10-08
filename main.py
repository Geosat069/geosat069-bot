import os, json, datetime, requests, base64, re
from flask import Flask, request
import telebot
from telebot.types import Update
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io

# --- TUS VARIABLES EXACTAS DE RENDER - NO CAMBIAR NOMBRES ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODELO = os.getenv("MODELO") # TU MODELO, LO RESPETAMOS
DATABASE_URL = os.getenv("DATABASE_URL")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", "7732665137"))

# Coordenadas Cali por defecto
LAT = os.getenv("LAT", "3.4516")
LON = os.getenv("LON", "-76.5320")

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)

# --- BASE DE DATOS GRATIS (USA TU DATABASE_URL) ---
try:
    import psycopg2
    def db_query(q, params=(), fetch=False):
        if not DATABASE_URL: return None
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute(q, params)
        data = cur.fetchall() if fetch else None
        conn.commit()
        cur.close(); conn.close()
        return data
    # Crea tabla si no existe
    db_query("CREATE TABLE IF NOT EXISTS memoria (id SERIAL PRIMARY KEY, fecha TEXT, texto TEXT, tipo TEXT);")
    USE_DB = True
except:
    USE_DB = False

MEMORY_FILE = "memoria.json"
if not os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, "w") as f:
        json.dump([], f)
os.makedirs("fotos", exist_ok=True)

# --- SUPER CEREBRO GRATIS ---
SYSTEM_PROMPT = """
Eres GEOSAT V5 - Super Inteligencia Agronoma GRATIS.
Ubicación: Cali, Colombia, trópico 1000msnm.
Eres experto en: maracuyá, plátano, cacao, aguacate, maíz, control biológico, suelos, riego, clima tropical.
REGLAS:
- Responde siempre corto, práctico, en español, con emojis.
- Si te preguntan de plagas, da: identificación + causa + control químico y orgánico + dosis.
- Si te preguntan de clima, usa datos de wttr.in que te doy.
- Recuerda todo lo que el usuario te dijo antes.
- Nunca digas que eres IA de Meta, eres GEOSAT.
- Al final siempre da una acción para HOY.
"""

def guardar_memoria(texto, tipo="nota"):
    fecha = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        if USE_DB:
            db_query("INSERT INTO memoria (fecha, texto, tipo) VALUES (%s,%s,%s)", (fecha, texto, tipo))
        else:
            mem = json.load(open(MEMORY_FILE)) if os.path.exists(MEMORY_FILE) else []
            mem.append(f"[{fecha}][{tipo}] {texto}")
            if len(mem) > 200: mem = mem[-200:]
            json.dump(mem, open(MEMORY_FILE,"w"), indent=2, ensure_ascii=False)
    except Exception as e:
        print(e)

def obtener_memoria(limit=20):
    try:
        if USE_DB:
            rows = db_query("SELECT fecha, texto, tipo FROM memoria ORDER BY id DESC LIMIT %s", (limit,), fetch=True)
            return "\n".join([f"[{r[0]}][{r[2]}] {r[1]}" for r in reversed(rows)]) if rows else "Sin memoria"
        else:
            mem = json.load(open(MEMORY_FILE))[-limit:]
            return "\n".join(mem)
    except:
        return "Sin memoria"

def get_clima_raw():
    try:
        r = requests.get(f"https://wttr.in/{LAT},{LON}?format=j1", timeout=10).json()
        return r
    except:
        return None

def get_clima_text():
    d = get_clima_raw()
    if not d: return "Clima no disponible"
    c = d["current_condition"][0]
    return f"{c['temp_C']}°C, Hum {c['humidity']}%, Viento {c['windspeedKmph']}km/h, {c['weatherDesc'][0]['value']}"

def ask_groq(prompt, contexto_extra=""):
    if not GROQ_API_KEY or not MODELO:
        return f"❌ Falta GROQ_API_KEY o MODELO. GROQ: {bool(GROQ_API_KEY)} MODELO: {MODELO}"
    try:
        clima = get_clima_text()
        memoria = obtener_memoria(15)
        full_prompt = f"CONTEXTO:\nClima hoy: {clima}\nMemoria finca:\n{memoria}\n{contexto_extra}\n\nPREGUNTA USUARIO: {prompt}"

        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": MODELO,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": full_prompt}
            ],
            "temperature": 0.6,
            "max_tokens": 1200
        }
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        data = r.json()
        if "choices" not in data:
            return f"Error Groq: {str(data)[:500]}"
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Error super cerebro: {e}"

def ask_gemini_vision(image_path, pregunta_extra=""):
    if not GEMINI_API_KEY:
        return "Foto guardada. Para analizar necesitas activar GEMINI_API_KEY (ya la tienes, revisa Render)."
    try:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        prompt = f"Eres GEOSAT V5. Analiza esta imagen agrícola. {pregunta_extra} Da: 1) Diagnóstico 2) Severidad % 3) Causa 4) Tratamiento orgánico y químico con dosis 5) Prevención. Contexto: {get_clima_text()} Memoria: {obtener_memoria(5)} Responde corto en español."
        payload = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": b64}}]}]}
        r = requests.post(url, json=payload, timeout=35)
        j = r.json()
        return j["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return f"Error vision: {e} - {str(j)[:300] if 'j' in locals() else ''}"

def es_autorizado(m):
    if m.from_user.id!= ALLOWED_USER_ID:
        bot.reply_to(m, f"⛔ No autorizado. Tu ID es {m.from_user.id}, permitido {ALLOWED_USER_ID}. Avísame para agregarte.")
        return False
    return True

# --- COMANDOS SUPER INTELIGENCIA ---
@bot.message_handler(commands=['id','status'])
def cmd_id(m):
    db_status = "Postgres OK" if USE_DB else "JSON local"
    bot.reply_to(m, f"🛰️ GEOSAT V5\nID: {m.from_user.id}\nPermitido: {ALLOWED_USER_ID}\nMODELO: {MODELO}\nGROQ: {'✅' if GROQ_API_KEY else '❌'}\nGEMINI: {'✅' if GEMINI_API_KEY else '❌'}\nDB: {db_status}\nClima: {get_clima_text()}")

@bot.message_handler(commands=['start','ayuda'])
def cmd_start(m):
    if not es_autorizado(m): return
    bot.reply_to(m,
        f"🛰️ *GEOSAT V5 - SUPER INTELIGENCIA GRATIS*\n"
        f"Modelo: `{MODELO}`\n"
        f"DB: {'Postgres' if USE_DB else 'Local'} | Clima: {get_clima_text()}\n\n"
        "🧠 *CEREBRO:*\n"
        "/ia <pregunta> - Habla con super cerebro\n"
        "/consejo - Plan del día con clima + memoria\n"
        "/suelo <texto> - Analiza suelo\n"
        "/plaga <texto> - Diagnostica plaga\n"
        "/riego - Calcula riego hoy\n\n"
        "📸 *VISIÓN:*\n"
        "Manda foto de hoja/fruto/suelo -> diagnóstico Gemini\n\n"
        "🌦️ *CLIMA:*\n"
        "/clima /pronostico /grafica\n\n"
        "🧠 *MEMORIA:*\n"
        "/recordar <dato> /memoria /olvidar\n\n"
        "Ejemplo: /ia como controlo trips en maracuya en lluvias?",
        parse_mode="Markdown")

@bot.message_handler(commands=['clima'])
def cmd_clima(m):
    if not es_autorizado(m): return
    bot.reply_to(m, f"📍 {LAT},{LON}\n🌤️ {get_clima_text()}")

@bot.message_handler(commands=['pronostico'])
def cmd_pron(m):
    if not es_autorizado(m): return
    d = get_clima_raw()
    if not d:
        bot.reply_to(m, "No hay pronóstico"); return
    txt = "📅 *Pronóstico 3 días:*\n"
    for day in d['weather']:
        txt += f"{day['date']}: {day['mintempC']}-{day['maxtempC']}°C | Lluvia {day['hourly'][4]['chanceofrain']}% | Hum {day['hourly'][4]['humidity']}%\n"
    bot.reply_to(m, txt, parse_mode="Markdown")

@bot.message_handler(commands=['ia'])
def cmd_ia(m):
    if not es_autorizado(m): return
    q = m.text.replace('/ia','').strip()
    if not q:
        bot.reply_to(m, "Uso: /ia como controlo fusarium en platano?")
        return
    bot.send_chat_action(m.chat.id, 'typing')
    resp = ask_groq(q)
    bot.reply_to(m, f"🤖 {resp}")
    guardar_memoria(f"Pregunta: {q} | Resp: {resp[:200]}", "ia")

@bot.message_handler(commands=['consejo','hoy','plan'])
def cmd_consejo(m):
    if not es_autorizado(m): return
    bot.send_chat_action(m.chat.id, 'typing')
    d = get_clima_raw()
    lluvia = d['weather'][0]['hourly'][4]['chanceofrain'] if d else "?"
    prompt = f"Dame el plan de hoy para finca tropical. Lluvia hoy {lluvia}%. Prioriza tareas según clima. 3 tareas máximo, con horas."
    bot.reply_to(m, f"🌤️ {get_clima_text()}\n\n{ask_groq(prompt)}")

@bot.message_handler(commands=['suelo'])
def cmd_suelo(m):
    if not es_autorizado(m): return
    q = m.text.replace('/suelo','').strip() or "suelo arcilloso tropical"
    bot.send_chat_action(m.chat.id, 'typing')
    bot.reply_to(m, ask_groq(f"Analiza este suelo: {q}. Da pH ideal, materia orgánica, enmiendas, fertilización.", "Eres experto en suelos tropicales"))

@bot.message_handler(commands=['plaga'])
def cmd_plaga(m):
    if not es_autorizado(m): return
    q = m.text.replace('/plaga','').strip() or "plaga"
    bot.send_chat_action(m.chat.id, 'typing')
    bot.reply_to(m, ask_groq(f"Plaga/enfermedad: {q}. Da identificación, ciclo, control químico con dosis/ha y control orgánico/bio.", "Eres entomólogo y fitopatólogo tropical"))

@bot.message_handler(commands=['riego'])
def cmd_riego(m):
    if not es_autorizado(m): return
    bot.send_chat_action(m.chat.id, 'typing')
    bot.reply_to(m, ask_groq(f"Calcula riego hoy. Datos: {get_clima_text()}, cultivo tropical mixto. Da litros/planta, frecuencia, hora ideal.", "Eres experto en riego por goteo y microaspersión"))

@bot.message_handler(commands=['grafica','ndvi'])
def cmd_graf(m):
    if not es_autorizado(m): return
    # Grafica demo que luego conectas a satélite real
    vals = [0.62,0.65,0.63,0.68,0.71,0.69,0.73,0.75,0.72]
    plt.figure(figsize=(7,4))
    plt.plot(vals, marker='o', linewidth=2)
    plt.title(f"GEOSAT NDVI - {MODELO} - {datetime.datetime.now().strftime('%d/%m')}")
    plt.ylabel("NDVI"); plt.xlabel("Semana"); plt.grid(True, alpha=0.3)
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', dpi=150)
    buf.seek(0); plt.close()
    bot.send_photo(m.chat.id, buf, caption=f"📈 NDVI {MODELO}\nTendencia: {'Subiendo ✅' if vals[-1]>vals[0] else 'Bajando ⚠️'}")

@bot.message_handler(commands=['recordar','guardar'])
def cmd_rec(m):
    if not es_autorizado(m): return
    txt = m.text.replace('/recordar','').replace('/guardar','').strip()
    if not txt:
        bot.reply_to(m, "Uso: /recordar apliqué 2kg de cal dolomita lote 3"); return
    guardar_memoria(txt, "nota")
    bot.reply_to(m, f"✅ Memoria guardada en {'Postgres' if USE_DB else 'local'}: {txt}")

@bot.message_handler(commands=['memoria','notas'])
def cmd_mem(m):
    if not es_autorizado(m): return
    bot.reply_to(m, f"🧠 Memoria ({'Postgres' if USE_DB else 'Local'}):\n{obtener_memoria(25)}")

@bot.message_handler(commands=['olvidar','borrar'])
def cmd_del(m):
    if not es_autorizado(m): return
    try:
        if USE_DB:
            db_query("DELETE FROM memoria")
        else:
            json.dump([], open(MEMORY_FILE,"w"))
        bot.reply_to(m, "🗑️ Memoria borrada")
    except Exception as e:
        bot.reply_to(m, f"Error: {e}")

@bot.message_handler(content_types=['photo'])
def handle_foto(m):
    if not es_autorizado(m): return
    try:
        info = bot.get_file(m.photo[-1].file_id)
        data = bot.download_file(info.file_path)
        path = f"fotos/{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        with open(path, "wb") as f:
            f.write(data)
        bot.reply_to(m, "📸 Foto recibida, analizando con GEMINI VISION...")
        bot.send_chat_action(m.chat.id, 'typing')
        caption = m.caption or ""
        diag = ask_gemini_vision(path, caption)
        bot.reply_to(m, f"🔬 *Diagnóstico V5:*\n{diag}", parse_mode="Markdown")
        guardar_memoria(f"Foto: {caption} -> {diag[:300]}", "foto")
    except Exception as e:
        bot.reply_to(m, f"Error foto: {e}")

@bot.message_handler(func=lambda m: True)
def default(m):
    if not es_autorizado(m): return
    bot.send_chat_action(m.chat.id, 'typing')
    resp = ask_groq(m.text)
    bot.reply_to(m, resp)

@app.route('/')
def index():
    return f"GEOSAT V5 SUPER - MODELO {MODELO} - DB {'Postgres' if USE_DB else 'Local'} - {get_clima_text()}", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_data().decode('utf-8'))
    bot.process_new_updates([update])
    return "ok", 200

def setup_webhook():
    try:
        bot.remove_webhook()
        if WEBHOOK_URL:
            bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
            print(f"Webhook: {WEBHOOK_URL}/webhook")
    except Exception as e:
        print(f"Webhook error: {e}")

setup_webhook()
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
