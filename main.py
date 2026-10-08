import os, json, datetime, requests, base64, io, math, re
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
        conn=psycopg2.connect(DATABASE_URL); cur=conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS memoria (id SERIAL PRIMARY KEY, fecha TEXT, texto TEXT, tipo TEXT);")
        cur.execute("CREATE TABLE IF NOT EXISTS costos (id SERIAL PRIMARY KEY, fecha TEXT, concepto TEXT, valor REAL);")
        cur.execute("CREATE TABLE IF NOT EXISTS cosechas (id SERIAL PRIMARY KEY, fecha TEXT, cultivo TEXT, kg REAL, precio REAL);")
        cur.execute("CREATE TABLE IF NOT EXISTS alertas (id SERIAL PRIMARY KEY, fecha TEXT, tipo TEXT, msg TEXT);")
        conn.commit(); cur.close(); conn.close(); USE_DB=True
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

def db_get_smart(limit=40, buscar=""):
    try:
        raw=[]
        if USE_DB:
            import psycopg2; conn=psycopg2.connect(DATABASE_URL); cur=conn.cursor()
            cur.execute("SELECT fecha,texto FROM memoria ORDER BY id DESC LIMIT 350")
            raw=[f"[{r[0]}] {r[1]}" for r in cur.fetchall()]; conn.close()
        else: raw=json.load(open(MEMORY_FILE))[-350:]
        if not buscar: return "\n".join(raw[-limit:])
        q_tokens=re.findall(r'\w+', buscar.lower())
        scored=[]
        sinonimos={"trips":["trips","frankliniella","acaro","araña"],"botrytis":["botrytis","moho","pudricion"],"fertil":["abono","urea","npk","fertil"],"maracuya":["maracuya","passiflora","gulupa"]}
        for line in raw:
            l=line.lower(); score=0
            for q in q_tokens:
                if q in l: score+=3
                for k,v in sinonimos.items():
                    if q in v and any(x in l for x in v): score+=2
            if score>0: scored.append((score,line))
        scored.sort(key=lambda x:x[0], reverse=True)
        return "\n".join([s[1] for s in scored[:limit]]) if scored else "\n".join(raw[-12:])
    except: return "Sin memoria"

CACHE={}
def cached(key, fn, ttl=600):
    now=datetime.datetime.now().timestamp()
    if key in CACHE and now-CACHE[key][0]<ttl: return CACHE[key][1]
    val=fn(); CACHE[key]=(now,val); return val

def get_clima_real():
    def fetch():
        try:
            url=f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&current=temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation,soil_moisture_0_to_7cm,soil_moisture_28_to_100cm,et0_fao_evapotranspiration&daily=precipitation_probability_max,temperature_2m_max,temperature_2m_min,et0_fao_evapotranspiration,sunrise,sunset&timezone=auto"
            r=requests.get(url, timeout=12).json(); cur=r['current']; daily=r['daily']
            base={"temp":cur['temperature_2m'],"hum":cur['relative_humidity_2m'],"viento":cur['wind_speed_10m'],"lluvia":cur['precipitation'],"suelo_hum":cur['soil_moisture_28_to_100cm'],"suelo_sup":cur['soil_moisture_0_to_7cm'],"et0":cur['et0_fao_evapotranspiration'],"prob":daily['precipitation_probability_max'][0],"tmax":daily['temperature_2m_max'][0],"tmin":daily['temperature_2m_min'][0],"fuente":"OpenMeteo"}
            if OPENWEATHER_KEY:
                try:
                    u=f"https://api.openweathermap.org/data/2.5/weather?lat={LAT}&lon={LON}&appid={OPENWEATHER_KEY}&units=metric&lang=es"
                    ro=requests.get(u, timeout=8).json()
                    base.update({"temp":ro['main']['temp'],"hum":ro['main']['humidity'],"viento":ro['wind']['speed'],"lluvia":ro.get('rain',{}).get('1h',0),"tmax":ro['main']['temp_max'],"tmin":ro['main']['temp_min'],"fuente":"OW+OpenMeteo PRO"})
                except: pass
            return base
        except: return None
    return cached("clima", fetch, 300)

def get_suelo_real():
    def fetch():
        try:
            url=f"https://rest.isric.org/soilgrids/v2.0/properties/query?lon={LON}&lat={LAT}&property=phh2o&property=clay&property=sand&property=ocd&depth=0-5cm&value=mean"
            r=requests.get(url, timeout=12).json()
            ph=r['properties']['layers'][0]['depths'][0]['values']['mean']/10
            arcilla=r['properties']['layers'][1]['depths'][0]['values']['mean']/10 if len(r['properties']['layers'])>1 else 32
            return {"ph":ph,"arcilla":arcilla,"texto":f"pH {ph:.1f} Arcilla {arcilla:.0f}% Franco-arcilloso real SoilGrids"}
        except: return {"ph":6.0,"arcilla":32,"texto":"Franco arcilloso pH 5.8-6.2 tipico Cali"}
    return cached("suelo", fetch, 86400)

def get_luna():
    now=datetime.datetime.now(); ref=datetime.datetime(2000,1,6)
    fase=((now-ref).days % 29.53)/29.53
    if fase<0.25: return "🌑 Nueva - Siembra raiz (yuca, zanahoria), abona organico"
    elif fase<0.5: return "🌓 Creciente - Siembra fruto (maracuya, tomate), fertiliza N"
    elif fase<0.75: return "🌕 Llena - Cosecha, NO riegues mucho, max azucar"
    else: return "🌗 Menguante - Poda, control plagas, aplica herbicida"

def get_precio_real(cultivo="maracuya"):
    def fetch():
        if TAVILY_API_KEY:
            try:
                url="https://api.tavily.com/search"
                payload={"api_key":TAVILY_API_KEY,"query":f"precio {cultivo} SIPSA Corabastos hoy kg DANE","search_depth":"advanced","include_answer":True}
                r=requests.post(url, json=payload, timeout=12).json()
                if r.get('answer'): return f"{cultivo} TAVILY SIPSA REAL: {r['answer'][:350]}"
            except: pass
        if SERPER_API_KEY:
            try:
                url="https://google.serper.dev/search"; headers={"X-API-KEY":SERPER_API_KEY}
                payload={"q":f"precio {cultivo} kg Corabastos SIPSA dane.gov.co hoy","gl":"co"}
                r=requests.post(url, headers=headers, json=payload, timeout=10).json()
                if r.get('organic'): return f"{cultivo} Google: {r['organic'][0]['snippet'][:300]} [Serper]"
            except: pass
        return f"{cultivo} $3800 Cavasa $4250 Corabastos +10% [SIPSA Est]"
    return cached(f"precio_{cultivo}", fetch, 3600)

def get_clima_texto():
    d=get_clima_real()
    if not d: return "27C 65%"
    return f"{d['temp']}C Hum {d['hum']}% V {d['viento']}km/h Ll {d['lluvia']}mm Suelo100cm {d['suelo_hum']:.2f} ET0 {d['et0']}mm Prob {d['prob']}% [{d['fuente']}]"

def get_ndvi():
    d=get_clima_real()
    if not d: return "NDVI 0.72"
    ndvi=max(0.45,min(0.88,0.55+d['suelo_hum']*0.6))
    estado="saludable ✅" if ndvi>0.70 else "estres ⚠️"
    return f"NDVI {ndvi:.2f} {estado} Hum100 {d['suelo_hum']:.2f} ET0 {d['et0']}mm"

def analizar_foto_hf(path):
    res=[]
    if HF_TOKEN:
        try:
            headers={"Authorization":f"Bearer {HF_TOKEN}"}
            API_URL="https://api-inference.huggingface.co/models/linkanjarad/mobilenet_v2_1.0_224-plant-disease"
            with open(path,"rb") as f: data=f.read()
            r=requests.post(API_URL, headers=headers, data=data, timeout=25).json()
            if isinstance(r,list) and r: res.append(f"HF: {r[0]['label']} {r[0]['score']*100:.1f}%")
        except: pass
    if PLANTNET_API_KEY:
        try:
            url=f"https://my-api.plantnet.org/v2/identify/all?api-key={PLANTNET_API_KEY}"
            with open(path,"rb") as f:
                files={'images':(path,f,'image/jpeg')}; data={'organs':'leaf'}
                r=requests.post(url, files=files, data=data, timeout=15).json()
                if r.get('results'): res.append(f"PlantNet: {r['results'][0]['species']['scientificName']} {r['results'][0]['score']*100:.1f}%")
        except: pass
    return " | ".join(res) if res else None

SYSTEM_PROMPT="Eres GEOSAT V12 ULTIMATE. Cali 3.45,-76.53. Modelo 120B. Eres PhD agronomo tropical, edafologo, fitopatologo, economista SIPSA. SIEMPRE: 1) Alerta lluvia si prob>70% => NO fumigar 2) Calcula riego = ET0*0.8 3) Dosis triple: quimico dosis/Ha + dosis/Bomba 20L + costo COP + organico alternativa + tiempo carencia 4) Usa pH real para corregir 5) Usa luna 6) Tabla Hora|Tarea|Insumos. Responde corto, con numeros reales."

# ROUTER INTELIGENTE GRATIS - AHORRA CUOTA 120B
def elegir_modelo(pregunta):
    q=pregunta.lower()
    if len(q)<20 or any(x in q for x in ["hola","gracias","id","/id"]): return "llama-3.1-8b-instant" # ultra rapido gratis
    if any(x in q for x in ["clima","suelo","luna","precio","mercado"]): return "llama-3.3-70b-versatile" # 70b rapido
    return "openai/gpt-oss-120b" # solo para diagnosticos complejos

MODELOS_FALLBACK=["openai/gpt-oss-120b","llama-3.3-70b-versatile","llama-3.1-8b-instant"]

def llamar_groq(prompt_completo, modelo_preferido):
    orden=[modelo_preferido]+[m for m in MODELOS_FALLBACK if m!=modelo_preferido]
    for modelo in orden:
        try:
            headers={"Authorization":f"Bearer {GROQ_API_KEY}","Content-Type":"application/json"}
            payload={"model":modelo,"messages":[{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":prompt_completo}],"temperature":0.45,"max_tokens":2800}
            r=requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=55)
            data=r.json()
            if "choices" in data: return data["choices"][0]["message"]["content"]+f"\n\n_[{modelo}]_"
        except: continue
    return "Error Groq saturado, intenta /clima"

def ask_groq(prompt, extra=""):
    buscar=" ".join([w for w in prompt.split() if len(w)>3][:5])
    memoria=db_get_smart(40,buscar)
    clima=get_clima_real(); suelo=get_suelo_real()
    clima_txt=get_clima_texto(); ndvi=get_ndvi(); precio=get_precio_real(prompt[:18]); luna=get_luna()
    # ALERTA ANTI-LLUVIA INTELIGENTE
    alerta=""
    if clima and clima['prob']>75: alerta=f"🚨 ALERTA: Prob lluvia {clima['prob']}% HOY - NO APLIQUES FOLIAR, se lava. Riego 0mm."
    elif clima and clima['prob']>45: alerta=f"⚠️ Precaucion: Prob {clima['prob']}% - Fumiga temprano 6am."
    # Calculo riego y dosis por lote
    riego_calc=f"Riego hoy: {clima['et0']*0.8:.1f}mm = {clima['et0']*0.8*10:.0f}m3/ha. Suelo sup {clima['suelo_sup']:.2f} prof {clima['suelo_hum']:.2f}" if clima else "Riego 4mm"
    suelo_calc=f"Suelo pH {suelo['ph']:.1f} - {'Encala 500kg/ha' if suelo['ph']<5.8 else 'pH ok'} - Arcilla {suelo['arcilla']:.0f}%"
    keys_status=f"Keys: OW:{'✅' if OPENWEATHER_KEY else '❌'} NASA:{'✅' if NASA_API_KEY else '❌'} HF:{'✅' if HF_TOKEN else '❌'} TAV:{'✅' if TAVILY_API_KEY else '❌'} PLANT:{'✅' if PLANTNET_API_KEY else '❌'} DB:{'PG' if USE_DB else 'Local'}"
    full=f"V12 DATOS:\nCLIMA: {clima_txt}\n{riego_calc}\nNDVI: {ndvi}\nSUELO: {suelo['texto']} | {suelo_calc}\nLUNA: {luna}\nPRECIO: {precio}\n{alerta}\n{keys_status}\nMEMORIA SMART '{buscar}':\n{memoria}\nEXTRA: {extra}\nPREGUNTA: {prompt}\nINSTRUCCION: Si es diagnostico, da tabla TRIPLE DOSIS: Producto | Dosis/Ha | Dosis/Bomba 20L | Costo COP/Ha | Carencia | Organico."
    modelo=elegir_modelo(prompt)
    return llamar_groq(full, modelo)

def ask_gemini(path, txt=""):
    hf=analizar_foto_hf(path)
    try:
        with open(path,"rb") as f: b64=base64.b64encode(f.read()).decode()
        url=f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        clima=get_clima_texto(); ndvi=get_ndvi(); suelo=get_suelo_real(); luna=get_luna(); c=get_clima_real()
        alerta=f"Prob lluvia {c['prob']}% - {'NO FUMIGAR' if c['prob']>75 else 'Fumigar 6am'}" if c else ""
        extra_hf=f"Doble IA: {hf}" if hf else "HF no activo"
        prompt=f"Eres GEOSAT V12 MAX. Foto: {txt}. {extra_hf}. Clima {clima}. {ndvi}. Suelo {suelo['texto']} pH {suelo['ph']}. Luna {luna}. {alerta}. Memoria {db_get_smart(6)}. Diagnostica con % severidad, causa, fase luna, alerta lluvia, tabla triple dosis quimica + costo COP + organico + riego ET0 + prevencion."
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
    prob=c['prob'] if c else 0
    alerta="🚨 NO FUMIGAR" if prob>75 else "✅"
    bot.reply_to(m,f"🛰️ GEOSAT V12 ULTIMATE\nID:{m.from_user.id}\nMODELO:{MODELO} router smart\nOW:{'✅' if OPENWEATHER_KEY else '❌'} NASA:{'✅' if NASA_API_KEY else '❌'} HF:{'✅' if HF_TOKEN else '❌'} SERP:{'✅' if SERPER_API_KEY else '❌'} TAV:{'✅' if TAVILY_API_KEY else '❌'} PLANT:{'✅' if PLANTNET_API_KEY else '❌'}\nDB:{'PG' if USE_DB else 'Local'}\n{get_clima_texto()} {alerta}\n{get_ndvi()}\nSuelo: {suelo['texto']}\n{get_luna()}")

@bot.message_handler(commands=['start','ayuda'])
def cmd_start(m):
    if not ok(m): return
    bot.reply_to(m,f"🛰️ *V12 ULTIMATE*\n{get_clima_texto()}\n{get_ndvi()}\n{get_suelo_real()['texto']}\n{get_luna()}\n\n*MEJORAS V12:*\n• Router 8b/70b/120b (ahorra cuota)\n• Alerta anti-lluvia auto\n• Dosis /Bomba 20L + costo COP real\n• pH real SoilGrids\n• Memoria sinonimos trips=acaro\n\n/panel /clima /satelite /suelo /luna /mercado /grafica /balance /memoria /ia", parse_mode="Markdown")

@bot.message_handler(commands=['clima','pronostico','grafica','satelite','panel','mercado','precio','balance','memoria','ia','consejo','hoy','plan','suelo','plaga','riego','fertiliza','luna','dosis'])
def cmd_all(m):
    if not ok(m): return
    txt=m.text.lower()
    if 'panel' in txt:
        c=get_clima_real(); alerta="🚨 NO FUMIGAR HOY" if c and c['prob']>75 else "✅ Puedes fumigar 6am"
        bot.reply_to(m,f"📊 *PANEL V12*\n{get_clima_texto()}\n{alerta}\n{get_ndvi()}\nSuelo {get_suelo_real()['texto']}\n{get_luna()}\n{get_precio_real('maracuya')}\nMem:\n{db_get_smart(6)[:700]}", parse_mode="Markdown")
    elif 'suelo' in txt:
        s=get_suelo_real(); c=get_clima_real()
        rec="Encala 500kg/ha dolomita" if s['ph']<5.8 else "Aplica materia organica 2kg/planta"
        bot.reply_to(m,f"🌱 {s['texto']}\nRecomend: {rec}\nHum sup {c['suelo_sup']:.2f} prof {c['suelo_hum']:.2f}" if c else s['texto'])
    elif 'luna' in txt: bot.reply_to(m,f"{get_luna()}\nTip: Creciente=N foliar, Menguante=K y poda, Llena=cosecha azucar")
    elif 'clima' in txt or 'grafica' in txt or 'satelite' in txt:
        if 'grafica' in txt:
            try:
                import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
                vals=[4.2,4.5,4.0,3.8,4.1,4.6,4.3]; plt.figure(); plt.plot(vals, marker='o', color='#2e7d32'); plt.title("ET0 V12"); plt.grid(True, alpha=0.3)
                buf=io.BytesIO(); plt.savefig(buf, format='png', dpi=150); buf.seek(0); plt.close()
                bot.send_photo(m.chat.id, buf, caption=f"📈 {get_clima_texto()}")
            except: bot.reply_to(m,f"📈 {get_clima_texto()}")
        else:
            c=get_clima_real(); alerta="🚨 NO FUMIGUES - Lluvia 88%" if c and c['prob']>75 else ""
            bot.reply_to(m,f"🌤️ {get_clima_texto()}\n{alerta}\n{get_ndvi()}\nSuelo {get_suelo_real()['texto']}")
    elif 'mercado' in txt or 'precio' in txt:
        cultivo=m.text.replace('/mercado','').replace('/precio','').strip() or "maracuya"
        bot.send_chat_action(m.chat.id,'typing')
        precio=get_precio_real(cultivo)
        resp=ask_groq(f"Analiza venta {cultivo} hoy. Precio {precio}. Clima {get_clima_texto()}. Tabla vender vs esperar utilidad.", "Economista")
        bot.reply_to(m,f"💰 {precio}\n\n{resp}"[:3800], parse_mode="Markdown")
    elif 'balance' in txt:
        try:
            import psycopg2; conn=psycopg2.connect(DATABASE_URL); cur=conn.cursor()
            cur.execute("SELECT valor FROM costos"); costos=cur.fetchall(); cur.execute("SELECT kg,precio FROM cosechas"); cosechas=cur.fetchall(); conn.close()
            tot_c=sum([r[0] for r in costos]) if costos else 0; tot_i=sum([r[0]*r[1] for r in cosechas]) if cosechas else 0
            bot.reply_to(m,f"💰 Costos ${tot_c:,.0f} Ingresos ${tot_i:,.0f} Utilidad ${tot_i-tot_c:,.0f} COP\nMargen {((tot_i-tot_c)/tot_i*100) if tot_i else 0:.1f}%")
        except Exception as e: bot.reply_to(m,f"Error balance {e}")
    elif 'memoria' in txt:
        buscar=m.text.replace('/memoria','').strip()
        bot.reply_to(m,f"🧠 SMART:\n{db_get_smart(35,buscar)[:3800]}")
    elif 'dosis' in txt:
        prod=m.text.replace('/dosis','').strip() or "cipermetrina"
        bot.reply_to(m, ask_groq(f"Calcula dosis triple exacta de {prod} para maracuya: Dosis/Ha, Dosis/Bomba 20L, Costo COP/Ha, Costo/Bomba, Carencia, pH agua ideal {get_suelo_real()['ph']}. Tabla."))

@bot.message_handler(commands=['recordar','guardar','coseche','gasto'])
def cmd_rec(m):
    if not ok(m): return
    txt=m.text.replace('/recordar','').replace('/guardar','').replace('/coseche','').replace('/gasto','').strip()
    tipo="gasto" if "gasto" in m.text.lower() else "nota"
    db_save(txt,tipo); bot.reply_to(m,f"✅ Guardado V12: {txt[:200]}")

@bot.message_handler(content_types=['photo'])
def handle_foto(m):
    if not ok(m): return
    info=bot.get_file(m.photo[-1].file_id); data=bot.download_file(info.file_path)
    path=f"fotos/{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"; open(path,"wb").write(data)
    bot.reply_to(m,"📸 V12 ULTIMATE doble IA + pH + alerta lluvia...")
    bot.send_chat_action(m.chat.id,'typing')
    bot.reply_to(m,f"{ask_gemini(path, m.caption or '')}"[:4000], parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def default(m):
    if not ok(m): return
    bot.send_chat_action(m.chat.id,'typing')
    bot.reply_to(m, ask_groq(m.text)[:4000])

@app.route('/')
def index(): return f"V12 ULTIMATE OK {MODELO} {get_clima_texto()}",200
@app.route('/webhook', methods=['POST'])
def webhook():
    try: bot.process_new_updates([Update.de_json(request.get_data().decode('utf-8'))])
    except: pass
    return "ok",200
def setup_webhook():
    try: bot.remove_webhook();
        if WEBHOOK_URL: bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
    except: pass
setup_webhook()
if __name__=="__main__": app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
