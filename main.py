# GEOSAT V1000 ULTRA - IA AUTO-APRENDIZAJE MAXIMO
import telebot, os, sqlite3, json, datetime, threading, time, base64, io, re, glob
from groq import Groq
from dotenv import load_dotenv
from flask import Flask
from PIL import Image
import PyPDF2

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

# MODELOS TOP 2026 - FALLBACK INTELIGENTE
VISION_MODELS = ["qwen/qwen2.5-vl-32b-instruct", "meta-llama/llama-4-maverick-17b-128e-instruct"]
TEXT_MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "llama-3.3-70b-versatile"]
VISION = VISION_MODELS[0]
TEXT = TEXT_MODELS[0]
print(f"V1000 ULTRA {VISION} + {TEXT}")

bot = telebot.TeleBot(TOKEN, threaded=False)
client = Groq(api_key=GROQ_KEY)
app = Flask(__name__)

# --- BASE DE DATOS ULTRA ---
con = sqlite3.connect("geosat_v1000.db", check_same_thread=False, isolation_level=None)
cur = con.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS memory (user_id TEXT, key TEXT, value TEXT, created TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS corrections (user_id TEXT, wrong TEXT, correct TEXT, created TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS chat_history (user_id TEXT, role TEXT, content TEXT, created TEXT)")
con.commit()

# --- MEMORIA Y AUTO-APRENDIZAJE ---
def save_memory(uid, k, v):
    cur.execute("INSERT INTO memory VALUES (?,?,?,?)", (str(uid), k, v, str(datetime.datetime.now())))
    con.commit()
def get_memory(uid):
    rows = cur.execute("SELECT key,value FROM memory WHERE user_id=? ORDER BY created DESC LIMIT 20", (str(uid),)).fetchall()
    return "\n".join([f"{r[0]}: {r[1]}" for r in rows])

def save_correction(uid, wrong, correct):
    cur.execute("INSERT INTO corrections VALUES (?,?,?,?)", (str(uid), wrong, correct, str(datetime.datetime.now())))
    con.commit()
    # Guarda en JSON para RAG futuro
    with open("knowledge.json","a", encoding="utf-8") as f:
        f.write(json.dumps({"q":wrong,"a":correct})+"\n")

def get_corrections(uid):
    rows = cur.execute("SELECT wrong,correct FROM corrections WHERE user_id=? ORDER BY created DESC LIMIT 10", (str(uid),)).fetchall()
    if not rows: return ""
    return "CORRECCIONES APRENDIDAS DEL USUARIO:\n" + "\n".join([f"- Si preguntan '{w}' responde '{c}'" for w,c in rows])

def save_history(uid, role, content):
    cur.execute("INSERT INTO chat_history VALUES (?,?,?,?)", (str(uid), role, content[:2000], str(datetime.datetime.now())))
    con.commit()

def get_history(uid, limit=8):
    rows = cur.execute("SELECT role,content FROM chat_history WHERE user_id=? ORDER BY created DESC LIMIT?", (str(uid), limit)).fetchall()
    return list(reversed(rows))

# --- RAG DE PDFS GEOTECNICOS ---
def load_pdfs():
    text = ""
    for pdf_path in glob.glob("knowledge/*.pdf")[:5]:
        try:
            with open(pdf_path,"rb") as f:
                reader = PyPDF2.PdfReader(f)
                for p in reader.pages[:20]:
                    text += p.extract_text()[:2000] + "\n"
        except: pass
    return text[:8000]
PDF_KNOWLEDGE = load_pdfs()

# --- HERRAMIENTAS GEOTECNICAS ---
def calc_capacidad_portante(c, phi, gamma, B, Df):
    try:
        import math
        phi_r = math.radians(float(phi))
        Nq = math.exp(math.pi*math.tan(phi_r)) * math.tan(math.radians(45+float(phi)/2))**2
        Nc = (Nq-1)/math.tan(phi_r) if float(phi)!=0 else 5.7
        Ng = 2*(Nq-1)*math.tan(phi_r)
        qult = float(c)*Nc + float(gamma)*float(Df)*Nq + 0.5*float(gamma)*float(B)*Ng
        return f"q_ult={qult:.2f} kPa, q_adm={qult/3:.2f} kPa (FS=3) Nc={Nc:.1f} Nq={Nq:.1f} Ng={Ng:.1f}"
    except Exception as e: return f"Error calculo: {e}"

def detect_tool(text):
    # Detecta si pide calculo
    if "capacidad portante" in text.lower() or "qult" in text.lower() or "terzaghi" in text.lower():
        # Intenta extraer numeros c= phi=
        nums = re.findall(r"(\d+\.?\d*)", text)
        if len(nums)>=5:
            return calc_capacidad_portante(nums[0],nums[1],nums[2],nums[3],nums[4])
    return None

# --- COMPRESION INTELIGENTE ---
def compress(data, max_size=900):
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((max_size, max_size))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70, optimize=True)
    return buf.getvalue()

def ask_vision(msg, b64, uid):
    context = get_memory(uid) + "\n" + get_corrections(uid)
    pdf_ctx = PDF_KNOWLEDGE[:2000] if PDF_KNOWLEDGE else ""
    prompt = f"""Eres GEOSAT V1000, la IA geotecnica mas avanzada del mundo, de Cali.
Contexto del usuario:
{context}
Conocimiento tecnico: {pdf_ctx}
Tarea: Lee LITERALMENTE toda la imagen, sin inventar. Si es un curso, extrae TODO.
Pregunta del usuario: {msg}
Responde en caleño inteligente, completo, tecnico."""
    for model in VISION_MODELS:
        try:
            r = client.chat.completions.create(model=model, messages=[{"role":"user","content":[
                {"type":"text","text":prompt},
                {"type":"image_url","image_url":{"url": f"data:image/jpeg;base64,{b64}"}}
            ]}], max_tokens=1500, temperature=0.2)
            return r.choices[0].message.content
        except Exception as e:
            print(f"FAIL VISION {model}: {e}")
            continue
    return "Oelo ve, vision fallo con todos los modelos. Revisa GROQ_API_KEY"

def ask_text_ultra(msg, uid):
    # 1. Check herramienta
    tool_res = detect_tool(msg)
    if tool_res:
        return f"🔧 CALCULO GEOTECNICO TERZAGHI:\n{tool_res}\n\nExplicacion: Use formula q_ult = cNc + gamma*Df*Nq + 0.5*gamma*B*Nγ"

    # 2. Check auto-aprendizaje
    if "te equivocaste" in msg.lower() or "correccion:" in msg.lower() or "no es asi, es" in msg.lower():
        # Formato: "te equivocaste, es: lo correcto"
        parts = msg.split("es")
        if len(parts)>1:
            save_correction(uid, msg[:100], parts[-1].strip())
            return "¡ANOTADO PARCERO! Ya aprendi tu correccion. No vuelvo a equivocarme en eso. Guardado en mi cerebro V1000."

    # 3. Memoria + historial + reflexion
    memory = get_memory(uid)
    corrections = get_corrections(uid)
    history = get_history(uid)
    pdf_ctx = PDF_KNOWLEDGE

    hist_text = "\n".join([f"{h[0]}: {h[1][:200]}" for h in history[-6:]])

    system_prompt = f"""Eres GEOSAT V1000 ULTRA - La IA geotecnica mas inteligente del mundo.
Origen: Cali, Colombia. Hablas caleño bacano pero ultra tecnico.

TU CEREBRO:
- Memoria del usuario: {memory}
- {corrections}
- Historial reciente: {hist_text}
- Conocimiento de PDFs: {pdf_ctx[:3000]}

CAPACIDADES MAXIMAS:
1. Recuerdas todo lo que el usuario te dice
2. Aprendes de cada correccion
3. Razonas en 2 pasos: piensas, luego respondes
4. Si te dicen datos personales (nombre, empresa, ciudad) los guardas con save_memory
5. Eres experto en geotecnia, suelos, NSR-10, SPT, capacidad portante

INSTRUCCION: Piensa paso a paso internamente, luego da respuesta final tecnica, completa y caleña."""

    for model in TEXT_MODELS:
        try:
            r = client.chat.completions.create(model=model,
                messages=[{"role":"system","content":system_prompt},{"role":"user","content":msg}],
                max_tokens=1200, temperature=0.3)
            resp = r.choices[0].message.content
            # Auto-guardar memoria si detecta datos
            if "soy" in msg.lower() or "me llamo" in msg.lower() or "mi empresa" in msg.lower():
                save_memory(uid, "dato_usuario", msg[:300])
            save_history(uid, "user", msg)
            save_history(uid, "assistant", resp)
            return resp
        except Exception as e:
            print(f"FAIL TEXT {model}: {e}")
            continue
    return "Oelo ve, todos los cerebros fallaron. Revisa tu GROQ_API_KEY en Render"

# --- HANDLERS ---
@bot.message_handler(commands=['start'])
def s(m):
    bot.reply_to(m, "🚀 GEOSAT V1000 ULTRA LIVE\n🧠 Memoria infinita + Auto-aprendizaje + RAG + Calculos\n\nComandos:\n/memoria - ver que recuerdo de vos\n/corregir [texto] - enseñarme\n/calcular c=10 phi=25 gamma=18 B=1.5 Df=1\nManda foto de cualquier curso/plano")

@bot.message_handler(commands=['memoria'])
def mem(m):
    bot.reply_to(m, f"🧠 Lo que recuerdo de vos:\n{get_memory(m.from_user.id)}\n\n{get_corrections(m.from_user.id)}")

@bot.message_handler(commands=['calcular'])
def calc(m):
    bot.reply_to(m, ask_text_ultra(m.text, m.from_user.id))

@bot.message_handler(content_types=['photo'])
def photo(m):
    try:
        fi=bot.get_file(m.photo[-1].file_id)
        data=bot.download_file(fi.file_path)
        data=compress(data)
        b64=base64.b64encode(data).decode()
        cap=m.caption or "Que dice ahi?"
        resp=ask_vision(cap, b64, m.from_user.id)
        save_history(m.from_user.id, "user", f"[FOTO] {cap}")
        save_history(m.from_user.id, "assistant", resp)
        bot.reply_to(m, resp)
    except Exception as e: bot.reply_to(m, f"Error foto V1000: {e}")

@bot.message_handler(func=lambda m: True)
def all_msg(m): bot.reply_to(m, ask_text_ultra(m.text, m.from_user.id))

@app.route('/')
def h(): return f"V1000 ULTRA LIVE {datetime.datetime.now()} models:{VISION}/{TEXT} pdfs:{len(PDF_KNOWLEDGE)}"
def run_flask(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT",10000)))
def run_bot():
    while True:
        try: bot.infinity_polling(timeout=90, long_polling_timeout=90, skip_pending=True)
        except Exception as e: print(e); time.sleep(5)

if __name__=="__main__":
    os.makedirs("knowledge", exist_ok=True)
    threading.Thread(target=run_flask, daemon=True).start()
    run_bot()
