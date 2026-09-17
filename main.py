async def procesar_comando_universal(update, texto):
 low=texto.lower().strip()
 if not low: return
 if low in ["hola","buenas","hi","hey","ola","holaa","que tal","q mas","que mas","buenos dias","buenos días"]:
  await update.message.reply_text("Hola! Que mas? Soy Geosat V27, dime lo que necesites 🌎")
  return

 quiere_visual=any(k in low for k in ["imagen","foto","grafica","gráfica","visual","mapa","muestrame","dibuja","foto real","imagen real"])
 quiere_buscar= "busca" in low or "foto real" in low or "imagen real" in low
 # CLIMA solo si NO esta pidiendo foto real explicitamente
 es_clima_puro = any(k in low for k in ["temperatura","precipitacion","era5","clima"]) or (low.strip()=="cali" or low.strip()=="temperatura cali")

 # 1. PRIORIDAD MAXIMA: BUSCAR FOTO REAL
 if quiere_buscar and quiere_visual:
  prompt=texto
  for w in ["busca imagen real de","buscar imagen real de","busca imagen de","buscar imagen de","foto real de","imagen real de","busca foto de","busca","buscar"]:
   prompt=prompt.lower().replace(w,"")
  prompt=prompt.strip() or "Cali Colombia"
  await update.message.reply_text(f"🔍 Buscando foto real de: {prompt}...")
  foto=buscar_imagen_real(prompt)
  if foto:
   with open(foto,'rb') as f:
    await update.message.reply_photo(photo=f.read(),caption=f"Foto real de {prompt} - tomada de internet")
   return
  else:
   await update.message.reply_text(f"No pude traer foto real de {prompt}, pero intento generar una...")
   foto2=generar_imagen_ia(prompt)
   if foto2:
    with open(foto2,'rb') as f:
     await update.message.reply_photo(photo=f.read(),caption=f"Imagen IA de {prompt}")
    return

 # 2. CLIMA / GRAFICA
 if es_clima_puro and quiere_visual:
  datos=get_clima_real()
  foto=crear_foto_clima(datos)
  cap=llamar_groq(texto, f"datos {datos}")
  with open(foto,'rb') as f:
   await update.message.reply_photo(photo=f.read(),caption=cap[:1000])
  return

 # 3. GENERAR CUALQUIER IMAGEN
 if quiere_visual:
  prompt=texto
  for w in ["dame una imagen de","imagen de","foto de","genera la imagen de","generar imagen de","crea imagen de","genera imagen de","muestrame"]:
   prompt=prompt.lower().replace(w,"")
  prompt=prompt.strip() or "paisaje"
  await update.message.reply_text(f"🎨 Generando imagen IA de: {prompt}...")
  foto=generar_imagen_ia(prompt)
  if foto:
   with open(foto,'rb') as f:
    await update.message.reply_photo(photo=f.read(),caption=f"Imagen IA de {prompt}")
   return

 # 4. TEXTO GENERAL
 resp=llamar_groq(texto)
 await update.message.reply_text(resp)
