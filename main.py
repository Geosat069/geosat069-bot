# GEOSAT V1012 MAX VENDEDOR - OCR BONITO + ESTABLE + GROQ
import telebot, os, threading, time, datetime, io, json
from flask import Flask
from PIL import Image, ImageEnhance, ImageOps
import pytesseract
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

bot = telebot.TeleBot(TOKEN, threaded=False)
client = Groq(api_key=GROQ_KEY)
app = Flask(__name__)

MEMORY_FILE = "memoria_geosat.jsonl"
MODELOS_TEXTO = [GROQ_MODEL, "llama-3.3-70b-versatile", "openai/gpt-oss-20b"]

def guardar_memoria(user_id, tipo, contenido):
    try:
        data = {"fecha": str(datetime.datetime.now()), "user": user_id, "tipo": tipo, "contenido": contenido[:1000]}
        with open(MEMORY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
    except: pass

def leer_memoria_usuario(user_id, limite=6):
    try:
        if not os.path.exists(MEMORY_FILE): return ""
        lineas = open(MEMORY_FILE, encoding="utf-8").readlines()[-100:]
        historial = []
        for l in lineas:
            try:
                j = json.loads(l)
                if str(j["user"]) == str(user_id):
                    historial.append(f"{j['tipo']}: {j['contenido'][:200]}")
            except: continue
        return "\n".join(historial[-limite:])
    except: return ""

def mejorar_imagen(data):
    img = Image.open(io.BytesIO(data)).convert("L")
    max_width = 1600
    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)
    elif img.width < 800:
        img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
    img = ImageOps.autocontrast(img, cutoff=1)
    img = ImageEnhance.Contrast(img).enhance(1.8)
    return img

def ocr_maximo(data):
    try:
        img = mejorar_imagen(data)
        for psm in [6, 3]:
            config = f'--oem 3 --psm {psm}'
            try:
                t = pytesseract.image_to_string(img, lang='spa+eng', config=config)
                if len(t.strip()) > 20:
                    return t.strip()
            except: continue
    except Exception as e:
        print(f"OCR error: {e}")
    return None

def consulta_groq_max(prompt, memoria=""):
    system = f"Eres Geosat V1012, IA vendedora de Cali, experta en camaras y geologia. Historial:\n{memoria}\nResponde util y directa. Si es un afiche, conviertelo en texto vendedor."
    for model in MODELOS_TEXTO:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                max_tokens=1200,
                temperature=0.4
            )
            return resp.choices[0].message.content
        except Exception as e:
            print(f"Fallo {model}: {e}")
            continue
    return "Estoy en mantenimiento, pero ya guarde tu mensaje."

@bot.message_handler(commands=['start'])
def start(m):
    guardar_memoria(m.from_user.id, "start", "/start")
    bot.reply_to(m, "🚀 GEOSAT V1012 MAX VENDEDOR LIVE\n\nSoy tu IA al maximo:\n✅ Leo afiches y los convierto en texto de venta\n✅ Aprendo de ti\n📸 Mandame una foto de un afiche y te lo hago bonito para WhatsApp.")

@bot.message_handler(content_types=['photo'])
def foto(m):
    try:
        bot.send_chat_action(m.chat.id, 'typing')
        file_id = m.photo[-2].file_id if len(m.photo) > 1 else m.photo[-1].file_id
        file_info = bot.get_file(file_id)
        data = bot.download_file(file_info.file_path)

        texto_ocr = ocr_maximo(data)

        if not texto_ocr:
            bot.reply_to(m, "📸 Recibi la foto pero el texto esta borroso. Mandala de frente con buena luz porfa.")
            return

        guardar_memoria(m.chat.id, "foto_ocr", texto_ocr)
        memoria = leer_memoria_usuario(m.chat.id)

        prompt = f"""
Tienes el texto OCR de este afiche de camaras:

{texto_ocr}

Caption usuario: {m.caption or 'sin caption'}

TAREA: Conviertelo en un mensaje VENDEDOR listo para copiar/pegar en WhatsApp.
REGLAS:
- No uses tablas con | ni
