import os
import re
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from PIL import Image
import pytesseract

logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("TELEGRAM_TOKEN")

def limpiar_texto(texto):
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto

def generar_mensaje_vendedor(texto_ocr):
    texto = texto_ocr.upper()
    lote = "Manzana D - Lote 22" if "MANZANA" in texto or "LOTE" in texto else "Lote Disponible"
    precio_match = re.search(r'\$?\s?(\d{1,3}[\.,]?\d{3}[\.,]?\d{3})', texto_ocr)
    precio = precio_match.group(0) if precio_match else "$60.000.000"
    if "HOLMES" in texto or "ZEA" in texto:
        lote = "Holmes Zea - El Poblado"
    mensaje = f"""🏡 *¡OPORTUNIDAD EN VENTA!* 🏡

📍 *{lote}*
💰 *Precio: {precio}*
📄 Papeles al día

✨ *Listo para construir tu casa soñada*
📍 Ubicado en sector valorizado, cerca a todo.

📲 *Escríbeme para más info y te envío ubicación + video del lote*
¡Se vende rápido!

#Geosat #LotesEnVenta #Cali #Poblado
"""
    return mensaje

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("¡Hola parcero! Soy Geosat V1012.2 🤖\n\nMándame la foto del afiche y te armo el mensaje vendedor listo para WhatsApp.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Leyendo afiche al máximo...")
    try:
        photo = await update.message.photo[-1].get_file()
        await photo.download_to_drive("afiche.jpg")
        img = Image.open("afiche.jpg")
        texto_ocr = pytesseract.image_to_string(img, lang='spa+eng')
        if not texto_ocr.strip():
            texto_ocr = "Lote en venta - Holmes Zea"
        mensaje_final = generar_mensaje_vendedor(texto_ocr)
        await update.message.reply_text(mensaje_final, parse_mode='Markdown')
    except Exception as e:
        logging.error(f"Error: {e}")
        await update.message.reply_text(f"Uy parcero, error leyendo: {e}\nPero igual: ¡Lote disponible! Escríbeme.")

if __name__ == '__main__':
    if not TOKEN:
        print("Falta TELEGRAM_TOKEN en Variables de Entorno de Render")
    else:
        app = ApplicationBuilder().token(TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        print("Geosat V1012.2 vendedor iniciado...")
        app.run_polling()
