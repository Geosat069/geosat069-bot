import os, threading, traceback, requests, glob, re, json, datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

try: import fitz
except: fitz = None

BOT_TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY)
app = Flask(__name__)
os.makedirs("docs", exist_ok=True)

@app.route('/')
def home(): return "Geosat V21 FINAL - FUNCIONANDO"

def run_web():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

# 4. Lee tus PDFs de GitHub /docs
def cargar_pdfs():
    txt = ""
    for pdf in glob.glob("docs/*.pdf")[:8]:
        try:
            if fitz:
                doc = fitz.open(pdf)
                for p in doc[:8]:
                    txt += f"\n---{os.path.basename(pdf)}---\n" + p.get_text()[:3000]
        except: pass
    return txt[:12000]

# 5. Aprende de la red (info actual)
def buscar_web(query):
    try:
        url = f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1"
        r = requests.get(url, timeout=8).json()
        return r.get("AbstractText","")[:2000]
    except:
        return ""

# 3. SIN LIMITE DE AÑO - Desde 1940 hasta hoy (lo máximo de ERA5)
def expandir_anos(texto):
    low = texto.lower()
    actual = datetime.datetime.now().year
    m = re.search(r'desde\s+(\d{4}).*?(?:hasta|al|a)\s+(\d{4}|actual|ahora|hoy)', low)
    if m:
        ini = int(m.group(1))
        fin_str = m.group(2)
        fin = actual if not fin_str.isdigit() else int(fin_str)
        return list(range(ini, fin+1))
    m2 = re.search(r'(\d{4})\s*[-–]\s*(\d{4}|actual)', low)
    if m2:
        ini = int(m2.group(1))
        fin = actual if not m2.group(2).isdigit() else int(m2.group(2))
        return list(range(ini, fin+1))
    m3 = re.search(r'desde\s+(\d{4})', low)
    if m3:
        return list(range(int(m3.group(1)), actual+1))

    anos = [int(y) for y in re.findall(r'\b(19\d{2}|20\d{2})\b', texto)]
    if anos and "actual" in low and len(anos)==1:
        return list(range(anos[0], actual+1))
    return anos

def get_datos_clima(lat, lon, years):
    if not years: return {}
    ini = max(min(years), 1940)
    fin = max(years)
    try:
        url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={ini}-01-01&end_date={fin}-12-31&daily=temperature_2m_max&timezone=auto"
        j = requests.get(url, timeout=30).json()['daily']
        por_ano = {}
        for i, fecha in enumerate(j['time']):
            y = int(fecha[:4])
            if y >=
