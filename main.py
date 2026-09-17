import os, threading, traceback, requests, glob, re, json, datetime, time, urllib.parse
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import Flask
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
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
    return "Geosat V22 FIX - OK"

def run_web():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

def cargar_pdfs():
    txt = ""
    for pdf in glob.glob("docs/*.pdf")[:8]:
        try:
            if fitz:
                doc = fitz.open(pdf)
                for p in doc[:10]:
                    txt += p.get_text()[:3000]
        except Exception:
            continue
    return txt[:12000]

def buscar_ia_web(query):
    info = ""
    try:
        url = "https://api.duckduckgo.com/?q=%s&format=json&no_html=1" % urllib.parse.quote(query)
        r = requests.get(url, timeout=10).json()
        if r.get("AbstractText"):
            info += r.get("AbstractText")[:2000]
    except Exception:
        info = ""
    return info[:3000]

def expandir_anos(texto):
    low = texto.lower()
    actual = datetime.datetime.now().year
    m = re.search(r'desde\s+(\d{4}).*?(?:hasta|al|a)\s+(\d{4}|actual)', low)
    if m:
        ini = int(m.group(1))
        fin_str = m.group(2)
        fin = actual if not fin_str.isdigit() else int(fin_str)
        return list(range(max(ini,1940), fin+1))
    anos = [int(y) for y in re.findall(r'\b(19\d{2}|20\d{2})\b', texto)]
    if anos and "actual" in low and len(anos)==1:
        return list(range(max(anos[0],1940), actual+1))
    return anos

def get_datos_clima(lat, lon, years):
    if not years:
        return {}
    ini = max(min(years), 1940)
    fin = max(years)
    try:
        url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={ini}-01-01&end_date={fin}-12-31&daily=temperature_2m_max&timezone=auto"
        j = requests.get(url, timeout=25).json()
        daily = j.get('daily', {})
        times = daily.get('time', [])
        temps = daily.get('temperature_2m_max', [])
        por_ano = {}
        for i in range(len(times)):
            try:
                y = int(times[i][:4])
                v = temps[i]
                if v is None:
                    continue
                por_ano.setdefault(y, []).append(v)
            except Exception:
                continue
        return {y: round(sum(v)/len(v),1) for y,v in por_ano.items() if v}
    except Exception:
        return {}

def geocode(q):
    if len(q.strip()) < 3:
        q = "Cali"
    try:
        r = requests.get(f"https://nominatim.openstreetmap.org/search?q={q}&format=json&limit=1", headers={"User-Agent":"GeosatV22"}, timeout=10).json()
        if r:
            return r[0]['display_name'], float(r[0]['lat']), float(r[0]['lon'])
    except Exception:
        pass
    return "Cali, Colombia", 3.4419, -76.5287

def crear_grafica_desde_datos(datos_dict, titulo, path="/tmp/geosat.png"):
    try:
        plt.close('all')
        years = sorted(datos_dict.keys())
        vals = [datos_dict[y] for y in years]
        plt.figure(figsize=(13,6.5))
        plt.plot([str(y) for y in years], vals, marker='o', linewidth=2.8, color='#0a58ca')
        plt.title(titulo, fontweight='bold', fontsize=12)
        plt.xlabel("Ano")
        plt.ylabel("C")
        plt.xticks(rotation=45, fontsize=8)
        plt.grid(True, alpha=0.25, linestyle='--')
        plt.tight_layout()
        plt.savefig(path, dpi=250)
        plt.close('all')
        time.sleep(0.4)
        return path
    except Exception as e:
        print(e)
        plt.close('all')
        return None

def crear_grafica_generica(spec, path="/tmp/geosat.png"):
    try:
        plt.close('all')
        plt.figure(figsize=(12,6))
        labels = [str(l) for l in spec.get("labels",[])]
        for ds in spec.get("datasets",[]):
            data = ds.get("data",[])
            label = ds.get("label","Dato")
            if spec.get("type") == "bar":
                plt.bar(labels, data, alpha=0.85, label=label)
            else:
                plt.plot(labels, data, marker='o', linewidth=2.6, label=label)
        plt.title(spec.get("title","Grafica"), fontweight='bold', fontsize=12)
        plt.xticks(rotation=45, fontsize=8)
        plt.grid(True, alpha=0.25, linestyle='--')
        plt.legend()
        plt.tight_layout()
        plt.savefig(path, dpi=250)
        plt.close('all')
        time.sleep(0.4)
        return path
    except Exception as e:
        print(e)
        plt.close('all')
        return None

def crear_imagen_ia(prompt, path="/tmp/ia.png"):
    try:
        p = urllib.parse.quote(prompt[:150])
        url = f"https://image.pollinations.ai/prompt/{p}?width=1024&height=768&nologo=true"
        r = requests.get(url, timeout=30)
        open(path,'wb').write(r.content)
        return path
    except Exception:
        return None

async def handle_docs(update, context):
    try:
        file = await update.message.document.get_file()
        fname = update.message.document.file_name
        await file.download_to_drive(f"docs/{fname}")
        await update.message.reply_text(f"Aprendido: {fname}")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def handle_message(update, context):
    texto = update.message.text
    if not texto:
        return
    low = texto.lower()
    try:
        quiere_visual = any(k in low for k in ["grafic","imagen","foto","visual","mapa","chart","plot","dibuja","figura"])
        quiere_imagen_ia = any(k in low for k in ["imagen","foto","dibuja","genera imagen","crea imagen"])

        years = expandir_anos(texto)
        if quiere_visual and not years and "cali" in low and "temperatura" in low:
            years = list(range(2000, datetime.datetime.now().year+1))

        lugar_q = re.sub(r'19\d{2}|20\d{2}|desde|hasta|actual|grafica|imagen|mapa|con|una|dame|temperatura|media|anual','', low).strip()
        nombre, lat, lon = geocode(lugar_q) if len(lugar_q)>2 else ("Cali, Colombia", 3.4419, -76.5287)

        datos_clima = get_datos_clima(lat, lon, years) if years else {}
        pdfs = cargar_pdfs()
        web_ia = buscar_ia_web(texto[:120])

        prompt_sys = f"Eres GEOSAT V22 LIBRE. Responde cualquier tema. Ano actual 2026. Prefiere info actual. Memoria PDFs: {pdfs[:8000]} WEB: {web_ia[:2000]} Datos clima: {datos_clima} Lugar: {nombre} Pregunta: {texto} Si piden grafica de otro tema genera CHART_JSON: {{\"type\":\"line\",\"title\":\"titulo\",\"labels\":[\"A\",\"B\"],\"datasets\":[{{\"label\":\"valor\",\"data\":[1,2]}}]}}"

        comp = client.chat.completions.create(model="openai/gpt-oss-20b", messages=[{"role":"system","content":prompt_sys}], temperature=0.8, max_tokens=2200)
        resp = comp.choices[0].message.content

        resp_limpio = re.sub(r'```json.*?```','', resp, flags=re.DOTALL)
        jm = re.search(r'CHART_JSON:\s*(\{.*\})', resp, re.DOTALL)

        if quiere_visual and datos_clima:
            img = crear_grafica_desde_datos(datos_clima, f"Temp {nombre} {min(datos_clima)}-{max(datos_clima)}")
            if img:
                txt = re.sub(r'CHART_JSON:.*','', resp_limpio, flags=re.DOTALL).strip()
                with open(img,'rb') as f:
                    await update.message.reply_photo(photo=f.read(), caption=txt[:1000])
                return

        if jm and quiere_visual:
            try:
                raw = jm.group(1).strip().replace("'",'"')
                spec = json.loads(raw)
                img = crear_grafica_generica(spec)
                if img:
                    txt = re.sub(r'CHART_JSON:.*','', resp_limpio, flags=re.DOTALL).strip()
                    with open(img,'rb') as f:
                        await update.message.reply_photo(photo=f.read(), caption=txt[:1000] if txt else spec.get("title","Grafica"))
                    return
            except Exception as e:
                print(e)

        if quiere_visual and quiere_imagen_ia:
            img = crear_imagen_ia(texto)
            if img:
                txt = re.sub(r'CHART_JSON:.*','', resp_limpio, flags=re.DOTALL).strip()
                with open(img,'rb') as f:
                    await update.message.reply_photo(photo=f.read(), caption=txt[:1000])
                return

        final = re.sub(r'CHART_JSON:.*','', resp_limpio, flags=re.DOTALL).strip()
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
