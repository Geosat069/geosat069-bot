# GEOSAT V1012.1 FIX - SIN ERROR DE COMILLAS
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
                t = pytesseract.image_to_string(img
