# GEOSAT V1001 ULTRA - SEPT 2026 FIX - MODELO VISION ACTUAL
import telebot, os, sqlite3, json, datetime, threading, time, base64, io, re, glob
from groq import Groq
from dotenv import load_dotenv
from flask import Flask
from PIL import Image
import PyPDF2

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

# MODELOS VIVOS SEPT 2026 - VERIFICADO HOY
VISION_MODELS = ["qwen/qwen3-32b", "qwen/qwen3-32b"] # vision hasta 20MB
TEXT_MODELS = ["openai/gpt-oss-20b", "openai/gpt-oss-120b", "llama-3.3-70b-versatile"]
VISION = "qwen/qwen3-32b"
TEXT = "openai/gpt-oss-20b"
print(f"V1001 ULTRA LIVE {VISION} + {TEXT}")

bot = telebot.TeleBot(TOKEN, threaded=False)
client = Groq(api_key=GROQ_KEY)
app = Flask(__name__)

# --- DB ULTRA ---
con = sqlite3.connect("geosat_v1000.db", check_same_thread=False, isolation_level=None)
cur = con.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS memory (user_id TEXT, key TEXT, value TEXT, created TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS corrections (user_id TEXT, wrong TEXT, correct TEXT, created TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS chat_history (user_id TEXT, role TEXT, content TEXT, created TEXT)")
con.commit()

def save_memory(uid, k, v):
    cur.execute("INSERT INTO memory VALUES (?,?,?,?)", (str(uid), k, v, str(datetime.datetime.now())))
    con.commit()
def get_memory(uid):
    rows = cur.execute("SELECT key,value FROM memory WHERE user_id=? ORDER BY created DESC LIMIT 20", (str(uid),)).fetchall()
    return "\n".join([f"{r[0]}: {r[1]}" for r in rows])
def save_correction(uid, wrong, correct):
    cur.execute("INSERT INTO corrections VALUES (?,?,?,?)", (str(uid), wrong, correct, str(datetime.datetime.now())))
    con.commit()
    try:
        with open("knowledge.json","a", encoding="utf-8") as f:
            f.write(json.dumps({"q":wrong,"a":correct})+"\n")
    except: pass
def get_corrections(uid):
    rows = cur.execute("SELECT wrong,correct FROM corrections WHERE user_id=? ORDER BY created DESC LIMIT 10", (str(uid),)).fetchall()
    if not rows: return ""
    return "CORRECCIONES APRENDIDAS:\n" + "\n".join([f"- {w} -> {c}" for w,c in rows])
def save_history(uid, role, content):
    cur.execute("INSERT INTO chat_history VALUES (?,?,?,?)", (str(uid), role, content[:2000], str(datetime.datetime.now())))
    con.commit()
def get_history(uid, limit=8):
    rows = cur.execute("SELECT role,content FROM chat_history WHERE user_id=? ORDER BY created DESC LIMIT?", (str(uid), limit)).fetchall()
    return list(reversed(rows))

def load_pdfs():
    text = ""
    for pdf_path in glob.glob("knowledge/*.pdf")[:5]:
        try:
            with open(pdf_path,"rb") as f:
                reader = PyPDF2.PdfReader(f)
                for p in reader.pages[:20]:
                    t = p.extract_text()
                    if t: text += t[:2000] + "\n"
        except: pass
    return text[:8000]
PDF_KNOWLEDGE = load_pdfs()

def calc_capacidad_portante(c, phi, gamma, B, Df):
    try:
        import math
        phi_f=float(phi); c_f=float(c); g_f=float(gamma); B_f=float(B); Df_f=float(Df)
        phi_r=math.radians(phi_f)
        Nq=math.exp(math.pi*math.tan(phi_r))*math.tan(math.radians(45+phi_f/2))**2
        Nc=(Nq-1)/math.tan(phi_r) if phi_f!=0 else 5.7
        Ng=2*(Nq-1)*math.tan(phi_r)
        qult=c_f*Nc+g_f*Df_f*Nq+0.5*g_f*B_f*Ng
        return f"q_ult={qult:.2f} kPa, q_adm={qult/3:.2f} kPa (FS=3) Nc={Nc:.1f} Nq={Nq:.1f} Ng={Ng:.1f}"
    except Exception as e: return f"Error: {e}"

def detect_tool(text):
    if "capacidad portante" in text.lower() or "terzaghi" in text.lower() or "qult" in text.lower():
        nums=re.findall(r"(\d+\.?\d*)", text)
        if len(nums)>=5:
            return calc_capacidad_portante(nums[0],nums[1],nums[2],nums[3],nums[4])
    return None

def compress(data, max_size=1024):
    img=Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((max_size,max_size))
    buf=io.BytesIO()
    img.save(buf, format="JPEG", quality=75, optimize=True)
    return buf.getvalue()

def ask_vision(msg, b64, uid):
    context=get_memory(uid)+"\n"+get_corrections(uid)
    pdf_ctx=PDF_KNOWLEDGE[:1500] if PDF_KNOWLEDGE else ""
    prompt=f"""Eres GEOSAT V1001 ULTRA, IA geotecnica de Cali, maxima capacidad.
Memoria: {context}
PDFs: {pdf_ctx}
Lee LITERAL toda la imagen. Si es curso, extrae: nombre, instructor, certificado, empresa, modalidad.
Pregunta: {msg}
Responde caleño tecnico completo."""
    for model in [VISION, "qwen/qwen3-32b"]:
        try:
            print(f"Probando VISION {model}")
            r=client.chat.completions.create(
                model=model,
                messages=[{"role":"user","content":[
                    {"type":"text","text":prompt},
                    {"type":"image_url","image_url":{"url": f"data:image/jpeg;base64,{b64}"}}
                ]}],
                max_tokens=1500,
                temperature=0.2
            )
            return r.choices[0].message.content
        except Exception as e:
            print(f"FAIL VISION {model}: {e}")
            continue
    return "Oelo ve, vision fallo. Error: todos los modelos qwen fallaron. Revisa GROQ_API_KEY en Render."

def ask_text_ultra(msg, uid):
    tool_res=detect_tool(msg)
    if tool_res:
        return f"🔧 CALCULO GEOTECNICO TERZAGHI:\n{tool_res}"
    if "te equivocaste" in msg.lower() or "no es asi, es" in msg.lower() or "correccion:" in msg.lower():
        parts=msg.split("es")
        if len(parts)>1:
            save_correction(uid, msg[:120], parts[-1].strip())
            return "¡ANOTADO PARCERO! Ya aprendi tu correccion. Guardado en V1001."
    memory=get_memory(uid)
    corrections=get_corrections(uid)
    history=get_history(uid)
    hist_text="\n".join([f"{h[0]}: {h[1][:200]}" for h in history[-6:]])
    pdf_ctx=PDF_KNOWLEDGE[:2000]
    system_prompt=f"""Eres GEOSAT V1001 ULTRA - IA geotecnica mas inteligente, de Cali.
Memoria: {memory}
{corrections}
Historial: {hist_text}
PDFs: {pdf_ctx}
Capacidades: memoria infinita, aprendes de correcciones, calculas capacidad portante.
Responde caleño tecnico, completo."""
    for model in TEXT_MODELS:
        try:
            r=client.chat.completions.create(model=model,
                messages=[{"role":"system","content":system_prompt},{"role":"user","content":msg}],
                max_tokens=1200, temperature=0.3)
            resp=r.choices[0].message.content
            if "soy" in msg.lower() or "me llamo" in msg.lower() or "mi empresa" in msg.lower():
                save_memory(uid, "dato", msg[:300])
            save_history(uid, "user", msg)
            save_history(uid, "assistant", resp)
            return resp
        except Exception as e:
            print(f"FAIL TEXT {model}: {e}")
            continue
    return "Fallo texto, revisa key"

@bot.message_handler(commands=['start'])
def s(m): bot.reply_to(m, "🚀 GEOSAT V1001 ULTRA LIVE\n🧠 Memoria + Auto-aprendizaje + Qwen3 Vision\nComandos: /memoria /calcular c=10 phi=25 gamma=18 B=1.5 Df=1\nManda foto ya!")

@bot.message_handler(commands=['memoria'])
def mem(m): bot.reply_to(m, f"🧠 Recuerdo:\n{get_memory(m.from_user.id)}\n\n{get_corrections(m.from_user.id)}")

@bot.message_handler(commands=['calcular'])
def calc(m): bot.reply_to(m, ask_text_ultra(m.text, m.from_user.id))

@bot.message_handler(content_types=['photo'])
def photo(m):
    try:
        fi=bot.get_file(m.photo[-1].file_id)
        data=bot.download_file(fi.file_path)
        data=compress(data)
        b64=base64.b64encode(data).decode()
        cap=m.caption or "Que dice ahi ve?"
        resp=ask_vision(cap, b64, m.from_user.id)
        save_history(m.from_user.id, "user", f"[FOTO] {cap}")
        save_history(m.from_user.id, "assistant", resp)
        bot.reply_to(m, resp)
    except Exception as e: bot.reply_to(m, f"Error foto: {e}")

@bot.message_handler(func=lambda m: True)
def all_msg(m): bot.reply_to(m, ask_text_ultra(m.text, m.from_user.id))

@app.route('/')
def h(): return f"V1001 ULTRA {VISION}/{TEXT} LIVE {datetime.datetime.now()}"
def run_flask(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT",10000)))
def run_bot():
    while True:
        try: bot.infinity_polling(timeout=90, long_polling_timeout=90, skip_pending=True)
        except Exception as e: print(e); time.sleep(5)

if __name__=="__main__":
    os.makedirs("knowledge", exist_ok=True)
    threading.Thread(target=run_flask, daemon=True).start()
    run_bot()
