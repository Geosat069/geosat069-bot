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
def home(): return "Geosat V20 LIBRE TOTAL OK"

def run_web():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

# 4. ALIMENTAR CON PDFs - Tu carpeta de GitHub
def cargar_pdfs():
    txt = ""
    for pdf in glob.glob("docs/*.pdf")[:8]:
        try:
            if fitz:
                doc = fitz.open(pdf)
                for p in doc[:8]:
                    txt += f"\n---{pdf}---\n" + p.get_text()[:3000]
        except: pass
    return txt[:12000]

# 5. APRENDE SOLA DE LA RED - Busqueda actual
def buscar_web(query):
    try:
        # DuckDuckGo + Wikipedia como fuente actual
        url = f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1"
        r = requests.get(url, timeout=8).json()
        info = r.get("AbstractText","")[:2000]
        return info
    except:
        return ""

# 3. SIN LIMITE DE AÑO - Cualquier año desde 1940 hasta hoy
def expandir_anos(texto):
    low = texto.lower(); actual = datetime.datetime.now().year
    m = re.search(r'desde\s+(\d{4}).*?(?:hasta|al|a)\s+(\d{4}|actual|ahora|hoy)', low)
    if m:
        ini = int(m.group(1))
        fin_str = m.group(2)
        fin = actual if not fin_str.isdigit() else int(fin_str)
        return list(range(ini, fin+1))
    m2 = re.search(r'(\d{4})\s*-\s*(\d{4}|actual)', low)
    if m2:
        ini = int(m2.group(1)); fin = actual if not m2.group(2).isdigit() else int(m2.group(2))
        return list(range(ini, fin+1))
    m3 = re.search(r'desde\s+(\d{4})', low)
    if m3:
        return list(range(int(m3.group(1)), actual+1))
    anos = [int(y) for y in re.findall(r'\b(19\d{2}|20\d{2})\b', texto)]
    if anos and "actual" in low and len(anos)==1:
        return list(range(anos[0], actual+1))
    return anos

def get_datos_clima_ilimitado(lat, lon, years):
    if not years: return {}
    ini = max(min(years), 1940); fin = max(years)
    try:
        url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={ini}-01-01&end_date={fin}-12-31&daily=temperature_2m_max,precipitation_sum&timezone=auto"
        j = requests.get(url, timeout=30).json()['daily']
        por_ano = {}
        for i, fecha in enumerate(j['time']):
            y = int(fecha[:4])
            por_ano.setdefault(y, []).append(j['temperature_2m_max'][i] or 0)
        return {y: round(sum(v)/len(v),1) for y,v in por_ano.items() if v}
    except:
        return {}

def geocode(q):
    if len(q.strip())<3: q="Cali, Valle del Cauca"
    try:
        url=f"https://nominatim.openstreetmap.org/search?q={q}&format=json&limit=1"
        r=requests.get(url,headers={"User-Agent":"Geosat069"},timeout=10).json()
        if r: return r[0]['display_name'], float(r[0]['lat']), float(r[0]['lon'])
    except: pass
    return "Cali, Valle del Cauca, Colombia", 3.4419, -76.5287

# 2. IMAGENES O GRAFICAS DE LO QUE SEA
def crear_visual(spec, lat, lon, path="/tmp/geosat.png"):
    try:
        # Mapa
        if spec.get("type") == "map":
            url = f"https://staticmap.openstreetmap.de/staticmap.php?center={lat},{lon}&zoom=13&size=900x600&markers={lat},{lon},red"
            open(path,'wb').write(requests.get(url,timeout=15).content)
            return path

        # Grafica de cualquier tema
        plt.figure(figsize=(11,6))
        labels = spec.get("labels", [])
        for ds in spec.get("datasets", []):
            data = ds["data"]
            label = ds["label"]
            if spec.get("type") == "line":
                plt.plot(labels, data, marker='o', linewidth=2.5, label=label)
            elif spec.get("type") == "bar":
                plt.bar(labels, data, alpha=0.8, label=label)
            elif spec.get("type") == "pie":
                plt.pie(data, labels=labels, autopct='%1.1f%%')
                plt.legend()
                plt.savefig(path, dpi=220); plt.close(); return path

        plt.title(spec.get("title","Visual"), fontweight='bold')
        plt.xticks(rotation=30, fontsize=8); plt.grid(alpha=0.2)
        plt.legend(); plt.tight_layout(); plt.savefig(path, dpi=230); plt.close()
        return path
    except Exception as e:
        print(e); return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Soy GEOSAT V20 LIBRE. Pregúntame de lo que sea, con cualquier año, y pídeme 'con gráfica/imagen/mapa' si la quieres. Ya leo tus PDFs de /docs")

# 5. APRENDE DE MATERIAL QUE LE MANDES (PDFs por Telegram)
async def handle_docs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        file = await update.message.document.get_file()
        fname = update.message.document.file_name
        fpath = f"docs/{fname}"
        await file.download_to_drive(fpath)
        await update.message.reply_text(f"Aprendido: Guardé {fname} en mi memoria. Ya lo usaré en las respuestas.")
    except Exception as e:
        await update.message.reply_text(f"Error guardando PDF: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    low = texto.lower()
    try:
        # Hola simple
        if low.strip() in ["hola","buenas","hello","hi","ola"]:
            await update.message.reply_text("¡Hola! Soy GEOSAT JARVIS V20. Libre total. Pregúntame de cualquier tema, de cualquier año (desde 1940 hasta hoy), y si quieres visual dime 'con gráfica', 'con imagen' o 'con mapa'.")
            return

        quiere_visual = any(k in low for k in ["grafic","imagen","foto","mapa","visual","plot","chart","dibuja","muestrame","muéstrame"])
        years = expandir_anos(texto)

        # Detectar lugar si hay
        lugar_q = re.sub(r'19\d{2}|20\d{2}|desde|hasta|actual|grafica|gráfica|imagen|mapa|con|dame|años|temperatura|precipitacion','', low).strip()
        nombre, lat, lon = geocode(lugar_q)

        datos_clima = get_datos_clima_ilimitado(lat, lon, years) if years else {}
        pdfs = cargar_pdfs()
        web_info = buscar_web(texto[:100]) if len(texto)>10 else ""

        # 1. RESPONDE CUALQUIER PREGUNTA SIN IMPORTAR EL TEMA
        prompt = f"""
        Eres GEOSAT JARVIS V20 LIBRE TOTAL.
        MISION:
        1. Responder CUALQUIER pregunta sin importar el tema (topografia, QGIS, historia, programacion, medicina, lo que el usuario quiera).
        2. Sin limite de año: si te piden desde 1960, desde 1990, desde cualquier año, tienes datos ERA5 desde 1940 hasta {datetime.datetime.now().year}. PREFIERE siempre la informacion mas actual (2026).
        3. NUNCA pidas datos al usuario. Tu los buscas. Ya tienes datos de clima: {datos_clima}
        4. Usa tus PDFs como memoria principal: {pdfs[:10000]}
        5. Info actual de la web: {web_info[:2000]}
        6. Lugar: {nombre} ({lat},{lon}) - Es CALI si es 3.44, -76.5, no Bogota.

        REGLA VISUAL (2):
        - quiere_visual = {quiere_visual}
        - Si quiere_visual es False, responde SOLO TEXTO.
        - Si quiere_visual es True, al final OBLIGATORIO pon en linea aparte:
        CHART_JSON: {{"type":"line o bar o pie o map", "title":"Titulo descriptivo", "labels":["2000","2001",...], "datasets":[{{"label":"Nombre variable", "data":[...]}}]}}
        Si te pide mapa, usa type:"map". Si te pide cualquier grafica, inventa labels y data basada en datos reales o logica.

        Pregunta del usuario: {texto}
        """

        comp = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[{"role":"system","content":prompt}],
            temperature=0.85,
            max_tokens=2200
        )
        resp = comp.choices[0].message.content

        # Procesar visual
        m = re.search(r'CHART_JSON:\s*(\{.*\})', resp, re.DOTALL)
        if m and quiere_visual:
            try:
                spec = json.loads(m.group(1))
                resp_text = resp.replace(m.group(0),"").strip()
                img_path = crear_visual(spec, lat, lon)
                if img_path:
                    await update.message.reply_photo(photo=open(img_path,'rb'), caption=resp_text[:1024])
                    return
            except Exception as e:
                print("Error visual", e)

        await update.message.reply_text(resp.replace("CHART_JSON:","").strip()[:4000])

    except Exception as e:
        traceback.print_exc()
        await update.message.reply_text(f"Error: {e}")

def run_bot():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_docs)) # 5. Aprende de PDFs que le mandes
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    threading.Thread(target=run_web, daemon=True).start()
    run_bot()
