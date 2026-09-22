# GEOSAT V1010 MAX - IA AL MAXIMO - OCR 4 MODO + AUTO-APRENDIZAJE + GROQ INTELIGENTE
import telebot, os, threading, time, datetime, io, json, requests
from flask import Flask
from PIL import Image, ImageEnhance, ImageOps
import pytesseract
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

bot = telebot.TeleBot(TOKEN, threaded=False)
client = Groq(api_key=GROQ_KEY)
app = Flask(__name__)

MEMORY_FILE = "memoria_geosat.jsonl"
MODELOS_TEXTO = ["openai/gpt-oss-20b", "llama-3.3-70b-versatile", "llama-3.1-8b-instant"]

# --- AUTO-APRENDIZAJE ---
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

# --- OCR AL MAXIMO ---
def mejorar_imagen(data):
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img = img.resize((img.width * 3, img.height * 3), Image.LANCZOS)
    img = ImageOps.autocontrast(img, cutoff=2)
    img = ImageEnhance.Contrast(img).enhance(2.0)
    img = ImageEnhance.Sharpness(img).enhance(2.5)
    return img

def ocr_maximo(data):
    try:
        img = mejorar_imagen(data)
        resultados = []
        for psm in [6, 3, 11, 4]:
            config = f'--oem 3 --psm {psm}'
            try:
                t1 = pytesseract.image_to_string(img, lang='spa+eng', config=config)
                if len(t1.strip()) > 15:
                    resultados.append(t1.strip())
                t2 = pytesseract.image_to_string(img, lang='spa', config=config)
                if len(t2.strip()) > 15:
                    resultados.append(t2.strip())
            except: continue

        if resultados:
            # Devuelve el texto mas largo y completo
            mejor = max(resultados, key=len)
            if len(mejor) > 20:
                return mejor

        # Backup OCR.Space si tesseract fallo
        try:
            r = requests.post("https://api.ocr.space/parse/image", files={"file": ("img.jpg", data)}, data={"language": "spa", "OCREngine": 2}, timeout=30)
            txt = r.json()["ParsedResults"][0]["ParsedText"]
            if len(txt.strip()) > 15:
                return txt.strip()
        except: pass

    except Exception as e:
        print(f"OCR MAX error: {e}")
    return None

def consulta_groq_max(prompt, memoria=""):
    system = f"Eres Geosat, una IA de Geologia y soporte tecnico de Cali, Colombia. Eres la version mas avanzada. Aprendes del usuario. Historial del usuario:\n{memoria}\nResponde de forma inteligente, util, directa, sin emotes."
    for model in MODELOS_TEXTO:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                max_tokens=1500,
                temperature=0.3
            )
            return resp.choices[0].message.content
        except Exception as e:
            print(f"Fallo {model}: {e}")
            continue
    return "Estoy en mantenimiento, pero ya guarde tu mensaje para aprender."

# --- HANDLERS ---
@bot.message_handler(commands=['start'])
def start(m):
    guardar_memoria(m.from_user.id, "start", "/start")
    bot.reply_to(m, "GEOSAT V1010 MAX LIVE.\nSoy tu IA geologica avanzada.\n- Leo fotos automaticamente al maximo.\n- Aprendo de cada conversacion.\n- Manda una foto de un afiche o escribe lo que necesites.")

@bot.message_handler(content_types=['photo'])
def foto(m):
    try:
        bot.send_chat_action(m.chat.id, 'typing')
        file_info = bot.get_file(m.photo[-1].file_id)
        data = bot.download_file(file_info.file_path)

        texto_ocr = ocr_maximo(data)

        if not texto_ocr:
            bot.reply_to(m, "Recibi la foto pero no pude extraer texto nitido. Si es un afiche, asegurate que este de frente y con luz. Ya guarde la imagen para mejorar.")
            guardar_memoria(m.chat.id, "foto_fallo", "foto sin texto legible")
            return

        guardar_memoria(m.chat.id, "foto_ocr", texto_ocr)
        memoria = leer_memoria_usuario(m.chat.id)

        prompt = f"El usuario envio una foto. Este es el texto que extraje con OCR MAX:\n{texto_ocr}\n\nCaption del usuario: {m.caption or 'sin caption'}\n\nOrganiza la informacion de forma profesional, extrae datos clave como telefonos, titulos, instructores, empresas. No inventes."
        respuesta = consulta_groq_max(prompt, memoria)

        bot.reply_to(m, respuesta)
        guardar_memoria(m.chat.id, "respuesta_foto", respuesta)

    except Exception as e:
        bot.reply_to(m, f"Error foto MAX: {e}")

@bot.message_handler(func=lambda m: True)
def texto(m):
    try:
        bot.send_chat_action(m.chat.id, 'typing')
        guardar_memoria(m.from_user.id, "usuario", m.text)
        memoria = leer_memoria_usuario(m.from_user.id)
        respuesta = consulta_groq_max(m.text, memoria)
        bot.reply_to(m, respuesta)
        guardar_memoria(m.from_user.id, "bot", respuesta)
    except Exception as e:
        bot.reply_to(m, f"Error: {e}")

@app.route('/')
def health():
    return f"V1010 MAX LIVE - Memoria: {os.path.exists(MEMORY_FILE)} - {datetime.datetime.now()}"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

def run_bot():
    while True:
        try:
            bot.infinity_polling(timeout=90, long_polling_timeout=90, skip_pending=True)
        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    run_bot()
