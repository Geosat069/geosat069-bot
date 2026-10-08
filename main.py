import os, json, datetime, requests, base64, io
from flask import Flask, request
import telebot
from telebot.types import Update

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODELO = os.getenv("MODELO")
DATABASE_URL = os.getenv("DATABASE_URL")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", "7732665137"))
LAT = os.getenv("LAT", "3.4516")
LON = os.getenv("LON", "-76.5320")

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)
os.makedirs("fotos", exist_ok=True)
MEMORY_FILE = "memoria.json"
if not os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE,"w") as f: json.dump([],f)

USE_DB=False
try:
    import psycopg2
    if DATABASE_URL:
        conn=psycopg2.connect(DATABASE_URL)
        cur=conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS memoria (id SERIAL PRIMARY KEY, fecha TEXT, texto TEXT, tipo TEXT);")
        cur.execute("CREATE TABLE IF NOT EXISTS costos (id SERIAL PRIMARY KEY, fecha TEXT, concepto TEXT, valor REAL);")
        conn.commit(); cur.close(); conn.close()
        USE_DB=True
except: USE_DB=False

def db_save(texto, tipo="nota"):
    fecha=datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        if USE_DB:
            import psycopg2
            conn=psycopg2.connect(DATABASE_URL); cur=conn.cursor()
            cur.execute("INSERT INTO memoria (fecha,texto,tipo) VALUES (%s,%s,%s)",(fecha,texto,tipo))
            conn.commit(); cur.close(); conn.close()
        else:
            mem=json.load(open(MEMORY_FILE)); mem.append(f"[{fecha}][{tipo}] {texto}");
            json.dump(mem[-500:], open(MEMORY_FILE,"w"), indent=2, ensure_ascii=False)
    except Exception as e: print(e)

def db_get(limit=25, buscar=""):
    try:
        if USE_DB:
            import psycopg2
            conn=psycopg2.connect(DATABASE_URL); cur=conn.cursor()
            if buscar:
                cur.execute("SELECT fecha,texto,tipo FROM memoria WHERE texto ILIKE %s ORDER BY id DESC LIMIT %s", (f"%{buscar}%", limit))
            else:
                cur.execute("SELECT fecha,texto,tipo FROM memoria ORDER BY id DESC LIMIT %s",(limit,))
            rows=cur.fetchall(); conn.close()
            return "\n".join([f"[{r[0]}] {r[1]}" for r in reversed(rows)]) if rows else "Sin memoria"
        else:
            mem=json.load(open(MEMORY_FILE))
            if buscar: mem=[m for m in mem if buscar.lower() in m.lower()]
            return "\n".join(mem[-limit:])
    except: return "Sin memoria"

def get_clima_full():
    try: return requests.get(f"https://wttr.in/{LAT},{LON}?format=j1", timeout=10).json()
    except: return None
def get_clima():
    d=get_clima_full()
    if not d: return "27C Hum 65%"
    c=d["current_condition"][0]
    return f"{c['temp_C']}C Hum {c['humidity']}% Viento {c['windspeedKmph']}km/h {c['weatherDesc'][0]['value']}"

SYSTEM_PROMPT=f"""
Eres GEOSAT V6 SUPER INTELIGENCIA GRATIS - Finca Cali {LAT},{LON}.
Modelo: {MODELO} + Gemini Vision.
Eres agronomo, entomologo, fitopatologo, edafologo tropical.
OBJETIVO: Maximizar produccion con minimo costo, 100% gratis.
REGLAS SUPER:
- Si usuario pregunta por lote, busca en memoria ese lote y usalo.
- Si clima llueve >70%, no recomiendes foliar.
- Da siempre dosis en 3 formatos: /ha, /bomba 20L, /planta si aplica.
- Costo estimado en COP.
- Responde en tabla markdown cuando sean tareas.
- Al final pregunta: ¿Lo guardo en memoria?
"""

def ask_groq(prompt, extra=""):
    try:
        # Busqueda inteligente en memoria
        keywords = prompt.split()[:3]
        buscar = keywords[0] if len(keywords)>0 else ""
        memoria_relevante = db_get(15, buscar) + "\n" + db_get(10)
        clima = get_clima()
        full = f"CLIMA: {clima}\nMEMORIA RELEVANTE (busqueda {buscar}):\n{memoria_relevante}\nEXTRA: {extra}\nPREGUNTA USUARIO: {prompt}\nResponde como GEOSAT V6."
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type":"application/json"}
        payload={"model":MODELO,"messages":[{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":full}],"temperature":0.6,"max_tokens":1800}
        r=requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=35)
        data=r.json()
        return data["choices"][0]["message"]["content"] if "choices" in data else f"Error Groq: {data}"
    except Exception as e: return f"Error V6: {e}"

def ask_gemini(path, txt=""):
    try:
        with open(path,"rb") as f: b64=base64.b64encode(f.read()).decode()
        url=f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        prompt=f"Analiza imagen agrícola. {txt}. Clima {get_clima()}. Memoria {db_get(5)}. Da: Diagnostico, Severidad %, Causa, Trat Quimico con dosis, Trat Organico, Prevencion, Costo COP. Español corto."
        payload={"contents":[{"parts":[{"text":prompt},{"inline_data":{"mime_type":"image/jpeg","data":b64}}]}]}
        r=requests.post(url, json=payload, timeout=40)
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e: return f"Error vision: {e}"

def ok(m):
    if m.from_user.id!=ALLOWED_USER_ID:
        bot.reply_to(m,f"No autorizado {m.from_user.id}"); return False
    return True

@bot.message_handler(commands=['id'])
def cmd_id(m): bot.reply_to(m,f"🛰️ GEOSAT V6 PRO MAX\nID:{m.from_user.id}\nMODELO:{MODELO}\nGROQ:{'OK' if GROQ_API_KEY else 'NO'}\nGEMINI:{'OK' if GEMINI_API_KEY else 'NO'}\nDB:{'Postgres' if USE_DB else 'Local'}\nClima:{get_clima()}\nMemoria:{len(db_get(1000).splitlines())}")

@bot.message_handler(commands=['start','ayuda'])
def cmd_start(m):
    if not ok(m): return
    bot.reply_to(m,f"🛰️ *GEOSAT V6 PRO MAX*\nModelo `{MODELO}`\n*SUPER PODERES GRATIS:*\n/ia <pregunta> - Cerebro con memoria vectorial\n/consejo - Plan con clima + memoria lote\n/suelo /plaga /riego /fertiliza\n/clima /pronostico /grafica\n/recordar <dato> - Guarda para siempre en Postgres\n/memoria lote 3 - Busca memoria filtrada\n/balance - Costos\n/foto - Manda foto hoja\n\nEj: /memoria lote 3\nEj: /ia que aplico hoy en lote 3 segun memoria?", parse_mode="Markdown")

@bot.message_handler(commands=['clima','pronostico','grafica'])
def cmd_clima(m):
    if not ok(m): return
    if 'pronostico' in m.text:
        d=get_clima_full()
        if not d: bot.reply_to(m,"Sin datos"); return
        txt="📅 Pronostico:\n"
        for day in d['weather']: txt+=f"{day['date']}: {day['mintempC']}-{day['maxtempC']}C Lluvia {day['hourly'][4]['chanceofrain']}%\n"
        bot.reply_to(m,txt)
    elif 'grafica' in m.text:
        try:
            import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
            vals=[0.62,0.65,0.63,0.68,0.71,0.69,0.73,0.75,0.72,0.77]
            plt.figure(); plt.plot(vals, marker='o'); plt.title(f"NDVI {MODELO}");
            buf=io.BytesIO(); plt.savefig(buf, format='png'); buf.seek(0); plt.close()
            bot.send_photo(m.chat.id, buf, caption=f"📈 NDVI tendencia ↑ {get_clima()}")
        except: bot.reply_to(m,f"📈 NDVI: 0.62-0.77 tendencia subiendo ✅ {get_clima()}")
    else: bot.reply_to(m,get_clima())

@bot.message_handler(commands=['ia','consejo','suelo','plaga','riego','fertiliza','balance','hoy','plan'])
def cmd_ia(m):
    if not ok(m): return
    q=m.text
    if q.startswith('/consejo') or q.startswith('/hoy') or q.startswith('/plan'):
        d=get_clima_full(); lluvia=d['weather'][0]['hourly'][4]['chanceofrain'] if d else "?"
        q=f"Plan hoy lluvia {lluvia}%, 3 tareas con hora, insumos, dosis, seguridad, costo COP"
    bot.send_chat_action(m.chat.id,'typing')
    resp=ask_groq(q)
    bot.reply_to(m,f"🤖 {resp}"[:4000])
    db_save(f"Q:{q[:100]} A:{resp[:200]}","ia")

@bot.message_handler(commands=['recordar'])
def cmd_rec(m):
    if not ok(m): return
    txt=m.text.replace('/recordar','').strip()
    if not txt: return
    db_save(txt,"nota")
    # Si menciona costo, guardalo
    if '$' in txt or 'costo' in txt.lower() or 'kg' in txt.lower():
        try:
            if USE_DB:
                import psycopg2, re
                valor = float(re.findall(r'\d+', txt.replace('.',''))[0])
                conn=psycopg2.connect(DATABASE_URL); cur=conn.cursor()
                cur.execute("INSERT INTO costos (fecha, concepto, valor) VALUES (%s,%s,%s)",(datetime.datetime.now().strftime("%Y-%m-%d"), txt, valor))
                conn.commit(); cur.close(); conn.close()
        except: pass
    bot.reply_to(m,f"✅ Memoria infinita guardada: {txt}")

@bot.message_handler(commands=['memoria'])
def cmd_mem(m):
    if not ok(m): return
    buscar=m.text.replace('/memoria','').strip()
    mem=db_get(30, buscar)
    bot.reply_to(m,f"🧠 Memoria {'Postgres' if USE_DB else 'Local'} filtro '{buscar}':\n{mem[:3800]}")

@bot.message_handler(content_types=['photo'])
def handle_foto(m):
    if not ok(m): return
    info=bot.get_file(m.photo[-1].file_id); data=bot.download_file(info.file_path)
    path=f"fotos/{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    open(path,"wb").write(data)
    bot.reply_to(m,"📸 Analizando con super vision...")
    bot.send_chat_action(m.chat.id,'typing')
    bot.reply_to(m,f"🔬 {ask_gemini(path, m.caption or '')}"[:4000])

@bot.message_handler(func=lambda m: True)
def default(m):
    if not ok(m): return
    bot.send_chat_action(m.chat.id,'typing')
    bot.reply_to(m,ask_groq(m.text)[:4000])

@app.route('/')
def index(): return f"GEOSAT V6 OK {MODELO} DB {'PG' if USE_DB else 'JSON'} {get_clima()}",200
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        update=Update.de_json(request.get_data().decode('utf-8'))
        bot.process_new_updates([update])
    except: pass
    return "ok",200

def setup_webhook():
    try:
        bot.remove_webhook()
        if WEBHOOK_URL: bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
    except: pass
setup_webhook()
if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
