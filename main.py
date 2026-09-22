import os, re, logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from PIL import Image
import pytesseract

logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("TELEGRAM_TOKEN")

def generar_mensaje_vendedor(texto_ocr):
    t = texto_ocr.upper()
    curso = "GEOLOGÍA APLICADA, CARACTERIZACIÓN GEOTÉCNICA Y GEOMECÁNICA AVANZADA DE SUELOS"
    if "GEOLOGIA" in t:
        curso = "Geología Aplicada, Caracterización Geotécnica y Geomecánica Avanzada de Suelos"
    
    instructor = "LUIS FELIPE MEDINA MOLINA - Magíster en Ciencias de la Ingeniería, Ing. Civil Geólogo"
    
    return f"""🔥 *CURSO ESPECIALIZADO 100% VIRTUAL* 🔥

📚 *{curso}*

👨‍🏫 *Instructor:* {instructor}
🎓 *Certificado:* APGEO + Colegio de Ingenieros del Perú
💻 *Modalidad:* 100% Virtual vía ZOOM
🏢 *Organiza:* Gesconvial

¡INSCRÍBETE HOY! Cupos limitados.

📲 Escríbeme para info de fechas, inversión y link de inscripción.

#Geotecnia #Geologia #Suelos #CursoVirtual
"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("¡Hola! Soy Geosat V1012.2 VENDEDOR 🤖\nMándame el afiche y te armo el mensaje listo para WhatsApp, sin tablas.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Leyendo afiche...")
    try:
        file = await update.message.photo[-1].get_file()
        await file.download_to_drive("afiche.jpg")
        img = Image.open("afiche.jpg")
        texto = pytesseract.image_to_string(img, lang='spa+eng')
        msg = generar_mensaje_vendedor(texto)
        await update.message.reply_text(msg, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    print("Geosat V1012.2 VENDEDOR iniciado...")
    app.run_polling()
