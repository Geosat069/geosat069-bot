import os, base64, json, logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from openai import OpenAI

logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("TELEGRAM_TOKEN")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Memoria simple de auto-aprendizaje
MEMORIA_FILE = "memoria_geosat.json"
def cargar_memoria():
    try:
        with open(MEMORIA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"correcciones": [], "estilo": "Vendedor agresivo, cercano, parcero, con emojis, para WhatsApp, Geosat"}

def guardar_correccion(texto_usuario):
    mem = cargar_memoria()
    mem["correcciones"].append(texto_usuario)
    # Solo guarda las ultimas 20 para no saturar
    mem["correcciones"] = mem["correcciones"][-20:]
    with open(MEMORIA_FILE, "w", encoding="utf-8") as f:
        json.dump(mem, f, ensure_ascii=False, indent=2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔥 **GEOSAT V1020 SUPER IA** 🔥\n"
        "Ya soy inteligente de verdad.\n\n"
        "Mándame cualquier afiche (aunque esté borroso) y te armo el mensaje vendedor perfecto.\n"
        "Si no te gusta como quedó, solo dime: *'corrígelo así:...'* y aprendo para siempre."
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🧠 V1020 analizando con visión IA... dame 10 seg.")
    try:
        photo = await update.message.photo[-1].get_file()
        await photo.download_to_drive("afiche.jpg")

        with open("afiche.jpg", "rb") as img_file:
            b64 = base64.b64encode(img_file.read()).decode('utf-8')

        memoria = cargar_memoria()

        prompt = f"""
        Eres GEOSAT V1020, la IA vendedora más avanzada de Geosat.
        Tu estilo es: {memoria['estilo']}
        Tus ultimas correcciones aprendidas del jefe son: {memoria['correcciones']}

        TAREA:
        1. Lee TODO lo que dice el afiche de la imagen (curso, instructor, fechas, certificado, organizador).
        2. No inventes precios si no están, di "Inversión por interno".
        3. Genera un mensaje de venta para WhatsApp, corto, potente, con emojis, que venda.
        4. Estructura: Gancho + Nombre del curso + Instructor + Modalidad + Certificación + CTA de WhatsApp + Hashtags.
        5. Si es de construcción/geotecnia/geología, usa palabras de ingenieros.

        Devuelve SOLO el mensaje final listo para copiar y pegar.
        """

        response = client.chat.completions.create(
            model="gpt-4o-mini", # Vision super barato y potente
            messages=[
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                ]}
            ],
            max_tokens=800
        )

        mensaje = response.choices[0].message.content
        await update.message.reply_text(mensaje)

    except Exception as e:
        logging.error(e)
        await update.message.reply_text(f"Uy parcero, error en mi cerebro: {e}\nVerifica que pusiste OPENAI_API_KEY en Render.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    # Auto-aprendizaje
    if "corrige" in texto.lower() or "corrigelo" in texto.lower() or "aprende" in texto.lower():
        guardar_correccion(texto)
        await update.message.reply_text(f"✅ ¡Aprendido parcero! Guardé: '{texto}'\nLa próxima vez lo haré así. Ya estoy más inteligente.")
    else:
        await update.message.reply_text("Mándame el afiche en foto, o si quieres corregirme escribe: 'corrige, hazlo más corto' por ejemplo.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("GEOSAT V1020 SUPER IA INICIADA")
    app.run_polling()
