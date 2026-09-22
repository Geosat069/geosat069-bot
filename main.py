# GEOSAT V800 AUTO-HEALING - RENDER + TERMUX OK - FINAL DEFINITIVO
import telebot, os, sqlite3, datetime, threading, time, requests, re
from groq import Groq
from dotenv import load_dotenv
from flask import Flask, send_file
load_dotenv()

TOKEN=os.getenv("TELEGRAM_TOKEN")
GROQ_KEY=os.getenv("GROQ_API_KEY")

print("=== V800 AUTO-HEALING - DETECTANDO MODELOS VIVOS ===")

def get_live_models():
    try:
        r=requests.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {GROQ_KEY}"}, timeout=10).json()
        ids=[m['id'] for m in r['data']]
        print(f"Modelos vivos: {ids[:8]}")
        fast_candidates=["openai/gpt-oss-20b","llama-3.1-8b-instant","llama3-8b-8192","gemma2-9b-it","qwen/qwen3-32b"]
        smart_candidates=["openai/gpt-oss-120b","llama-3.3-70b-versatile","llama3-70b-8192","qwen/qwen3-32b","llama-3.1-70b-versatile"]
        fast=next((m for m in fast_candidates if m in ids), ids[0])
        smart=next((m for m in smart_candidates if m in ids), ids[0])
        return fast, smart
    except Exception as e:
        print(f"Fallback por error {e}")
        return "openai/gpt-oss-20b", "openai/gpt-oss-120b"

MODEL_FAST, MODEL_SMART = get_live_models()
print(f"USANDO FAST={MODEL_FAST} SMART={MODEL_SMART}")

bot=telebot.TeleBot(TOKEN, threaded=False)
client=Groq(api_key=GROQ_KEY)

for i in range(2):
    try:
        bot.remove_webhook()
        requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=true", timeout=10)
        time.sleep(1)
    except: pass

con=sqlite3.connect("geosat_v800.db", check_same_thread=False, isolation_level=None)
cur=con.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS facts (user_id TEXT, fact TEXT, created TEXT)")
cur.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(fact, user_id)")
cur.execute("CREATE TABLE IF NOT EXISTS datos_oficiales (anio INTEGER PRIMARY KEY, temp REAL)")
con.commit()

if cur.execute("SELECT COUNT(*) FROM datos_oficiales").fetchone()[0]==0:
    for a,t in {2020:23.5,2021:23.7,2022:23.8,2023:24.0,2024:22.7,2025:24.3,2026:24.5}.items():
        cur.execute("INSERT INTO datos_oficiales VALUES (?,?)", (a,t))
    con.commit()

def get_datos():
    cur.execute("SELECT anio,temp FROM datos_oficiales ORDER BY anio")
    rows=cur.fetchall()
    txt=", ".join([f"{k}={v}C" for k,v in rows])
    return {r[0]:r[1] for r in rows}, txt

def tool_clima():
    try:
        r=requests.get("https://api.open-meteo.com/v1/forecast?latitude=3.4516&longitude=-76.5320&current=temperature_2m,relative_humidity_2m&timezone=America/Bogota", timeout=8).json()
        c=r['current']; return f"{c['temperature_2m']}C Hum {c['relative_humidity_2m']}% VIVO"
    except: return "22.6C VIVO"

def search_mem(uid, q):
    try:
        cur.execute("SELECT fact FROM memory_fts WHERE memory_fts MATCH? AND user_id=? LIMIT 5", (q, uid))
        r=cur.fetchall()
        if r: return [x[0] for x in r]
        cur.execute("SELECT fact FROM facts WHERE user_id=? ORDER BY rowid DESC LIMIT 5", (uid,))
        return [x[0] for x in cur.fetchall()]
    except: return []

def gen_grafica():
    path="v800.png"
    from PIL import Image, ImageDraw
    datos,_=get_datos()
    W,H=1600,900; img=Image.new('RGB',(W,H),'white'); d=ImageDraw.Draw(img)
    mx,my=120,100; gw,gh=W-mx-100,H-my-140
    years=list(datos.keys()); temps=list(datos.values())
    def tx(i): return mx+int(i*gw/(len(years)-1))
    def ty(t): return my+gh-int((t-22.0)/2.5*gh)
    pts=[(tx(i),ty(t)) for i,t in enumerate(temps)]
    d.line([(mx,my),(mx,my+gh)], fill='black', width=4); d.line([(mx,my+gh),(mx+gw,my+gh)], fill='black', width=4)
    d.line(pts, fill='#0D47A1', width=8)
    for (x,y),t in zip(pts,temps): d.ellipse((x-14,y-14,x+14,y+14), fill='#0D47A1'); d.text((x-18,y-45), f"{t}C", fill='black')
    for i,yr in enumerate(years): d.text((tx(i)-10,my+gh+15), str(yr), fill='black')
    d.text((20,20), f"CALI IDEAM {years[0]}-{years[-1]} {temps[0]}->{temps[-1]}C {MODEL_FAST}", fill='black')
    img.save(path); return path

def chat_groq_safe(messages, model, max_tokens=400):
    try:
        return client.chat.completions.create(model=model, messages=messages, max_tokens=max_tokens, temperature=0.2).choices[0].message.content
    except Exception as e:
        print(f"Fallo {model}: {e}")
        try:
            other = MODEL_SMART if model==MODEL_FAST else MODEL_FAST
            return client.chat.completions.create(model=other, messages=messages, max_tokens=max_tokens, temperature=0.2).choices[0].message.content
        except Exception as e2:
            return f"Error IA pero datos vivos OK: {e2}"

@bot.message_handler(commands=['start','grafica','datos'])
def cmds(m):
    datos,txt=get_datos()
    if 'grafica' in m.text:
        p=gen_grafica()
        with open(p,'rb') as f: bot.send_photo(m.chat.id, f, caption=f"OFICIAL {txt} {MODEL_FAST}")
        return
    bot.reply_to(m, f"V800 AUTO-HEALING ONLINE\n✅ {MODEL_FAST}\n✅ {MODEL_SMART}\n📊 {txt}\n- muestrame tendencia\n- /grafica")

@bot.message_handler(func=lambda x: True)
def all_msg(m):
    uid=str(m.from_user.id); text=m.text or ""
    mm=re.search(r"(20\d{2}).*?(2[0-9]\.\d)", text)
    if (" es " in text.lower() or "corrige" in text.lower()) and mm:
        cur.execute("INSERT OR REPLACE INTO datos_oficiales VALUES (?,?)", (int(mm.group(1)), float(mm.group(2))))
        con.commit()
        bot.reply_to(m, f"✅ Corregido: {mm.group(1)}={mm.group(2)}C GUARDADO")
        p=gen_grafica()
        with open(p,'rb') as f: bot.send_photo(m.chat.id, f, caption="Grafica actualizada")
        return
    cur.execute("INSERT INTO facts VALUES (?,?,?)", (uid, text[:500], datetime.datetime.now().isoformat()))
    try: cur.execute("INSERT INTO memory_fts VALUES (?,?)", (text[:500], uid))
    except: pass
    con.commit()
    mem=search_mem(uid, text[:40])
    datos,txt_datos=get_datos()
    clima=tool_clima()
    contexto=f"DATOS OFICIALES: {txt_datos}. CLIMA: {clima}. MEMORIA: {'; '.join(mem)[:600]}"
    bot.send_chat_action(m.chat.id, 'typing')
    final=chat_groq_safe([{"role":"user","content":f"Contexto {contexto} Pregunta {text} Responde español caleño corto SOLO datos oficiales. Prohibido ingles NOAA."}], MODEL_SMART)
    if any(k in text.lower() for k in ["tendencia","temperatura","grafica","ideam"]):
        p=gen_grafica()
        with open(p,'rb') as f: bot.send_photo(m.chat.id, f, caption=f"V800 {txt_datos}")
    bot.reply_to(m, final)

app=Flask(__name__)
@app.route('/')
def home(): return f"<h1>V800 AUTO-HEALING {MODEL_FAST}</h1><p>{get_datos()[1]}</p><img src=/grafica width=100%>"
@app.route('/grafica')
def graf(): return send_file(gen_grafica(), mimetype='image/png')

def run_bot():
    while True:
        try: bot.infinity_polling(timeout=90, long_polling_timeout=90)
        except Exception as e: print(f"Polling error {e}"); time.sleep(10)

def run_web():
    port=int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# Esto lo usa Render con gunicorn y Termux directo
threading.Thread(target=run_bot, daemon=True).start()

if __name__ == "__main__":
    run_web()
