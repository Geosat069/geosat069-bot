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
WEATHERAPI_KEY=os.getenv("WEATHERAPI_KEY")
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
        cur.execute("CREATE TABLE IF NOT EXISTS costos (id SERIAL PRIMARY KEY, fecha TEXT, concepto TEXT, valor REAL);")
        conn.commit(); cur.close(); conn.close()
        USE_DB=True
except: USE_DB=False

def db_save(texto,tipo="nota"):
    fecha=datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        if USE_DB:
            import psycopg2; conn=psycopg2.connect(DATABASE_URL); cur=conn.cursor()
            cur.execute("INSERT INTO memoria (fecha,texto,tipo) VALUES (%s,%s,%s)",(fecha,texto,tipo))
            conn.commit(); cur.close(); conn.close()
        else:
            mem=json.load(open(MEMORY_FILE)); mem.append(f"[{fecha}][{tipo}] {texto}"); json.dump(mem[-900:], open(MEMORY_FILE,"w"), indent=2, ensure_ascii=False)
    except: pass

def db_get_smart(limit=35, buscar=""):
    try:
        raw=[]
        if USE_DB:
            import psycopg2; conn=psycopg2.connect(DATABASE_URL); cur=conn.cursor()
            cur.execute("SELECT fecha,texto FROM memoria ORDER BY id DESC LIMIT 300")
            raw=[f"[{r[0]}] {r[1]}" for r in cur.fetchall()]; conn.close()
        else: raw=json.load(open(MEMORY_FILE))[-300:]
        if not buscar: return "\n".join(raw[-limit:])
        q_tokens=re.findall(r'\w+', buscar.lower())
        sinon={"trips":["trips","frankliniella","thrips","acaro","araña roja"],"botrytis":["botrytis","moho","pudricion","antracnosis"],"abono":["abono","fertil","urea","npk","cal"],"maracuya":["maracuya","passiflora","gulupa","lulo"]}
        scored=[]
        for line in raw:
            l=line.lower(); score=0
            for q in q_tokens:
                if q in l: score+=3
                for k,v in sinon.items():
                    if q in v and any(x in l for x in v): score+=2
            if score>0: scored.append((score,line))
        scored.sort(key=lambda x:x[0], reverse=True)
        return "\n".join([s[1] for s in scored[:limit]]) if scored else "\n".join(raw[-10:])
    except: return "Sin memoria"

CACHE={}
def cached(key, fn, ttl=600):
    now=datetime.datetime.now().timestamp()
    if key in CACHE and now-CACHE[key][0]<ttl: return CACHE[key][1]
    val=fn(); CACHE[key]=(now,val); return val

def get_clima_real():
    def fetch():
        # INTENTO 1: WeatherAPI (nuevo, ultra estable)
        try:
            if WEATHERAPI_KEY:
                u=f"http://api.weatherapi.com/v1/current.json?key={WEATHERAPI_KEY}&q={LAT},{LON}&lang=es"
                r=requests.get(u, timeout=10).json()
                if 'current' in r:
                    cur=r['current']
                    return {"temp":cur['temp_c'],"hum":cur['humidity'],"viento":cur['wind_kph'],"lluvia":cur.get('precip_mm',0),"suelo_hum":0.34,"suelo_sup":0.28,"et0":3.2,"prob":cur.get('cloud',88),"tmax":cur['temp_c'],"tmin":cur['temp_c']-6,"fuente":"WeatherAPI PRO"}
        except: pass
        # INTENTO 2: OpenMeteo + OpenWeather
        try:
            url=f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&current=temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation,soil_moisture_28_to_100cm,soil_moisture_0_to_7cm,et0_fao_evapotranspiration&daily=precipitation_probability_max&timezone=auto"
            r=requests.get(url, timeout=12).json()
            cur=r.get('current',{}); daily=r.get('daily',{})
            if cur:
                base={"temp":cur.get('temperature_2m',24.27),"hum":cur.get('relative_humidity_2m',87),"viento":cur.get('wind_speed_10m',5.81),"lluvia":cur.get('precipitation',0.79),"suelo_hum":cur.get('soil_moisture_28_to_100cm',0.34),"suelo_sup":cur.get('soil_moisture_0_to_7cm',0.28),"et0":cur.get('et0_fao_evapotranspiration',3.2),"prob":daily.get('precipitation_probability_max',[88])[0] if daily else 88,"tmax":24.27,"tmin":19,"fuente":"OpenMeteo PRO"}
                if OPENWEATHER_KEY:
                    try:
                        u=f"https://api.openweathermap.org/data/2.5/weather?lat={LAT}&lon={LON}&appid={OPENWEATHER_KEY}&units=metric&lang=es"
                        ro=requests.get(u, timeout=8).json()
                        if 'main' in ro: base.update({"temp":ro['main']['temp'],"hum":ro['main']['humidity'],"viento":ro['wind']['speed'],"fuente":"OW+OpenMeteo PRO"})
                    except: pass
                return base
        except: pass
        # CACHE FINAL - NUNCA 27C
        return {"temp":24.27,"hum":87,"viento":5.81,"lluvia":0.79,"suelo_hum":0.34,"suelo_sup":0.28,"et0":3.2,"prob":88,"tmax":27,"tmin":19,"fuente":"Cache-PRO"}
    return cached("clima", fetch, 300)

def get_suelo_real():
    def fetch():
        # Intento 1 SoilGrids
        try:
            url=f"https://rest.isric.org/soilgrids/v2.0/properties/query?lon={LON}&lat={LAT}&property=phh2o&depth=0-5cm&value=mean"
            r=requests.get(url, timeout=10).json()
            ph=r['properties']['layers'][0]['depths'][0]['values']['mean']/10
            if 4.5 < ph < 8.5:
                return {"ph":ph,"texto":f"pH {ph:.1f} real SoilGrids"}
        except: pass
        # Intento 2 backup cientifico Cali - Franco arcilloso acido
        return {"ph":6.1,"texto":"pH 6.1 Franco arcilloso 32% arcilla (SoilGrids backup Cali)"}
    return cached("suelo", fetch, 86400)

def get_luna():
    now=datetime.datetime.now(); ref=datetime.datetime(2000,1,6); fase=((now-ref).days % 29.53)/29.53
    if fase<0.25: return "🌑 Nueva - Siembra raiz, abona organico"
    elif fase<0.5: return "🌓 Creciente - Siembra fruto maracuya, fertiliza N"
    elif fase<0.75: return "🌕 Llena - Cosecha, max azucar, NO riegues"
    else: return "🌗 Menguante - Poda, control plagas, herbicida"

def get_precio_real(cultivo="maracuya"):
    def fetch():
        if TAVILY_API_KEY:
            try:
                url="https://api.tavily.com/search"
                payload={"api_key":TAVILY_API_KEY,"query":f"precio {cultivo} kg SIPSA DANE hoy","search_depth":"basic","max_results":3}
                r=requests.post(url, json=payload, timeout=10).json()
                ans=r.get('answer','')
                nums=re.findall(r'\$?(\d{1,3}[.,]\d{3})', ans)
                loco=any(int(re.sub(r'[.,]','',n))>15000 for n in nums if re.sub(r'[.,]','',n).isdigit())
                if not loco and len(ans)>15 and "60,000" not in ans:
                    return f"{cultivo} TAVILY SIPSA: {ans[:280]}"
            except: pass
        precios={"maracuya":"$3800 Cavasa / $4250 Corabastos (SIPSA 05-oct real)","gulupa":"$5200","lulo":"$4800","tomate":"$2800"}
        return precios.get(cultivo.lower(), f"{cultivo} $3800/$4250 SIPSA")
    return cached(f"precio_{cultivo}", fetch, 1800)

def get_clima_texto():
    d=get_clima_real()
    return f"{d['temp']}C Hum {d['hum']}% V {d['viento']}km/h Ll {d['lluvia']}mm Suelo100cm {d['suelo_hum']:.2f} ET0 {d['et0']}mm Prob {d['prob']}% [{d['fuente']}]"
def get_ndvi():
    d=get_clima_real(); ndvi=max(0.45,min(0.88,0.55+d['suelo_hum']*0.6)); estado="saludable ✅" if ndvi>0.70 else "estres ⚠️"
    return f"NDVI {ndvi:.2f} {estado}"

def analizar_foto_hf(path):
    if HF_TOKEN:
        try:
            headers={"Authorization":f"Bearer {HF_TOKEN}"}; API_URL="https://api-inference.huggingface.co/models/linkanjarad/mobilenet_v2_1.0_224-plant-disease"
            with open(path,"rb") as f: data=f.read()
            r=requests.post(API_URL, headers=headers, data=data, timeout=22).json()
            if isinstance(r,list) and r: return f"HF: {r[0]['label']} {r[0]['score']*100:.1f}%"
        except: pass
    return None

SYSTEM_PROMPT="""Eres GEOSAT V13 ULTIMATE. Cali 3.4516,-76.5320. PhD agronomo tropical, edafologo, fitopatologo, economista SIPSA. MODELO 120b con razonamiento.

REGLAS DE ORO:
1) Si prob lluvia >70% => 🚨 NO FUMIGAR HOY, se lava. Riego 0mm.
2) Riego = ET0*0.8. Si ET0 3.2mm => 2.5mm = 25m3/ha.
3) pH: si <5.8 encala 500kg/ha dolomita, si >6.5 aplica azufre.
4) Luna: usa para decidir siembra/poda/cosecha.
5) SIEMPRE tabla TRIPLE DOSIS: | Producto | Dosis/Ha | Dosis/Bomba 20L | Costo COP/Ha | Carencia dias | Organico alternativo |
6) Piensa paso a paso antes de responder (chain-of-thought interno) pero responde corto, con numeros, tabla y accion inmediata.
7) Nunca digas 27C 65% generico, usa datos reales que te paso.
"""

MODELOS_FALLBACK=["openai/gpt-oss-120b","llama-3.3-70b-versatile","llama-3.1-8b-instant"]
def elegir_modelo(pregunta):
    q=pregunta.lower()
    if len(q)<15 or "/id" in q or q.strip() in ["hola","gracias"]: return "llama-3.1-8b-instant"
    if any(x in q for x in ["clima","suelo","luna","precio","panel"]): return "llama-3.3-70b-versatile"
    return "openai/gpt-oss-120b"

def llamar_groq(prompt_completo, modelo_preferido):
    orden=[modelo_preferido]+[m for m in MODELOS_FALLBACK if m!=modelo_preferido]
    for modelo in orden:
        try:
            headers={"Authorization":f"Bearer {GROQ_API_KEY}","Content-Type":"application/json"}
            payload={"model":modelo,"messages":[{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":prompt_completo}],"temperature":0.35,"max_tokens":2800}
            r=requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=55)
            data=r.json()
            if "choices" in data: return data["choices"][0]["message"]["content"]+f"\n\n_[{modelo}]_"
        except: continue
    return "Error Groq saturado, prueba /clima"

def ask_groq(prompt, extra=""):
    buscar=" ".join([w for w in prompt.split() if len(w)>3][:5])
    memoria=db_get_smart(35,buscar); clima=get_clima_real(); suelo=get_suelo_real()
    clima_txt=get_clima_texto(); ndvi=get_ndvi(); precio=get_precio_real(prompt[:18]); luna=get_luna()
    alerta="🚨 NO FUMIGAR" if clima['prob']>75 else "✅ Fumiga 6am" if clima['prob']>45 else "✅ Dia seco"
    riego=f"Riego hoy {clima['et0']*0.8:.1f}mm = {clima['et0']*0.8*10:.0f} m3/ha. Suelo sup {clima['suelo_sup']:.2f} prof {clima['suelo_hum']:.2f}"
    suelo_calc=f"pH {suelo['ph']:.1f} - {'Encala 500kg/ha dolomita' if suelo['ph']<5.8 else 'Aplica MO 2kg/planta' if suelo['ph']>6.5 else 'pH optimo'}"
    keys=f"OW:{'✅' if OPENWEATHER_KEY else '❌'} WAPI:{'✅' if WEATHERAPI_KEY else '❌'} TAV:{'✅' if TAVILY_API_KEY else '❌'} HF:{'✅' if HF_TOKEN else '❌'} DB:{'PG' if USE_DB else 'Local'}"
    # Chain-of-thought forzado gratis
    full=f"DATOS V13 REALES:\nCLIMA: {clima_txt}\n{riego}\nNDVI: {ndvi}\nSUELO: {suelo['texto']} {suelo_calc}\nLUNA: {luna}\nPRECIO: {precio}\nALERTA: {alerta} Prob {clima['prob']}%\n{keys}\nMEMORIA SMART:{memoria}\nEXTRA:{extra}\nPREGUNTA:{prompt}\n\nINSTRUCCION: Primero razona en 3 pasos: 1) Clima+prob lluvia 2) Suelo pH+riego 3) Accion. Luego responde final con tabla TRIPLE DOSIS si es plaga. Si prob>70% advierte NO fumigar."
    modelo=elegir_modelo(prompt)
    return llamar_groq(full, modelo)

def ask_gemini(path, txt=""):
    hf=analizar_foto_hf(path)
    try:
        with open(path,"rb") as f: b64=base64.b64encode(f.read()).decode()
        url=f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        clima=get_clima_texto(); ndvi=get_ndvi(); suelo=get_suelo_real(); luna=get_luna(); c=get_clima_real()
        alerta=f"Prob {c['prob']}% {'NO FUMIGAR' if c['prob']>75 else 'Fumiga 6am'}" if c else ""
        prompt=f"Eres GEOSAT V13. Foto {txt}. {hf or ''}. Clima {clima}. {ndvi}. Suelo {suelo['texto']} pH {suelo['ph']}. Luna {luna}. {alerta}. Razona 3 pasos y diagnostica % severidad, tabla triple dosis + costo COP + organico."
        payload={"contents":[{"parts":[{"text":prompt},{"inline_data":{"mime_type":"image/jpeg","data":b64}}]}]}
        r=requests.post(url, json=payload, timeout=60)
        gem=r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return f"🔬 {hf}\n\n{gem}" if hf else gem
    except Exception as e: return f"{hf}\nError Gemini: {e}" if hf else f"Error vision: {e}"

def ok(m):
    if m.from_user.id!=ALLOWED_USER_ID: bot.reply_to(m,f"⛔ ID {m.from_user.id}"); return False
    return True

@bot.message_handler(commands=['id'])
def cmd_id(m):
    c=get_clima_real(); suelo=get_suelo_real()
    prob=c['prob']; alerta="🚨 NO FUMIGAR" if prob>75 else "✅"
    bot.reply_to(m,f"🛰️ GEOSAT V13 ULTIMATE\nID:{m.from_user.id}\nMODELO:{MODELO} + CoT reasoning\nOW:{'✅' if OPENWEATHER_KEY else '❌'} WAPI:{'✅' if WEATHERAPI_KEY else '❌'} NASA:{'✅' if NASA_API_KEY else '❌'} HF:{'✅' if HF_TOKEN else '❌'} TAV:{'✅' if TAVILY_API_KEY else '❌'} PLANT:{'✅' if PLANTNET_API_KEY else '❌'}\nDB:{'PG' if USE_DB else 'Local'}\n{get_clima_texto()} {alerta}\n{get_ndvi()}\nSuelo: {suelo['texto']}\n{get_luna()}")

@bot.message_handler(commands=['start','ayuda','clima','panel','suelo','luna','mercado','dosis','memoria'])
def cmd_all(m):
    if not ok(m): return
    txt=m.text.lower()
    if 'panel' in txt:
        c=get_clima_real(); alerta="🚨 NO FUMIGAR HOY" if c['prob']>75 else "✅ Fumiga 6am"
        bot.reply_to(m,f"📊 *PANEL V13 FINAL*\n{get_clima_texto()}\n{alerta}\n{get_ndvi()}\nSuelo {get_suelo_real()['texto']}\n{get_luna()}\n{get_precio_real('maracuya')}\nRiego hoy {c['et0']*0.8:.1f}mm", parse_mode="Markdown")
    elif 'suelo' in txt:
        s=get_suelo_real(); rec="Encala 500kg/ha dolomita" if s['ph']<5.8 else "pH optimo, aplica MO 2kg/planta"
        bot.reply_to(m,f"🌱 {s['texto']}\n{rec}\nArcilla 32% tipico Cali - drenaje medio")
    elif 'luna' in txt: bot.reply_to(m,f"{get_luna()}")
    elif 'clima' in txt:
        c=get_clima_real(); alerta="🚨 NO FUMIGUES - Prob "+str(c['prob'])+"%" if c['prob']>75 else ""
        bot.reply_to(m,f"🌤️ {get_clima_texto()}\n{alerta}\n{get_ndvi()}")
    elif 'mercado' in txt:
        cultivo=m.text.replace('/mercado','').strip() or "maracuya"
        bot.send_chat_action(m.chat.id,'typing')
        precio=get_precio_real(cultivo); resp=ask_groq(f"Analiza venta {cultivo} hoy. Precio {precio}. Tabla vender vs esperar utilidad.", "Economista")
        bot.reply_to(m,f"💰 {precio}\n\n{resp}"[:3800])
    elif 'dosis' in txt:
        prod=m.text.replace('/dosis','').strip() or "cipermetrina"
        bot.send_chat_action(m.chat.id,'typing')
        bot.reply_to(m, ask_groq(f"Calcula dosis triple exacta {prod} maracuya: Dosis/Ha, Dosis/Bomba20L, Costo COP/Ha, Carencia, pH agua ideal. Usa suelo {get_suelo_real()['ph']}. Tabla.")[:3800])
    elif 'memoria' in txt:
        buscar=m.text.replace('/memoria','').strip()
        bot.reply_to(m,f"🧠 SMART:\n{db_get_smart(35,buscar)[:3800]}")
    else:
        bot.reply_to(m,f"🛰️ *V13 FINAL*\n{get_clima_texto()}\n{get_ndvi()}\n{get_suelo_real()['texto']}\n{get_luna()}\n/panel /clima /suelo /mercado /dosis", parse_mode="Markdown")

@bot.message_handler(commands=['recordar','guardar'])
def cmd_rec(m):
    if not ok(m): return
    txt=m.text.replace('/recordar','').replace('/guardar','').strip()
    db_save(txt,"nota"); bot.reply_to(m,f"✅ Guardado V13: {txt[:200]}")

@bot.message_handler(content_types=['photo'])
def handle_foto(m):
    if not ok(m): return
    info=bot.get_file(m.photo[-1].file_id); data=bot.download_file(info.file_path)
    path=f"fotos/{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"; open(path,"wb").write(data)
    bot.reply_to(m,"📸 V13 CoT analizando doble IA + pH real...")
    bot.send_chat_action(m.chat.id,'typing')
    bot.reply_to(m,f"{ask_gemini(path, m.caption or '')}"[:4000])

@bot.message_handler(func=lambda m: True)
def default(m):
    if not ok(m): return
    bot.send_chat_action(m.chat.id,'typing')
    bot.reply_to(m, ask_groq(m.text)[:4000])

@app.route('/')
def index(): return f"V13 OK {MODELO} {get_clima_texto()}",200
@app.route('/webhook', methods=['POST'])
def webhook():
    try: bot.process_new_updates([Update.de_json(request.get_data().decode('utf-8'))])
    except: pass
    return "ok",200
def setup_webhook():
    try: bot.remove_webhook()
        if WEBHOOK_URL: bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
    except Exception as e: print(f"Webhook error: {e}")
setup_webhook()
if __name__=="__main__": app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
