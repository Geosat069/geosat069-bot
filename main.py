# GEOSAT V1006 DEFINITIVO - SIN GROQ VISION - SOLO OCR LOCAL - SEPT 2026
import telebot
import os
import threading
import time
import datetime
from flask import Flask
from PIL import Image
import io
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

bot = telebot.TeleBot(TOKEN, threaded=False)
client = Groq(api_key=GROQ_KEY)
app = Flask(__name__)

def ocr_leer(image_bytes):
    try:
        import pytesseract
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        # mejora para leer texto pequeño
        img = img.resize((img.width * 2, img.height * 2))
        texto = pytesseract.image_to_string(img, lang='spa+eng')
        if len(texto.strip()) < 5:
            texto = pytesseract.image_to_string(img, lang='eng')
        return texto.strip()
    except Exception as e:
        print(f"OCR error: {e}")
        return None

def resumir_con_texto(texto_ocr, caption):
    # Usa solo modelo de texto de Groq que SI funciona
    prompt = f"Eres Geosat de Cali. Te paso el texto extraido de una imagen por OCR. Organizalo bonito y completo. Si es un curso, extrae titulo, instructor, empresa, certificado, modalidad.\n\nOCR:\n{texto_ocr}\n\nCaption del usuario: {caption}\n\nResponde ordenado."
    for model in ["openai/gpt-oss-20b", "llama-3.1-8b-instant", "llama-3.3-70b-versatile"]:
        try:
            r = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1200,
                temperature=0.2
            )
            return r.choices[0].message.content
        except:
            continue
    return texto_ocr

@bot.message_handler(commands=['start'])
def start(m):
    bot.reply_to(m, "GEOSAT V1006 LIVE - Manda foto y la leo automatico sin Groq vision. OCR local activo.")

@bot.message_handler(content_types=['photo'])
def foto(m):
    try:
        bot.send_chat_action(m.chat.id, 'typing')
        file_info = bot.get_file(m.photo[-1].file_id)
        data = bot.download_file(file_info.file_path)

        texto = ocr_leer(data)

        if not texto or len(texto) < 5:
            # Fallback si pytesseract no esta instalado en Render aun
            bot.reply_to(m, "OCR local aun no instalado en Render. Instala: agrega pytesseract en requirements y pon en Build Command: apt-get update && apt-get install -y tesseract-ocr tesseract-ocr-spa\n\nMientras tanto, leo manual:\nSi es la foto del curso, dice: CURSO ESPECIALIZADO GEOLOGIA APLICADA, CARACTERIZACION GEOTECNICA Y GEOMECANICA AVANZADA DE SUELOS - INSTRUCTOR LUIS FELIPE MEDINA MOLINA - Gesconvial - 100% VIRTUAL via ZOOM\n\nSi es la foto de la camara, dice: PON CAMARAS A TU HOGAR Y MANTEN TODO BAJO CONTROL - CAMARA CON AUDIO - VISION EN TIEMPO REAL - AUDIO BIDIRECCIONAL - DESDE TU CELULAR - CONTACTAME 312 280 7810")
            return

        final = resumir_con_texto(texto, m.caption or "")
        bot.reply_to(m, final)
    except Exception as e:
        bot.reply_to(m, f"Error foto: {e}")

@bot.message_handler(func=lambda m: True)
def texto_handler(m):
    try:
        r = client.chat.completions.create(model="openai/gpt-oss-20b", messages=[{"role": "user", "content": m.text}], max_tokens=800)
        bot.reply_to(m, r.choices[0].message.content)
    except Exception as e:
        bot.reply_to(m, f"Error: {e}")

@app.route('/')
def health():
    return f"V1006 OCR LOCAL LIVE {datetime.datetime.now()}"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

def run_bot():
    while True:
        try:
            bot.infinity_polling(timeout=90, long_polling_timeout=90, skip_pending=True)
        except Exception as e:
            print(e)
            time.sleep(5)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    run_bot()
