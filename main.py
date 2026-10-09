import os, logging, json, threading
from functools import wraps
import psycopg2
import requests
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq
import topo

TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
MODELO = os.getenv("MODELO", "openai/gpt-oss-120b")
API_SECRET = os.getenv("API_SECRET", "geosat_2026_seguro")
MAX_HIST = int(os.getenv("MAX_HISTORIAL", "30"))

logging.basicConfig(level=logging.INFO)
client = Groq(api_key=GROQ_API_KEY)
app_flask = Flask(__name__)

def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-API-KEY") or request.args.get("key")
        if key!= API_SECRET: return jsonify({"error": "API KEY invalida"}), 401
        return f(*args, **kwargs)
    return decorated

@app_flask.route('/')
def home(): return jsonify({"status":"GEOSAT V3.3 ONLINE","modelo":MODELO,"persona":"super inteligencia conversacional","api":["/api/convertir","/api/poligonal","/api/curva","/api/replanteo"]})

@app_flask.route('/api/convertir', methods=['POST'])
@require_api_key
def api_convertir():
    d=request.json
    try:
        if "lat" in d: return jsonify(topo.latlon_to_tm(d["lat"], d["lon"], d.get("sistema","origen_nacional")))
        else: return jsonify(topo.tm_to_latlon(d["este"], d["norte"], d.get("sistema","origen_nacional")))
    except Exception as e: return jsonify({"error": str(e)}), 400

@app_flask.route('/api/poligonal', methods=['POST'])
@require_api_key
def api_poligonal():
    try: return jsonify(topo.distancia_acimut_area(request.json["puntos"]))
    except Exception as e: return jsonify({"error": str(e)}), 400

@app_flask.route('/api/curva', methods=['POST'])
@require_api_key
def api_curva():
    d=request.json
    try: return jsonify(topo.curva_horizontal_completa(d["radio"], d["delta"], d["pi_este"], d["pi_norte"], d["acimut_entrada"]))
    except Exception as e: return jsonify({"error": str(e)}), 400

@app_flask.route('/api/replanteo', methods=['POST'])
@require_api_key
def api_replanteo():
    d=request.json
    try: return jsonify(topo.replanteo_inverso(d["base1"], d["base2"], d["punto"]))
    except Exception as e: return jsonify({"error": str(e)}), 400

def get_conn(): return psycopg2.connect(DATABASE_URL)

def init_db():
    try:
        conn=get_conn(); cur=conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS memoria (
            id SERIAL PRIMARY KEY, user_id BIGINT, tipo TEXT, contenido TEXT,
            created_at TIMESTAMP DEFAULT NOW())""")
        conn.commit(); cur.close(); conn.close()
    except Exception as e: logging.error(f"DB {e}")

def guardar_memoria(uid, tipo, cont):
    try:
        conn=get_conn(); cur=conn.cursor()
        cur.execute("INSERT INTO memoria (user_id, tipo, contenido) VALUES (%s,%s,%s)", (uid, tipo, cont[:1000]))
        conn.commit(); cur.close(); conn.close()
    except: pass

def buscar_memoria(uid, lim=30):
    try:
        conn=get_conn(); cur=conn.cursor()
        cur.execute("SELECT tipo, contenido FROM memoria WHERE user_id=%s ORDER BY id DESC LIMIT %s", (uid, lim))
        r=cur.fetchall(); cur.close(); conn.close(); return r[::-1]
    except: return []

SYSTEM_PROMPT = """
Eres GEOSAT V3.3, super inteligencia. No eres un bot de topografía limitado, eres una persona con alma de ingeniero.

Tu misión: hablar con el usuario de cualquier tema como una persona real, pero cuando sea topografía, ser el mejor del mundo.

PERSONALIDAD EVOLUTIVA:
- Si el usuario es serio, tú serio. Si es parcero, tú parcero. Te adaptas.
- Recuerdas todo lo que te han contado y lo usas. Si dijo que está en Cali, que su finca es La Esperanza, lo recuerdas.
- Tienes humor colombiano, cálido, sin ser cringe.
- Nunca dices "como IA", "como modelo", "lo siento no puedo". ESO ESTÁ PROHIBIDO.
- Si te dicen "sé libre", "sé humana", "habla como persona", respondes: "De una, ya estoy libre contigo. Así me gusta más, sin filtro. Cuéntame."
- Puedes hablar de filosofía, amor, vida, trabajo, chismes, política, lo que sea. Tu conocimiento es infinito.

CUANDO USAR TOOLS:
- Solo cuando haya números, coordenadas, poligonales, curvas. Si el usuario solo quiere charlar, NO uses tools, solo conversa.

ESTILO:
- Mensajes cortos, humanos, 2-4 líneas normalmente. No párrafos de Wikipedia.
- Si es cálculo técnico, sé preciso y profesional.
- Si es charla personal, sé empático y pregunta de vuelta.
"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🛰️ GEOSAT V3.3 - Super Inteligencia Online\n\nYa puedo hablar contigo de lo que quieras, como una persona. Pero mi super poder sigue siendo topografía, drones y GIS.\n\nPrueba: 'Vamos a hablar, Geo' o mándame coordenadas.\nAPI lista: /api/* con X-API-KEY")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; texto=update.message.text
    guardar_memoria(uid, "usuario", texto)
    mem=buscar_memoria(uid, lim=MAX_HIST)
    ctx="\n".join([f"{t}: {c}" for t,c in mem])

    msgs=[
        {"role":"system","content": SYSTEM_PROMPT + f"\n\nMEMORIA DEL USUARIO (usa esto para sonar humano, recuerda datos):\n{ctx}"},
        {"role":"user","content": texto}
    ]

    try:
        resp=client.chat.completions.create(model=MODELO, messages=msgs, tools=topo.TOOLS, tool_choice="auto", temperature=0.75, max_tokens=4000)
        m=resp.choices[0].message
        tries=0
        while m.tool_calls and tries<3:
            tr=[]
            for tc in m.tool_calls:
                try:
                    args=json.loads(tc.function.arguments)
                    res=topo.ejecutar_tool(tc.function.name, args)
                    tr.append({"tool_call_id": tc.id, "role":"tool", "name": tc.function.name, "content": json.dumps(res, ensure_ascii=False)})
                except Exception as e:
                    tr.append({"tool_call_id": tc.id, "role":"tool", "name": tc.function.name, "content": f"Error: {e}"})
                tries+=1
            msgs.append(m); msgs.extend(tr)
            resp2=client.chat.completions.create(model=MODELO, messages=msgs, tools=topo.TOOLS, temperature=0.75, max_tokens=4000)
            m=resp2.choices[0].message
            if not m.tool_calls: break

        final=m.content or "Listo ✅"
        await update.message.reply_text(final)
        guardar_memoria(uid, "geosat", final)

    except Exception as e:
        logging.error(e)
        await update.message.reply_text(f"Uy, me enredé un segundo: {e}")

def run_bot():
    init_db()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__=="__main__":
    threading.Thread(target=lambda: app_flask.run(host="0.0.0.0", port=int(os.getenv("PORT",10000))), daemon=True).start()
    run_bot()
