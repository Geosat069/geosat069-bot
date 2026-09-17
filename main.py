import os, threading, traceback, requests, glob, re, json, datetime, time, urllib.parse
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import Flask
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from groq import Groq

try: import fitz
except: fitz = None

BOT_TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY)

app = Flask(__name__)
os.makedirs("docs", exist_ok=True)
os.makedirs("/tmp/imagenes", exist_ok=True)

@app.route('/')
def home(): return "Geosat V22 - 6 requisitos OK"

def run_web():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

# --- 4. Lee tus PDFs de GitHub /docs ---
def cargar_pdfs():
    txt=""
    for pdf in glob.glob("docs/*.pdf")[:8]:
        try:
            if fitz:
                doc=fitz.open(pdf)
                for p in doc[:10]:
                    t=p.get_text()
                    t=re.sub(r'```json.*?```','',t,flags=re.DOTALL)
                    txt+=f"\n[{os.path.basename(pdf)}] {t[:3000]}"
        except: continue
    return txt[:15000]

# --- 6. Motor de auto-alimentación IA (DuckDuckGo + Wikipedia) ---
def buscar_ia_web(query):
    info=""
    try:
        # DuckDuckGo Instant
        r=requests.get(f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1&skip_disambig=1", timeout=10).json()
        if r.get("AbstractText"):
            info+=r["AbstractText"][:2000]+"\n"
        # Wikipedia
        try:
            w=requests.get(f"https://es.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(query[:60])}", timeout=8).json()
            if w.get("extract"):
                info+=w["extract"][:2000]
        except: pass
    except: pass
    return info[:4000]

# --- 3. Sin limite de año, desde 1940 hasta hoy ---
def expandir_anos(texto):
    low=texto.lower()
    actual=datetime.datetime.now().year
    m=re.search(r'desde\s+(\d{4}).*?(?:hasta|al|a)\s+(\d{4}|actual|hoy|ahora)', low)
    if m:
        ini=int(m.group(1)); fin=actual if not m.group(2).isdigit() else int(m.group(2))
        return list(range(max(ini,1940), fin+1))
    m2=re.search(r'(\d{4})\s*-\s*(\d{4}|actual)', low)
    if m2:
        ini=int(m2.group(1)); fin=actual if not m2.group(2).isdigit() else int(m2.group(2))
        return list(range(max(ini,1940), fin+1))
    m3=re.search(r'desde\s+(\d{4})', low)
    if m3: return list(range(max(int(m3.group(1)),1940), actual+1))
    anos=[int(y) for y in re.findall(r'\b(19\d{2}|20\d{2})\b', texto)]
    if anos and "actual" in low and len(anos)==1:
        return list(range(max(anos[0],1940), actual+1))
    return anos

def get_datos_clima(lat, lon, years):
    if not years: return {}
    ini=max(min(years),1940); fin=max(years)
    try:
        url=f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={ini}-01-01&end_date={fin}-12-31&daily=temperature_2m_max&timezone=auto"
        j=requests.get(url,timeout=25).json()['daily']
        por_ano={}
        for i in range(len(j['time'])):
            try:
                y=int(j['time'][i][:4]); v=j['temperature_2m_max'][i]
                if v is None: continue
                por_ano.setdefault(y,[]).append(v)
            except: continue
        return {y: round(sum(v)/len(v),1) for y,v in por_ano.items() if v}
    except: return {}

def geocode(q):
    if len(q.strip())<3: q="Cali"
    try:
        r=requests.get(f"https://nominatim.openstreetmap.org/search?q={q}&format=json&limit=1", headers={"User-Agent":"GeosatV22"}, timeout=10).json()
        if r: return r[0]['display_name'], float(r[0]['lat']), float(r[0]['lon'])
    except: pass
    return "Cali, Colombia", 3.4419, -76.5287

# --- 2. Genera IMAGENES o GRAFICAS de lo que sea ---
def crear_grafica_desde_datos(datos_dict, titulo, path="/tmp/geosat.png"):
    try:
        plt.close('all')
        years=sorted(datos_dict.keys())
        vals=[datos_dict[y] for y in years]
        plt.figure(figsize=(13,6.5))
        plt.plot([str(y) for y in years], vals, marker='o', linewidth=2.8, color='#0a58ca')
        plt.title(titulo, fontweight='bold', fontsize=12)
        plt.xlabel("Año"); plt.ylabel("Valor")
        plt.xticks(rotation=45, fontsize=8)
        plt.grid
