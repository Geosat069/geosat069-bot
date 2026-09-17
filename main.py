import os, threading, traceback, requests, glob, re, json, datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

try:
    import fitz
except:
    fitz = None

BOT_TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY)
app = Flask(__name__)
os.makedirs("docs", exist_ok=True)

@app.route('/')
def home():
    return "Geosat V21.1 OK - Deploy fixed"

def run_web():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

def cargar_pdfs():
    txt = ""
    for pdf in glob.glob("docs/*.pdf")[:8]:
        try:
            if fitz:
                doc = fitz.open(pdf)
                for p in doc[:8]:
                    txt += f"\n---{os.path.basename(pdf)}---\n" + p.get_text()[:3000]
        except:
            pass
    return txt[:12000]

def buscar_web(query):
    try:
        url = f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1"
        r = requests.get(url, timeout=8).json()
        return r.get("AbstractText","")[:2000]
    except:
        return ""

def expandir_anos(texto):
    low = texto.lower()
    actual = datetime.datetime.now().year
    m = re.search(r'desde\s+(\d{4}).*?(?:hasta|al|a)\s+(\d{4}|actual|ahora|hoy)', low)
    if m:
        ini = int(m.group(1))
        fin_str = m.group(2)
        fin = actual if not fin_str.isdigit() else int(fin_str)
        return list(range(ini, fin+1))
    m2 = re.search(r'(\d{4})\s*[-](\d{4}|actual)', low)
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
    if not years:
        return {}
    ini = max(min(years), 1940)
    fin = max(years)
    try:
        url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={ini}-01-01&end_date={fin}-12-31&daily=temperature_2m_max&timezone=auto"
        j = requests.get(url, timeout=30).json()
        daily = j.get('daily', {})
        times = daily.get('time', [])
        temps = daily.get('temperature_2m_max', [])
        por_ano = {}
        for i in range(len(times)):
            y = int(times[i][:4])
            v = temps[i]
            if v is None:
                continue
            por_ano.setdefault(y, []).append(v)
        res = {}
        for y, vals in por_ano.items():
            if vals:
                res[y] = round(sum(vals)/len(vals), 1)
        return res
    except Exception as e:
        print(f"Error clima: {e}")
        return {}

def geocode(q):
    if len(q.strip()) < 3:
        q = "Cali, Valle del Cauca"
    try:
        url = f"https://nominatim.openstreetmap.org/search?q={q}&format=json&limit=1"
        r = requests.get(url, headers={"User-Agent":"Geosat069"}, timeout=10).json()
        if r:
            return r[0]['display_name'], float(r[0]['lat']), float(r[0]['lon'])
    except:
        pass
    return "Cali, Valle del Cauca, Colombia", 3.4419, -76.5287

def crear_visual(spec, lat, lon, path="/tmp/geosat.png"):
    try:
        if spec.get("type") == "map":
            url = f"https://staticmap.openstreetmap.de/staticmap.php?center={lat},{lon}&zoom=13&size=900x700&markers={lat},{lon},red"
            open(path,'wb').write(requests.get(url,timeout=15).content)
            return path
        plt.figure(figsize=(13,6.5))
        labels = spec.get("labels", [])
        for ds in spec.get("datasets", []):
            data = ds.get("data", [])
            label = ds.get("label","Temp C")
            if spec.get("type") == "bar":
                plt.bar(labels, data, alpha=0.85, label=label, color='#0a58ca')
            else:
                plt.plot(labels, data, marker='o', linewidth=2.8, label=label, color='#0a58ca')
        plt.title(spec.get("title","Temperatura media anual de Cali (2000-2026)"), fontweight='bold', fontsize=13)
        plt.xlabel("Ano")
        plt.ylabel("C")
        plt.xticks(rotation=45, fontsize=9)
        plt.grid(True, alpha=0.25, linestyle='--')
        plt.legend()
        plt.tight_layout()
        plt.savefig(path, dpi=300)
        plt.close()
        return path
    except Exception as e:
        print(f"Error visual: {e} {traceback.format_exc()}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Soy GEOSAT V21.1 listo.")

async def handle_docs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        file = await update.message.document.get_file()
        fname = update.message.document.file_name
        await file.download_to_drive(f"docs/{fname}")
        await update.message.reply_text(f"Aprendido: {fname} guardado.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    low = texto.lower()
    try:
        if low.strip() in ["hola","buenas","hello","hi","ola","hey"]:
            await update.message.reply_text("Hola! Soy GEOSAT V21.1. Sin limite de año. Di 'con grafica / con imagen / con mapa'")
            return
        quiere_visual = any(k in low for k in ["grafic","imagen","foto","mapa","visual","plot","chart","dibuja","muestrame"])
        years = expandir_anos(texto)
        lugar_q = re.sub(r'19\d{2}|20\d{2}|desde|hasta|actual|grafica|imagen|mapa|con|dame|temperatura|anos|ano|media|anual','', low).strip()
        nombre, lat, lon = geocode(lugar_q)
        datos_clima = get_datos_clima(lat, lon, years) if years else {}
        pdfs = cargar_pdfs()
        web_info = buscar_web(texto[:120]) if len(texto)>10 else ""
        prompt = f"""Eres GEOSAT V21.1 LIBRE TOTAL. Responde cualquier tema. Sin limite de año desde 1940 hasta 2026. Datos reales: {datos_clima} Lugar: {nombre} ({lat},{lon}) PDFs: {pdfs[:9000]} Web: {web_info[:1500]} quiere_visual={quiere_visual} Si quiere_visual True al final agrega: CHART_JSON: {{"type":"line","title":"Temperatura media anual de Cali (2000-2026)","labels":["2000",...],"datasets":[{{"label":"Temp C","data":[...]}}]}} Pregunta: {texto}"""
        comp = client.chat.completions.create(model="openai/gpt-oss-20b", messages=[{"role":"system","content":prompt}], temperature=0.8, max_tokens=2200)
        resp = comp.choices[0].message.content
        json_match = re.search(r'CHART_JSON:\s*(\{.*\})', resp, re.DOTALL)
        if not json_match:
            json_match = re.search(r'(\{\s*"type"\s*:\s*".*?"\s*,.*\})', resp, re.DOTALL)
        if json_match and quiere_visual:
            try:
                raw = json_match.group(1).strip()
                raw = re.sub(r'```json|```','', raw).strip()
                raw = raw.replace("'",'"')
                spec = json.loads(raw)
                resp_clean = re.sub(r'CHART_JSON:\s*\{.*\}\s*', '', resp, flags=re.DOTALL)
                resp_clean = re.sub(r'```json.*?```', '', resp_clean, flags=re.DOTALL)
                resp_clean = re.sub(r'\{\s*"type".*\}\s*\}\s*\}', '', resp_clean, flags=re.DOTALL).strip()
                img_path = crear_visual(spec, lat, lon)
                if img_path:
                    await update.message.reply_photo(photo=open(img_path,'rb'), caption=resp_clean[:1024])
                    return
            except Exception as e:
                print(f"Error visual parse: {e}")
        resp_final = re.sub(r'CHART_JSON:.*', '', resp, flags=re.DOTALL).strip()
        await update.message.reply_text(resp_final[:4000])
    except Exception as e:
