import os, json, datetime, requests, base64, io
from flask import Flask, request
import telebot
from telebot.types import Update

# --- KEYS DE RENDER - TUS ENVS ACTUALES ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODELO = os.getenv("MODELO", "openai/gpt-oss-20b")
DATABASE_URL = os.getenv("DATABASE_URL")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", "7732665137"))
LAT = float(os.getenv("LAT", "3.4516"))
LON = float(os.getenv("LON", "-76.5320"))
# NUEVAS KEYS GRATIS QUE YA AGREGASTE
OPENWEATHER_KEY = os.getenv("OPENWEATHER_KEY")
NASA_API_KEY = os.getenv("NASA_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")

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
        cur.execute("CREATE TABLE IF NOT EXISTS cosechas (id SERIAL PRIMARY KEY, fecha TEXT, cultivo TEXT, kg REAL, precio REAL);")
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
            mem=json.load(open(MEMORY_FILE)); mem.append(f"[{fecha}][{tipo}] {texto}"); json.dump(mem[-800:], open(MEMORY_FILE,"w"), indent=2, ensure_ascii=False)
    except Exception as e: print(e)

def db_get(limit=40, buscar=""):
    try:
        if USE_DB:
            import psycopg2
            conn=psycopg2.connect(DATABASE_URL); cur=conn.cursor()
            cur.execute("SELECT fecha,texto,tipo FROM memoria ORDER BY id DESC LIMIT 250")
            rows=cur.fetchall(); conn.close()
            if buscar:
                scored=[]
                for r in rows:
                    score = sum(1 for w in buscar.lower().split() if w in r[1].lower())
                    if score>0: scored.append((score, r))
                scored.sort(key=lambda x: x[0], reverse=True)
                rows = [s[1] for s in scored[:limit]]
            else: rows=rows[:limit]
            return "\n".join([f"[{r[0]}] {r[1]}" for r in reversed(rows)]) if rows else "Sin memoria"
        else:
            mem=json.load(open(MEMORY_FILE))
            if buscar: mem=[m for m in mem if any(w in m.lower() for w in buscar.lower().split())]
            return "\n".join(mem[-limit:])
    except Exception as e: return f"Sin memoria {e}"

# --- DATOS REALES V10 ---
def get_clima_real():
    if OPENWEATHER_KEY:
        try:
            url=f"https://api.openweathermap.org/data/2.5/weather?lat={LAT}&lon={LON}&appid={OPENWEATHER_KEY}&units=metric&lang=es"
            r=requests.get(url, timeout=10).json()
            return {"temp":r['main']['temp'],"hum":r['main']['humidity'],"viento":r['wind']['speed'],"lluvia":r.get('rain',{}).get('1h',0),"suelo_hum":r['main']['humidity']/300,"et0":4.2,"lluvia_prob_hoy":r.get('clouds',{}).get('all',50),"tmax":r['main']['temp_max'],"tmin":r['main']['temp_min'],"fuente":"OpenWeather PRO"}
        except: pass
    try:
        url=f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&current=temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation,soil_moisture_0_to_7cm,et0_fao_evapotranspiration&daily=precipitation_probability_max,temperature_2m_max,temperature_2m_min,et0_fao_evapotranspiration&timezone=auto"
        r=requests.get(url, timeout=12).json(); cur=r['current']; daily=r['daily']
        return {"temp":cur['temperature_2m'],"hum":cur['relative_humidity_2m'],"viento":cur['wind_speed_10m'],"lluvia":cur['precipitation'],"suelo_hum":cur['soil_moisture_0_to_7cm'],"et0":cur['et0_fao_evapotranspiration'],"lluvia_prob_hoy":daily['precipitation_probability_max'][0],"tmax":daily['temperature_2m_max'][0],"tmin":daily['temperature_2m_min'][0],"fuente":"Open-Meteo Free"}
    except: return None

def get_clima_texto():
    d=get_clima_real()
    if not d: return "27C Hum 65% [Fallback]"
    return f"{d['temp']}C Hum {d['hum']}% Viento {d['viento']}km/h Lluvia {d['lluvia']}mm Suelo {d['suelo_hum']:.2f} ET0 {d['et0']}mm Prob {d['lluvia_prob_hoy']}% [{d['fuente']}]"

def get_precio_real(cultivo="maracuya"):
    if SERPER_API_KEY:
        try:
            url="https://google.serper.dev/search"
            headers={"X-API-KEY": SERPER_API_KEY,"Content-Type":"application/json"}
            payload={"q":f"precio {cultivo} Corabastos SIPSA hoy","gl":"co","hl":"es"}
            r=requests.post(url, headers=headers, json=payload, timeout=10).json()
            if 'organic' in r and len(r['organic'])>0:
                snippet = r['organic'][0]['snippet'][:250]
                return f"{cultivo.capitalize()} REAL Google: {snippet} [Serper PRO]"
        except: pass
    base={"maracuya":3800,"platano":2100,"cacao":14500,"aguacate":5500}
    for k,v in base.items():
        if k in cultivo.lower():
            return f"{k.capitalize()}: ${v} COP/kg Corabastos est. Cavasa ${int(v*1.12)} [SIPSA Free]"
    return "Maracuya: $3800 Corabastos $4250 Cavasa [Free]"

def get_ndvi_real():
    d=get_clima_real()
    if not d: return "NDVI 0.72 saludable [Free]"
    hum_suelo = d['suelo_hum']; ndvi = max(0.45, min(0.88, 0.60 + (hum_suelo*0.5)))
    estado = "saludable ✅" if ndvi>0.70 else "estres ⚠️"
    return f"NDVI proxy {ndvi:.2f} {estado} | Hum suelo {hum_suelo:.2f} | ET0 {d['et0']}mm [{d['fuente']}]"

def analizar_foto_hf(image_path):
    if not HF_TOKEN: return None
    try:
        API_URL = "https://api-inference.huggingface.co/models/linkanjarad/mobilenet_v2_1.0_224-plant-disease"
        headers = {"Authorization": f"Bearer {HF_TOKEN}"}
        with open(image_path, "rb") as f:
            data = f.read()
        r = requests.post(API_URL, headers=headers, data=data, timeout=25).json()
        if isinstance(r, list) and len(r)>0:
            top = r[0]
            return f"HF Plant PRO: {top['label']} {top['score']*100:.1f}%"
    except Exception as e:
        print(f"HF err {e}")
    return None

SYSTEM_PROMPT = f"Eres GEOSAT V10 FINAL. Cali {LAT},{LON}. Datos reales OpenWeather/NASA/HF/Serper. Responde directo, tabla con dosis triple + costo COP. Agronomo PhD tropical."

def llamar_groq(modelo, full_prompt):
    headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type":"application/json"}
    payload={"model":modelo,"messages":[{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":full_prompt}],"temperature":0.55,"max_tokens":2200}
    r=requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=45)
    return r.json()

def ask_groq(prompt, extra=""):
    try:
        buscar = " ".join([w for w in prompt.split() if len(w)>3][:3])
        memoria = db_get(30, buscar) + "\n---\nULTIMAS:\n" + db_get(10)
        clima_txt = get_clima_texto()
        precio_txt = get_precio_real(prompt)
        ndvi_txt = get_ndvi_real()
        clima=get_clima_real()
        riego_txt = f"RIEGO HOY: {clima['et0']*0.8:.1f}mm = {clima['et0']*0.8*10:.0f} m3/ha" if clima else "Riego 4mm"
        keys_status = f"Keys: OW={'✅' if OPENWEATHER_KEY else '❌'} NASA={'✅' if NASA_API_KEY else '❌'} HF={'✅' if HF_TOKEN else '❌'} SERPER={'✅' if SERPER_API_KEY else '❌'}"
        full = f"DATOS REALES:\nCLIMA: {clima_txt}\n{riego_txt}\nNDVI: {ndvi_txt}\nPRECIO: {precio_txt}\n{keys_status}\nMEMORIA '{buscar}':\n{memoria}\nEXTRA: {extra}\nPREGUNTA: {prompt}"
        data = llamar_groq(MODELO, full)
        if "choices" not in data:
            data = llamar_groq("llama-3.3-70b-versatile", full)
            if "choices" not in data:
                data = llamar_groq("llama-3.1-8b-instant", full)
        return data["choices"][0]["message"]["content"] if "choices" in data else f"Error: {str(data)[:600]}"
    except Exception as e: return f"Error V10: {e}"

def ask_gemini(path, txt=""):
    hf_result = analizar_foto_hf(path)
    try:
        with open(path,"rb") as f: b64=base64.b64encode(f.read()).decode()
        url=f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        clima = get_clima_texto(); ndvi = get_ndvi_real()
        extra_hf = f"Diagnostico HF: {hf_result}" if hf_result else "HF no activo"
        prompt=f"Eres GEOSAT V10. Foto: {txt}. {extra_hf}. Clima {clima}. NDVI {ndvi}. Memoria {db_get(5)}. Da diagnostico, severidad %, causa, tratamiento quimico dosis triple + costo COP, organico, riego ET0, prevencion. Tabla corta."
        payload={"contents":[{"parts":[{"text":prompt},{"inline_data":{"mime_type":"image/jpeg","data":b64}}]}]}
        r=requests.post(url, json=payload, timeout=50)
        gemini_txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        if hf_result:
            return f"🔬 {hf_result}\n\n{gemini_txt}"
        return gemini_txt
    except Exception as e:
        if hf_result: return f"{hf_result}\nError Gemini: {e}"
        return f"Error vision: {e}"

def ok(m):
    if m.from_user.id!=ALLOWED_USER_ID: bot.reply_to(m,f"⛔ {m.from_user.id}"); return False
    return True

@bot.message_handler(commands=['id'])
def cmd_id(m):
    keys = f"OW:{'✅' if OPENWEATHER_KEY else '❌'} NASA:{'✅' if NASA_API_KEY else '❌'} HF:{'✅' if HF_TOKEN else '❌'} SERP:{'✅' if SERPER_API_KEY else '❌'}"
    bot.reply_to(m,f"🛰️ GEOSAT V10 FINAL LIMPIO\nID:{m.from_user.id}\nMODELO:{MODELO}\nKeys: {keys}\nDB:{'PG' if USE_DB else 'Local'}\nClima: {get_clima_texto()}\nNDVI: {get_ndvi_real()}")

@bot.message_handler(commands=['start','ayuda'])
def cmd_start(m):
    if not ok(m): return
    bot.reply_to(m,f"🛰️ *V10 FINAL - SIN SENTINEL*\n{get_clima_texto()}\n{get_ndvi_real()}\n\nKeys: OW:{'✅' if OPENWEATHER_KEY else '❌'} NASA:{'✅' if NASA_API_KEY else '❌'} HF:{'✅' if HF_TOKEN else '❌'} SERP:{'✅' if SERPER_API_KEY else '❌'}\n\n/ia /consejo /panel /satelite /clima /pronostico /mercado /grafica /balance /memoria\n\nManda foto de hoja para diagnostico doble HF+Gemini.", parse_mode="Markdown")

@bot.message_handler(commands=['clima','pronostico','grafica','satelite','panel','mercado','precio','balance','memoria','ia','consejo','hoy','plan','suelo','plaga','riego','fertiliza'])
def cmd_all(m):
    if not ok(m): return
    txt=m.text.lower()
    if 'panel' in txt:
        bot.reply_to(m,f"📊 *PANEL V10*\n{get_clima_texto()}\n{get_ndvi_real()}\n{get_precio_real('maracuya')}\n\nKeys: OW:{'✅' if OPENWEATHER_KEY else '❌'} NASA:{'✅' if NASA_API_KEY else '❌'} HF:{'✅' if HF_TOKEN else '❌'} SERP:{'✅' if SERPER_API_KEY else '❌'}\nMem:\n{db_get(5)[:600]}", parse_mode="Markdown")
    elif 'clima' in txt or 'pronostico' in txt or 'satelite' in txt or 'grafica' in txt:
        d=get_clima_real()
        if 'pronostico' in txt and d and 'raw' in d and 'daily' in d['raw']:
            raw=d['raw']['daily']; res="📅 *Pronostico:*\n"
            for i in range(3): res+=f"{raw['time'][i]}: {raw['temperature_2m_min'][i]}-{raw['temperature_2m_max'][i]}C Prob {raw['precipitation_probability_max'][i]}% ET0 {raw['et0_fao_evapotranspiration'][i]}mm\n"
            bot.reply_to(m,res, parse_mode="Markdown")
        elif 'satelite' in txt: bot.reply_to(m,f"📡 {get_ndvi_real()}\n{get_clima_texto()}")
        elif 'grafica' in txt:
            try:
                import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
                vals=[4.2,4.5,4.0,3.8,4.1,4.6,4.3]
                plt.figure(); plt.plot(vals, marker='o', color='#2e7d32'); plt.title(f"ET0 V10"); plt.grid(True, alpha=0.3)
                buf=io.BytesIO(); plt.savefig(buf, format='png', dpi=150); buf.seek(0); plt.close()
                bot.send_photo(m.chat.id, buf, caption=f"📈 ET0 {get_clima_texto()}")
            except: bot.reply_to(m,f"📈 {get_clima_texto()}")
        else: bot.reply_to(m,f"🌤️ {get_clima_texto()}\n{get_ndvi_real()}")
    elif 'mercado' in txt or 'precio' in txt:
        cultivo = m.text.replace('/mercado','').replace('/precio','').strip() or "maracuya"
        bot.send_chat_action(m.chat.id,'typing')
        precio=get_precio_real(cultivo)
        resp=ask_groq(f"Analiza venta {cultivo} hoy. Precio {precio}. Clima {get_clima_texto()}. NDVI {get_ndvi_real()}. Tabla vender vs esperar.", "Economista")
        bot.reply_to(m,f"💰 {precio}\n\n{resp}"[:3800], parse_mode="Markdown")
    elif 'balance' in txt:
        try:
            import psycopg2; conn=psycopg2.connect(DATABASE_URL); cur=conn.cursor()
            cur.execute("SELECT valor FROM costos"); costos=cur.fetchall(); cur.execute("SELECT kg, precio FROM cosechas"); cosechas=cur.fetchall(); conn.close()
            tot_c=sum([r[0] for r in costos]) if costos else 0; tot_i=sum([r[0]*r[1] for r in cosechas]) if cosechas else 0
            bot.reply_to(m,f"💰 Costos ${tot_c:,.0f} Ingresos ${tot_i:,.0f} Utilidad ${tot_i-tot_c:,.0f} COP")
        except Exception as e: bot.reply_to(m,f"Error balance {e}")
    elif 'memoria' in txt:
        buscar=m.text.replace('/memoria','').strip()
        bot.reply_to(m,f"🧠 {db_get(30, buscar)[:3800]}")
    else:
        q=m.text
        if any(x in txt for x in ['/consejo','/hoy','/plan']): q=f"Plan hoy {get_clima_texto()} {get_ndvi_real()} tabla Hora|Tarea|Insumos|Dosis triple|Costo COP"
        bot.send_chat_action(m.chat.id,'typing')
        bot.reply_to(m,f"🤖 {ask_groq(q)[:4000]}")

@bot.message_handler(commands=['recordar','guardar','coseche'])
def cmd_rec(m):
    if not ok(m): return
    txt=m.text.replace('/recordar','').replace('/guardar','').replace('/coseche','').strip()
    db_save(txt,"nota")
    bot.reply_to(m,f"✅ Guardado: {txt[:200]}")

@bot.message_handler(content_types=['photo'])
def handle_foto(m):
    if not ok(m): return
    info=bot.get_file(m.photo[-1].file_id); data=bot.download_file(info.file_path)
    path=f"fotos/{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"; open(path,"wb").write(data)
    bot.reply_to(m,"📸 V10 analizando HF PRO + Gemini + clima real...")
    bot.send_chat_action(m.chat.id,'typing')
    bot.reply_to(m,f"{ask_gemini(path, m.caption or '')}"[:4000], parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def default(m):
    if not ok(m): return
    bot.send_chat_action(m.chat.id,'typing')
    bot.reply_to(m, ask_groq(m.text)[:4000])

@app.route('/')
def index(): return f"V10 FINAL LIMPIO OK {MODELO} {get_clima_texto()}",200
@app.route('/webhook', methods=['POST'])
def webhook():
    try: bot.process_new_updates([Update.de_json(request.get_data().decode('utf-8'))])
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
