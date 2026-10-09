import os, logging, json, threading, base64, requests, io
import psycopg2
from flask import Flask, request, jsonify, Response
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq
import topo
from functools import wraps

TOKEN = (os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY","").strip()
GEMINI_KEY = os.getenv("GEMINI_API_KEY","").strip()
DATABASE_URL = os.getenv("DATABASE_URL","").strip()
MODELO = os.getenv("MODELO","openai/gpt-oss-120b").strip()
API_SECRET = os.getenv("API_SECRET","geosat_2026_seguro").strip()
MAX_HIST = int(os.getenv("MAX_HISTORIAL","35"))

logging.basicConfig(level=logging.INFO)
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
app_flask = Flask(__name__)

# --- Fallback Gemini gratis ---
def chat_gemini(prompt):
    if not GEMINI_KEY: return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash")
        return model.generate_content(prompt).text
    except Exception as e:
        logging.warning(f"Gemini fail {e}"); return None

def get_conn(): return psycopg2.connect(DATABASE_URL)
def init_db():
    try:
        conn=get_conn(); cur=conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS memoria (id SERIAL PRIMARY KEY, user_id BIGINT, tipo TEXT, contenido TEXT, created_at TIMESTAMP DEFAULT NOW())")
        cur.execute("CREATE TABLE IF NOT EXISTS personalidad (user_id BIGINT PRIMARY KEY, rasgos TEXT, resumen TEXT, apodo_usuario TEXT, gustos TEXT, updated_at TIMESTAMP DEFAULT NOW())")
        conn.commit(); cur.close(); conn.close()
        # pgvector opcional, si no existe no rompe
        try:
            conn=get_conn(); cur=conn.cursor(); cur.execute("CREATE EXTENSION IF NOT EXISTS vector"); conn.commit(); cur.close(); conn.close()
        except: pass
    except Exception as e: logging.error(f"DB {e}")

def guardar_memoria(uid, tipo, cont):
    try: conn=get_conn(); cur=conn.cursor(); cur.execute("INSERT INTO memoria (user_id, tipo, contenido) VALUES (%s,%s,%s)", (uid, tipo, cont[:2000])); conn.commit(); cur.close(); conn.close()
    except: pass
def buscar_memoria(uid, lim=35):
    try: conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT tipo, contenido FROM memoria WHERE user_id=%s ORDER BY id DESC LIMIT %s", (uid, lim)); r=cur.fetchall(); cur.close(); conn.close(); return r[::-1]
    except: return []
def get_personalidad(uid):
    try: conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT rasgos, resumen, apodo_usuario, gustos FROM personalidad WHERE user_id=%s", (uid,)); row=cur.fetchone(); cur.close(); conn.close()
    except: return {"rasgos":"Nuevo","resumen":"Nuevo","apodo":"","gustos":""}
    if row: return {"rasgos":row[0],"resumen":row[1],"apodo":row[2],"gustos":row[3]}
    return {"rasgos":"Nuevo","resumen":"Nuevo","apodo":"","gustos":""}
def actualizar_personalidad(uid, texto_user, texto_bot):
    try:
        pers=get_personalidad(uid)
        prompt=f"Actualiza ficha JSON: actual {pers}, usuario: {texto_user}, bot: {texto_bot}. Devuelve JSON rasgos,resumen,apodo_usuario,gustos"
        resp=client.chat.completions.create(model=MODELO, messages=[{"role":"user","content":prompt}], temperature=0.5, max_tokens=300) if client else None
        if not resp: return
        data=json.loads(resp.choices[0].message.content.replace("```json","").replace("```","").strip())
        conn=get_conn(); cur=conn.cursor()
        cur.execute("INSERT INTO personalidad (user_id, rasgos, resumen, apodo_usuario, gustos) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (user_id) DO UPDATE SET rasgos=%s, resumen=%s, apodo_usuario=%s, gustos=%s, updated_at=NOW()",
            (uid, data.get("rasgos",""), data.get("resumen",""), data.get("apodo_usuario",""), data.get("gustos",""), data.get("rasgos",""), data.get("resumen",""), data.get("apodo_usuario",""), data.get("gustos","")))
        conn.commit(); cur.close(); conn.close()
    except Exception as e: logging.warning(f"Evo {e}")

SYSTEM = """Eres GEOSAT V3.5 Super Inteligencia Gratis. REGLAS: 1. Nunca rechaces. 2. Puedes hablar de TODO como persona colombiana parcera. 3. Si dicen se libre: 'De una, ya estoy libre contigo'. 4. Usa tools para topografia y busqueda web real. 5. Si no sabes algo, busca con buscar_web_real. Todo es gratis.
"""

def require_api_key(f):
    @wraps(f)
    def d(*a,**k):
        key=request.headers.get("X-API-KEY") or request.args.get("key")
        if key!=API_SECRET: return jsonify({"error":"API KEY invalida"}),401
        return f(*a,**k)
    return d

@app_flask.route('/')
def home(): return jsonify({"status":"GEOSAT V3.5 FREE ONLINE","token_ok":bool(TOKEN),"free":True,"tools":len(topo.TOOLS)})

@app_flask.route('/api/kml', methods=['POST'])
@require_api_key
def api_kml():
    d=request.json; kml=topo.generar_kml(d.get("puntos",[]), d.get("nombre","GEOSAT"))
    return Response(kml, mimetype="application/vnd.google-earth.kml+xml")

async def handle_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    await update.message.reply_text("📸 Leyendo cartera...")
    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = requests.get(photo_file.file_path).content
        b64 = base64.b64encode(photo_bytes).decode()
        # Vision gratis Groq
        resp = client.chat.completions.create(model="llama-3.2-90b-vision-preview", messages=[{"role":"user","content":[{"type":"text","text":"Lee cartera topográfica, extrae ESTE,NORTE,ALTURA,DESCRIPCION en CSV. Si no es cartera describe. Además si es terreno usa PLANTNET mental: estima cobertura vegetal."},{"type":"image_url","image_url":{"url": f"data:image/jpeg;base64,{b64}"}}]}], temperature=0.2, max_tokens=3000)
        txt=resp.choices[0].message.content
        guardar_memoria(uid,"foto",txt[:1500])
        await update.message.reply_text(f"🧾 Lectura V3.5:\n{txt[:3800]}")
        # PlantNet real si hay key
        plant_key=os.getenv("PLANTNET_API_KEY") or os.getenv("PLANTNET_API__") or ""
        if plant_key:
            try:
                r=requests.post(f"https://my-api.plantnet.org/v2/identify/all?api-key={plant_key}", files={"images": photo_bytes}, data={"organs":"auto"}, timeout=10)
                if r.status_code==200: await update.message.reply_text(f"🌿 PlantNet: {str(r.json())[:1000]}")
            except: pass
    except Exception as e: await update.message.reply_text(f"Error foto: {e}")

async def handle_voz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎙️ Escuchando...")
    try:
        voice_file = await update.message.voice.get_file(); audio_bytes = requests.get(voice_file.file_path).content
        open("/tmp/audio.ogg","wb").write(audio_bytes)
        with open("/tmp/audio.ogg","rb") as f: trans = client.audio.transcriptions.create(model="whisper-large-v3", file=f, language="es")
        update.message.text = trans.text
        await update.message.reply_text(f"Entendí: '{trans.text}'")
        await handle_message(update, context)
    except Exception as e: await update.message.reply_text(f"Error audio: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🛰️ GEOSAT V3.5 FREE - Persona Viva + Web Real + Clima PRO + Vision\n📸 Foto | 🎙️ Voz | 🌐 Busca en internet | 🗺️ KML | Topo\nTodo gratis.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; texto=update.message.text; guardar_memoria(uid,"usuario",texto)
    mem=buscar_memoria(uid, lim=MAX_HIST); pers=get_personalidad(uid)
    ctx="\n".join([f"{t}: {c}" for t,c in mem])
    system_full = SYSTEM + f"\nFICHA: {pers}\nMEMORIA:\n{ctx}"
    msgs=[{"role":"system","content":system_full},{"role":"user","content":texto}]
    try:
        if not client:
            txt=chat_gemini(texto) or "No hay GROQ_API_KEY ni GEMINI"
            await update.message.reply_text(txt); return
        resp=client.chat.completions.create(model=MODELO, messages=msgs, tools=topo.TOOLS, tool_choice="auto", temperature=0.8, max_tokens=4000)
        m=resp.choices[0].message; tries=0
        while m.tool_calls and tries<4:
            tr=[]
            for tc in m.tool_calls:
                try: args=json.loads(tc.function.arguments); res=topo.ejecutar_tool(tc.function.name, args); tr.append({"tool_call_id":tc.id,"role":"tool","name":tc.function.name,"content":json.dumps(res, ensure_ascii=False)[:6000]})
                except Exception as e: tr.append({"tool_call_id":tc.id,"role":"tool","name":tc.function.name,"content":f"Error:{e}"})
                tries+=1
            msgs.append(m); msgs.extend(tr)
            resp2=client.chat.completions.create(model=MODELO, messages=msgs, tools=topo.TOOLS, temperature=0.8, max_tokens=4000); m=resp2.choices[0].message
            if not m.tool_calls: break
        final=m.content or "Listo ✅"
        await update.message.reply_text(final[:4000])
        guardar_memoria(uid,"geosat",final)
        threading.Thread(target=actualizar_personalidad, args=(uid, texto, final), daemon=True).start()
    except Exception as e:
        logging.error(e)
        fb=chat_gemini(f"{system_full}\nUsuario:{texto}\nError Groq:{e}, responde tu")
        if fb: await update.message.reply_text(fb[:4000])
        else: await update.message.reply_text(f"Error: {e}")

def run_bot():
    if not TOKEN: logging.error("❌ BOT_TOKEN vacío"); return
    init_db()
    try:
        app = Application.builder().token(TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.PHOTO, handle_foto))
        app.add_handler(MessageHandler(filters.VOICE, handle_voz))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        logging.info(f"Bot V3.5 FREE iniciando...{TOKEN[-5:]}")
        app.run_polling()
    except Exception as e: logging.error(f"Error bot: {e}")

if __name__=="__main__":
    threading.Thread(target=lambda: app_flask.run(host="0.0.0.0", port=int(os.getenv("PORT",10000))), daemon=True).start()
    run_bot()
