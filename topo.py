import math, json, re, requests
A = 6378137.0
F = 1/298.257223563
ORIGENES = {
    "origen_nacional": {"lat0": 4.0, "lon0": -73.0, "false_e": 5000000, "false_n": 2000000},
    "bogota": {"lat0": 4.596200, "lon0": -74.077508, "false_e": 1000000, "false_n": 1000000},
    "este_este": {"lat0": 4.0, "lon0": -71.5, "false_e": 5000000, "false_n": 2000000},
    "oeste": {"lat0": 4.0, "lon0": -79.0, "false_e": 5000000, "false_n": 2000000},
}
def latlon_to_tm(lat, lon, sistema="origen_nacional"):
    o = ORIGENES.get(sistema, ORIGENES["origen_nacional"])
    lat0 = math.radians(o["lat0"]); lon0 = math.radians(o["lon0"])
    latr = math.radians(lat); lonr = math.radians(lon)
    k0=0.9992; e2=2*F-F*F
    N = A / math.sqrt(1 - e2*math.sin(latr)**2)
    T = math.tan(latr)**2; C = e2/(1-e2)*math.cos(latr)**2
    A_ = (lonr-lon0)*math.cos(latr)
    M = A*(1-e2/4-3*e2**2/64)*(latr-lat0)
    este = o["false_e"] + k0*N*(A_ + (1-T+C)*A_**3/6)
    norte = o["false_n"] + k0*(M + N*math.tan(latr)*(A_**2/2))
    return {"este": este, "norte": norte, "sistema": sistema}
def tm_to_latlon(este, norte, sistema="origen_nacional"):
    o = ORIGENES.get(sistema, ORIGENES["origen_nacional"])
    lat = o["lat0"] + (norte - o["false_n"])/111319.9
    lon = o["lon0"] + (este - o["false_e"])/(111319.9*math.cos(math.radians(lat)))
    return {"lat": lat, "lon": lon, "sistema": sistema}
def distancia_acimut_area(puntos):
    dists=[]; azims=[]
    for i in range(len(puntos)-1):
        dx=puntos[i+1][0]-puntos[i][0]; dy=puntos[i+1][1]-puntos[i][1]
        d=math.hypot(dx,dy); az=(math.degrees(math.atan2(dx,dy))+360)%360
        dists.append(d); azims.append(az)
    area=0
    for i in range(len(puntos)):
        j=(i+1)%len(puntos); area+=puntos[i][0]*puntos[j][1]-puntos[j][0]*puntos[i][1]
    area=abs(area)/2
    cierre=math.hypot(puntos[-1][0]-puntos[0][0], puntos[-1][1]-puntos[0][1]) if len(puntos)>2 else 0
    perim=sum(dists)
    return {"distancias_m": dists, "acimuts_deg": azims, "area_m2": round(area,3), "area_ha": round(area/10000,6), "perimetro_m": round(perim,3), "cierre_m": round(cierre,3)}
def radiacion_polar(este_base, norte_base, acimut_base, angulo, distancia):
    az=(acimut_base+angulo)%360
    e=este_base+distancia*math.sin(math.radians(az)); n=norte_base+distancia*math.cos(math.radians(az))
    return {"este": e, "norte": n, "acimut_final": az}
def curva_horizontal_completa(radio, delta, pi_este, pi_norte, acimut_entrada):
    d=math.radians(delta); T=radio*math.tan(d/2); LC=radio*d; E=radio*(1/math.cos(d/2)-1); C=2*radio*math.sin(d/2)
    pc_e=pi_este - T*math.sin(math.radians(acimut_entrada)); pc_n=pi_norte - T*math.cos(math.radians(acimut_entrada))
    az_sal=(acimut_entrada+delta)%360
    pt_e=pi_este + T*math.sin(math.radians(az_sal)); pt_n=pi_norte + T*math.cos(math.radians(az_sal))
    return {"T": round(T,3), "LC": round(LC,3), "E": round(E,3), "C": round(C,3), "PC": [pc_e, pc_n], "PT": [pt_e, pt_n]}
def helmert_2d(origen, destino):
    n=len(origen)
    if n<2: return {"error":"Min 2 puntos"}
    sx=sum(o[0] for o in origen)/n; sy=sum(o[1] for o in origen)/n
    dx=sum(d[0] for d in destino)/n; dy=sum(d[1] for d in destino)/n
    return {"tx": dx-sx, "ty": dy-sy, "puntos": n}
def replanteo_inverso(base1, base2, punto):
    def calc(b,p): return {"dist": round(math.hypot(p[0]-b[0], p[1]-b[1]),3), "az": round((math.degrees(math.atan2(p[0]-b[0], p[1]-b[1]))+360)%360,4)}
    return {"desde_base1": calc(base1,punto), "desde_base2": calc(base2,punto)}
def gsd_dron(altura): return {"gsd_cm": round((altura*100*6.17)/(3.6*4000),2)}
def ventana_vuelo(lat, lon):
    try: return requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=windspeed_10m_max,precipitation_sum&timezone=auto", timeout=5).json()
    except Exception as e: return {"error": str(e)}
def ejecutar_tool(nombre, args):
    if nombre=="convertir_coordenada":
        if "lat" in args: return latlon_to_tm(args["lat"], args["lon"], args.get("sistema","origen_nacional"))
        else: return tm_to_latlon(args["este"], args["norte"], args.get("sistema","origen_nacional"))
    if nombre=="distancia_acimut_area": return distancia_acimut_area(args["puntos"])
    if nombre=="radiacion_polar": return radiacion_polar(args["este_base"], args["norte_base"], args["acimut_base"], args["angulo"], args["distancia"])
    if nombre=="curva_horizontal_completa": return curva_horizontal_completa(args["radio"], args["delta"], args["pi_este"], args["pi_norte"], args["acimut_entrada"])
    if nombre=="transformacion_helmert": return helmert_2d(args["origen"], args["destino"])
    if nombre=="replanteo_inverso": return replanteo_inverso(args["base1"], args["base2"], args["punto"])
    if nombre=="gsd_dron": return gsd_dron(args["altura"])
    if nombre=="ventana_vuelo": return ventana_vuelo(args["lat"], args["lon"])
    return {"error":"Tool no encontrada"}
TOOLS = [
    {"type":"function","function":{"name":"convertir_coordenada","description":"Convierte lat/lon a Este/Norte MAGNA","parameters":{"type":"object","properties":{"lat":{"type":"number"},"lon":{"type":"number"},"este":{"type":"number"},"norte":{"type":"number"},"sistema":{"type":"string"}},"required":[]}}},
    {"type":"function","function":{"name":"distancia_acimut_area","description":"Area y distancias poligonal","parameters":{"type":"object","properties":{"puntos":{"type":"array"}},"required":["puntos"]}}},
    {"type":"function","function":{"name":"radiacion_polar","description":"Radiacion polar","parameters":{"type":"object","properties":{"este_base":{"type":"number"},"norte_base":{"type":"number"},"acimut_base":{"type":"number"},"angulo":{"type":"number"},"distancia":{"type":"number"}},"required":["este_base","norte_base","acimut_base","angulo","distancia"]}}},
    {"type":"function","function":{"name":"curva_horizontal_completa","description":"Curva horizontal","parameters":{"type":"object","properties":{"radio":{"type":"number"},"delta":{"type":"number"},"pi_este":{"type":"number"},"pi_norte":{"type":"number"},"acimut_entrada":{"type":"number"}},"required":["radio","delta","pi_este","pi_norte","acimut_entrada"]}}},
    {"type":"function","function":{"name":"transformacion_helmert","description":"Helmert dron a GNSS","parameters":{"type":"object","properties":{"origen":{"type":"array"},"destino":{"type":"array"}},"required":["origen","destino"]}}},
    {"type":"function","function":{"name":"replanteo_inverso","description":"Replanteo inverso","parameters":{"type":"object","properties":{"base1":{"type":"array"},"base2":{"type":"array"},"punto":{"type":"array"}},"required":["base1","base2","punto"]}}},
    {"type":"function","function":{"name":"gsd_dron","description":"GSD dron","parameters":{"type":"object","properties":{"altura":{"type":"number"}},"required":["altura"]}}},
    {"type":"function","function":{"name":"ventana_vuelo","description":"Ventana vuelo","parameters":{"type":"object","properties":{"lat":{"type":"number"},"lon":{"type":"number"}},"required":["lat","lon"]}}},
]
