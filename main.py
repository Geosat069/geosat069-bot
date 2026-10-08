import os, json, datetime, requests, base64, io, re
from flask import Flask, request
import telebot
from telebot.types import Update

BOT_TOKEN=os.getenv("BOT_TOKEN")
WEBHOOK_URL=os.getenv("WEBHOOK_URL")
GROQ_API_KEY=os.getenv("GROQ_API_KEY")
GEMINI_API_KEY=os.getenv("GEMINI_API_KEY")
MODELO=os.getenv("MODELO","openai/gpt-oss-120b")
DATABASE_URL=os.getenv("DATABASE_URL")
ALLOWED_USER_ID=int(os.getenv("ALLOWED_USER_ID",os.getenv("ALLOWED_USER_","7732665137")))
LAT=float(os.getenv("LAT","3.4516"))
LON=float(os.getenv("LON","-76.5320"))
OPENWEATHER_KEY=os.getenv("OPENWEATHER_KEY")
NASA_API_KEY=os.getenv("NASA_API_KEY")
HF_TOKEN=os.getenv("HF_TOKEN")
SERPER_API_KEY=os.getenv("SERPER_API_KEY")
TAVILY_API_KEY=os.getenv("TAVILY_API_KEY")
PLANTNET_API_KEY=os.getenv("PLANTNET_API_KEY")

bot=telebot.TeleBot(BOT_TOKEN, threaded=False)
app=Flask(__name__)
os.makedirs("fotos", exist_ok=True)
MEMORY_FILE="memoria.json"
if not os.path.exists(MEMORY_FILE):
    json.dump([], open(MEMORY_FILE,"w"))

USE_DB=False
try:
    import psycopg2
    if DATABASE_URL:
        conn=psycopg2.connect(DATABASE_URL)
        cur=conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS memoria (id SERIAL PRIMARY KEY, fecha TEXT, texto TEXT, tipo TEXT);")
        conn.commit()
        cur.close()
        conn.close()
        USE_DB=True
except:
    USE_DB=False

def db_save(texto,tipo="nota"):
    fecha=datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        if USE_DB:
            import psycopg2
            conn=psycopg2.connect(DATABASE_URL)
            cur=conn.cursor()
            cur.execute("INSERT INTO memoria (fecha,texto,tipo) VALUES (%s,%s,%s)",(fecha,texto,tipo))
            conn.commit()
            cur.close()
            conn.close()
        else:
            mem=json.load(open(MEMORY_FILE))
            mem.append(f"[{fecha}][{tipo}] {texto}")
            json.dump(mem[-900:], open(MEMORY_FILE,"w"), indent=2, ensure_ascii=False)
    except:
        pass

def db_get_smart(limit=30, buscar=""):
    try:
        raw=[]
        if USE_DB:
            import psycopg2
            conn=psycopg2.connect(DATABASE_URL)
            cur=conn.cursor()
            cur.execute("SELECT fecha,texto FROM memoria ORDER BY id DESC LIMIT 250")
            raw=[f"[{r[0]}] {r[1]}" for r in cur.fetchall()]
            conn.close()
        else:
            raw=json.load(open(MEMORY_FILE))[-250:]
        if not buscar:
            return "\n".join(raw[-limit:])
        q_tokens=re.findall(r'\w+', buscar.lower())
        sinon={"trips":["trips","frankliniella","acaro"],"botrytis":["botrytis","moho","pudricion"],"abono":["abono","urea","npk","fertil"]}
        scored=[]
        for line in raw:
            l=line.lower()
            score=0
            for q in q_tokens:
                if q in l:
                    score+=3
                for k,v in sinon.items():
                    if q in v and any(x in l for x in v):
                        score+=2
            if score>0:
                scored.append((score,line))
        scored.sort(key=lambda x:x[0], reverse=True)
        return "\n".join([s[1] for s in scored[:limit]]) if scored else "\n".join(raw[-8:])
    except:
        return "Sin memoria"

CACHE={}
def cached(key, fn, ttl=600):
    now=datetime.datetime.now().timestamp()
    if key in CACHE and now-CACHE[key][0]<ttl:
        return CACHE[key][1]
    val=fn()
    CACHE[key]=(now,val)
    return val

def get_clima_real():
    def fetch():
        try:
            url=f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&current=temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation,soil_moisture_0_to_7cm,soil_moisture_28_to_100cm,et0_fao_evapotranspiration&daily=precipitation_probability_max,temperature_2m_max,temperature_2m_min,et0_fao_evapotranspiration&timezone=auto"
            r=requests.get(url, timeout=12).json()
            cur=r['current']
            daily=r['daily']
            base={"temp":cur['temperature_2m'],"hum":cur['relative_humidity_2m'],"viento":cur['wind_speed_10m'],"lluvia":cur['precipitation'],"suelo_hum":cur['soil_moisture_28_to_100cm'],"suelo_sup":cur['soil_moisture_0_to_7cm'],"et0":cur['et0_fao_evapotranspiration'],"prob":daily['precipitation_probability_max'][0],"tmax":daily['temperature_2m_max'][0],"tmin":daily['temperature_2m_min'][0],"fuente":"OpenMeteo"}
            if OPENWEATHER_KEY:
                try:
                    u=f"https://api.openweathermap.org/data/2.5/weather?lat={LAT}&lon={LON}&appid={OPENWEATHER_KEY}&units=metric&lang=es"
                    ro=requests.get(u, timeout=8).json()
                    base.update({"temp":ro['main']['temp'],"hum":ro['main']['humidity'],"viento":ro['wind']['speed'],"fuente":"OW+OpenMeteo PRO"})
                except:
                    pass
            return base
        except:
            return None
    return cached("clima", fetch, 300)

def get_suelo_real():
    def fetch():
        try:
            url=f"https://rest.isric.org/soilgrids/v2.0/properties/query?lon={LON}&lat={LAT}&property=phh2o&property=clay&depth=0-5cm&value=mean"
            r=requests.get(url, timeout=12).json()
            ph=r['properties']['layers'][0]['depths'][0]['values']['mean']/10
            return {"ph":ph,"texto":f"pH {ph:.1f} Franco-arcilloso real SoilGrids"}
        except:
            return {"ph":6.0,"texto":"Franco arcilloso pH 5.8-6.2 tipico Cali"}
    return cached("suelo", fetch, 86400)

def get_luna():
    now=datetime.datetime.now()
    ref=datetime.datetime(2000,1,6)
    fase=((now-ref).days % 29.53)/29.53
    if fase<0.25:
        return "🌑 Nueva - Siembra raiz"
    elif fase<0.5:
        return "🌓 Creciente - Siembra fruto, fertiliza N"
    elif fase<0.75:
        return "🌕 Llena - Cosecha, NO riegues"
    else:
        return "🌗 Menguante - Poda, control plagas"

def get_precio_real(cultivo="maracuya"):
    def fetch():
        if TAVILY_API_KEY:
            try:
                url="https://api.tavily.com/search"
                payload={"api_key":TAVILY_API_KEY,"query":f"precio {cultivo} SIPSA Corabastos hoy kg DANE","search_depth":"advanced","include_answer":True}
                r=requests.post(url, json=payload, timeout=12).json()
                if r.get('answer'):
                    return f"{cultivo} SIPSA REAL: {r['answer'][:300]}"
            except:
                pass
        return f"{cultivo} $3800 Cavasa $4250 Corabastos [SIPSA Est]"
    return cached(f"precio_{cultivo}", fetch, 3600)

def get_clima_texto():
    d=get_clima_real()
    if not d:
        return "27C 65%"
    return f"{d['temp']}C Hum {d['hum']}% V {d['viento']}km/h Ll {d['lluvia']}mm Suelo100cm {d['suelo_hum']:.2f} ET0 {d['et0']}mm Prob {d['prob']}% [{d['fuente']}]"

def get_ndvi():
    d=get_clima_real()
    if not d:
        return "NDVI 0.72"
    ndvi=max(0.45,min(0.88,0.55+d['suelo_hum']*0.6))
    estado="saludable ✅" if ndvi>0.70 else "estres ⚠️"
    return f"NDVI {ndvi:.2f} {estado}"

def analizar_foto_hf(path):
    if HF_TOKEN:
        try:
            headers={"Authorization":f"Bearer {HF_TOKEN}"}
            API_URL="https://api-inference.huggingface.co/models/linkanjarad/mobilenet_v2_1.0_224-plant-disease"
            with open(path,"rb") as f:
                data=f.read()
            r=requests.post(API_URL, headers=headers, data=data, timeout=25).json()
            if isinstance(r,list) and r:
                return f"HF: {r[0]['label']} {r[0]['score']*100:.1f}%"
        except:
            pass
    return None

SYSTEM_PROMPT="Eres GEOSAT V12. Cali. PhD agronomo tropical. SIEMPRE alerta lluvia si prob>70% => NO fumigar. Calcula riego ET0*0.8. Dosis triple: quimica Dosis/Ha + Dosis/Bomba20L + costo COP + organico + carencia. Usa pH real."

MODELOS_FALLBACK=["openai/gpt-oss-120b","llama-3.3-70b-versatile","llama-3.1-8b-instant"]

def elegir_modelo(pregunta):
    q=pregunta.lower()
    if len(q)<18 or "hola" in q or "/id" in q:
        return "llama-3.1-8b-instant"
    if any(x in q for x in ["clima","suelo","luna","precio"]):
        return "llama-3.3-70b-versatile"
    return "openai/gpt-oss-120b"

def llamar_groq(prompt_completo, modelo_preferido):
    orden=[modelo_preferido]+[m for m in MODELOS_FALLBACK if m!=modelo_preferido]
    for modelo in orden:
        try:
            headers={"Authorization":f"Bearer {GROQ_API_KEY}","Content-Type":"application/json"}
            payload={"model":modelo,"messages":[{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":prompt_completo}],"temperature":0.4,"max_tokens":2500}
            r=requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=50)
            data=r.json()
            if "choices" in data:
                return data["choices"][0]["message"]["content"]+f"\n\n_[{modelo}]_"
        except:
            continue
    return "Error Groq, intenta /clima"

def ask_groq(prompt, extra=""):
    buscar=" ".join([w for w in prompt.split() if len(w)>3][:5])
    memoria=db_get_smart(35,buscar)
    clima=get_clima_real()
    suelo=get_suelo_real()
    clima_txt=get_clima_texto()
    ndvi=get_ndvi()
    precio=get_precio_real(prompt[:18])
    luna=get_luna()
    alerta=""
    if clima and clima['prob']>75:
        alerta=f"🚨 ALERTA Prob lluvia {clima['prob']}% - NO APLIQUES FOLIAR HOY"
    elif clima and clima['prob']>45:
        alerta=f"⚠️ Prob {clima['prob']}% - Fumiga 6am"
    suelo_calc=f"pH {suelo['ph']:.1f} - {'Encala 500kg/ha' if suelo['ph']<5.8 else 'pH ok'}"
    keys_status=f"OW:{'✅' if OPENWEATHER_KEY else '❌'} NASA:{'✅' if NASA_API_KEY else '❌'} HF:{'✅' if HF_TOKEN else '❌'} TAV:{'✅' if TAVILY_API_KEY else '❌'}"
    full=f"DATOS V12:\nCLIMA: {clima_txt}\nNDVI: {ndvi}\nSUELO: {suelo['texto']} {suelo_calc}\nLUNA: {luna}\nPRECIO: {precio}\n{alerta}\n{keys_status}\nMEMORIA:{memoria}\nEXTRA:{extra}\nPREGUNTA:{prompt}\nResponde con tabla TRIPLE DOSIS si es plaga."
    modelo=elegir_modelo(prompt)
    return llamar_groq(full, modelo)

def ask_gemini(path, txt=""):
    hf=analizar_foto_hf(path)
    try:
        with open(path,"rb") as f:
            b64=base64.b64encode(f.read()).decode()
        url=f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        clima=get_clima_texto()
        ndvi=get_ndvi()
        suelo=get_suelo_real()
        luna=get_luna()
        extra_hf=f"Doble IA: {hf}" if hf else ""
        prompt=f"Eres GEOSAT V12 MAX. Foto {txt}. {extra_hf}. Clima {clima}. {ndvi}. Suelo {suelo['texto']}. Luna {luna}. Diagnostica % severidad, causa, tabla dosis triple quimica + costo + organico + riego."
        payload={"contents":[{"parts":[{"text":prompt},{"inline_data":{"mime_type":"image/jpeg","data":b64}}]}]}
        r=requests.post(url, json=payload, timeout=60)
        gem=r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return f"{hf}\n\n{gem}" if hf else gem
    except Exception as e:
        return f"{hf}\nError Gemini: {e}" if hf else f"Error vision: {e}"

def ok(m):
    if m.from_user.id!=ALLOWED_USER_ID:
        bot.reply_to(m,f"⛔ ID {m.from_user.id}")
        return False
    return True

@bot.message_handler(commands=['id'])
def cmd_id(m):
    c=get_clima_real()
    prob=c['prob'] if c else 0
    alerta="🚨 NO FUMIGAR" if prob>75 else "✅"
    suelo=get_suelo_real()
    bot.reply_to(m,f"🛰️ GEOSAT V12 ULTIMATE\nID:{m.from_user.id}\nMODELO:{MODELO} router smart\nOW:{'✅' if OPENWEATHER_KEY else '❌'} NASA:{'✅' if NASA_API_KEY else '❌'} HF:{'✅' if HF_TOKEN else '❌'} SERP:{'✅' if SERPER_API_KEY else '❌'} TAV:{'✅' if TAVILY_API_KEY else '❌'} PLANT:{'✅' if PLANTNET_API_KEY else '❌'}\nDB:{'PG' if USE_DB else 'Local'}\n{get_clima_texto()} {alerta}\n{get_ndvi()}\nSuelo: {suelo['texto']}\n{get_luna()}")

@bot.message_handler(commands=['start','ayuda'])
def cmd_start(m):
    if not ok(m):
        return
    bot.reply_to(m,f"🛰️ *V12 ULTIMATE FIXED*\n{get_clima_texto()}\n{get_ndvi()}\n{get_suelo_real()['texto']}\n{get_luna()}\n\nV12: router 8b/70b/120b + alerta lluvia + dosis Bomba20L + pH SoilGrids\n/panel /clima /suelo /luna /mercado /dosis /memoria", parse_mode="Markdown")

@bot.message_handler(commands=['clima','panel','suelo','luna','mercado','dosis','memoria','grafica','satelite'])
def cmd_all(m):
    if not ok(m):
        return
    txt=m.text.lower()
    if 'panel' in txt:
        c=get_clima_real()
        alerta="🚨 NO FUMIGAR HOY" if c and c['prob']>75 else "✅ Fumiga 6am"
        bot.reply_to(m,f"📊 *PANEL V12*\n{get_clima_texto()}\n{alerta}\n{get_ndvi()}\nSuelo {get_suelo_real()['texto']}\n{get_luna()}\n{get_precio_real('maracuya')}", parse_mode="Markdown")
    elif 'suelo' in txt:
        s=get_suelo_real()
        rec="Encala 500kg/ha" if s['ph']<5.8 else "Aplica organico 2kg/planta"
        bot.reply_to(m,f"🌱 {s['texto']}\n{rec}")
    elif 'luna' in txt:
        bot.reply_to(m,get_luna())
    elif 'clima' in txt or 'grafica' in txt or 'satelite' in txt:
        c=get_clima_real()
        alerta="🚨 NO FUMIGUES" if c and c['prob']>75 else ""
        bot.reply_to(m,f"🌤️ {get_clima_texto()}\n{alerta}\n{get_ndvi()}")
    elif 'mercado' in txt:
        cultivo=m.text.replace('/mercado','').strip() or "maracuya"
        bot.send_chat_action(m.chat.id,'typing')
        precio=get_precio_real(cultivo)
        resp=ask_groq(f"Analiza venta {cultivo} hoy. Precio {precio}. Tabla vender vs esperar.", "Economista")
        bot.reply_to(m,f"💰 {precio}\n\n{resp}"[:3800])
    elif 'dosis' in txt:
        prod=m.text.replace('/dosis','').strip() or "cipermetrina"
        bot.send_chat_action(m.chat.id,'typing')
        bot.reply_to(m, ask_groq(f"Dosis triple exacta {prod} maracuya: Dosis/Ha, Dosis/Bomba20L, Costo COP/Ha, Carencia, pH agua {get_suelo_real()['ph']}. Tabla.")[:3800])
    elif 'memoria' in txt:
        buscar=m.text.replace('/memoria','').strip()
        bot.reply_to(m,f"🧠 SMART:\n{db_get_smart(35,buscar)[:3800]}")

@bot.message_handler(commands=['recordar','guardar'])
def cmd_rec(m):
    if not ok(m):
        return
    txt=m.text.replace('/recordar','').replace('/guardar','').strip()
    db_save(txt,"nota")
    bot.reply_to(m,f"✅ Guardado V12: {txt[:200]}")

@bot.message_handler(content_types=['photo'])
def handle_foto(m):
    if not ok(m):
        return
    info=bot.get_file(m.photo[-1].file_id)
    data=bot.download_file(info.file_path)
    path=f"fotos/{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    open(path,"wb").write(data)
    bot.reply_to(m,"📸 V12 analizando doble IA...")
    bot.send_chat_action(m.chat.id,'typing')
    bot.reply_to(m,f"{ask_gemini(path, m.caption or '')}"[:4000])

@bot.message_handler(func=lambda m: True)
def default(m):
    if not ok(m):
        return
    bot.send_chat_action(m.chat.id,'typing')
    bot.reply_to(m, ask_groq(m.text)[:4000])

@app.route('/')
def index():
    return f"V12 OK {MODELO} {get_clima_texto()}",200

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        bot.process_new_updates([Update.de_json(request.get_data().decode('utf-8'))])
    except:
        pass
    return "ok",200

def setup_webhook():
    try:
        bot.remove_webhook()
        if WEBHOOK_URL:
            bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
    except Exception as e:
        print(f"Webhook error: {e}")

setup_webhook()

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
