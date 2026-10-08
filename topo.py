"""
topo.py - GEOSAT V2.2 - Cálculos exactos + exportación mejorada + importación CSV
Python puro, sin librerías pesadas. Gratis en Render.
"""
import math
import re
import unicodedata
import csv
import io
import requests

WGS84 = (6378137.0, 1 / 298.257223563)
GRS80 = (6378137.0, 1 / 298.257222101)

class TM:
    def __init__(self, elipsoide, lat0, lon0, k0, fe, fn):
        a, f = elipsoide
        n = f / (2 - f)
        n2, n3, n4 = n*n, n**3, n**4
        self.k0, self.fe, self.fn = k0, fe, fn
        self.lon0 = math.radians(lon0)
        self.A = a / (1 + n) * (1 + n2/4 + n4/64)
        self.c = 2 * math.sqrt(n) / (1 + n)
        self.alfa = (n/2-2*n2/3+5*n3/16+41*n4/180,13*n2/48-3*n3/5+557*n4/1440,61*n3/240-103*n4/140,49561*n4/161280)
        self.beta = (n/2-2*n2/3+37*n3/96-n4/360,n2/48+n3/15-437*n4/1440,17*n3/480-37*n4/840,4397*n4/161280)
        self.delta = (2*n-2*n2/3-2*n3+116*n4/45,7*n2/3-8*n3/5-227*n4/45,56*n3/15-136*n4/35,4279*n4/630)
        self.xi0 = self._xi_eta(math.radians(lat0), self.lon0)[0]
    def _xi_eta(self, phi, lam):
        c = self.c
        t = math.sinh(math.atanh(math.sin(phi)) - c*math.atanh(c*math.sin(phi)))
        dl = lam - self.lon0
        xi1 = math.atan2(t, math.cos(dl))
        eta1 = math.asinh(math.sin(dl) / math.hypot(t, math.cos(dl)))
        xi, eta = xi1, eta1
        for j, al in enumerate(self.alfa, start=1):
            xi += al*math.sin(2*j*xi1)*math.cosh(2*j*eta1)
            eta += al*math.cos(2*j*xi1)*math.sinh(2*j*eta1)
        return xi, eta
    def directa(self, lat, lon):
        xi, eta = self._xi_eta(math.radians(lat), math.radians(lon))
        return (self.fe + self.k0*self.A*eta, self.fn + self.k0*self.A*(xi-self.xi0))
    def inversa(self, este, norte):
        xi = (norte-self.fn)/(self.k0*self.A)+self.xi0
        eta = (este-self.fe)/(self.k0*self.A)
        xi2, eta2 = xi, eta
        for j, b in enumerate(self.beta, start=1):
            xi2 -= b*math.sin(2*j*xi)*math.cosh(2*j*eta)
            eta2 -= b*math.cos(2*j*xi)*math.sinh(2*j*eta)
        chi = math.asin(math.sin(xi2)/math.cosh(eta2))
        phi = chi
        for j, d in enumerate(self.delta, start=1):
            phi += d*math.sin(2*j*chi)
        lam = self.lon0 + math.atan2(math.sinh(eta2), math.cos(xi2))
        return math.degrees(phi), math.degrees(lam)

_LAT0_MAGNA = 4.59620041666667
_ZONAS_MAGNA = {3114:("MAGNA-SIRGAS / Zona Oeste-Oeste (EPSG:3114)",-80.0775079166667),3115:("MAGNA-SIRGAS / Zona Oeste (EPSG:3115)",-77.0775079166667),3116:("MAGNA-SIRGAS / Zona Bogotá (EPSG:3116)",-74.0775079166667),3117:("MAGNA-SIRGAS / Zona Este Central (EPSG:3117)",-71.0775079166667),3118:("MAGNA-SIRGAS / Zona Este (EPSG:3118)",-68.0775079166667)}
_ALIAS = {"wgs84":4326,"gps":4326,"magna":4686,"magna sirgas":4686,"sirgas":4686,"origen nacional":9377,"origen":9377,"oeste":3115,"magna oeste":3115,"cali":3115,"bogota":3116,"magna bogota":3116,"este central":3117,"este":3118,"oeste oeste":3114,"far west":3114}
_CACHE = {}

def _normalizar(texto):
    t = unicodedata.normalize("NFD", str(texto).strip().lower())
    t = "".join(ch for ch in t if unicodedata.category(ch)!= "Mn")
    t = t.replace("epsg:", "").replace("epsg", "")
    return re.sub(r"[\s_\-/]+", " ", t).strip()

def _sistema(nombre, lat=None, lon=None):
    n = _normalizar(nombre)
    if n == "utm":
        if lat is None or lon is None:
            raise ValueError("'utm' automático solo como destino.")
        zona = int((lon + 180)//6)+1
        n = f"utm {zona}{'n' if lat>=0 else 's'}"
    m = re.fullmatch(r"utm?(\d{1,2})?([ns])", n)
    if m:
        zona, hem = int(m.group(1)), m.group(2)
        codigo = (32600 if hem=="n" else 32700)+zona
    elif n in _ALIAS:
        codigo = _ALIAS[n]
    elif re.fullmatch(r"\d{4,6}", n):
        codigo = int(n)
    else:
        raise ValueError(f"Sistema no reconocido: '{nombre}'. Usa /sistemas")
    if codigo in _CACHE:
        return _CACHE[codigo]
    if codigo==4326:
        s={"codigo":codigo,"nombre":"WGS84 geográficas (EPSG:4326)","tipo":"geo"}
    elif codigo==4686:
        s={"codigo":codigo,"nombre":"MAGNA-SIRGAS geográficas (EPSG:4686)","tipo":"geo"}
    elif codigo==9377:
        s={"codigo":codigo,"nombre":"MAGNA-SIRGAS / Origen Nacional (EPSG:9377)","tipo":"proy","tm":TM(GRS80,4.0,-73.0,0.9992,5_000_000.0,2_000_000.0),"lon0":-73.0,"limite":6.0}
    elif codigo in _ZONAS_MAGNA:
        nom, lon0 = _ZONAS_MAGNA[codigo]
        s={"codigo":codigo,"nombre":nom,"tipo":"proy","tm":TM(GRS80,_LAT0_MAGNA,lon0,1.0,1_000_000.0),"lon0":lon0,"limite":3.5}
    elif 32601<=codigo<=32660 or 32701<=codigo<=32760:
        norte=codigo<32700
        zona=codigo-(32600 if norte else 32700)
        lon0=-183.0+6.0*zona
        s={"codigo":codigo,"nombre":f"WGS84 / UTM zona {zona}{'N' if norte else 'S'} (EPSG:{codigo})","tipo":"proy","tm":TM(WGS84,0.0,lon0,0.9996,500_000.0,0.0 if norte else 10_000_000.0),"lon0":lon0,"limite":4.0}
    else:
        raise ValueError(f"EPSG:{codigo} no soportado.")
    _CACHE[codigo]=s
    return s

def _a_geo(sis,v1,v2):
    if sis["tipo"]=="geo":
        if abs(v1)>90 or abs(v2)>180:
            raise ValueError("Geográficas fuera de rango (lat,lon).")
        return v1,v2
    return sis["tm"].inversa(v1,v2)

def _de_geo(sis,lat,lon):
    return (lat,lon) if sis["tipo"]=="geo" else sis["tm"].directa(lat,lon)

def _aviso(sis,lon):
    if sis["tipo"]=="proy" and abs(lon-sis["lon0"])>sis["limite"]:
        return f"\nAviso: a {abs(lon-sis['lon0']):.1f}° del meridiano central; distorsión grande."
    return ""

def _num(v):
    if isinstance(v,(int,float)): return float(v)
    s=str(v).strip()
    if "," in s and "." not in s: s=s.replace(",",".")
    return float(s)

def _par(p):
    if not isinstance(p,(list,tuple)) or len(p)!=2:
        raise ValueError(f"Punto debe ser [v1,v2]; recibí {p}")
    return _num(p[0]), _num(p[1])

def _a_decimal(v):
    if isinstance(v,(int,float)): return float(v)
    s=str(v).strip()
    nums=re.findall(r"\d+(?:[.,]\d+)?", s)
    if not nums: raise ValueError(f"Ángulo no válido: {v}")
    d=float(nums[0].replace(",",".")); m=float(nums[1].replace(",",".")) if len(nums)>1 else 0.0; sg=float(nums[2].replace(",",".")) if len(nums)>2 else 0.0
    val=d+m/60+sg/3600
    return -val if s.startswith("-") else val

def _dms(g):
    signo="-" if g<0 else ""; g=abs(g); d=int(g); m=int((g-d)*60); s=round((g-d-m/60)*3600,2)
    if s>=60: s,m=0.0,m+1
    if m>=60: m,d=0,d+1
    return f"{signo}{d}°{m:02d}'{s:05.2f}\""

def _rumbo(az):
    if az<90: return f"N {_dms(az)} E"
    if az<180: return f"S {_dms(180-az)} E"
    if az<270: return f"S {_dms(az-180)} W"
    return f"N {_dms(360-az)} W"

def _geodesica(lat1,lon1,lat2,lon2):
    a,f=WGS84; b=a*(1-f); phi1,phi2=math.radians(lat1),math.radians(lat2); L=math.radians(lon2-lon1)
    U1,U2=math.atan((1-f)*math.tan(phi1)),math.atan((1-f)*math.tan(phi2)); sU1,cU1,sU2,cU2=math.sin(U1),math.cos(U1),math.sin(U2),math.cos(U2); lam=L
    for _ in range(200):
        sl,cl=math.sin(lam),math.cos(lam); ss=math.hypot(cU2*sl,cU1*sU2-sU1*cU2*cl)
        if ss==0: return 0.0,0.0,0.0
        cs=sU1*sU2+cU1*cU2*cl; sigma=math.atan2(ss,cs); sa=cU1*cU2*sl/ss; c2a=1-sa*sa; c2sm=cs-2*sU1*sU2/c2a if c2a!=0 else 0.0
        C=f/16*c2a*(4+f*(4-3*c2a)); prev=lam; lam=L+(1-C)*f*sa*(sigma+C*ss*(c2sm+C*cs*(-1+2*c2sm**2)))
        if abs(lam-prev)<1e-12: break
    else:
        h=math.sin((phi2-phi1)/2)**2+math.cos(phi1)*math.cos(phi2)*math.sin(L/2)**2; d=2*6371008.8*math.asin(math.sqrt(h)); az=math.degrees(math.atan2(math.sin(L)*math.cos(phi2),math.cos(phi1)*math.sin(phi2)-math.sin(phi1)*math.cos(phi2)*math.cos(L)))%360; return d,az,(az+180)%360
    u2=c2a*(a*a-b*b)/(b*b); A_=1+u2/16384*(4096+u2*(-768+u2*(320-175*u2))); B_=u2/1024*(256+u2*(-128+u2*(74-47*u2)))
    dsig=B_*ss*(c2sm+B_/4*(cs*(-1+2*c2sm**2)-B_/6*c2sm*(-3+4*ss**2)*(-3+4*c2sm**2))); s=b*A_*(sigma-dsig)
    az1=math.degrees(math.atan2(cU2*sl,cU1*sU2-sU1*cU2*cl))%360; az2=math.degrees(math.atan2(cU1*sl,-sU1*cU2+cU1*sU2*cl))%360
    return s,az1,(az2+180)%360

def sistemas():
    return "Sistemas: wgs84(4326), magna(4686), origen_nacional(9377), oeste(3115 Cali), bogota(3116), este_central(3117), este(3118), oeste_oeste(3114), utm_18n(32618)... o 'utm' automático.\nGeográficas: (lat,lon). Proyectadas: (Este,Norte)."

def convertir_coordenadas(valor_1,valor_2,origen,destino):
    o=_sistema(origen); lat,lon=_a_geo(o,_num(valor_1),_num(valor_2)); d=_sistema(destino,lat,lon); r1,r2=_de_geo(d,lat,lon)
    if d["tipo"]=="geo": txt=f"Latitud {r1:.8f}° ({_dms(r1)}), Longitud {r2:.8f}° ({_dms(r2)})\nSistema: {d['nombre']}"
    else: txt=f"Este {r1:.3f} m, Norte {r2:.3f} m\nSistema: {d['nombre']}"
    return txt+_aviso(d,lon)

def distancia_azimut(punto_a,punto_b,sistema):
    s=_sistema(sistema); (a1,a2),(b1,b2)=_par(punto_a),_par(punto_b)
    if s["tipo"]=="geo": dist,az,contra=_geodesica(a1,a2,b1,b2); base="Distancia geodésica sobre el elipsoide"
    else: dist=math.hypot(b1-a1,b2-a2); az=math.degrees(math.atan2(b1-a1,b2-a2))%360; contra=(az+180)%360; base="Distancia horizontal sobre cuadrícula"
    if dist==0: return "Puntos coinciden."
    return f"{base}: {dist:.3f} m\nAzimut A->B: {az:.6f}° ({_dms(az)})\nContra: {contra:.6f}°\nRumbo: {_rumbo(az)}\nSistema: {s['nombre']}"

def area_poligono(puntos,sistema):
    s=_sistema(sistema); pts=[_par(p) for p in puntos]
    if len(pts)>1 and pts[0]==pts[-1]: pts=pts[:-1]
    if len(pts)<3: raise ValueError("Mín 3 vértices.")
    if s["tipo"]=="geo":
        latc=sum(p[0] for p in pts)/len(pts); lonc=sum(p[1] for p in pts)/len(pts); local=TM(WGS84,latc,lonc,1.0,0.0,0.0); xy=[local.directa(la,lo) for la,lo in pts]; perim=sum(_geodesica(*pts[i],*pts[(i+1)%len(pts)])[0] for i in range(len(pts))); nota="Área sobre elipsoide (proyección local)."
    else: xy=pts; perim=sum(math.hypot(xy[(i+1)%len(xy)][0]-xy[i][0],xy[(i+1)%len(xy)][1]-xy[i][1]) for i in range(len(xy))); nota="Área sobre cuadrícula."
    area=abs(sum(xy[i][0]*xy[(i+1)%len(xy)][1]-xy[(i+1)%len(xy)][0]*xy[i][1] for i in range(len(xy))))/2
    return f"Área: {area:,.2f} m² = {area/10000:,.4f} ha\nPerímetro: {perim:,.3f} m\nVértices: {len(pts)}\n{nota}\nSistema: {s['nombre']}"

def cierre_poligonal(este_inicial,norte_inicial,tramos):
    e0,n0=_num(este_inicial),_num(norte_inicial); legs=[(_num(t[0]),_a_decimal(t[1])) for t in tramos]; perim=sum(d for d,_ in legs); raw=[]; e,n=e0,n0
    for d,az in legs: e+=d*math.sin(math.radians(az)); n+=d*math.cos(math.radians(az)); raw.append((e,n))
    ex,ey=raw[-1][0]-e0,raw[-1][1]-n0; err=math.hypot(ex,ey); prec="infinita (cierre perfecto)" if err<1e-9 else f"1:{int(perim/err):,}"
    lineas=[]; cum=0.0
    for k,((d,_),(re_,rn)) in enumerate(zip(legs,raw),start=1): cum+=d; ae,an=re_-ex*cum/perim,rn-ey*cum/perim; et=f"V{k}" if k<len(legs) else f"V{k} (=V0)"; lineas.append(f"{et}: Este {ae:.3f}, Norte {an:.3f}")
    return f"Perímetro: {perim:.3f} m\nError Este: {ex:+.4f}, Norte: {ey:+.4f}\nError cierre: {err:.4f} m\nPrecisión: {prec}\n"+"\n".join(lineas)

def cierre_angular(angulos,tipo="interior",precision_seg=10):
    ang=[_a_decimal(a) for a in angulos]; n=len(ang); teorica=(n-2)*180 if tipo=="interior" else (n+2)*180; err_seg=(sum(ang)-teorica)*3600; tol=_num(precision_seg)*math.sqrt(n); corr=-err_seg/n
    return f"Ángulos: {n} ({tipo})\nSuma obs: {_dms(sum(ang))}\nSuma teó: {_dms(teorica)}\nError: {err_seg:+.1f}\"\nTol ±{tol:.1f}\" -> {'CUMPLE' if abs(err_seg)<=tol else 'NO CUMPLE'}\nCorr por ángulo: {corr:+.2f}\"\nCorregidos: {', '.join(_dms(a+corr/3600) for a in ang)}"

def nivelacion(cota_inicial,lecturas,cota_final_conocida=None,distancia_km=None,mm_por_raiz_km=10):
    cota=_num(cota_inicial); filas=[]; calc=[]
    for k,par in enumerate(lecturas,start=1):
        va,vd=_par(par); hi=cota+va; cota=hi-vd; calc.append(cota); filas.append((k,va,vd,hi,cota))
    err=calc[-1]-_num(cota_final_conocida) if cota_final_conocida is not None else 0.0
    out=[f"Desnivel: {calc[-1]-_num(cota_inicial):+.4f} m",f"Cota final: {calc[-1]:.4f} m"]
    if cota_final_conocida is not None: out.append(f"Error cierre: {err*1000:+.1f} mm")
    for k,va,vd,hi,c in filas: out.append(f"Est {k}: VA {va:.3f} VD {vd:.3f} cota {c:.4f} -> {c-err*k/len(calc):.4f}")
    return "\n".join(out)

def elevacion_punto(latitud,longitud):
    try: r=requests.get("https://api.open-meteo.com/v1/elevation",params={"latitude":_num(latitud),"longitude":_num(longitud)},timeout=10); r.raise_for_status(); elev=r.json()["elevation"][0]
    except: return "No pude consultar elevación."
    return f"Elevación ~{elev:.0f} m s.n.m. (90 m res, solo referencia)."

def gsd_dron(ancho_sensor_mm,distancia_focal_mm,ancho_imagen_px,alto_imagen_px,altura_m=None,gsd_deseado_cm=None,area_ha=None,traslape_frontal=0.8,traslape_lateral=0.7):
    sw,f=_num(ancho_sensor_mm),_num(distancia_focal_mm); wpx,hpx=_num(ancho_imagen_px),_num(alto_imagen_px)
    h=_num(altura_m) if altura_m is not None else _num(gsd_deseado_cm)/100*f*wpx/sw; gsd=h*sw/(f*wpx); huella_w,huella_h=gsd*wpx,gsd*hpx
    out=[f"Altura: {h:.1f} m",f"GSD: {gsd*100:.2f} cm/px (≈{gsd:.4f} m/px)",f"Huella: {huella_w:.1f} m x {huella_h:.1f} m"]
    if area_ha is not None: dx,dy=huella_h*(1-_num(traslape_frontal)),huella_w*(1-_num(traslape_lateral)); fotos=math.ceil(_num(area_ha)*10000/(dx*dy)); out.append(f"Fotos para {_num(area_ha):g} ha: ~{fotos} +20% bordes")
    return "\n".join(out)

def convertir_angulo(valor,a="decimal"): dec=_a_decimal(valor); return _dms(dec) if str(a).lower()=="dms" else f"{dec:.8f}°"

# --- FASE 2/3 EXPORTACIÓN
def _a_wgs84_lista(puntos,sistema):
    s=_sistema(sistema); out=[]
    for p in puntos: v1,v2=_par(p); lat,lon=_a_geo(s,v1,v2); e,n=(v1,v2) if s["tipo"]=="proy" else _de_geo(_sistema("origen_nacional"),lat,lon); out.append((e,n,lat,lon))
    return out

def exportar_csv(puntos,sistema,nombre="poligono"):
    s=_sistema(sistema); datos=_a_wgs84_lista(puntos,sistema); lineas=[f"ID,Este_{s['codigo']},Norte_{s['codigo']},Latitud_WGS84,Longitud_WGS84,Sistema"]
    for i,(e,n,lat,lon) in enumerate(datos,1): lineas.append(f"{i},{e:.3f},{n:.3f},{lat:.8f},{lon:.8f},{s['nombre']}")
    return "\n".join(lineas)

def exportar_kml(puntos,sistema,nombre="GEOSAT_Poligono"):
    datos=_a_wgs84_lista(puntos,sistema)
    if not datos: return ""
    coords_poly="\n".join(f" {lon:.8f},{lat:.8f},0" for _,_,lat,lon in datos)+f"\n {datos[0][3]:.8f},{datos[0][2]:.8f},0"
    puntos_kml=""
    for i,(e,n,lat,lon) in enumerate(datos,1):
        puntos_kml+=f"""<Placemark><name>V{i}</name><description>Este {e:.3f} Norte {n:.3f}</description><Point><coordinates>{lon:.8f},{lat:.8f},0</coordinates></Point></Placemark>\n"""
    return f"""<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>{nombre}</name>
<Style id="amarillo"><LineStyle><color>ff00ffff</color><width>3</width></LineStyle><PolyStyle><color>4000ff00</color></PolyStyle></Style>
{puntos_kml}
<Placemark><name>{nombre} - Poligono</name><styleUrl>#amarillo</styleUrl><Polygon><outerBoundaryIs><LinearRing><coordinates>{coords_poly}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
</Document></kml>"""

def exportar_dxf(puntos,sistema,nombre="GEOSAT"):
    pts=[_par(p) for p in puntos];
    if pts[0]!=pts[-1]: pts.append(pts[0])
    ent=""
    for i in range(len(pts)-1): x1,y1=pts[i]; x2,y2=pts[i+1]; ent+=f"0\nLINE\n8\n{nombre}\n10\n{x1:.3f}\n20\n{y1:.3f}\n11\n{x2:.3f}\n21\n{y2:.3f}\n"
    ent+=f"0\nLWPOLYLINE\n8\n{nombre}_POLY\n90\n{len(pts)}\n70\n1\n"
    for x,y in pts: ent+=f"10\n{x:.3f}\n20\n{y:.3f}\n"
    return f"0\nSECTION\n2\nHEADER\n9\n$ACADVER\n1\nAC1009\n0\nENDSEC\n0\nSECTION\n2\nENTITIES\n{ent}0\nENDSEC\n0\nEOF\n"

def poligonal_a_puntos(este_inicial,norte_inicial,tramos):
    e0,n0=_num(este_inicial),_num(norte_inicial); pts=[(e0,n0)]; e,n=e0,n0
    for t in tramos:
        d=_num(t[0]); az=_a_decimal(t[1]); e+=d*math.sin(math.radians(az)); n+=d*math.cos(math.radians(az)); pts.append((e,n))
    return pts

def convertir_lote_csv(texto_csv,sistema_origen="origen_nacional",sistema_destino="wgs84"):
    # Detecta delimitador
    f=io.StringIO(texto_csv.strip())
    sample=f.read(1024); f.seek(0)
    delim="," if sample.count(",")>=sample.count(";") else ";"
    reader=csv.DictReader(f, delimiter=delim)
    if not reader.fieldnames:
        # sin encabezado: intenta Este,Norte
        f.seek(0); reader=csv.reader(f, delimiter=delim)
        pts=[]; out=[]
        for row in reader:
            if len(row)<2: continue
            try: v1,v2=_num(row[0]),_num(row[1]); pts.append((v1,v2))
            except: continue
        for v1,v2 in pts:
            lat,lon=_a_geo(_sistema(sistema_origen),v1,v2)
            r1,r2=_de_geo(_sistema(sistema_destino),lat,lon)
            out.append((v1,v2,r1,r2))
        return out
    # con encabezado
    pts=[]; keys=[k.lower() for k in reader.fieldnames]
    for row in reader:
        try:
            # busca columnas este/norte/x/y
            vals=list(row.values())
            v1=_num(vals[0]); v2=_num(vals[1]); pts.append((v1,v2))
        except: continue
    out=[]
    for v1,v2 in pts:
        lat,lon=_a_geo(_sistema(sistema_origen),v1,v2)
        r1,r2=_de_geo(_sistema(sistema_destino),lat,lon)
        out.append((v1,v2,r1,r2))
    return out

def _tool(nombre,descripcion,props,req=()):
    return {"type":"function","function":{"name":nombre,"description":descripcion,"parameters":{"type":"object","properties":props,"required":list(req)}}}
_N={"type":"number"}; _S={"type":"string"}; _PTO={"type":"array","items":_N}
TOOLS=[
_tool("convertir_coordenadas","Convierte coordenadas. Geo: v1=lat,v2=lon. Proy: v1=Este,v2=Norte. Sistemas: wgs84,magna,origen_nacional,oeste,bogota,utm_18n,'utm' solo destino.",{"valor_1":_N,"valor_2":_N,"origen":_S,"destino":_S},["valor_1","valor_2","origen","destino"]),
_tool("distancia_azimut","Distancia y azimut entre 2 puntos.",{"punto_a":_PTO,"punto_b":_PTO,"sistema":_S},["punto_a","punto_b","sistema"]),
_tool("area_poligono","Área y perímetro polígono [[v1,v2],...]",{"puntos":{"type":"array"},"sistema":_S},["puntos","sistema"]),
_tool("cierre_poligonal","Cierre Bowditch. tramos [[dist,azimut],...] azimut decimal o DMS",{"este_inicial":_N,"norte_inicial":_N,"tramos":{"type":"array"}},["este_inicial","norte_inicial","tramos"]),
_tool("cierre_angular","Error cierre angular",{"angulos":{"type":"array"},"tipo":{"type":"string","enum":["interior","exterior"]},"precision_seg":_N},["angulos"]),
_tool("nivelacion","Nivelación [[VA,VD],...]",{"cota_inicial":_N,"lecturas":{"type":"array"},"cota_final_conocida":_N,"distancia_km":_N,"mm_por_raiz_km":_N},["cota_inicial","lecturas"]),
_tool("elevacion_punto","Elevación ~90m de punto WGS84",{"latitud":_N,"longitud":_N},["latitud","longitud"]),
_tool("gsd_dron","GSD dron. ancho_px es PRIMER numero WxH (5472 de 5472x3648)",{"ancho_sensor_mm":_N,"distancia_focal_mm":_N,"ancho_imagen_px":_N,"alto_imagen_px":_N,"altura_m":_N,"gsd_deseado_cm":_N,"area_ha":_N},["ancho_sensor_mm","distancia_focal_mm","ancho_imagen_px","alto_imagen_px"]),
_tool("convertir_angulo","Convierte ángulo decimal<->DMS",{"valor":{"type":"string"},"a":{"type":"string","enum":["decimal","dms"]}},["valor","a"]),
_tool("exportar_csv","Genera CSV Este,Norte,Lat,Lon",{"puntos":{"type":"array"},"sistema":_S,"nombre":_S},["puntos","sistema"]),
_tool("exportar_kml","Genera KML con vértices etiquetados para Google Earth",{"puntos":{"type":"array"},"sistema":_S,"nombre":_S},["puntos","sistema"]),
_tool("exportar_dxf","Genera DXF R12 para AutoCAD",{"puntos":{"type":"array"},"sistema":_S,"nombre":_S},["puntos","sistema"]),
_tool("poligonal_a_puntos","Convierte poligonal inicio+tramos a lista de puntos",{"este_inicial":_N,"norte_inicial":_N,"tramos":{"type":"array"}},["este_inicial","norte_inicial","tramos"]),
]

FUNCIONES={"convertir_coordenadas":convertir_coordenadas,"distancia_azimut":distancia_azimut,"area_poligono":area_poligono,"cierre_poligonal":cierre_poligonal,"cierre_angular":cierre_angular,"nivelacion":nivelacion,"elevacion_punto":elevacion_punto,"gsd_dron":gsd_dron,"convertir_angulo":convertir_angulo,"exportar_csv":exportar_csv,"exportar_kml":exportar_kml,"exportar_dxf":exportar_dxf,"poligonal_a_puntos":poligonal_a_puntos}

def ejecutar(nombre,args):
    fn=FUNCIONES.get(nombre)
    if fn is None: return f"Herramienta desconocida: {nombre}"
    try: return fn(**args)
    except TypeError as e: return f"Parámetros inválidos para {nombre}: {e}"
    except (ValueError,ZeroDivisionError,OverflowError) as e: return f"No pude calcular: {e}"
