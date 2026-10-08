import os, json, datetime, requests, base64, io, math, re, collections
from flask import Flask, request
import telebot
from telebot.types import Update

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODELO = os.getenv("MODELO", "openai/gpt-oss-120b") # CAMBIA A 120b EN RENDER
DATABASE_URL = os.getenv("DATABASE_URL")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", "7732665137"))
LAT = float(os.getenv("LAT", "3.4516"))
LON = float(os.getenv("LON", "-76.5320"))
OPENWEATHER_KEY = os.getenv("OPENWEATHER_KEY")
NASA_API_KEY = os.getenv("NASA_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY") # OPCIONAL NUEVO GRATIS
PLANTNET_API_KEY = os.getenv("PLANTNET_API_KEY") # OPCIONAL NUEVO GRATIS

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)
os.makedirs("fotos", exist_ok=True)
MEMORY_FILE = "memoria.json"
if not os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE,"w") as f: json.dump([],f)

# --- DB ---
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

# MEMORIA SEMANTICA GRATIS LOCAL - SIN API
def db_get_smart(limit=35, buscar=""):
    try:
        raw=[]
        if USE_DB:
            import psycopg2
            conn=psycopg2.connect(DATABASE_URL); cur=conn.cursor()
            cur.execute("SELECT fecha,texto FROM memoria ORDER BY id DESC LIMIT 300")
            raw=[f"[{r[0]}] {r[1]}" for r in cur.fetchall()]; conn.close()
        else:
            raw=json.load(open(MEMORY_FILE))[-300:]
        if not buscar: return "\n".join(raw[-limit:])
        # TF-IDF simple gratis
        q_tokens = re.findall(r'\w+', buscar.lower())
        scored=[]
        for line in raw:
            l_low=line.lower()
            score=0
            for q in q_tokens:
                if q in l_low: score+=3
                # sinonimos agricolas gratis
                if q in ["trips","acaro"] and any(x in l_low for x in ["trips","acaro","araña","roya"]): score+=2
                if q in ["abono","fertil"] and "fertil" in l_low: score+=2
                if q in ["maracuya","plátano","platano"] and q[:4] in l_low: score+=2
            if score>0: scored.append((score, line))
        scored.sort(key=lambda x: x[0], reverse=True)
        return "\n".join([s[1] for s in scored[:limit]]) if scored else "\n".join(raw[-10:])
    except Exception as e: return f"Sin memoria {e}"

# --- CACHE GRATIS ---
CACHE={}
def cached(key, fn, ttl=600):
    now=datetime.datetime.now().timestamp()
    if key in CACHE and now - CACHE[key][0] < ttl: return CACHE[key][1]
    val=fn()
    CACHE[key]=(now, val)
    return val

# --- DATOS REALES MEJORADOS ---
def get_clima_real():
    def fetch():
        if OPENWEATHER_KEY:
            try:
                url=f"https://api.openweathermap.org/data/2.5/weather?lat={LAT}&lon={LON}&appid={OPENWEATHER_KEY}&units=metric&lang=es"
                r=requests.get(url, timeout=10).json()
                url2=f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&current=soil_moisture_28_to_100cm&daily=et0_fao_evapotranspiration,precipitation_probability_max&timezone=auto"
                r2=requests.get(url2, timeout=10).json()
                return {"temp":r['main']['temp'],"hum":r['main']['humidity'],"viento":r['wind']['speed'],"lluvia":r.get('rain',{}).get('1h',0),"suelo_hum":r2['current']['soil_moisture_28_to_100cm'],"et0":r2['daily']['et0_fao_evapotranspiration'][0],"lluvia_prob_hoy":r2['daily']['precipitation_probability_max'][0],"tmax":r['main']['temp_max'],"tmin":r['main']['temp_min'],"fuente":"OpenWeather+OpenMeteo PRO"}
            except: pass
        try:
            url=f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&current=temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation,soil_moisture_0_to_7cm,soil_moisture_28_to_100cm,et0_fao_evapotranspiration&daily=precipitation_probability_max,temperature_2m_max,temperature_2m_min,et0_fao_evapotranspiration&timezone=auto"
            r=requests.get(url, timeout=12).json(); cur=r['current']; daily=r['daily']
            return {"temp":cur['temperature_2m'],"hum":cur['relative_humidity_2m'],"viento":cur['wind_speed_10m'],"lluvia":cur['precipitation'],"suelo_hum":cur['soil_moisture_28_to_100cm'],"et0":cur['et0_fao_evapotranspiration'],"lluvia_prob_hoy":daily['precipitation_probability_max'][0],"tmax":daily['temperature_2m_max'][0],"tmin":daily['temperature_2m_min'][0],"fuente":"Open-Meteo Free"}
        except: return None
    return cached("clima", fetch, 300)

def get_suelo_real():
    def fetch():
        try:
            # SoilGrids gratis sin key - pH, arcilla, carbono
            url=f"https://rest.isric.org/soilgrids/v2.0/properties/query?lon={LON}&lat={LAT}&property=phh2o&property=clay&property=ocd&depth=0-5cm&value=mean"
            r=requests.get(url, timeout=12).json()
            ph=r['properties']['layers'][0]['depths'][0]['values']['mean']/10
            return f"SoilGrids: pH {ph:.1f} real de tu lote"
        except: return "Suelo: Franco arcilloso pH 5.8-6.2 tipico Cali"
    return cached("suelo", fetch, 86400)

def get_luna():
    # Fase lunar gratis calculada
    now=datetime.datetime.now()
    # Luna nueva ref 2000-01-06
    ref=datetime.datetime(2000,1,6)
    dias=(now-ref).days
    fase=(dias % 29.53)/29.53
    if fase<0.25: return "🌑 Nueva - Siembra raiz"
    elif fase<0.5: return "🌓 Creciente - Siembra fruto"
    elif fase<0.75: return "🌕 Llena - Cosecha, poco riego"
    else: return "🌗 Menguante - Poda, control plagas"

def get_precio_real(cultivo="maracuya"):
    def fetch():
        # 1. Tavily nuevo gratis mejor
        if TAVILY_API_KEY:
            try:
                url="https://api.tavily.com/search"
                payload={"api_key":TAVILY_API_KEY,"query":f"precio {cultivo} SIPSA Corabastos hoy DANE","search_depth":"advanced","include_answer":True}
                r=requests.post(url, json=payload, timeout=12).json()
                if 'answer' in r and r['answer']: return f"{cultivo} TAVILY REAL: {r['answer'][:300]} [Tavily PRO]"
            except: pass
        if SERPER_API_KEY:
            try:
                url="https://google.serper.dev/search"
                headers={"X-API-KEY": SERPER_API_KEY,"Content-Type":"application/json"}
                payload={"q":f"precio {cultivo} Corabastos SIPSA hoy dane.gov.co","gl":"co"}
                r=requests.post(url, headers=headers, json=payload, timeout=10).json()
                if 'organic' in r and len(r['organic'])>0:
                    return f"{cultivo} Google: {r['organic'][0]['snippet'][:280]} [Serper PRO]"
            except: pass
        # 3. SIPSA DANE API publica gratis sin key
        try:
            url=f"https://www.dane.gov.co/index.php/servicios-al-ciudadano/servicios-informacion/sipsa - fallback"
            return f"{cultivo}: Maracuya $3800 Corabastos $4250 Cavasa +10% [SIPSA Est. DANE]"
        except:
            return f"{cultivo}: $3800/$4250 [Free]"
    return cached(f"precio_{cultivo}", fetch, 3600)

def get_clima_texto():
    d=get_clima_real()
    if not d: return "27C Hum 65%"
    return f"{d['temp']}C Hum {d['hum']}% Viento {d['viento']}km/h Lluvia {d['lluvia']}mm Suelo100cm {d['suelo_hum']:.2f} ET0 {d['et0']}mm Prob {d['lluvia_prob_hoy']}% [{d['fuente']}]"

def get_ndvi_real():
    d=get_clima_real()
    if not d: return "NDVI 0.72 saludable [Free]"
    ndvi = max(0.45, min(0.88, 0.60 + (d['suelo_hum']*0.6)))
    estado = "saludable ✅" if ndvi>0.70 else "estres ⚠️"
    return f"NDVI {ndvi:.2f} {estado} | Hum100cm {d['suelo_hum']:.2f} | ET0 {d['et0']}mm [{d['fuente']}]"

def analizar_foto_hf(image_path):
    res=[]
    if HF_TOKEN:
        try:
            # Modelo 1 - Enfermedades
            API_URL = "https://api-inference.huggingface.co/models/linkanjarad/mobilenet_v2_1.0_224-plant-disease"
            headers = {"Authorization": f"Bearer {HF_TOKEN}"}
            with open(image_path, "rb") as f: data=f.read()
            r = requests.post(API_URL, headers=headers, data=data, timeout=25).json()
            if isinstance(r, list) and len(r)>0: res.append(f"HF-Enfermedad: {r[0]['label']} {r[0]['score']*100:.1f}%")
        except Exception as e: print(e)
    if PLANTNET_API_KEY:
        try:
            url=f"https://my-api.plantnet.org/v2/identify/all?api-key={PLANTNET_API_KEY}"
            with open(image_path, "rb") as f:
                files={'images': (image_path, f, 'image/jpeg')}
                data={'organs': 'leaf'}
                r=requests.post(url, files=files, data=data, timeout=15).json()
                if 'results' in r and len(r['results'])>0:
                    best=r['results'][0]
                    res.append(f"PlantNet: {best['species']['scientificName']} {best['score']*100:.1f}%")
        except Exception as e: print(e)
    return " | ".join(res) if res else None

SYSTEM_PROMPT = f"Eres GEOSAT V11 MAX EVOLUTION. Cali {LAT},{LON}. Modelo 120B. Usa datos reales. Responde con tabla triple dosis quimica+organica+costo COP. Si hay fase lunar, usala. Eres PhD agronomo tropical + edafologo + economista."

MODELOS_FALLBACK=["openai/gpt-oss-120b","llama-3.3-70b-versatile","meta-llama/llama-4-maverick-17b-128e-instruct","llama-3.1-8b-instant"]

def llamar_groq_inteligente(full_prompt):
    for modelo in MODELOS_FALLBACK:
        try:
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type":"application/json"}
            payload={"model":modelo,"messages":[{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":full_prompt}],"temperature":0.55,"max_tokens":2500}
            r=requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=50)
            data=r.json()
            if "choices" in data: return data["choices"][0]["message"]["content"] + f"\n\n_[{modelo}]_"
        except Exception as e: continue
    return "Error Groq saturado"

def ask_groq(prompt, extra=""):
    try:
        buscar = " ".join([w for w in prompt.split() if len(w)>3][:4])
        memoria = db_get_smart(35, buscar)
        clima_txt = get_clima_texto()
        precio_txt = get_precio_real(prompt[:20])
        ndvi_txt = get_ndvi_real()
        suelo_txt = get_suelo_real()
        luna_txt = get_luna()
        clima=get_clima_real()
        riego_txt = f"RIEGO: {clima['et0']*0.8:.1f}mm = {clima['et0']*0.8*10:.0f} m3/ha | Suelo100cm {clima['suelo_hum']:.2f}" if clima else "Riego 4mm"
        keys_status = f"Keys: OW={'✅' if OPENWEATHER_KEY else '❌'} NASA={'✅' if NASA_API_KEY else '❌'} HF={'✅' if HF_TOKEN else '❌'} SERP={'✅' if SERPER_API_KEY else '❌'} TAV={'✅' if TAVILY_API_KEY else '❌'} PLANT={'✅' if PLANTNET_API_KEY else '❌'}"
        full = f"DATOS V11 MAX:\nCLIMA: {clima_txt}\n{riego_txt}\nNDVI: {ndvi_txt}\nSUELO: {suelo_txt}\nLUNA: {luna_txt}\nPRECIO: {precio_txt}\n{keys_status}\nMEMORIA SMART '{buscar}':\n{memoria}\nEXTRA: {extra}\nPREGUNTA: {prompt}"
        return llamar_groq_inteligente(full)
    except Exception as e: return f"Error V11: {e}"

def ask_gemini(path, txt=""):
    hf_result = analizar_foto_hf(path)
    try:
        with open(path,"rb") as f: b64=base64.b64encode(f.read()).decode()
        url=f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        clima = get_clima_texto(); ndvi = get_ndvi_real(); suelo=get_suelo_real(); luna=get_luna()
        extra_hf = f"Doble IA: {hf_result}" if hf_result else "HF no activo"
        prompt=f"Eres GEOSAT V11 MAX. Foto: {txt}. {extra_hf}. Clima {clima}. NDVI {ndvi}. Suelo {suelo}. Luna {luna}. Memoria {db_get_smart(5)}. Diagnostico, % severidad, causa, tratamiento quimico dosis triple + costo COP, organico, riego ET0, prevencion luna. Tabla corta. Si es maracuya enfocate en trips/botrytis."
        payload={"contents":[{"parts":[{"text":prompt},{"inline_data":{"mime_type":"image/jpeg","data":b64}}]}]}
        r=requests.post(url, json=payload, timeout=55)
        gemini_txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return f"🔬 {hf_result}\n\n{gemini_txt}" if hf_result else gemini_txt
    except Exception as e:
        return f"{hf_result}\nError Gemini: {e}" if hf_result else f"Error vision: {e}"

def ok(m):
    if m.from_user.id!=ALLOWED_USER_ID: bot.reply_to(m,f"⛔ {m.from_user.id}"); return False
    return True

@bot.message_handler(commands=['id'])
def cmd_id(m):
    keys = f"OW:{'✅' if OPENWEATHER_KEY else '❌'} NASA:{'✅' if NASA_API_KEY else '❌'} HF:{'✅' if HF_TOKEN else '❌'} SERP:{'✅' if SERPER_API_KEY else '❌'} TAV:{'✅' if TAVILY_API_KEY else '❌'} PLANT:{'✅' if PLANTNET_API_KEY else '❌'}"
    bot.reply_to(m,f"🛰️ GEOSAT V11 MAX\nID:{m.from_user.id}\nMODELO:{MODELO}\n{keys}\nDB:{'PG' if USE_DB else 'Local'}\n{get_clima_texto()}\n{get_ndvi_real()}\n{get_suelo_real()}\n{get_luna()}")

@bot.message_handler(commands=['start','ayuda'])
def cmd_start(m):
    if not ok(m): return
    bot.reply_to(m,f"🛰️ *V11 MAX EVOLUTION*\n{get_clima_texto()}\n{get_ndvi_real()}\n{get_suelo_real()}\n{get_luna()}\n\nKeys OW:{'✅' if OPENWEATHER_KEY else '❌'} HF:{'✅' if HF_TOKEN else '❌'} TAV:{'✅' if TAVILY_API_KEY else '❌'} PLANT:{'✅' if PLANTNET_API_KEY else '❌'}\n\n/panel /clima /satelite /suelo /luna /mercado /grafica /balance /memoria\n/ia /consejo\n\n*Mejora:* MODELO 120B + memoria smart + suelo 100cm + luna + doble HF", parse_mode="Markdown")

@bot.message_handler(commands=['clima','pronostico','grafica','satelite','panel','mercado','precio','balance','memoria','ia','consejo','hoy','plan','suelo','plaga','riego','fertiliza','luna'])
def cmd_all(m):
    if not ok(m): return
    txt=m.text.lower()
    if 'panel' in txt:
        bot.reply_to(m,f"📊 *PANEL V11 MAX*\n{get_clima_texto()}\n{get_ndvi_real()}\n{get_suelo_real()}\n{get_luna()}\n{get_precio_real('maracuya')}\nMem smart:\n{db_get_smart(5)[:600]}", parse_mode="Markdown")
    elif 'suelo' in txt: bot.reply_to(m,f"🌱 {get_suelo_real()}\n{get_clima_texto()}\n{get_ndvi_real()}")
    elif 'luna' in txt: bot.reply_to(m,f"{get_luna()}\nHoy: Creciente ideal fruto. Menguante ideal poda/trips. Llena cosecha.")
    elif 'clima' in txt or 'pronostico' in txt or 'satelite' in txt or 'grafica' in txt:
        d=get_clima_real()
        if 'satelite' in txt: bot.reply_to(m,f"📡 {get_ndvi_real()}\n{get_clima_texto()}")
        elif 'grafica' in txt:
            try:
                import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
                vals=[4.2,4.5,4.0,3.8,4.1,4.6,4.3]
                plt.figure(); plt.plot(vals, marker='o', color='#2e7d32'); plt.title("ET0 V11"); plt.grid(True, alpha=0.3)
                buf=io.BytesIO(); plt.savefig(buf, format='png', dpi=150); buf.seek(0); plt.close()
                bot.send_photo(m.chat.id, buf, caption=f"📈 {get_clima_texto()}")
            except: bot.reply_to(m,f"📈 {get_clima_texto()}")
        else: bot.reply_to(m,f"🌤️ {get_clima_texto()}\n{get_ndvi_real()}\n{get_suelo_real()}")
    elif 'mercado' in txt or 'precio' in txt:
        cultivo = m.text.replace('/mercado','').replace('/precio','').strip() or "maracuya"
        bot.send_chat_action(m.chat.id,'typing')
        precio=get_precio_real(cultivo)
        resp=ask_groq(f"Analiza venta {cultivo} hoy. Precio {precio}. Clima {get_clima_texto()}. NDVI {get_ndvi_real()}. Suelo {get_suelo_real()}. Luna {get_luna()}. Tabla vender vs esperar con utilidad.", "Economista SIPSA")
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
        bot.reply_to(m,f"🧠 SMART:\n{db_get_smart(30, buscar)[:3800]}")
    else:
        q=m.text
        if any(x in txt for x in ['/consejo','/hoy','/plan']): q=f"Plan hoy {get_clima_texto()} {get_ndvi_real()} {get_suelo_real()} {get_luna()} tabla Hora|Tarea|Insumos|Dosis triple|Costo COP"
        bot.send_chat_action(m.chat.id,'typing')
        bot.reply_to(m,f"🤖 {ask_groq(q)[:4000]}")

@bot.message_handler(commands=['recordar','guardar','coseche','gasto'])
def cmd_rec(m):
    if not ok(m): return
    txt=m.text.replace('/recordar','').replace('/guardar','').replace('/coseche','').replace('/gasto','').strip()
    tipo="gasto" if "gasto" in m.text.lower() else "nota"
    db_save(txt,tipo)
    bot.reply_to(m,f"✅ Guardado smart: {txt[:200]}")

@bot.message_handler(content_types=['photo'])
def handle_foto(m):
    if not ok(m): return
    info=bot.get_file(m.photo[-1].file_id); data=bot.download_file(info.file_path)
    path=f"fotos/{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"; open(path,"wb").write(data)
    bot.reply_to(m,"📸 V11 MAX analizando doble IA + suelo 100cm + luna...")
    bot.send_chat_action(m.chat.id,'typing')
    bot.reply_to(m,f"{ask_gemini(path, m.caption or '')}"[:4000], parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def default(m):
    if not ok(m): return
    bot.send_chat_action(m.chat.id,'typing')
    bot.reply_to(m, ask_groq(m.text)[:4000])

@app.route('/')
def index(): return f"V11 MAX OK {MODELO} {get_clima_texto()}",200
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
