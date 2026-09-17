import os, threading, traceback, requests, glob, re, json, datetime, time
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
    return "Geosat V20.3 FIX JSON - OK"

def run_web():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

def cargar_pdfs():
    txt = ""
    for pdf in glob.glob("docs/*.pdf")[:8]:
        try:
            if fitz:
                doc = fitz.open(pdf)
                for p in doc[:8]:
                    txt += p.get_text()[:3000]
        except:
            continue
    return txt[:12000]

def expandir_anos(texto):
    low = texto.lower()
    actual = datetime.datetime.now().year
    m = re.search(r'desde\s+(\d{4}).*?(?:hasta|al|a)\s+(\d{4}|actual|hoy|ahora)', low)
    if m:
        ini = int(m.group(1))
        fin_str = m.group(2)
        fin = actual if not fin_str.isdigit() else int(fin_str)
        return list(range(ini, fin+1))
    m2 = re.search(r'(\d{4})\s*-\s*(\d{4}|actual)', low)
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
            try:
                y = int(times[i][:4])
                v = temps[i]
                if v is None: continue
                por_ano.setdefault(y, []).append(v)
            except:
                continue
        return {y: round(sum(v)/len(v),1) for y,v in por_ano.items() if v}
    except:
        return {}

def geocode(q):
    if len(q.strip()) < 3:
        q = "Cali"
    try:
        r = requests.get(f"https://nominatim.openstreetmap.org/search?q={q}&format=json&limit=1", headers={"User-Agent":"Geosat069"}, timeout=10).json()
        if r:
            return r[0]['display_name'], float(r[0]['lat']), float(r[0]['lon'])
    except:
        pass
    return "Cali, Colombia", 3.4419, -76.5287

def crear_visual(spec, path="/tmp/geosat.png"):
    try:
        plt.close('all')
        plt.figure(figsize=(12,6))
        labels = spec.get("labels", [])
        # convierte 2000 -> "2000"
        labels = [str(l) for l in labels]
        for ds in spec.get("datasets", []):
            data = ds.get("data", [])
            label = ds.get("label", "Temp C")
            plt.plot(labels, data, marker='o', linewidth=2.6, label=label, color='#0a58ca')
        plt.title(spec.get("title","Temperatura media anual - Cali"), fontweight='bold', fontsize=12)
        plt.xlabel("Año")
        plt.ylabel("°C")
        plt.xticks(rotation=45, fontsize=8)
        plt.grid(True, alpha=0.3, linestyle='--')
        plt.legend()
        plt.tight_layout()
        plt.savefig(path, dpi=240, format='png')
        plt.close('all')
        time.sleep(0.6)
        return path
    except Exception as e:
        print(f"Error visual: {e} {traceback.format_exc()}")
        plt.close('all')
        return None

async def handle_docs(update, context):
    try:
        file = await update.message.document.get_file()
        fname = update.message.document.file_name
        await file.download_to_drive(f"docs/{fname}")
        await update.message.reply_text(f"Guardado: {fname}. Ya lo uso como memoria.")
    except Exception as e:
        await update.message.reply_text(f"Error guardando: {e}")

async def handle_message(update, context):
    texto = update.message.text
    if not texto:
        return
    low = texto.lower()
    try:
        if low.strip() in ["hola","buenas","hi","hey"]:
            await update.message.reply_text("Hola! Soy GEOSAT V20.3. Dime 'temperatura de Cali desde 2000 hasta actual con grafica' y te mando la foto, no el JSON.")
            return

        quiere_visual = any(k in low for k in ["grafic","imagen","foto","visual","mapa","chart","plot"])
        years = expandir_anos(texto)
        lugar_q = re.sub(r'desde|hasta|actual|grafica|gráfica|imagen|mapa|con|una|dame|temperatura|año|anos|2000|20\d{2}|19\d{2}', '', low).strip()
        nombre, lat, lon = geocode(lugar_q if lugar_q else "Cali")
        datos = get_datos_clima(lat, lon, years) if years else {}
        pdfs = cargar_pdfs()

        prompt = f"""
        Eres GEOSAT V20.3. Responde TODO tema.
        Lugar: {nombre} lat {lat} lon {lon}
        Datos clima reales: {datos}
        Memoria PDFs: {pdfs[:8000]}
        Año actual: 2026
        Pregunta: {texto}
        quiere_visual={quiere_visual}
        Si quiere_visual es True, al FINAL agrega OBLIGATORIO:
        CHART_JSON: {{"type":"line","title":"Temp Cali 2000-2026","labels":[2000,2001,2002,2003,2004,2005,2006,2007,2008,2009,2010,2011,2012,2013,2014,2015,2016,2017,2018,2019,2020,2021,2022,2023,2024,2025,2026],"datasets":[{{"label":"Temp C","data":[...]}}]}}
        Usa los datos reales.
        """

        comp = client.chat.completions.create(model="openai/gpt-oss-20b", messages=[{"role":"system","content":prompt}], temperature=0.7, max_tokens=2500)
        resp = comp.choices[0].message.content

        # --- FIX DEL BUG DE TU CAPTURA ---
        # Tu bot mandaba el JSON en texto. Ahora lo interceptamos
        jm = re.search(r'CHART_JSON:\s*(\{.*\})', resp, re.DOTALL)
        if not jm:
            jm = re.search(r'```json\s*(\{.*?\})\s*```', resp, re.DOTALL)
        if not jm:
            jm = re.search(r'(\{\s*"type"\s*:\s*"line".*?\}\s*\]\s*\})', resp, re.DOTALL)

        if jm and quiere_visual:
            try:
                raw = jm.group(1).strip()
                raw = re.sub(r'```json|```', '', raw).strip()
                raw = raw.replace("'", '"')
                spec = json.loads(raw)

                # Limpia TODO el JSON del texto para que NO salga como en tu foto
                texto_limpio = resp
                texto_limpio = re.sub(r'CHART_JSON:\s*\{.*\}', '', texto_limpio, flags=re.DOTALL)
                texto_limpio = re.sub(r'```json.*?```', '', texto_limpio, flags=re.DOTALL)
                texto_limpio = texto_limpio.strip()
                if len(texto_limpio) < 10:
                    texto_limpio = f"Evolución de la temperatura media anual en {nombre} {min(years) if years else ''}-{max(years) if years else 2026} (ERA5)"

                img_path = crear_visual(spec, path="/tmp/geosat.png")
                if img_path and os.path.exists(img_path):
                    with open(img_path, 'rb') as f:
                        await update.message.reply_photo(photo=f.read(), caption=texto_limpio[:1000])
                    return
            except Exception as e:
                print(f"Parse visual error: {e} {traceback.format_exc()}")

        # Si no pide visual, manda texto sin JSON
        final = re.sub(r'CHART_JSON:.*', '', resp, flags=re.DOTALL)
        final = re.sub(r'```json.*?```', '', final, flags=re.DOTALL).strip()
        await update.message.reply_text(final[:4000])

    except Exception as e:
        traceback.print_exc()
        await update.message.reply_text(f"Error: {e}")

def run_bot():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(MessageHandler(filters.Document.ALL, handle_docs))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    threading.Thread(target=run_web, daemon=True).start()
    run_bot()
