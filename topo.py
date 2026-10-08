"""
topo.py - Herramientas de topografía y geomática para GEOSAT.

Cálculos exactos en Python puro (sin librerías pesadas). El modelo de IA decide
qué herramienta usar; las cuentas las hace este código, no la IA.

Sistemas soportados: WGS84 (4326), MAGNA-SIRGAS geográficas (4686),
MAGNA-SIRGAS Origen Nacional (9377), zonas MAGNA Colombia (3114 a 3118) y UTM.
"""
import math
import re
import unicodedata

import requests

WGS84 = (6378137.0, 1 / 298.257223563)
GRS80 = (6378137.0, 1 / 298.257222101)  # elipsoide de MAGNA-SIRGAS


# ------------------------------------------------- proyección transversa de Mercator
class TM:
    """Transversa de Mercator (series de Krüger, 4.º orden: precisión sub-milimétrica)."""

    def __init__(self, elipsoide, lat0, lon0, k0, fe, fn):
        a, f = elipsoide
        n = f / (2 - f)
        n2, n3, n4 = n * n, n**3, n**4
        self.k0, self.fe, self.fn = k0, fe, fn
        self.lon0 = math.radians(lon0)
        self.A = a / (1 + n) * (1 + n2 / 4 + n4 / 64)
        self.c = 2 * math.sqrt(n) / (1 + n)
        self.alfa = (
            n / 2 - 2 * n2 / 3 + 5 * n3 / 16 + 41 * n4 / 180,
            13 * n2 / 48 - 3 * n3 / 5 + 557 * n4 / 1440,
            61 * n3 / 240 - 103 * n4 / 140,
            49561 * n4 / 161280,
        )
        self.beta = (
            n / 2 - 2 * n2 / 3 + 37 * n3 / 96 - n4 / 360,
            n2 / 48 + n3 / 15 - 437 * n4 / 1440,
            17 * n3 / 480 - 37 * n4 / 840,
            4397 * n4 / 161280,
        )
        self.delta = (
            2 * n - 2 * n2 / 3 - 2 * n3 + 116 * n4 / 45,
            7 * n2 / 3 - 8 * n3 / 5 - 227 * n4 / 45,
            56 * n3 / 15 - 136 * n4 / 35,
            4279 * n4 / 630,
        )
        self.xi0 = self._xi_eta(math.radians(lat0), self.lon0)[0]

    def _xi_eta(self, phi, lam):
        c = self.c
        t = math.sinh(math.atanh(math.sin(phi)) - c * math.atanh(c * math.sin(phi)))
        dl = lam - self.lon0
        xi1 = math.atan2(t, math.cos(dl))
        eta1 = math.asinh(math.sin(dl) / math.hypot(t, math.cos(dl)))
        xi, eta = xi1, eta1
        for j, al in enumerate(self.alfa, start=1):
            xi += al * math.sin(2 * j * xi1) * math.cosh(2 * j * eta1)
            eta += al * math.cos(2 * j * xi1) * math.sinh(2 * j * eta1)
        return xi, eta

    def directa(self, lat, lon):
        """(lat, lon en grados) -> (Este, Norte)"""
        xi, eta = self._xi_eta(math.radians(lat), math.radians(lon))
        return (
            self.fe + self.k0 * self.A * eta,
            self.fn + self.k0 * self.A * (xi - self.xi0),
        )

    def inversa(self, este, norte):
        """(Este, Norte) -> (lat, lon en grados)"""
        xi = (norte - self.fn) / (self.k0 * self.A) + self.xi0
        eta = (este - self.fe) / (self.k0 * self.A)
        xi2, eta2 = xi, eta
        for j, b in enumerate(self.beta, start=1):
            xi2 -= b * math.sin(2 * j * xi) * math.cosh(2 * j * eta)
            eta2 -= b * math.cos(2 * j * xi) * math.sinh(2 * j * eta)
        chi = math.asin(math.sin(xi2) / math.cosh(eta2))
        phi = chi
        for j, d in enumerate(self.delta, start=1):
            phi += d * math.sin(2 * j * chi)
        lam = self.lon0 + math.atan2(math.sinh(eta2), math.cos(xi2))
        return math.degrees(phi), math.degrees(lam)


# ------------------------------------------------------------- sistemas de coordenadas
_LAT0_MAGNA = 4.59620041666667
_ZONAS_MAGNA = {
    3114: ("MAGNA-SIRGAS / Zona Oeste-Oeste (EPSG:3114)", -80.0775079166667),
    3115: ("MAGNA-SIRGAS / Zona Oeste (EPSG:3115)", -77.0775079166667),
    3116: ("MAGNA-SIRGAS / Zona Bogotá (EPSG:3116)", -74.0775079166667),
    3117: ("MAGNA-SIRGAS / Zona Este Central (EPSG:3117)", -71.0775079166667),
    3118: ("MAGNA-SIRGAS / Zona Este (EPSG:3118)", -68.0775079166667),
}
_ALIAS = {
    "wgs84": 4326, "gps": 4326,
    "magna": 4686, "magna sirgas": 4686, "sirgas": 4686,
    "origen nacional": 9377, "origen": 9377,
    "oeste": 3115, "magna oeste": 3115, "cali": 3115,
    "bogota": 3116, "magna bogota": 3116,
    "este central": 3117, "este": 3118, "oeste oeste": 3114, "far west": 3114,
}
_CACHE = {}


def _normalizar(texto):
    t = unicodedata.normalize("NFD", str(texto).strip().lower())
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    t = t.replace("epsg:", "").replace("epsg", "")
    return re.sub(r"[\s_\-/]+", " ", t).strip()


def _sistema(nombre, lat=None, lon=None):
    n = _normalizar(nombre)
    if n == "utm":
        if lat is None or lon is None:
            raise ValueError("'utm' automático solo sirve como sistema de destino.")
        zona = int((lon + 180) // 6) + 1
        n = f"utm {zona}{'n' if lat >= 0 else 's'}"
    m = re.fullmatch(r"utm ?(\d{1,2}) ?([ns])", n)
    if m:
        zona, hem = int(m.group(1)), m.group(2)
        if not 1 <= zona <= 60:
            raise ValueError(f"Zona UTM inválida: {zona}")
        codigo = (32600 if hem == "n" else 32700) + zona
    elif n in _ALIAS:
        codigo = _ALIAS[n]
    elif re.fullmatch(r"\d{4,6}", n):
        codigo = int(n)
    else:
        raise ValueError(f"Sistema no reconocido: '{nombre}'. Usa /sistemas para ver los disponibles.")

    if codigo in _CACHE:
        return _CACHE[codigo]
    if codigo == 4326:
        s = {"codigo": codigo, "nombre": "WGS84 geográficas (EPSG:4326)", "tipo": "geo"}
    elif codigo == 4686:
        s = {"codigo": codigo, "nombre": "MAGNA-SIRGAS geográficas (EPSG:4686)", "tipo": "geo"}
    elif codigo == 9377:
        s = {"codigo": codigo, "nombre": "MAGNA-SIRGAS / Origen Nacional (EPSG:9377)", "tipo": "proy",
             "tm": TM(GRS80, 4.0, -73.0, 0.9992, 5_000_000.0, 2_000_000.0), "lon0": -73.0, "limite": 6.0}
    elif codigo in _ZONAS_MAGNA:
        nom, lon0 = _ZONAS_MAGNA[codigo]
        s = {"codigo": codigo, "nombre": nom, "tipo": "proy",
             "tm": TM(GRS80, _LAT0_MAGNA, lon0, 1.0, 1_000_000.0, 1_000_000.0), "lon0": lon0, "limite": 3.5}
    elif 32601 <= codigo <= 32660 or 32701 <= codigo <= 32760:
        norte = codigo < 32700
        zona = codigo - (32600 if norte else 32700)
        lon0 = -183.0 + 6.0 * zona
        s = {"codigo": codigo, "nombre": f"WGS84 / UTM zona {zona}{'N' if norte else 'S'} (EPSG:{codigo})",
             "tipo": "proy", "tm": TM(WGS84, 0.0, lon0, 0.9996, 500_000.0, 0.0 if norte else 10_000_000.0),
             "lon0": lon0, "limite": 4.0}
    else:
        raise ValueError(f"EPSG:{codigo} no está soportado. Usa /sistemas para ver los disponibles.")
    _CACHE[codigo] = s
    return s


def _a_geo(sis, v1, v2):
    """Entrada del sistema -> (lat, lon). Geográficas: (lat, lon); proyectadas: (Este, Norte)."""
    if sis["tipo"] == "geo":
        if abs(v1) > 90 or abs(v2) > 180:
            raise ValueError("Coordenadas geográficas fuera de rango: usa (latitud, longitud) en grados.")
        return v1, v2
    return sis["tm"].inversa(v1, v2)


def _de_geo(sis, lat, lon):
    return (lat, lon) if sis["tipo"] == "geo" else sis["tm"].directa(lat, lon)


def _aviso(sis, lon):
    if sis["tipo"] == "proy" and abs(lon - sis["lon0"]) > sis["limite"]:
        return (f"\nAviso: el punto está a {abs(lon - sis['lon0']):.1f}° del meridiano central de "
                f"{sis['nombre']}; la distorsión puede ser grande.")
    return ""


# --------------------------------------------------------------------- utilidades
def _num(v):
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    return float(s)


def _par(p):
    if not isinstance(p, (list, tuple)) or len(p) != 2:
        raise ValueError(f"Cada punto debe ser [valor_1, valor_2]; recibí {p}")
    return _num(p[0]), _num(p[1])


def _a_decimal(v):
    """Número, o texto en grados/minutos/segundos (76°31'55.2\"), a grados decimales."""
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    nums = re.findall(r"\d+(?:[.,]\d+)?", s)
    if not nums:
        raise ValueError(f"Ángulo no válido: {v}")
    d = float(nums[0].replace(",", "."))
    m = float(nums[1].replace(",", ".")) if len(nums) > 1 else 0.0
    sg = float(nums[2].replace(",", ".")) if len(nums) > 2 else 0.0
    if m >= 60 or sg >= 60:
        raise ValueError(f"Minutos o segundos fuera de rango en: {v}")
    val = d + m / 60 + sg / 3600
    return -val if s.startswith("-") else val


def _dms(grados):
    signo = "-" if grados < 0 else ""
    g = abs(grados)
    d = int(g)
    m = int((g - d) * 60)
    s = round((g - d - m / 60) * 3600, 2)
    if s >= 60:
        s, m = 0.0, m + 1
    if m >= 60:
        m, d = 0, d + 1
    return f"{signo}{d}°{m:02d}'{s:05.2f}\""


def _rumbo(az):
    if az < 90:
        return f"N {_dms(az)} E"
    if az < 180:
        return f"S {_dms(180 - az)} E"
    if az < 270:
        return f"S {_dms(az - 180)} W"
    return f"N {_dms(360 - az)} W"


def _geodesica(lat1, lon1, lat2, lon2):
    """Problema inverso de Vincenty sobre WGS84: (distancia m, azimut A->B, azimut B->A)."""
    a, f = WGS84
    b = a * (1 - f)
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    L = math.radians(lon2 - lon1)
    U1, U2 = math.atan((1 - f) * math.tan(phi1)), math.atan((1 - f) * math.tan(phi2))
    sU1, cU1, sU2, cU2 = math.sin(U1), math.cos(U1), math.sin(U2), math.cos(U2)
    lam = L
    for _ in range(200):
        sl, cl = math.sin(lam), math.cos(lam)
        ss = math.hypot(cU2 * sl, cU1 * sU2 - sU1 * cU2 * cl)
        if ss == 0:
            return 0.0, 0.0, 0.0
        cs = sU1 * sU2 + cU1 * cU2 * cl
        sigma = math.atan2(ss, cs)
        sa = cU1 * cU2 * sl / ss
        c2a = 1 - sa * sa
        c2sm = cs - 2 * sU1 * sU2 / c2a if c2a != 0 else 0.0
        C = f / 16 * c2a * (4 + f * (4 - 3 * c2a))
        prev = lam
        lam = L + (1 - C) * f * sa * (sigma + C * ss * (c2sm + C * cs * (-1 + 2 * c2sm**2)))
        if abs(lam - prev) < 1e-12:
            break
    else:  # no convergió (puntos casi antípodas): aproximación esférica
        h = math.sin((phi2 - phi1) / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(L / 2) ** 2
        d = 2 * 6371008.8 * math.asin(math.sqrt(h))
        az = math.degrees(math.atan2(math.sin(L) * math.cos(phi2),
                                     math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(L))) % 360
        return d, az, (az + 180) % 360
    u2 = c2a * (a * a - b * b) / (b * b)
    A_ = 1 + u2 / 16384 * (4096 + u2 * (-768 + u2 * (320 - 175 * u2)))
    B_ = u2 / 1024 * (256 + u2 * (-128 + u2 * (74 - 47 * u2)))
    dsig = B_ * ss * (c2sm + B_ / 4 * (cs * (-1 + 2 * c2sm**2)
                                       - B_ / 6 * c2sm * (-3 + 4 * ss**2) * (-3 + 4 * c2sm**2)))
    s = b * A_ * (sigma - dsig)
    az1 = math.degrees(math.atan2(cU2 * sl, cU1 * sU2 - sU1 * cU2 * cl)) % 360
    az2 = math.degrees(math.atan2(cU1 * sl, -sU1 * cU2 + cU1 * sU2 * cl)) % 360
    return s, az1, (az2 + 180) % 360


# ------------------------------------------------------------------ herramientas
def sistemas():
    return (
        "Sistemas disponibles (nombre o EPSG):\n"
        "- wgs84 (4326): geográficas WGS84\n"
        "- magna (4686): geográficas MAGNA-SIRGAS\n"
        "- origen_nacional (9377): MAGNA-SIRGAS Origen Nacional, oficial en Colombia\n"
        "- oeste (3115): MAGNA zona Oeste (Cali y el occidente)\n"
        "- bogota (3116): MAGNA zona Bogotá\n"
        "- este_central (3117), este (3118), oeste_oeste (3114)\n"
        "- utm_18n (32618), utm_17n, utm_19n... o 'utm' para zona automática\n"
        "Geográficas: (latitud, longitud). Proyectadas: (Este, Norte).\n"
        "Nota: WGS84 y MAGNA-SIRGAS se tratan como equivalentes (difieren en centímetros). "
        "Datums antiguos (Bogotá 1975, etc.) no están soportados."
    )


def convertir_coordenadas(valor_1, valor_2, origen, destino):
    o = _sistema(origen)
    lat, lon = _a_geo(o, _num(valor_1), _num(valor_2))
    d = _sistema(destino, lat, lon)
    r1, r2 = _de_geo(d, lat, lon)
    if d["tipo"] == "geo":
        txt = (f"Latitud {r1:.8f}° ({_dms(r1)}), Longitud {r2:.8f}° ({_dms(r2)})\n"
               f"Sistema: {d['nombre']}")
    else:
        txt = f"Este {r1:.3f} m, Norte {r2:.3f} m\nSistema: {d['nombre']}"
    return txt + _aviso(d, lon)


def distancia_azimut(punto_a, punto_b, sistema):
    s = _sistema(sistema)
    (a1, a2), (b1, b2) = _par(punto_a), _par(punto_b)
    if s["tipo"] == "geo":
        dist, az, contra = _geodesica(a1, a2, b1, b2)
        base = "Distancia geodésica sobre el elipsoide"
    else:
        dist = math.hypot(b1 - a1, b2 - a2)
        az = math.degrees(math.atan2(b1 - a1, b2 - a2)) % 360
        contra = (az + 180) % 360
        base = "Distancia horizontal sobre la cuadrícula (no corregida por escala de la proyección)"
    if dist == 0:
        return "Los dos puntos coinciden: distancia 0, azimut indefinido."
    return (f"{base}: {dist:.3f} m\n"
            f"Azimut A->B: {az:.6f}° ({_dms(az)})\n"
            f"Contra-azimut B->A: {contra:.6f}° ({_dms(contra)})\n"
            f"Rumbo A->B: {_rumbo(az)}\nSistema: {s['nombre']}")


def area_poligono(puntos, sistema):
    s = _sistema(sistema)
    pts = [_par(p) for p in puntos]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        raise ValueError("Se necesitan al menos 3 vértices distintos.")
    if s["tipo"] == "geo":
        latc = sum(p[0] for p in pts) / len(pts)
        lonc = sum(p[1] for p in pts) / len(pts)
        local = TM(WGS84, latc, lonc, 1.0, 0.0, 0.0)
        xy = [local.directa(la, lo) for la, lo in pts]
        perim = sum(_geodesica(*pts[i], *pts[(i + 1) % len(pts)])[0] for i in range(len(pts)))
        nota = "Área calculada sobre el elipsoide (proyección local)."
    else:
        xy = pts
        perim = sum(math.hypot(xy[(i + 1) % len(xy)][0] - xy[i][0], xy[(i + 1) % len(xy)][1] - xy[i][1])
                    for i in range(len(xy)))
        nota = "Área sobre la cuadrícula de la proyección; difiere un poco del área sobre el terreno."
    area = abs(sum(xy[i][0] * xy[(i + 1) % len(xy)][1] - xy[(i + 1) % len(xy)][0] * xy[i][1]
                   for i in range(len(xy)))) / 2
    return (f"Área: {area:,.2f} m² = {area / 10000:,.4f} ha ({area / 1e6:,.6f} km²)\n"
            f"Perímetro: {perim:,.3f} m\nVértices: {len(pts)}\n{nota}\nSistema: {s['nombre']}")


def cierre_poligonal(este_inicial, norte_inicial, tramos):
    e0, n0 = _num(este_inicial), _num(norte_inicial)
    legs = []
    for t in tramos:
        if not isinstance(t, (list, tuple)) or len(t) != 2:
            raise ValueError(f"Cada tramo debe ser [distancia, azimut]; recibí {t}")
        legs.append((_num(t[0]), _a_decimal(t[1])))
    if len(legs) < 3:
        raise ValueError("Una poligonal cerrada necesita al menos 3 tramos.")
    perim = sum(d for d, _ in legs)
    if perim <= 0:
        raise ValueError("El perímetro debe ser mayor que 0.")
    raw, e, n = [], e0, n0
    for d, az in legs:
        e += d * math.sin(math.radians(az))
        n += d * math.cos(math.radians(az))
        raw.append((e, n))
    ex, ey = raw[-1][0] - e0, raw[-1][1] - n0
    err = math.hypot(ex, ey)
    prec = "infinita (cierre perfecto)" if err < 1e-9 else f"1:{int(perim / err):,}"
    lineas, cum = [], 0.0
    for k, ((d, _), (re_, rn)) in enumerate(zip(legs, raw), start=1):
        cum += d
        ae, an = re_ - ex * cum / perim, rn - ey * cum / perim
        etiqueta = f"V{k}" if k < len(legs) else f"V{k} (= V0, cierre)"
        lineas.append(f"{etiqueta}: Este {ae:.3f}, Norte {an:.3f}")
    return (f"Perímetro: {perim:.3f} m\nError en Este: {ex:+.4f} m, error en Norte: {ey:+.4f} m\n"
            f"Error lineal de cierre: {err:.4f} m\nPrecisión relativa: {prec}\n"
            f"Coordenadas ajustadas (método de Bowditch / brújula):\n" + "\n".join(lineas) +
            "\nCompara la precisión con la tolerancia de tu norma o contrato.")


def cierre_angular(angulos, tipo="interior", precision_seg=10):
    if tipo not in ("interior", "exterior"):
        raise ValueError("tipo debe ser 'interior' o 'exterior'.")
    ang = [_a_decimal(a) for a in angulos]
    n = len(ang)
    if n < 3:
        raise ValueError("Se necesitan al menos 3 ángulos.")
    teorica = (n - 2) * 180 if tipo == "interior" else (n + 2) * 180
    err_seg = (sum(ang) - teorica) * 3600
    tol = _num(precision_seg) * math.sqrt(n)
    corr = -err_seg / n
    corregidos = ", ".join(_dms(a + corr / 3600) for a in ang)
    return (f"Ángulos: {n} ({tipo}es)\nSuma observada: {_dms(sum(ang))}\nSuma teórica: {_dms(teorica)}\n"
            f"Error angular de cierre: {err_seg:+.1f}\"\n"
            f"Tolerancia (a·√n con a={_num(precision_seg):g}\"): ±{tol:.1f}\" -> "
            f"{'CUMPLE' if abs(err_seg) <= tol else 'NO CUMPLE, repetir mediciones'}\n"
            f"Corrección por ángulo: {corr:+.2f}\"\nÁngulos corregidos: {corregidos}")


def nivelacion(cota_inicial, lecturas, cota_final_conocida=None, distancia_km=None, mm_por_raiz_km=10):
    cota = _num(cota_inicial)
    filas, calc = [], []
    for k, par in enumerate(lecturas, start=1):
        va, vd = _par(par)
        hi = cota + va
        cota = hi - vd
        calc.append(cota)
        filas.append((k, va, vd, hi, cota))
    n = len(calc)
    if n == 0:
        raise ValueError("Faltan lecturas [vista_atrás, vista_adelante].")
    salida = [f"Desnivel total: {calc[-1] - _num(cota_inicial):+.4f} m", f"Cota final calculada: {calc[-1]:.4f} m"]
    err = 0.0
    if cota_final_conocida is not None:
        err = calc[-1] - _num(cota_final_conocida)
        salida.append(f"Error de cierre: {err * 1000:+.1f} mm")
        if distancia_km is not None:
            tol = _num(mm_por_raiz_km) * math.sqrt(_num(distancia_km))
            salida.append(f"Tolerancia ({_num(mm_por_raiz_km):g} mm·√km, {_num(distancia_km):g} km): "
                          f"±{tol:.1f} mm -> {'CUMPLE' if abs(err * 1000) <= tol else 'NO CUMPLE'}")
            salida.append("Verifica el coeficiente mm·√km con la norma de tu proyecto.")
    salida.append("Cotas (sin ajustar -> ajustadas):")
    for k, va, vd, hi, c in filas:
        ajustada = c - err * k / n
        salida.append(f"Estación {k}: VA {va:.3f}, VD {vd:.3f}, cota {c:.4f} -> {ajustada:.4f} m")
    return "\n".join(salida)


def elevacion_punto(latitud, longitud):
    try:
        r = requests.get("https://api.open-meteo.com/v1/elevation",
                         params={"latitude": _num(latitud), "longitude": _num(longitud)}, timeout=10)
        r.raise_for_status()
        elev = r.json()["elevation"][0]
    except (requests.RequestException, KeyError, IndexError, ValueError):
        return "No pude consultar la elevación en este momento."
    return (f"Elevación aproximada: {elev:.0f} m s. n. m. (modelo digital de ~90 m de resolución; "
            "sirve de referencia, NO para trabajos de ingeniería).")


def gsd_dron(ancho_sensor_mm, distancia_focal_mm, ancho_imagen_px, alto_imagen_px,
             altura_m=None, gsd_deseado_cm=None, area_ha=None, traslape_frontal=0.8, traslape_lateral=0.7):
    sw, f = _num(ancho_sensor_mm), _num(distancia_focal_mm)
    wpx, hpx = _num(ancho_imagen_px), _num(alto_imagen_px)
    if min(sw, f, wpx, hpx) <= 0:
        raise ValueError("Sensor, focal y resolución deben ser mayores que 0.")
    if altura_m is None and gsd_deseado_cm is None:
        raise ValueError("Indica altura_m o gsd_deseado_cm.")
    h = _num(altura_m) if altura_m is not None else _num(gsd_deseado_cm) / 100 * f * wpx / sw
    gsd = h * sw / (f * wpx)  # m/px
    huella_w, huella_h = gsd * wpx, gsd * hpx
    out = [f"Altura de vuelo: {h:.1f} m", f"GSD: {gsd * 100:.2f} cm/px",
           f"Huella de cada foto: {huella_w:.1f} m (ancho) x {huella_h:.1f} m (alto)"]
    if area_ha is not None:
        fr, la = _num(traslape_frontal), _num(traslape_lateral)
        if not (0 <= fr < 1 and 0 <= la < 1):
            raise ValueError("Los traslapes van entre 0 y 0.99.")
        dx, dy = huella_h * (1 - fr), huella_w * (1 - la)
        fotos = math.ceil(_num(area_ha) * 10000 / (dx * dy))
        out += [f"Separación entre fotos: {dx:.1f} m; entre líneas de vuelo: {dy:.1f} m",
                f"Fotos estimadas para {_num(area_ha):g} ha: ~{fotos} (suma ~20% por bordes)",
                "Supone la imagen apaisada con su lado largo perpendicular a la línea de vuelo."]
    out.append("Verifica la normativa vigente de la Aerocivil y la altura máxima permitida antes de volar.")
    return "\n".join(out)


def convertir_angulo(valor, a="decimal"):
    dec = _a_decimal(valor)
    return _dms(dec) if str(a).lower() == "dms" else f"{dec:.8f}°"


# ------------------------------------------------------- definición para el modelo
def _tool(nombre, descripcion, props, req=()):
    return {"type": "function", "function": {
        "name": nombre, "description": descripcion,
        "parameters": {"type": "object", "properties": props, "required": list(req)}}}


_N = {"type": "number"}
_S = {"type": "string"}
_PTO = {"type": "array", "items": _N, "description": "[valor_1, valor_2]"}

TOOLS = [
    _tool("convertir_coordenadas",
          "Convierte coordenadas entre sistemas. Geográficas: valor_1=latitud, valor_2=longitud. "
          "Proyectadas: valor_1=Este, valor_2=Norte. Sistemas: wgs84, magna, origen_nacional, oeste, "
          "bogota, este_central, este, utm_18n; 'utm' (solo destino) elige la zona.",
          {"valor_1": _N, "valor_2": _N, "origen": _S, "destino": _S},
          ["valor_1", "valor_2", "origen", "destino"]),
    _tool("distancia_azimut",
          "Distancia y azimut entre dos puntos. Geográficas [lat, lon]; proyectadas [Este, Norte].",
          {"punto_a": _PTO, "punto_b": _PTO, "sistema": _S}, ["punto_a", "punto_b", "sistema"]),
    _tool("area_poligono", "Área y perímetro de un polígono. Puntos [[v1, v2], ...] en orden.",
          {"puntos": {"type": "array", "items": _PTO}, "sistema": _S}, ["puntos", "sistema"]),
    _tool("cierre_poligonal",
          "Cierre y ajuste (Bowditch) de una poligonal cerrada. tramos: [[distancia_m, azimut], ...]; "
          "azimut en grados decimales o texto DMS. El último tramo vuelve al punto inicial.",
          {"este_inicial": _N, "norte_inicial": _N, "tramos": {"type": "array", "items": {"type": "array"}}},
          ["este_inicial", "norte_inicial", "tramos"]),
    _tool("cierre_angular",
          "Error de cierre angular de una poligonal. angulos: números decimales o texto DMS.",
          {"angulos": {"type": "array"}, "tipo": {"type": "string", "enum": ["interior", "exterior"]},
           "precision_seg": _N}, ["angulos"]),
    _tool("nivelacion",
          "Nivelación geométrica. lecturas: [[vista_atras, vista_adelante], ...] por estación.",
          {"cota_inicial": _N, "lecturas": {"type": "array", "items": {"type": "array"}},
           "cota_final_conocida": _N, "distancia_km": _N, "mm_por_raiz_km": _N},
          ["cota_inicial", "lecturas"]),
    _tool("elevacion_punto", "Elevación aproximada (~90 m de resolución) de un punto WGS84.",
          {"latitud": _N, "longitud": _N}, ["latitud", "longitud"]),
    _tool("gsd_dron",
      "GSD, altura de vuelo, huella. Da altura_m o gsd_deseado_cm. IMPORTANTE: ancho_imagen_px es el PRIMER numero de WxH (ej 5472 de 5472x3648), alto_imagen_px es el segundo (3648).",
          {"ancho_sensor_mm": _N, "distancia_focal_mm": _N, "ancho_imagen_px": _N, "alto_imagen_px": _N,
           "altura_m": _N, "gsd_deseado_cm": _N, "area_ha": _N, "traslape_frontal": _N, "traslape_lateral": _N},
          ["ancho_sensor_mm", "distancia_focal_mm", "ancho_imagen_px", "alto_imagen_px"]),
    _tool("convertir_angulo", "Convierte un ángulo entre grados decimales y grados-minutos-segundos.",
          {"valor": {"type": "string", "description": "ángulo como texto: 76.5 o 76°30'00\""}, "a": {"type": "string", "enum": ["decimal", "dms"]}},
          ["valor", "a"]),
]

FUNCIONES = {
    "convertir_coordenadas": convertir_coordenadas,
    "distancia_azimut": distancia_azimut,
    "area_poligono": area_poligono,
    "cierre_poligonal": cierre_poligonal,
    "cierre_angular": cierre_angular,
    "nivelacion": nivelacion,
    "elevacion_punto": elevacion_punto,
    "gsd_dron": gsd_dron,
    "convertir_angulo": convertir_angulo,
}


def ejecutar(nombre, args):
    """Ejecuta una herramienta y devuelve texto (nunca lanza errores de datos)."""
    fn = FUNCIONES.get(nombre)
    if fn is None:
        return f"Herramienta desconocida: {nombre}"
    try:
        return fn(**args)
    except TypeError as e:
        return f"Parámetros inválidos para {nombre}: {e}"
    except (ValueError, ZeroDivisionError, OverflowError) as e:
        return f"No pude calcular: {e}"
