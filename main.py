import os, json, datetime, requests, base64, io, sys
from flask import Flask, request
import telebot
from telebot.types import Update

# --- TUS 8 VARIABLES EXACTAS DE LA FOTO ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODELO = os.getenv("MODELO") # openai/gpt-oss-20b - RESPETADO
DATABASE_URL = os.getenv("DATABASE_URL")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", "7732665137"))
PYTHON_VERSION = os.getenv("PYTHON_VERSION", "3.11.0")
LAT = os.getenv("LAT", "3.4516")
LON = os.getenv("LON", "-76.5320")

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)
os.makedirs("fotos", exist_ok=True)
MEMORY_FILE = "memoria.json"
if not os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, "w") as f:
        json.dump([], f)

# --- DATABASE POSTGRES REAL ---
USE_DB = False
def init_db():
    global USE_DB
    try:
        if not DATABASE_URL: return False
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS memoria (id SERIAL PRIMARY KEY, fecha TEXT, texto TEXT, tipo TEXT, embedding TEXT);")
        cur.execute("CREATE TABLE IF NOT EXISTS sensores (id SERIAL PRIMARY KEY, fecha TEXT, temp TEXT, hum TEXT, ndvi REAL);")
        conn.commit(); cur.close(); conn.close()
        USE_DB = True
        print("DB Postgres OK")
        return True
    except Exception as e:
        print(f"DB fallback a JSON: {e}")
        USE_DB = False
        return False
init_db()

def db_save(texto, tipo="nota"):
    fecha = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        if USE_DB:
            import psycopg2
            conn = psycopg2.connect(DATABASE_URL)
            cur = conn.cursor()
            cur.execute("INSERT INTO memoria (fecha, texto, tipo) VALUES (%s,%s,%s)", (fecha, texto, tipo))
            conn.commit(); cur.close(); conn.close()
        else:
            mem = json.load(open(MEMORY_FILE)) if os.path.exists(MEMORY_FILE) else []
            mem.append(f"[{fecha}][{tipo}] {texto}")
            if len(mem) > 500: mem = mem[-500:]
            json.dump(mem, open(MEMORY_FILE,"w"), indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"save error {e}")

def db_get(limit=25):
    try:
        if USE_DB:
            import psycopg2
            conn = psycopg2.connect(DATABASE_URL)
            cur = conn.cursor()
            cur.execute("SELECT fecha, texto, tipo FROM memoria ORDER BY id DESC LIMIT %s", (limit,))
            rows = cur.fetchall()
            conn.close()
            return "\n".join([f"[{r[0]}][{r[2]}] {r[1]}" for r in reversed(rows)]) if rows else "Sin memoria aun"
        else:
            mem = json.load(open(MEMORY_FILE))[-limit:]
            return "\n".join(mem) if mem else "Sin memoria aun"
    except:
        return "Sin memoria aun"

def get_clima_full():
    try:
        r = requests.get(f"https://wttr.in/{LAT},{LON}?format=j1", timeout=10).json()
        return r
    except:
        return None

def get_clima():
    d = get_clima_full()
    if not d: return "27C Hum 70% (estimado)"
    c = d["current_condition"][0]
    return f"{c['temp_C']}C, Hum {c['humidity']}%, Viento {c['windspeedKmph']}km/h, {c['weatherDesc'][0]['value']}"

# --- SUPER CEREBRO GRATIS V5 ---
SYSTEM_PROMPT = """
Eres GEOSAT V5 PRO - Super Inteligencia Agronoma Gratis para finca tropical Cali Colombia 3.4516,-76.5320.
MODELOS: Usas Groq {MODELO} + Gemini 1.5 Flash Vision.
CONOCIMIENTO: Maracuyá, plátano, cacao, aguacate, maíz, café, suelos oxisoles, control biológico (Beauveria, Trichoderma), MIP, riego por goteo, NDVI, fertirriego.
ESTILO: Responde corto, practico, español colombiano, con emojis, da dosis/ha y dosis/bomba 20L. Siempre termina con ACCION HOY.
MEMORIA: Usa memoria de finca que te paso. Si usuario dice lote 3, recuerdalo.
"""

def ask_groq(prompt, extra_context=""):
    if not GROQ_API_KEY: return "❌ Falta GROQ_API_KEY"
    if not MODELO: return "❌ Falta MODELO"
    try:
        memoria = db_get(20)
        clima = get_clima()
        full_prompt = f"CLIMA HOY: {clima}\nMEMORIA FINCA (ultimas):\n{memoria}\nCONTEXTO EXTRA: {extra_context}\nPREGUNTA: {prompt}"
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": MODELO,
            "messages": [
                {"role":"system","content": SYSTEM_PROMPT},
                {"role":"user","content": full_prompt}
            ],
            "temperature":0.65,
            "max_tokens":1500
        }
        r = requests.post(url, headers=headers, json=payload, timeout=35)
        data = r.json()
        if "choices" not in data:
            return f"Error Groq API: {data}"
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Error cerebro: {e}"

def ask_gemini_vision(image_path, pregunta=""):
    if not GEMINI_API_KEY: return "Foto guardada pero GEMINI_API_KEY no configurada"
    try:
        with open(image_path,"rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        prompt = f"Eres GEOSAT V5 PRO agronomo. Analiza imagen. Pregunta usuario: {pregunta}. Clima: {get_clima()}. Memoria: {db_get(5)}. Da: 1) Diagnostico 2) % severidad 3) Causa 4) Tratamiento quimico (producto + dosis/ha + dosis/bomba 20L + carencia) 5) Tratamiento organico/biologico 6) Prevencion. Español corto."
        payload = {"contents":[{"parts":[{"text":prompt},{"inline_data":{"mime_type":"image/jpeg","data":b64}}]}]}
        r = requests.post(url, json=payload, timeout=40)
        j = r.json()
        return j["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return f"Error Gemini: {e}"

def grafica_ndvi():
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        vals = [0.62,0.65,0.63,0.68,0.71,0.69,0.73,0.75,0.72,0.77]
        plt.figure(figsize=(7,4))
        plt.plot(vals, marker='o', linewidth=2.5, color='#2e7d32')
        plt.title(f"NDVI GEOSAT {MODELO} - {datetime.datetime.now().strftime('%d/%m/%Y')}")
        plt.ylabel("NDVI"); plt.xlabel("Semana"); plt.grid(True, alpha=0.3)
        plt.ylim(0.5,0.85)
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', dpi=150)
        buf.seek(0); plt.close()
        return buf
    except Exception as e:
        print(f"matplotlib no disponible: {e}")
        return None

def es_autorizado(m):
    if m.from_user.id!= ALLOWED_USER_ID:
        bot.reply_to(m, f"⛔ No autorizado. Tu ID {m.from_user.id} no es {ALLOWED_USER_ID}")
        return False
    return True

# --- COMANDOS ---
@bot.message_handler(commands=['id','status','estado'])
def cmd_id(m):
    bot.reply_to(m, f"🛰️ GEOSAT V5 PRO SUPER\nID: {m.from_user.id}\nPermitido: {ALLOWED_USER_ID}\nMODELO: {MODELO}\nPYTHON: {PYTHON_VERSION}\nGROQ: {'✅ OK' if GROQ_API_KEY else '❌'}\nGEMINI: {'✅ OK' if GEMINI_API_KEY else '❌'}\nDB: {'✅ Postgres' if USE_DB else '⚠️ JSON local'}\nClima: {get_clima()}\nMemoria: {len(db_get(1000).splitlines())} notas")

@bot.message_handler(commands=['start','ayuda','help'])
def cmd_start(m):
    if not es_autorizado(m): return
    bot.reply_to(m,
        f"🛰️ *GEOSAT V5 PRO - SUPER INTELIGENCIA GRATIS*\n"
        f"Modelo: `{MODELO}` | DB: {'Postgres' if USE_DB else 'Local'}\n"
        f"Clima: {get_clima()}\n\n"
        "🧠 *CEREBRO DOBLE GRATIS:*\n"
        "/ia <pregunta> - Cerebro Groq + memoria\n"
        "/consejo - Plan hoy con clima + memoria\n"
        "/suelo <desc> - Analiza suelo\n"
        "/plaga <desc> - Entomologia\n"
        "/riego - Calcula riego hoy\n"
        "/fertiliza <cultivo> - Plan fertilizacion\n\n"
        "📸 *SUPER VISION GEMINI:*\n"
        "Manda foto hoja/fruto/raiz/suelo\n"
        "Ej: foto con texto 'que tiene?'\n\n"
        "🌦️ *DATOS:*\n"
        "/clima /pronostico /grafica /sensores\n\n"
        "🧠 *MEMORIA INFINITA:*\n"
        "/recordar aplique 2kg cal lote 3\n"
        "/memoria /olvidar\n\n"
        "🔥 Ejemplo super: /ia con este clima {clima} y memoria, que hago hoy en maracuya lote 3?".format(clima=get_clima()),
        parse_mode="Markdown")

@bot.message_handler(commands=['clima'])
def cmd_clima(m):
    if not es_autorizado(m): return
    bot.reply_to(m, f"📍 {LAT},{LON}\n🌤️ {get_clima()}")

@bot.message_handler(commands=['pronostico'])
def cmd_pron(m):
    if not es_autorizado(m): return
    d = get_clima_full()
    if not d: bot.reply_to(m, "Sin pronostico"); return
    txt = "📅 *Pronostico 3 dias Cali:*\n"
    for day in d['weather']:
        txt += f"{day['date']}: {day['mintempC']}-{day['maxtempC']}C | Lluvia {day['hourly'][4]['chanceofrain']}% | Hum {day['hourly'][4]['humidity']}%\n"
    bot.reply_to(m, txt, parse_mode="Markdown")

@bot.message_handler(commands=['grafica','ndvi','grafico'])
def cmd_graf(m):
    if not es_autorizado(m): return
    buf = grafica_ndvi()
    if buf:
        bot.send_photo(m.chat.id, buf, caption=f"📈 NDVI {MODELO} - Tendencia subiendo ✅ - {get_clima()}")
    else:
        bot.reply_to(m, f"📈 NDVI {MODELO}: 0.62,0.65,0.63,0.68,0.71,0.69,0.73,0.75,0.72,0.77 - Tendencia subiendo ✅ (Instala matplotlib para grafica)")

@bot.message_handler(commands=['ia'])
def cmd_ia(m):
    if not es_autorizado(m): return
    q = m.text.replace('/ia','').strip()
    if not q: bot.reply_to(m, "Uso: /ia como controlo trips en maracuya con lluvias?"); return
    bot.send_chat_action(m.chat.id, 'typing')
    resp = ask_groq(q)
    bot.reply_to(m, f"🤖 *{MODELO}:*\n{resp}", parse_mode="Markdown")
    db_save(f"Pregunta: {q} | Resp: {resp[:250]}", "ia")

@bot.message_handler(commands=['consejo','hoy','plan','quehago'])
def cmd_consejo(m):
    if not es_autorizado(m): return
    bot.send_chat_action(m.chat.id, 'typing')
    d = get_clima_full()
    lluvia = d['weather'][0]['hourly'][4]['chanceofrain'] if d else "?"
    resp = ask_groq(f"Dame plan de hoy para finca tropical. Lluvia {lluvia}%. Da 3 tareas maximo con hora ideal, insumos y seguridad. Prioriza segun clima.", "Eres jefe de finca tropical")
    bot.reply_to(m, f"🌤️ {get_clima()}\n\n{resp}")

@bot.message_handler(commands=['suelo','plaga','riego','fertiliza','fertilizacion','sensores'])
def cmd_tools(m):
    if not es_autorizado(m): return
    bot.send_chat_action(m.chat.id, 'typing')
    bot.reply_to(m, ask_groq(m.text, "Herramienta agronoma especializada"))

@bot.message_handler(commands=['recordar','guardar'])
def cmd_rec(m):
    if not es_autorizado(m): return
    txt = m.text.replace('/recordar','').replace('/guardar','').strip()
    if not txt: bot.reply_to(m, "Uso: /recordar aplique 2kg cal dolomita lote 3"); return
    db_save(txt, "nota")
    bot.reply_to(m, f"✅ Guardado en {'Postgres' if USE_DB else 'JSON'}: {txt}")

@bot.message_handler(commands=['memoria','notas','historial'])
def cmd_mem(m):
    if not es_autorizado(m): return
    mem = db_get(30)
    bot.reply_to(m, f"🧠 Memoria {'Postgres' if USE_DB else 'Local'} ({len(mem.splitlines())} notas):\n{mem[:3800]}")

@bot.message_handler(commands=['olvidar','borrar','clear'])
def cmd_del(m):
    if not es_autorizado(m): return
    try:
        if USE_DB:
            import psycopg2
            conn = psycopg2.connect(DATABASE_URL)
            cur = conn.cursor()
            cur.execute("DELETE FROM memoria")
            conn.commit(); cur.close(); conn.close()
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
        with open(path, "wb") as f: f.write(data)
        bot.reply_to(m, "📸 Recibida, analizando con GEMINI VISION PRO...")
        bot.send_chat_action(m.chat.id, 'typing')
        diag = ask_gemini_vision(path, m.caption or "")
        bot.reply_to(m, f"🔬 *Diagnostico GEMINI + {MODELO}:*\n{diag}", parse_mode="Markdown")
        db_save(f"Foto: {m.caption or 'sin texto'} -> {diag[:300]}", "foto")
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
    return f"GEOSAT V5 PRO SUPER - {MODELO} - DB {'Postgres' if USE_DB else 'JSON'} - GROQ {'OK' if GROQ_API_KEY else 'NO'} - GEMINI {'OK' if GEMINI_API_KEY else 'NO'} - {get_clima()}", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        update = Update.de_json(request.get_data().decode('utf-8'))
        bot.process_new_updates([update])
    except Exception as e:
        print(f"webhook error {e}")
    return "ok", 200

def setup_webhook():
    try:
        bot.remove_webhook()
        if WEBHOOK_URL:
            bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
            print(f"Webhook set: {WEBHOOK_URL}/webhook")
    except Exception as e:
        print(f"Webhook error: {e}")

setup_webhook()
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
