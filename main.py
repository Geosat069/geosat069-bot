<<<<<<< HEAD
# GEOSAT V1012.1 FIX - SIN ERROR DE COMILLAS
=======
# GEOSAT V1012.2 FIX FINAL
>>>>>>> 346b12b (FIX V1012.2 vendedor final)
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
    except:
        pass

def leer_memoria_usuario(user_id, limite=6):
    try:
        if not os.path.exists(MEMORY_FILE):
            return ""
        lineas = open(MEMORY_FILE, encoding="utf-8").readlines()[-100:]
        historial = []
        for l in lineas:
            try:
                j = json.loads(l)
                if str(j["user"]) == str(user_id):
                    historial.append(j["tipo"] + ": " + j["contenido"][:200])
            except:
                continue
        return "\n".join(historial[-limite:])
    except:
        return ""

def mejorar_imagen(data):
    img = Image.open(io.BytesIO(data)).convert("L")
    max_width = 1600
    if img.width > max_width:
<<<<<<< HEAD
        ratio = max_width / img.width
=======
        ratio = max_width / float(img.width)
>>>>>>> 346b12b (FIX V1012.2 vendedor final)
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
<<<<<<< HEAD
            config = f'--oem 3 --psm {psm}'
            try:
                t = pytesseract.image_to_string(img
=======
            cfg = "--oem 3 --psm " + str(psm)
            try:
                txt = pytesseract.image_to_string(img, lang="spa+eng", config=cfg)
                if len(txt.strip()) > 20:
                    return txt.strip()
            except:
                continue
    except Exception as e:
        print("OCR error: " + str(e))
    return None

def consulta_groq_max(prompt, memoria=""):
    system = "Eres Geosat V1012 vendedor Cali. Historial: " + memoria
    for model in MODELOS_TEXTO:
        try:
            resp = client.chat.completions.create(model=model, messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}], max_tokens=1200, temperature=0.4)
            return resp.choices[0].message.content
        except Exception as e:
            print("Fallo " + model + ": " + str(e))
            continue
    return "Mantenimiento, mensaje guardado."

@bot.message_handler(commands=["start"])
def start(m):
    guardar_memoria(m.from_user.id, "start", "/start")
    bot.reply_to(m, "GEOSAT V1012 MAX VENDEDOR LIVE - Manda foto de afiche.")

@bot.message_handler(content_types=["photo"])
def foto(m):
    try:
        bot.send_chat_action(m.chat.id, "typing")
        fid = m.photo[-2].file_id if len(m.photo) > 1 else m.photo[-1].file_id
        file_info = bot.get_file(fid)
        data = bot.download_file(file_info.file_path)
        texto_ocr = ocr_maximo(data)
        if not texto_ocr:
            bot.reply_to(m, "Foto borrosa. Mandala de frente con buena luz.")
            return
        guardar_memoria(m.chat.id, "foto_ocr", texto_ocr)
        memoria = leer_memoria_usuario(m.chat.id)
        prompt = "Texto OCR:\n" + texto_ocr + "\nCaption: " + (m.caption or "sin caption") + "\nHazlo mensaje vendedor WhatsApp, con emojis, resalta HOLMES ZEA y 312 280 7810, beneficios con check."
        respuesta = consulta_groq_max(prompt, memoria)
        bot.reply_to(m, respuesta)
        guardar_memoria(m.chat.id, "respuesta_foto", respuesta)
    except Exception as e:
        print("Error foto: " + str(e))
        bot.reply_to(m, "Error foto, mandala de nuevo.")

@bot.message_handler(func=lambda m: True)
def texto(m):
    try:
        bot.send_chat_action(m.chat.id, "typing")
        guardar_memoria(m.from_user.id, "usuario", m.text)
        memoria = leer_memoria_usuario(m.from_user.id)
        respuesta = consulta_groq_max(m.text, memoria)
        bot.reply_to(m, respuesta)
        guardar_memoria(m.from_user.id, "bot", respuesta)
    except Exception as e:
        bot.reply_to(m, "Error: " + str(e))

@app.route("/")
def health():
    return "V1012.2 FIX LIVE - " + str(datetime.datetime.now())

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

def run_bot():
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60, skip_pending=True)
        except Exception as e:
            print("Polling: " + str(e))
            time.sleep(5)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    run_bot()
>>>>>>> 346b12b (FIX V1012.2 vendedor final)
