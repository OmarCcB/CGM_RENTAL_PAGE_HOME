import os
import re
import json
import unicodedata
import logging
import smtplib
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ── GeoIP via Cloudflare proxy ────────────────────────────────────────────────
def _detect_country_from_ip(_ip: str = None) -> str:
    """Devuelve 'pe' o 'ar' usando el header CF-IPCountry de Cloudflare.
    Fallback: None  →  la ruta raíz usará DEFAULT_COUNTRY."""
    from flask import request as _req
    cf = _req.headers.get("CF-IPCountry", "").strip().upper()
    # XX = Cloudflare no detectó país  |  T1 = Tor
    if cf and cf not in ("XX", "T1"):
        return {"PE": "pe", "AR": "ar"}.get(cf)
    return None

from flask import (Flask, render_template, redirect, url_for, request,
                   session, jsonify, abort, g)
from flask_compress import Compress
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from dotenv import load_dotenv

from countries import COUNTRIES, DEFAULT_COUNTRY
from database import get_conn, init_db, init_admin_tables
import cache as _cache
import db_sqlserver
from pais_codigos import PAISES_CELULAR, PAISES_POR_ISO, validar_celular, codigo_default

load_dotenv()

# ── Security logger ──────────────────────────────────────────────────────────
security_logger = logging.getLogger("security")
security_logger.setLevel(logging.WARNING)
_sec_handler = logging.StreamHandler()
_sec_handler.setFormatter(logging.Formatter("[SECURITY] %(asctime)s  %(message)s"))
security_logger.addHandler(_sec_handler)

app = Flask(__name__)

# A02 — Secret key: no fallback inseguro en producción
_secret = os.getenv("FLASK_SECRET_KEY")
if not _secret:
    if os.getenv("FLASK_DEBUG", "").lower() in ("true", "1", "yes"):
        _secret = "cgm-dev-secret-SOLO-LOCAL"
    else:
        raise RuntimeError(
            "FLASK_SECRET_KEY no está configurada. "
            "Defínela como variable de entorno antes de iniciar la aplicación."
        )
app.secret_key = _secret

# A07 — Session timeout: 8 horas
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)

Compress(app)

# A08 — CSRF protection global
csrf = CSRFProtect(app)

# A04 — Rate limiting (por IP real detrás de proxy/Cloudflare)
def _get_real_ip():
    return (request.headers.get("CF-Connecting-IP")
            or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or request.remote_addr)

limiter = Limiter(
    app=app,
    key_func=_get_real_ip,
    default_limits=["120 per minute"],
    storage_uri="memory://",
)

# ── Admin blueprint ───────────────────────────────────────────────────────────
from admin.routes import admin_bp
app.register_blueprint(admin_bp)

# ── Categorías de productos ────────────────────────────────────────────────────
CATEGORIAS = {
    "alquiler":                                  ("alquiler", None,              None,                    "Alquiler"),
    "alquiler/construccion":                     ("alquiler", "Construcción",    None,                    "Construcción"),
    "alquiler/construccion/excavadora":          ("alquiler", "Construcción",    "Excavadora",            "Excavadoras"),
    "alquiler/construccion/cargador-frontal":    ("alquiler", "Construcción",    "Cargador Frontal",      "Cargadores Frontales"),
    "alquiler/construccion/tractor-de-orugas":   ("alquiler", "Construcción",    "Tractor de Orugas",     "Tractores de Orugas"),
    "alquiler/construccion/rodillo-compactador": ("alquiler", "Construcción",    "Rodillo Compactador",   "Rodillos Compactadores"),
    "alquiler/construccion/motoniveladora":      ("alquiler", "Construcción",    "Motoniveladora",        "Motoniveladoras"),
    "alquiler/construccion/retroexcavadora":     ("alquiler", "Construcción",    "Retroexcavadora",       "Retroexcavadoras"),
    "alquiler/construccion/minicargador":        ("alquiler", "Construcción",    "Minicargador",          "Minicargadores"),
    "alquiler/construccion/camion-cisterna":     ("alquiler", "Construcción",    "Camión Cisterna",       "Camiones Cisterna"),
    "alquiler/construccion/camion-grua":         ("alquiler", "Construcción",    "Camión Grúa",           "Camiones Grúa"),
    "alquiler/construccion/compresora":          ("alquiler", "Construcción",    "Compresora",            "Compresoras"),
    "alquiler/construccion/torre-de-iluminacion":("alquiler", "Construcción",    "Torre de Iluminación",  "Torres de Iluminación"),
    "alquiler/construccion/aditamentos":         ("alquiler", "Construcción",    "Aditamento",            "Aditamentos"),
    "alquiler/mineria":                          ("alquiler", "Mediana Minería", None,                    "Minería"),
    "alquiler/agricola":                         ("alquiler", "Agrícola",        None,                    "Agrícola"),
    "alquiler/energia":                          ("alquiler", "Energía",         None,                    "Energía"),
    "alquiler/construccion/camion-volquete":        ("alquiler", "Construcción",    "Camión Volquete",       "Camiones Volquete"),
    "alquiler/construccion/micropavimentadora":     ("alquiler", "Construcción",    "Micropavimentadora",    "Micropavimentadoras"),
    "alquiler/construccion/pavimentadora":          ("alquiler", "Construcción",    "Pavimentadora",         "Pavimentadoras"),
    "alquiler/construccion/autohormigonera":        ("alquiler", "Construcción",    "Autohormigonera",       "Autohormigoneras"),
    "alquiler/construccion/tren-de-chancado":       ("alquiler", "Construcción",    "Tren de Chancado",      "Tren de Chancado"),
    "alquiler/energia/grupo-electrogeno":           ("alquiler", "Energía",         "Generador",             "Grupos Electrógenos"),
    "alquiler/energia/compresora":                  ("alquiler", "Energía",         "Compresora",            "Compresoras"),
    "alquiler/energia/aditamentos":                 ("alquiler", "Energía",         "Aditamento",            "Aditamentos Energía"),
    "alquiler/agricola/aditamentos":                ("alquiler", "Agrícola",        "Aditamento",            "Aditamentos"),
    "usados":                                    ("usados",   None,              None,                    "Equipos Usados"),
    "usados/construccion":                       ("usados",   "Construcción",    None,                    "Usados Construcción"),
    "usados/agricola":                           ("usados",   "Agrícola",        None,                    "Usados Agrícola"),
    "usados/energia":                            ("usados",   "Energía",         None,                    "Usados Energía"),
}

PARTNERS = ["AJANI.svg", "COSAPI.svg", "CUMBRA.svg", "MOTA-ENGIL.svg",
            "MUR.svg", "SAN-MARTIN.svg", "STRACON.svg"]

# Orden y slugs de unidades para el sidebar de filtros
UNIDAD_NAV = [
    ("Construcción",    "construccion"),
    ("Agrícola",        "agricola"),
    ("Energía",         "energia"),
    ("Mediana Minería", "mineria"),
]

# ── Helpers ────────────────────────────────────────────────────────────────────

def get_country(code):
    """Devuelve datos del país mezclando countries.py con overrides de site_config (BD)
    y sucursales dinámicas de sucursales_db.
    El resultado se cachea 60s; el admin lo invalida explícitamente al guardar cambios."""
    cache_key = f"country:{code}"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached

    base = dict(COUNTRIES.get(code, COUNTRIES[DEFAULT_COUNTRY]))
    try:
        conn = get_conn()
        # Overrides simples (telefono, email, redes, youtube_video, etc.)
        rows = conn.execute(
            "SELECT key, value FROM site_config WHERE country_code=? AND value IS NOT NULL AND value != ''",
            (code,)
        ).fetchall()
        for r in rows:
            base[r["key"]] = r["value"]
        # Sucursales dinámicas: si hay registros en sucursales_db, reemplazan las de countries.py
        suc_rows = conn.execute(
            "SELECT nombre, tipo, direccion, telefono, lat, lng, maps_url "
            "FROM sucursales_db WHERE country_code=? ORDER BY orden",
            (code,)
        ).fetchall()
        if suc_rows:
            base["sucursales"] = [
                {
                    "nombre":    s["nombre"],
                    "tipo":      s["tipo"],
                    "direccion": s["direccion"],
                    "telefono":  s["telefono"] or "",
                    "lat":       s["lat"],
                    "lng":       s["lng"],
                    "maps_url":  s["maps_url"] or "",
                }
                for s in suc_rows
            ]
        conn.close()
    except Exception:
        pass

    _cache.set(cache_key, base)
    return base


def get_banners(country_code):
    """Devuelve {slot: filename} fusionando entradas globales ('*') con overrides por país.
    Las entradas country_code=país sobreescriben las globales para el mismo slot.
    El resultado se cachea 60s; el admin lo invalida explícitamente al guardar cambios."""
    cache_key = f"banners:{country_code or '*'}"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached

    try:
        conn = get_conn()
        rows = conn.execute(
            "SELECT slot, filename FROM banners_config WHERE country_code='*' AND activo=1"
        ).fetchall()
        result = {r["slot"]: r["filename"] for r in rows}
        if country_code:
            rows_cc = conn.execute(
                "SELECT slot, filename FROM banners_config WHERE country_code=? AND activo=1",
                (country_code,)
            ).fetchall()
            for r in rows_cc:
                result[r["slot"]] = r["filename"]
        conn.close()
        _cache.set(cache_key, result)
        return result
    except Exception:
        return {}


def send_email(subject, body, to=None):
    to = to or os.getenv("EMAIL_DESTINO", "contacto@cgmrental.com")
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    if not smtp_user or not smtp_pass:
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = smtp_user
        msg["To"] = to
        msg.attach(MIMEText(body, "html", "utf-8"))
        with smtplib.SMTP(smtp_host, smtp_port) as s:
            s.ehlo()
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.sendmail(smtp_user, [to], msg.as_string())
        return True
    except Exception:
        return False


# Unidades no habilitadas para Argentina (se muestran como "Próximamente")
UNIDADES_PROXIMAMENTE_ARG = {"Agrícola", "Energía"}

PER_PAGE = 12


def _unidad_clause(unidad, col="unidad"):
    """SQL fragment + params para coincidir con unidad que puede ser pipe-separada.
    Ej: unidad='Construcción' hace match con 'Construcción', 'Mediana Minería|Construcción', etc.
    """
    return (
        f"({col} = ? OR {col} LIKE ? OR {col} LIKE ? OR {col} LIKE ?)",
        [unidad, f"{unidad}|%", f"%|{unidad}|%", f"%|{unidad}"]
    )

def get_products_for_cat(tags, unidad, tipo, extra_tipo=None, country=None, proximamente=False, page=1):
    """Consulta SQLite filtrando por tags, unidad y tipo. Retorna (productos, total)."""
    conn = get_conn()
    clauses = ["activo = 1", "tags LIKE ?"]
    params = [f"%{tags}%"]
    if unidad:
        ucl, upr = _unidad_clause(unidad)
        clauses.append(ucl)
        params.extend(upr)
    if tipo:
        clauses.append("tipo = ?")
        params.append(tipo)
    elif extra_tipo:
        clauses.append("tipo = ?")
        params.append(extra_tipo)
    if country == 'ar' and not proximamente:
        clauses.append("show_arg = 1")
    elif country != 'ar':
        clauses.append("show_pe = 1")
    where = f"WHERE {' AND '.join(clauses)}"
    total = conn.execute(f"SELECT COUNT(*) FROM products {where}", params).fetchone()[0]
    offset = (page - 1) * PER_PAGE
    rows = conn.execute(
        f"SELECT * FROM products {where} ORDER BY nombre LIMIT {PER_PAGE} OFFSET {offset}",
        params
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows], total


def _cart_key(country=None):
    """Devuelve la clave de sesión del carrito para el país dado."""
    cc = (country or 'pe').lower()
    return f"cart_{cc}"

def cart_count(country=None):
    return sum(item["qty"] for item in session.get(_cart_key(country), {}).values())


# ── Inicializar BD al arrancar ────────────────────────────────────────────────
def seed_db():
    """Siembra productos y posts SOLO si las tablas correspondientes están vacías.
    La BD SQLite local es la fuente de verdad — nunca se sobreescriben filas existentes.

    Si la BD ya tiene datos (caso normal en producción) esta función es un no-op.
    Sirve únicamente como seed para entornos nuevos/vacíos.
    """
    conn = get_conn()

    # Products — solo sembrar si la tabla está vacía
    try:
        n_products = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    except Exception:
        n_products = -1

    if n_products == 0:
        products_file = os.path.join(os.path.dirname(__file__), "products.json")
        if os.path.exists(products_file):
            with open(products_file, encoding="utf-8") as f:
                products = json.load(f)
            for p in products:
                try:
                    conn.execute(
                        """INSERT INTO products
                           (slug,nombre,marca,descripcion,descripcion_texto,
                            ficha_url,tags,tipo,unidad,imagen,activo,show_arg)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (p["slug"], p["nombre"], p.get("marca",""),
                         p.get("descripcion",""), p.get("descripcion_texto",""),
                         p.get("ficha_url",""), p.get("tags",""), p.get("tipo",""),
                         p.get("unidad",""), p.get("imagen",""),
                         p.get("activo", 1), p.get("show_arg", 0))
                    )
                except Exception:
                    pass   # ignora duplicados o errores aislados
            conn.commit()

    # Blog posts
    if conn.execute("SELECT COUNT(*) FROM blog_posts").fetchone()[0] == 0:
        posts = [
            {
                "slug": "tka-y-cgm-rental-alianza-gruas-peru",
                "titulo": "TKA y CGM Rental: La Alianza Estratégica que Revoluciona el Mercado de Grúas en Perú",
                "categoria": "entrevistas",
                "fecha": "2024-12-20",
                "imagen": "blog/tka-elias-pelin-fiorese.png",
                "extracto": "Entrevista con Elías Pelin Fiorese, Gerente de Exportaciones de TKA. La empresa tiene el 30% del mercado brasileño de grúas y ahora apuesta por Perú de la mano de CGM Rental.",
                "contenido": """<p>En una entrevista exclusiva, Elías Pelin Fiorese, Gerente de Exportaciones de TKA, reveló los detalles de la alianza estratégica con CGM Rental para ingresar al mercado peruano de grúas.</p>
<h3>TKA: Líderes en el Mercado Brasileño</h3>
<p>TKA posee el 30% del mercado brasileño de grúas articuladas, fabricadas bajo los más exigentes estándares europeos EN12999. Sus equipos cuentan con GPS y WiFi para monitoreo remoto en tiempo real, una ventaja competitiva crucial en obras de gran envergadura.</p>
<h3>La Alianza con CGM Rental</h3>
<p>La alianza con CGM Rental abre las puertas del mercado peruano para TKA. CGM Rental, con su red de sucursales a nivel nacional y su experiencia en el sector, garantiza la disponibilidad de los equipos y el soporte técnico especializado que los clientes necesitan.</p>
<h3>Tecnología de Vanguardia</h3>
<p>Las grúas TKA incorporan sistemas de monitoreo remoto vía GPS y WiFi, permitiendo a los operadores y supervisores controlar el estado de los equipos desde cualquier lugar. Además, cumplen con las normativas europeas más estrictas, garantizando la máxima seguridad en obra.</p>""",
                "video_url": "https://www.youtube.com/watch?v=5dpT1XJRFrM",
                "activo": 1
            },
            {
                "slug": "tomas-spana-john-deere-innovacion-peru",
                "titulo": "Tomás Spana de John Deere: Innovación y Cercanía para el Mercado de Maquinaria Pesada en Perú",
                "categoria": "entrevistas",
                "fecha": "2024-12-20",
                "imagen": "blog/Entrevista-Tomas-Spana.png",
                "extracto": "Tomás Spana, Director de Marketing de John Deere Latinoamérica, habla sobre las tendencias del mercado minero peruano y la modalidad de alquiler como alternativa flexible.",
                "contenido": """<p>Tomás Spana, Director de Marketing de John Deere para Latinoamérica, compartió su visión sobre el mercado peruano de maquinaria pesada y la importancia de la modalidad de alquiler.</p>
<h3>El Mercado Minero Peruano</h3>
<p>Perú es uno de los principales mercados mineros de Latinoamérica, con proyectos de gran envergadura que demandan equipos de alta productividad y confiabilidad. John Deere ha desarrollado una línea específica para las condiciones extremas de la minería a gran altitud.</p>
<h3>El Alquiler como Alternativa Estratégica</h3>
<p>El mercado está evolucionando hacia el alquiler como modalidad preferida por las empresas que buscan flexibilidad operativa y optimización de recursos. CGM Rental, como aliado estratégico de John Deere en Perú, ofrece esta alternativa con el respaldo de la marca más reconocida del sector.</p>
<h3>Innovación Tecnológica</h3>
<p>John Deere continúa invirtiendo en tecnología, incorporando conectividad, telemetría avanzada y sistemas de gestión de flotas que permiten maximizar la productividad y minimizar el tiempo de inactividad.</p>""",
                "video_url": "https://www.youtube.com/watch?v=o3LySEWQtNs",
                "activo": 1
            },
            {
                "slug": "cgm-rental-cusco-sucursal-sur-peru",
                "titulo": "CGM Rental Cusco: Conoce Nuestra Sucursal y su Impacto en el Sur del Perú",
                "categoria": "articulos",
                "fecha": "2025-03-31",
                "imagen": "blog/Sucursal_de_cusco.jpg",
                "extracto": "Recorre nuestra sucursal de Cusco, ubicada en Carretera Cusco-Urcos Km 16.5 Oropesa. Más de 10 años de experiencia atendiendo proyectos en el sur del país.",
                "contenido": """<p>La sucursal de CGM Rental en Cusco se ha consolidado como el principal proveedor de maquinaria pesada en la macro región sur del Perú, con más de 10 años de experiencia atendiendo los más importantes proyectos de construcción e infraestructura de la región.</p>
<h3>Ubicación Estratégica</h3>
<p>Ubicada en la Carretera Cusco-Urcos Km 16.5, Oropesa, la sucursal cuenta con amplio espacio para el almacenamiento y mantenimiento de equipos, garantizando disponibilidad inmediata para los proyectos de la región.</p>
<h3>Recorrido con Luis Jiménez</h3>
<p>Luis Jiménez, jefe de la sucursal, nos guió por las instalaciones mostrando el taller de mantenimiento con sus cinco fases: recepción de equipos, evaluación técnica, reparación especializada, control de calidad y despacho. Un proceso riguroso que garantiza la máxima disponibilidad mecánica.</p>
<h3>Cobertura Regional</h3>
<p>La sucursal de Cusco atiende proyectos en toda la macro región sur, incluyendo Apurímac, Madre de Dios y Puno, con una flota diversa de excavadoras, cargadores frontales, tractores de orugas y equipos especializados para construcción y minería.</p>""",
                "video_url": "",
                "activo": 1
            },
            {
                "slug": "camiones-daf-ipesa-entrega-cgm-rental",
                "titulo": "Estrategia y Rendimiento en la Entrega Oficial de Camiones DAF a CGM Rental",
                "categoria": "articulos",
                "fecha": "2025-04-09",
                "imagen": "blog/luis-galvez_entrevista_camiones.jpg",
                "extracto": "Entrega oficial de 16 camiones DAF a CGM Rental. Luis Enrique Galvez de Ipesa Camiones explica las ventajas de los DAF para operaciones en altitud.",
                "contenido": """<p>CGM Rental incorporó a su flota 16 nuevas unidades de camiones DAF, en un acto oficial de entrega que contó con la presencia de ejecutivos de Ipesa Camiones y los principales directivos de CGM Rental.</p>
<h3>Los Camiones DAF en Altura</h3>
<p>Luis Enrique Galvez, representante de Ipesa Camiones, destacó las ventajas de los camiones DAF para operaciones en la sierra peruana. Con motor de 11 litros y 410 HP, estos camiones mantienen su rendimiento óptimo incluso a más de 4,000 metros de altura sobre el nivel del mar.</p>
<h3>Ergonomía y Confort</h3>
<p>Las cabinas ergonómicas de los DAF están diseñadas para garantizar el máximo confort del operador en jornadas largas, con sistemas de climatización avanzados y asientos con suspensión neumática que reducen la fatiga.</p>
<h3>Liderazgo Global</h3>
<p>DAF es líder en ventas en Europa y Brasil, con una reconocida trayectoria de confiabilidad y bajo costo de mantenimiento. Esta incorporación fortalece la flota de CGM Rental para atender proyectos que requieren transporte pesado en condiciones extremas.</p>""",
                "video_url": "",
                "activo": 1
            },
            {
                "slug": "cgm-rental-arequipa-sucursal",
                "titulo": "CGM Rental en Arequipa: Descubre Nuestra Sucursal y su Impacto en el Sur del País",
                "categoria": "articulos",
                "fecha": "2025-04-10",
                "imagen": "blog/Sucursal_de_arequipa.jpg",
                "extracto": "6 años de operación en Arequipa. Gianfranco Escobar lidera una sucursal que atiende construcción, agricultura y energía en el sur del país.",
                "contenido": """<p>La sucursal de CGM Rental en Arequipa cumplió 6 años de operaciones consolidándose como referente en alquiler de maquinaria pesada en el sur del Perú.</p>
<h3>Instalaciones de Primer Nivel</h3>
<p>Ubicada estratégicamente en la Vía de Evitamiento Km 4.1, Irrigación Zamacola, Cerro Colorado, la sucursal cuenta con un moderno taller de mantenimiento y amplias instalaciones para almacenamiento de equipos.</p>
<h3>Liderazgo de Gianfranco Escobar</h3>
<p>Bajo la dirección de Gianfranco Escobar como jefe de sucursal, el equipo ha logrado posicionar a CGM Rental como el proveedor preferido en la región, atendiendo los sectores de construcción, agricultura y energía con soluciones integrales.</p>
<h3>Impacto Regional</h3>
<p>La sucursal de Arequipa ha participado en los principales proyectos de infraestructura de la región, contribuyendo al desarrollo de vías, edificaciones y proyectos agrícolas que impulsan la economía del sur del Perú.</p>""",
                "video_url": "",
                "activo": 1
            },
            {
                "slug": "jorge-canedo-paccar-trucks-camiones-daf",
                "titulo": "Excelencia en el Transporte: Jorge Cañedo de Paccar Trucks Analiza el Rendimiento de Camiones DAF",
                "categoria": "entrevistas",
                "fecha": "2025-04-10",
                "imagen": "blog/Jorge_canedo_entrevista_ventas_paccar.jpg",
                "extracto": "Jorge Cañedo, Director de Ventas de Paccar Trucks, analiza el impacto de 10 nuevas unidades DAF CF410 6x4 con tanques de agua y grúas articuladas para CGM Rental.",
                "contenido": """<p>Jorge Cañedo, Director de Ventas para Centroamérica y la Región Andina de Paccar Trucks, compartió su análisis sobre el desempeño de los camiones DAF en las condiciones más exigentes del mercado peruano.</p>
<h3>Las Nuevas Unidades DAF CF410</h3>
<p>CGM Rental incorporó 10 nuevas unidades DAF CF410 6×4, equipadas con tanques de agua y grúas articuladas. Estas configuraciones especiales están diseñadas para atender las necesidades específicas de proyectos de construcción que requieren suministro de agua y capacidad de carga simultánea.</p>
<h3>El Motor MX-11: Potencia y Eficiencia</h3>
<p>El motor MX-11 de 410 HP y 2,100 Nm de torque garantiza el máximo rendimiento en cualquier condición, desde el nivel del mar hasta las más altas altitudes. Su eficiencia en el consumo de combustible reduce significativamente los costos operativos.</p>
<h3>Soporte Técnico Integral</h3>
<p>Paccar Trucks ofrece soporte técnico integral a través de su red de concesionarios, garantizando la máxima disponibilidad de los equipos y minimizando los tiempos de inactividad.</p>""",
                "video_url": "",
                "activo": 1
            },
            {
                "slug": "cgm-rental-innovacion-industria-alquiler",
                "titulo": "CGM Rental: Innovación y Compromiso que Transforman la Industria del Alquiler de Maquinaria",
                "categoria": "articulos",
                "fecha": "2025-05-13",
                "imagen": "blog/industria_alquiler_de_maquinaria_cgmrental.png",
                "extracto": "Publicado en la revista Perú Construye. CGM Rental lidera la transformación del sector con estrategias de diversificación, expansión y tecnología.",
                "contenido": """<p>CGM Rental ha construido un camino sólido en el sector del alquiler de maquinaria pesada, atendiendo los sectores de minería, construcción, agricultura y energía con una propuesta de valor integral que combina flota moderna, soporte técnico especializado y disponibilidad mecánica garantizada.</p>
<h3>Estrategia de Diversificación</h3>
<p>La estrategia de diversificación de CGM Rental abarca los cuatro pilares fundamentales de la economía peruana: construcción, minería, agricultura y energía. Esta diversificación permite a la empresa mantenerse robusta ante las fluctuaciones de cada sector.</p>
<h3>Expansión de Operaciones</h3>
<p>Con 8 sucursales a nivel nacional, CGM Rental garantiza presencia y soporte técnico en las principales zonas económicas del país. La reciente apertura de la sucursal de Piura consolida la presencia en el norte del Perú.</p>
<h3>Tecnología y Sostenibilidad</h3>
<p>La incorporación de tecnología de monitoreo satelital, mantenimiento predictivo y equipos de última generación posiciona a CGM Rental como líder en innovación dentro del sector del alquiler de maquinaria pesada en el Perú.</p>""",
                "video_url": "",
                "activo": 1
            },
            {
                "slug": "cgm-rental-piura-nueva-sucursal",
                "titulo": "Conoce la Nueva Sucursal de CGM Rental en Piura: Innovación y Servicio en el Norte del Perú",
                "categoria": "articulos",
                "fecha": "2025-05-14",
                "imagen": "blog/nueva_sucursal_piura.png",
                "extracto": "Nueva sucursal en Zona Industrial J1-J2, Piura. Inaugurada en 2025, atiende los sectores de construcción, agricultura y energía en el norte del país.",
                "contenido": """<p>CGM Rental inauguró su nueva sucursal en Piura, estratégicamente ubicada en la Zona Industrial J1-J2, Mz B Lt. 13, Distrito Veintiséis de Octubre, fortaleciendo su presencia en el norte del Perú.</p>
<h3>Infraestructura de Primer Nivel</h3>
<p>La nueva sucursal cuenta con modernas instalaciones que incluyen oficinas comerciales para atención personalizada, zona logística para recepción y despacho de equipos, y un taller especializado con sistemas de control de calidad que garantizan la máxima disponibilidad mecánica.</p>
<h3>Sectores Atendidos</h3>
<p>La sucursal de Piura está diseñada para atender los principales sectores productivos de la región: construcción de infraestructura vial y civil, agricultura de gran escala en los valles piuranos, y proyectos de energía que impulsan el desarrollo regional.</p>
<h3>Compromiso con el Norte</h3>
<p>Esta nueva apertura reafirma el compromiso de CGM Rental con el desarrollo del norte del Perú, poniendo a disposición de los empresarios y contratistas de la región la misma calidad de servicio y flota moderna que caracteriza a la empresa a nivel nacional.</p>""",
                "video_url": "",
                "activo": 1
            },
            {
                "slug": "rodillos-compactadores-infraestructura-vial",
                "titulo": "Rodillos Compactadores: La Clave para una Infraestructura Vial Segura y Duradera",
                "categoria": "articulos",
                "fecha": "2025-06-18",
                "imagen": "blog/Rodillos_compactadores_Hamm.png",
                "extracto": "Jaime Boza Arlotti, Gerente General de CGM Rental, explica cómo los rodillos HAMM alemanes garantizan la calidad en la compactación vial.",
                "contenido": """<p>Jaime Boza Arlotti, Gerente General de CGM Rental, comparte su expertise sobre el uso de rodillos compactadores en proyectos de infraestructura vial, destacando las ventajas de la tecnología HAMM alemana.</p>
<h3>La Importancia de la Compactación</h3>
<p>La compactación es uno de los procesos más críticos en la construcción de infraestructura vial. Una compactación deficiente puede resultar en asentamientos, deformaciones y deterioro prematuro del pavimento, con graves consecuencias para la seguridad vial y los costos de mantenimiento.</p>
<h3>Tecnología HAMM: Excelencia Alemana</h3>
<p>Los rodillos HAMM, fabricados en Alemania, representan lo mejor de la tecnología de compactación. Con equipos que van desde apisonadoras ligeras hasta modelos de 25 toneladas, la flota de CGM Rental puede atender proyectos de cualquier escala.</p>
<h3>Sistemas Avanzados</h3>
<p>Los rodillos HAMM incorporan sistemas diésel-hidráulicos de alta eficiencia, monitoreo satelital para seguimiento en tiempo real y la exclusiva tecnología de oscilación que permite la compactación efectiva incluso en áreas sensibles a las vibraciones, como puentes y zonas urbanas.</p>""",
                "video_url": "",
                "activo": 1
            },
            {
                "slug": "javier-ugaz-ipesa-tendencias-john-deere",
                "titulo": "Innovación en Maquinaria Pesada: Javier Ugaz de Ipesa Analiza el Crecimiento y Tendencias",
                "categoria": "entrevistas",
                "fecha": "2025-06-20",
                "imagen": "blog/entrevista_javier_ugaz.png",
                "extracto": "Javier Ugaz, Gerente Comercial de Ipesa División Construcción y Minería, analiza el mercado con 33 años de experiencia y el 17% de market share.",
                "contenido": """<p>Javier Ugaz, Gerente Comercial de la División de Construcción y Minería de Ipesa, compartió su análisis del mercado peruano de maquinaria pesada con más de 33 años de experiencia en el sector.</p>
<h3>Ipesa: 45 Años de Trayectoria</h3>
<p>Con 45 años en el mercado peruano e Ipesa mantiene el 17% de market share en equipos de construcción, una posición de liderazgo que refleja la confianza de los clientes en la calidad y el servicio de la empresa.</p>
<h3>Tendencias del Mercado</h3>
<p>Si bien el mercado peruano históricamente ha preferido la propiedad sobre el alquiler, la tendencia está cambiando. Las empresas están reconociendo las ventajas del alquiler: sin inversión inicial, mantenimiento incluido, y la flexibilidad para adaptar la flota a cada proyecto.</p>
<h3>La Alianza con CGM Rental</h3>
<p>La alianza entre Ipesa y CGM Rental representa una combinación ganadora: la calidad y tecnología de John Deere con la experiencia y red de soporte de CGM Rental. Una propuesta de valor integral que ningún competidor puede igualar en el mercado peruano.</p>""",
                "video_url": "",
                "activo": 1
            },
            {
                "slug": "consejos-alquilar-excavadoras-ricardo-olivos",
                "titulo": "¿Vas a Alquilar una Excavadora? Descubre los Consejos Clave de CGM Rental",
                "categoria": "entrevistas",
                "fecha": "2025-10-06",
                "imagen": "blog/Foto-portada.png",
                "extracto": "Ricardo Olivos, Gerente Comercial de CGM Rental, guía a los clientes en la selección del tipo, potencia y eficiencia de excavadora ideal para cada proyecto.",
                "contenido": """<p>Ricardo Olivos, Gerente Comercial de CGM Rental, comparte los consejos clave que todo cliente debe considerar antes de alquilar una excavadora, basados en años de experiencia atendiendo proyectos de todos los tamaños y complejidades.</p>
<h3>Tipo de Excavadora: Orugas vs. Ruedas</h3>
<p>La primera decisión es el tipo de desplazamiento. Las excavadoras de orugas son ideales para terrenos irregulares, fangosos o con pendientes, mientras que las de ruedas son perfectas para trabajos en superficies pavimentadas o cuando se requiere movilidad entre puntos distantes.</p>
<h3>Potencia y Tonelaje</h3>
<p>CGM Rental cuenta con una flota que va desde los 21 toneladas hasta los 120 toneladas para proyectos de gran minería. Los modelos más solicitados son los de 21 y 36 toneladas, que ofrecen el mejor equilibrio entre potencia y versatilidad para proyectos de construcción.</p>
<h3>Marcas de Confianza</h3>
<p>La flota de CGM Rental incluye exclusivamente marcas de primer nivel: John Deere y Hitachi, garantizando la máxima confiabilidad, disponibilidad mecánica y soporte técnico especializado para cada proyecto.</p>
<h3>Consideraciones de Seguridad</h3>
<p>La seguridad es prioritaria en toda operación. CGM Rental entrega todos sus equipos con inspección técnica completa, certificaciones vigentes y operadores capacitados disponibles si el cliente lo requiere.</p>""",
                "video_url": "",
                "activo": 1
            }
        ]
        for p in posts:
            try:
                conn.execute(
                    "INSERT INTO blog_posts (slug,titulo,categoria,fecha,imagen,extracto,contenido,video_url,activo) VALUES (?,?,?,?,?,?,?,?,?)",
                    (p["slug"], p["titulo"], p["categoria"], p["fecha"], p["imagen"],
                     p["extracto"], p["contenido"], p.get("video_url",""), p["activo"])
                )
            except Exception:
                pass
        conn.commit()
    conn.close()


def cleanup_hero_slots(conn):
    """Limpieza one-shot: elimina filas duplicadas o huérfanas en banners_config
    para slots de hero/slide-N. Específicamente, elimina filas con group_name
    'Home Hero' cuando ya existe un grupo principal con otro nombre — esto
    recupera la BD de un mal estado introducido por una versión previa.

    NO crea nuevos slots. La creación/eliminación de slots hero se hace
    desde el panel admin (ver admin/routes.py → banners_hero_add / banners_hero_remove).
    """
    try:
        principal = conn.execute(
            "SELECT 1 FROM banners_config "
            "WHERE slot LIKE 'hero/slide-%' "
            "AND group_name IS NOT NULL AND group_name != '' "
            "AND group_name != 'Home Hero' "
            "LIMIT 1"
        ).fetchone()
        if principal:
            conn.execute(
                "DELETE FROM banners_config "
                "WHERE slot LIKE 'hero/slide-%' "
                "AND group_name = 'Home Hero'"
            )
            conn.commit()
    except Exception as _e:
        app.logger.warning(f"cleanup_hero_slots: {_e}")


with app.app_context():
    init_db()
    seed_db()
    _admin_conn = get_conn()
    init_admin_tables(_admin_conn)
    # Limpieza de duplicados huérfanos creados por versiones previas
    cleanup_hero_slots(_admin_conn)
    _admin_conn.close()
    # ── SQL Server: crear tablas si no existen ────────────────────────────────
    if os.getenv("SQL_SERVER"):
        try:
            db_sqlserver.init_tables()
        except Exception as _e:
            app.logger.warning(f"SQL Server init skipped: {_e}")

# ── Conexión compartida por request (una sola por request vía g) ─────────────
@app.teardown_appcontext
def _close_db_conn(e=None):
    """Cierra la conexión compartida al terminar cada request."""
    conn = g.pop('_db_conn', None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass

# ── Timing middleware (debug) ─────────────────────────────────────────────────
import time as _time

@app.before_request
def _start_timer():
    if not request.path.startswith('/static'):
        session.permanent = True
    g._req_start = _time.perf_counter()

@app.after_request
def _log_timing(response):
    if hasattr(g, '_req_start'):
        elapsed = (_time.perf_counter() - g._req_start) * 1000
        # Solo loguear rutas de página, no estáticos
        if not request.path.startswith('/static'):
            print(f"[TIMING] {request.method} {request.path}  →  {elapsed:.0f} ms", flush=True)
    return response


@app.after_request
def _cache_headers(response):
    """Añade headers de cache HTTP para mejorar TTFB en visitas repetidas.

    - Archivos estáticos (CSS/JS/imágenes/fuentes): 1 año inmutable en browser.
    - Páginas HTML GET exitosas: 30s en CDN Cloudflare (s-maxage), privado en browser.
      Esto permite que Cloudflare sirva desde su edge (TTFB ~50ms) en lugar de
      llegar al servidor Flask en Lima (~400ms+).
    - Rutas de admin, carrito y POST: sin cache.
    """
    path = request.path

    # ── Assets estáticos ─────────────────────────────────────────────────────
    if path.startswith('/static/'):
        if response.status_code == 200 and 'Cache-Control' not in response.headers:
            # CSS, JS y fuentes: nunca cambian de nombre → 1 año inmutable
            if any(path.startswith(p) for p in ('/static/css/', '/static/js/', '/static/fonts/')):
                response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
            # Imágenes subidas por admin (banners, productos): pueden cambiar con mismo nombre
            # → 5 minutos. Suficiente para CDN pero el admin ve cambios rápido.
            elif any(path.startswith(p) for p in ('/static/images/banners/', '/static/products/')):
                response.headers['Cache-Control'] = 'public, max-age=300'
            # Resto de imágenes estáticas (logos, íconos): 7 días
            else:
                response.headers['Cache-Control'] = 'public, max-age=604800'
        return response

    # ── Páginas HTML: cache corto en CDN, no en browser ──────────────────────
    if (request.method == 'GET'
            and response.status_code == 200
            and response.content_type.startswith('text/html')
            and '/admin' not in path
            and '/carrito' not in path
            and 'Cache-Control' not in response.headers):
        # s-maxage: Cloudflare cachea 30s; max-age=0: browser siempre revalida
        response.headers['Cache-Control'] = 'public, s-maxage=30, max-age=0'
        response.headers['Vary'] = 'Cookie'

    return response


# A05 — Security headers
@app.after_request
def _security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    if request.is_secure:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response


# ── Categorías dinámicas (desde BD) ──────────────────────────────────────────
def get_nav_categorias():
    """Devuelve dict 'tag|unidad_slug' → [lista de filas] para el nav.
    Resultado cacheado 120 s; el admin invalida al guardar."""
    cache_key = "nav_categorias"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached
    result = {}
    ok = False
    try:
        conn = get_conn()
        rows = conn.execute(
            "SELECT * FROM categorias WHERE activo=1 ORDER BY tag, unidad_slug, orden"
        ).fetchall()
        for row in rows:
            key = f"{row['tag']}|{row['unidad_slug']}"
            result.setdefault(key, []).append(dict(row))
        conn.close()
        ok = True
    except Exception:
        pass
    if ok:                          # Fix 7: no cachear si hubo error de BD
        _cache.set(cache_key, result)
    return result


# ── Context Processor ──────────────────────────────────────────────────────────
@app.context_processor
def inject_globals():
    # Detectar el país activo desde la URL (e.g. /pe/, /ar/)
    path_parts = request.path.strip('/').split('/')
    cc = path_parts[0] if path_parts and path_parts[0] in COUNTRIES else 'pe'
    bans = get_banners(cc)

    def burl(slot, fallback=None):
        """Devuelve la URL estática completa del banner para el slot dado."""
        from flask import url_for as _uf
        if fallback is None:
            fallback = slot + ".webp"
        filename = bans.get(slot, fallback)
        return _uf("static", filename="images/banners/" + filename)

    def burl_mobile(slot, fallback=None):
        """Devuelve la URL de la versión mobile (800px) del banner para el slot dado.
        El archivo se llama igual que el principal pero con sufijo _mobile antes de la extensión."""
        from flask import url_for as _uf
        import os as _os
        if fallback is None:
            fallback = slot + ".webp"
        filename = bans.get(slot, fallback)
        stem, ext = _os.path.splitext(filename)
        mobile_filename = stem + "_mobile" + ext
        return _uf("static", filename="images/banners/" + mobile_filename)

    from datetime import datetime as _dt
    return {
        "cart_count": cart_count(cc),
        "COUNTRIES": COUNTRIES,
        "PARTNERS": PARTNERS,
        "banners": bans,
        "burl": burl,
        "burl_mobile": burl_mobile,
        "now": _dt.now(),
        "nav_cats": get_nav_categorias(),
        # Canonical URL: usa la URL base sin querystring (evita duplicados por UTM, etc.)
        # Las vistas pueden sobreescribir esto pasando canonical_url=... a render_template
        "canonical_url": request.base_url,
        # Cloudflare Turnstile site key (para inyectar en formularios)
        "CF_TURNSTILE_SITE_KEY": CF_TURNSTILE_SITE_KEY,
        # Códigos telefónicos de todos los países (para selector de celular)
        "PAISES_CELULAR": PAISES_CELULAR,
        "PAIS_CELULAR_DEFAULT": codigo_default(cc),
    }

# ══════════════════════════════════════════════════════════════════════════════
# RUTAS
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def root():
    # Obtener IP real (Nginx pasa X-Forwarded-For)
    ip = (request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
          or request.remote_addr)
    detected = _detect_country_from_ip(ip)
    country = detected if detected else DEFAULT_COUNTRY
    return redirect(f"/{country}/")


@app.route("/<country>/")
def home(country):
    c = get_country(country)
    if country not in COUNTRIES:
        return redirect(f"/{DEFAULT_COUNTRY}/")
    conn = get_conn()
    # 6 productos activos de alquiler — aleatorios en Python (evita ORDER BY NEWID() que es lento)
    country_col = "show_arg" if country == 'ar' else "show_pe"
    all_featured = conn.execute(
        f"SELECT * FROM products WHERE activo=1 AND tags LIKE ? AND {country_col}=1",
        ('%alquiler%',)
    ).fetchall()
    import random as _random
    featured = _random.sample(all_featured, min(6, len(all_featured)))
    # Últimas 6 noticias
    posts = conn.execute(
        f"SELECT * FROM blog_posts WHERE activo=1 AND {country_col}=1 ORDER BY fecha DESC"
    ).fetchall()
    conn.close()

    # Slots de hero a renderizar (dinámico, ordenado numéricamente).
    # Lee banners_config para detectar todos los hero/slide-N activos. Si la BD
    # aún no tiene slots (entorno fresh), fallback a slide-1..4 por defecto.
    bans = get_banners(country)
    hero_slots = sorted(
        [k for k in bans.keys() if k.startswith("hero/slide-")],
        key=lambda s: int(s.split("-")[-1]) if s.split("-")[-1].isdigit() else 9999
    )
    if not hero_slots:
        hero_slots = [f"hero/slide-{i}" for i in range(1, 5)]

    return render_template("pages/home.html",
                           country=c, country_code=country,
                           featured=[dict(r) for r in featured],
                           posts=[dict(r) for r in posts],
                           hero_slots=hero_slots)


@app.route("/<country>/nosotros/")
def nosotros(country):
    if country not in COUNTRIES:
        return redirect(f"/{DEFAULT_COUNTRY}/nosotros/")
    c = get_country(country)
    return render_template("pages/nosotros.html", country=c, country_code=country)


@app.route("/<country>/nuestros-locales/")
def nuestros_locales(country):
    if country not in COUNTRIES:
        return redirect(f"/{DEFAULT_COUNTRY}/nuestros-locales/")
    c = get_country(country)
    return render_template("pages/nuestros_locales.html", country=c, country_code=country)


@app.route("/<country>/contacto/")
def contacto(country):
    if country not in COUNTRIES:
        return redirect(f"/{DEFAULT_COUNTRY}/contacto/")
    c = get_country(country)
    return render_template("pages/contacto.html", country=c, country_code=country)


@app.route("/<country>/gracias/")
def gracias(country):
    if country not in COUNTRIES:
        return redirect(f"/{DEFAULT_COUNTRY}/gracias/")
    c = get_country(country)
    return render_template("pages/gracias.html", country=c, country_code=country)


@app.route("/<country>/leasing-operativo/")
def leasing(country):
    if country not in COUNTRIES:
        return redirect(f"/{DEFAULT_COUNTRY}/leasing-operativo/")
    c = get_country(country)
    return render_template("pages/leasing.html", country=c, country_code=country)


@app.route("/<country>/novedades/")
@app.route("/<country>/novedades/page/<int:p>/")
def blog_list(country, p=1):
    if country not in COUNTRIES:
        return redirect(f"/{DEFAULT_COUNTRY}/novedades/")
    c = get_country(country)
    PER_PAGE = 6
    cat_filter = request.args.get("cat", "")
    conn = get_conn()
    country_filter = " AND show_arg=1" if country == 'ar' else " AND show_pe=1"
    if cat_filter:
        total = conn.execute(
            f"SELECT COUNT(*) FROM blog_posts WHERE activo=1 AND categoria=?{country_filter}", (cat_filter,)
        ).fetchone()[0]
        posts = conn.execute(
            f"SELECT * FROM blog_posts WHERE activo=1 AND categoria=?{country_filter} ORDER BY fecha DESC LIMIT ? OFFSET ?",
            (cat_filter, PER_PAGE, (p - 1) * PER_PAGE)
        ).fetchall()
    else:
        total = conn.execute(f"SELECT COUNT(*) FROM blog_posts WHERE activo=1{country_filter}").fetchone()[0]
        posts = conn.execute(
            f"SELECT * FROM blog_posts WHERE activo=1{country_filter} ORDER BY fecha DESC LIMIT ? OFFSET ?",
            (PER_PAGE, (p - 1) * PER_PAGE)
        ).fetchall()
    conn.close()
    pages = (total + PER_PAGE - 1) // PER_PAGE
    return render_template("pages/blog_list.html",
                           country=c, country_code=country,
                           posts=[dict(r) for r in posts],
                           page=p, pages=pages, cat_filter=cat_filter)


@app.route("/<country>/novedades/<slug>/")
def blog_post(country, slug):
    if country not in COUNTRIES:
        return redirect(f"/{DEFAULT_COUNTRY}/novedades/{slug}/")
    c = get_country(country)
    conn = get_conn()
    country_col = "show_arg" if country == 'ar' else "show_pe"
    post = conn.execute(
        f"SELECT * FROM blog_posts WHERE slug=? AND activo=1 AND {country_col}=1", (slug,)
    ).fetchone()
    conn.close()
    if not post:
        abort(404)
    return render_template("pages/blog_post.html",
                           country=c, country_code=country, post=dict(post))


# Categoría con o sin prefijo de país
@app.route("/categoria-producto/<path:cat_path>/")
def categoria_legacy(cat_path):
    """URL legacy sin prefijo de país → 301 a la canónica del país default."""
    return redirect(f"/{DEFAULT_COUNTRY}/categoria-producto/{cat_path}/", code=301)


@app.route("/<country>/categoria-producto/<path:cat_path>/")
def categoria(country, cat_path=""):
    if country not in COUNTRIES:
        return redirect(f"/{DEFAULT_COUNTRY}/categoria-producto/{cat_path}/", code=301)
    c = get_country(country)
    if cat_path in CATEGORIAS:
        tags, unidad, tipo, titulo = CATEGORIAS[cat_path]
    else:
        # Intentar buscar ruta dinámica en tabla categorias (slug_sub)
        parts = cat_path.rstrip("/").split("/")
        cat_row = None
        if len(parts) == 3:
            _tag, _unidad_slug, _slug_sub = parts
            try:
                _conn = get_conn()
                cat_row = _conn.execute(
                    "SELECT * FROM categorias WHERE tag=? AND unidad_slug=? AND slug_sub=? AND activo=1",
                    (_tag, _unidad_slug, _slug_sub)
                ).fetchone()
                _conn.close()
            except Exception:
                pass
        if cat_row:
            tags, unidad, tipo, titulo = (
                cat_row["tag"], cat_row["unidad"], cat_row["tipo"], cat_row["tipo_titulo"]
            )
        else:
            abort(404)
    extra_tipo = request.args.get("tipo")
    page = max(1, request.args.get("page", 1, type=int))
    proximamente = country == 'ar' and unidad in UNIDADES_PROXIMAMENTE_ARG
    products, total = get_products_for_cat(tags, unidad, tipo, extra_tipo, country=country, proximamente=proximamente, page=page)
    total_pages = (total + PER_PAGE - 1) // PER_PAGE

    conn = get_conn()
    arg_filter = " AND show_arg=1" if country == 'ar' else " AND show_pe=1"

    # ── Conteo por unidad (misma etiqueta) ──
    unidad_counts = {}
    for u_name, u_slug in UNIDAD_NAV:
        path = f"{tags}/{u_slug}"
        if path in CATEGORIAS:
            _, u_db, _, _ = CATEGORIAS[path]
            ucl, upr = _unidad_clause(u_db)
            cnt = conn.execute(
                f"SELECT COUNT(*) FROM products WHERE activo=1 AND tags=? AND {ucl}{arg_filter}",
                [tags] + upr
            ).fetchone()[0]
            unidad_counts[u_name] = {"count": cnt, "path": path}

    # ── Conteo total por etiqueta ──
    tag_counts = {
        "alquiler": conn.execute(f"SELECT COUNT(*) FROM products WHERE activo=1 AND tags='alquiler'{arg_filter}").fetchone()[0],
        "usados":   conn.execute(f"SELECT COUNT(*) FROM products WHERE activo=1 AND tags='usados'{arg_filter}").fetchone()[0],
    }

    # ── URL de la etiqueta opuesta manteniendo unidad ──
    other_tag = "usados" if tags == "alquiler" else "alquiler"
    if unidad and "/" in cat_path:
        unidad_slug_last = cat_path.split("/")[1] if "/" in cat_path else cat_path.split("/")[-1]
        other_tag_path = f"{other_tag}/{unidad_slug_last}"
        if other_tag_path not in CATEGORIAS:
            other_tag_path = other_tag
    else:
        other_tag_path = other_tag

    # ── Conteo por tipo (Maquinaria) ──
    tipo_counts = {}
    if unidad:
        ucl_t, upr_t = _unidad_clause(unidad)
        all_tipos = conn.execute(
            f"SELECT DISTINCT tipo FROM products WHERE activo=1 AND {ucl_t}{arg_filter} ORDER BY tipo",
            upr_t
        ).fetchall()
        for row in all_tipos:
            t = row["tipo"]
            ucl_t2, upr_t2 = _unidad_clause(unidad)
            cnt = conn.execute(
                f"SELECT COUNT(*) FROM products WHERE activo=1 AND tags=? AND {ucl_t2} AND tipo=?{arg_filter}",
                [tags] + upr_t2 + [t]
            ).fetchone()[0]
            tipo_counts[t] = cnt

    conn.close()

    return render_template("pages/categoria.html",
                           country=c, country_code=country,
                           cat_path=cat_path, titulo=titulo,
                           products=products,
                           tags=tags, unidad=unidad,
                           tipo_sel=tipo or extra_tipo or "",
                           unidad_counts=unidad_counts,
                           tag_counts=tag_counts,
                           other_tag=other_tag,
                           other_tag_path=other_tag_path,
                           tipo_counts=tipo_counts,
                           UNIDAD_NAV=UNIDAD_NAV,
                           proximamente=proximamente,
                           page=page,
                           total_pages=total_pages,
                           total=total)


# Producto individual
@app.route("/producto/<slug>/")
def producto_legacy(slug):
    """URL legacy sin prefijo de país → 301 a la canónica del país default."""
    return redirect(f"/{DEFAULT_COUNTRY}/producto/{slug}/", code=301)


@app.route("/<country>/producto/<slug>/")
def producto(slug, country):
    if country not in COUNTRIES:
        return redirect(f"/{DEFAULT_COUNTRY}/producto/{slug}/", code=301)
    c = get_country(country)
    conn = get_conn()
    p = conn.execute("SELECT * FROM products WHERE slug=? AND activo=1", (slug,)).fetchone()
    if not p:
        conn.close()
        abort(404)
    prod = dict(p)
    # Parse descripción como lista de features (soporta | y array serializado)
    desc_raw = prod.get("descripcion", "") or ""
    features = [f.strip() for f in desc_raw.split("|") if f.strip()]
    prod["features"] = features
    # ficha_url puede venir como ficha_tecnica en importaciones antiguas
    prod["ficha_url"] = prod.get("ficha_url") or prod.get("ficha_tecnica") or ""
    # ── Productos relacionados con sistema de prioridades ──────────────────
    arg_filter = "AND show_arg = 1" if country == 'ar' else "AND show_pe = 1"
    p_tipo   = prod.get("tipo", "")
    p_unidad = prod.get("unidad", "")
    p_tags   = prod.get("tags", "")
    # Usar la primera unidad para matching de relacionados (soporta multi-unidad pipe-sep)
    p_unidad_main = p_unidad.split("|")[0].strip() if p_unidad else ""

    # Prioridad 1: mismo tipo + misma unidad + mismo tag (aleatorio en Python)
    ucl_r1, upr_r1 = _unidad_clause(p_unidad_main)
    cands1 = conn.execute(f"""
        SELECT slug, nombre, marca, imagen, descripcion, tipo, unidad
        FROM products
        WHERE activo=1 AND slug != ?
          AND tipo = ? AND {ucl_r1} AND tags LIKE ? {arg_filter}
    """, [slug, p_tipo] + upr_r1 + [f"%{p_tags}%"]).fetchall()
    import random as _random
    nivel1 = _random.sample(cands1, min(3, len(cands1)))

    slugs_vistos = {slug} | {r["slug"] for r in nivel1}

    # Prioridad 2: mismo tag + misma unidad, distinto tipo (aleatorio en Python)
    limite_n2 = 6 - len(nivel1)
    ucl_r2, upr_r2 = _unidad_clause(p_unidad_main)
    cands2 = conn.execute(f"""
        SELECT slug, nombre, marca, imagen, descripcion, tipo, unidad
        FROM products
        WHERE activo=1 AND slug NOT IN ({','.join('?'*len(slugs_vistos))})
          AND tags LIKE ? AND {ucl_r2} AND tipo != ? {arg_filter}
    """, [*slugs_vistos, f"%{p_tags}%"] + upr_r2 + [p_tipo]).fetchall()
    nivel2 = _random.sample(cands2, min(limite_n2, len(cands2)))

    slugs_vistos |= {r["slug"] for r in nivel2}

    relacionados = [dict(r) for r in list(nivel1) + list(nivel2)]
    conn.close()

    # ── Galería dinámica: leer imágenes reales del disco en el orden correcto ──
    img_folder = os.path.join(app.root_path, "static", "products", slug)
    imagenes = []
    if os.path.isdir(img_folder):
        all_files = [f for f in os.listdir(img_folder)
                     if f.lower().endswith((".webp", ".jpg", ".jpeg", ".png"))]
        orden = []
        raw_orden = prod.get("imagenes_orden")
        if raw_orden:
            try:
                orden = json.loads(raw_orden)
            except Exception:
                orden = []
        if orden:
            files_set = set(all_files)
            ordered   = [f for f in orden if f in files_set]
            remaining = sorted([f for f in all_files if f not in set(orden)],
                               key=lambda x: (0, int(os.path.splitext(x)[0]))
                               if os.path.splitext(x)[0].isdigit() else (1, x))
            imagenes = ordered + remaining
        else:
            def _natural(name):
                base = os.path.splitext(name)[0]
                try:
                    return (0, int(base))
                except ValueError:
                    return (1, base.lower())
            imagenes = sorted(all_files, key=_natural)

    proximamente = country == 'ar' and prod.get("unidad") in UNIDADES_PROXIMAMENTE_ARG
    return render_template("pages/producto.html",
                           country=c, country_code=country, product=prod,
                           relacionados=relacionados, proximamente=proximamente,
                           imagenes=imagenes)


@app.route("/producto/<slug>/ficha/")
def ficha_tecnica_legacy(slug):
    """URL legacy sin prefijo de país → 301 a la canónica del país default."""
    return redirect(f"/{DEFAULT_COUNTRY}/producto/{slug}/ficha/", code=301)


@app.route("/<country>/producto/<slug>/ficha/")
def ficha_tecnica(slug, country):
    import os as _os
    if country not in COUNTRIES:
        return redirect(f"/{DEFAULT_COUNTRY}/producto/{slug}/ficha/", code=301)
    c = get_country(country)
    conn = get_conn()
    p = conn.execute("SELECT * FROM products WHERE slug=? AND activo=1", (slug,)).fetchone()
    conn.close()
    if not p:
        abort(404)
    prod = dict(p)
    # Verificar si existe la ficha local usando ficha_url del registro
    ficha_url = prod.get("ficha_url") or ""
    if ficha_url and not ficha_url.startswith("http"):
        # ficha_url puede ser '/static/products/slug/file.pdf' (nuevo) o solo 'filename.pdf' (legado)
        if ficha_url.startswith("/static/"):
            local_path = _os.path.join(app.root_path, ficha_url.lstrip("/"))
        else:
            local_path = _os.path.join(app.static_folder, "docs", ficha_url)
        has_local = _os.path.exists(local_path)
        if has_local:
            ficha_pdf_url = ficha_url if ficha_url.startswith("/static/") else f"/static/docs/{ficha_url}"
        else:
            ficha_pdf_url = ficha_url
    else:
        has_local = False
        ficha_pdf_url = ficha_url
    return render_template("pages/ficha_tecnica.html",
                           country=c, country_code=country, product=prod,
                           has_local=has_local, ficha_pdf_url=ficha_pdf_url)


@app.route("/<country>/carrito/")
def carrito(country):
    if country not in COUNTRIES:
        return redirect(f"/{DEFAULT_COUNTRY}/carrito/")
    c = get_country(country)
    cart = session.get(_cart_key(country), {})
    return render_template("pages/carrito.html",
                           country=c, country_code=country, cart=cart)


@app.route("/<country>/canal-de-denuncias/")
def canal_denuncias(country):
    if country not in COUNTRIES:
        return redirect(f"/{DEFAULT_COUNTRY}/canal-de-denuncias/")
    c = get_country(country)
    return render_template("pages/canal_denuncias.html", country=c, country_code=country)


ISO_DATA = {
    "9001":  {"titulo": "ISO 9001", "subtitulo": "Gestión de Calidad",
              "descripcion": "La norma ISO 9001 establece los criterios para un sistema de gestión de la calidad. CGM Rental aplica esta norma para garantizar que sus productos y servicios cumplen consistentemente con los requisitos de los clientes.",
              "badge": "sig/iso-9001.svg", "pdf": "docs/iso-9001.pdf", "color": "#02534c"},
    "14001": {"titulo": "ISO 14001", "subtitulo": "Gestión Ambiental",
              "descripcion": "La norma ISO 14001 especifica los requisitos para un sistema de gestión ambiental eficaz. CGM Rental se compromete con la protección del medio ambiente y la reducción del impacto de sus operaciones.",
              "badge": "sig/iso-14001.svg", "pdf": "docs/iso-14001.pdf", "color": "#02534c"},
    "45001": {"titulo": "ISO 45001", "subtitulo": "Seguridad y Salud Ocupacional",
              "descripcion": "La norma ISO 45001 proporciona un marco para mejorar la seguridad de los trabajadores, reducir los riesgos laborales y crear condiciones de trabajo más seguras. CGM Rental prioriza el bienestar de cada colaborador.",
              "badge": "sig/iso-45001.svg", "pdf": "docs/iso-45001.pdf", "color": "#02534c"},
    "37001": {"titulo": "ISO 37001", "subtitulo": "Sistema Antisoborno",
              "descripcion": "La norma ISO 37001 especifica las medidas que una organización puede implementar para prevenir, detectar y abordar el soborno. CGM Rental mantiene los más altos estándares de integridad y ética empresarial.",
              "badge": "sig/iso-37001.svg", "pdf": "docs/iso-37001.pdf", "color": "#02534c"},
}

# OCULTO TEMPORALMENTE — ruta individual de certificaciones ISO
# Se mantiene para uso futuro. Los badges ahora abren modal con PDF directo.
# @app.route("/<country>/certificaciones/iso-<codigo>/")
# def certificacion_iso(country, codigo):
#     if country not in COUNTRIES:
#         return redirect(f"/{DEFAULT_COUNTRY}/certificaciones/iso-{codigo}/")
#     if codigo not in ISO_DATA:
#         return redirect(f"/{DEFAULT_COUNTRY}/")
#     c = get_country(country)
#     return render_template("pages/certificacion_iso.html",
#                            country=c, country_code=country,
#                            iso=ISO_DATA[codigo], codigo=codigo)


# OCULTO TEMPORALMENTE — página política integrada
# Se mantiene para uso futuro. El PDF ahora se abre en modal directo.
# @app.route("/<country>/politica-integrada/")
# def politica_integrada(country):
#     if country not in COUNTRIES:
#         return redirect(f"/{DEFAULT_COUNTRY}/politica-integrada/")
#     c = get_country(country)
#     return render_template("pages/politica_integrada.html", country=c, country_code=country)


@app.route("/<country>/capacita/")
def capacita(country):
    if country not in COUNTRIES:
        return redirect(f"/{DEFAULT_COUNTRY}/capacita/")
    c = get_country(country)
    return render_template("pages/capacita.html", country=c, country_code=country)


@app.route("/<country>/portalproveedores/")
def portal_proveedores(country):
    return redirect("https://portalproveedores.cgmrental.com", code=302)


# ── SITEMAP ────────────────────────────────────────────────────────────────────

@app.route("/robots.txt")
def robots():
    content = "User-agent: *\nAllow: /\nSitemap: https://cgmrental.com/sitemap.xml\n"
    return content, 200, {"Content-Type": "text/plain"}


@app.route("/sitemap.xml")
def sitemap():
    BASE = "https://cgmrental.com"

    # Páginas estáticas por país
    static_pages = [
        "",           # home
        "nosotros",
        "contacto",
        "leasing-operativo",
        "novedades",
        "capacita",
        "carrito",
        "canal-de-denuncias",
    ]

    urls = []

    for country_code in COUNTRIES:
        # Páginas estáticas
        for page in static_pages:
            path = f"/{country_code}/{page}/" if page else f"/{country_code}/"
            urls.append({"loc": BASE + path, "priority": "1.0" if not page else "0.8"})

        # Categorías de productos activos
        conn = get_conn()
        arg_filter = "AND show_arg = 1" if country_code == "ar" else "AND show_pe = 1"
        categorias = conn.execute(
            f"SELECT DISTINCT tags FROM products WHERE activo=1 AND tags != '' {arg_filter}"
        ).fetchall()
        for row in categorias:
            tag = row["tags"]
            urls.append({
                "loc": f"{BASE}/{country_code}/categoria-producto/{tag}/",
                "priority": "0.8"
            })

        # Productos activos individuales (con imagen para Google Image Sitemap)
        productos = conn.execute(
            f"SELECT slug, nombre, imagen FROM products WHERE activo=1 {arg_filter}"
        ).fetchall()
        for row in productos:
            entry = {
                "loc": f"{BASE}/{country_code}/producto/{row['slug']}/",
                "priority": "0.9",
            }
            if row["imagen"]:
                entry["image_loc"] = f"{BASE}/static/products/{row['imagen']}"
                entry["image_title"] = row["nombre"]
            urls.append(entry)
        conn.close()

    # Render XML con namespace de imágenes
    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
        '        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">',
    ]
    for u in urls:
        parts = ['  <url>',
                 f'    <loc>{u["loc"]}</loc>',
                 f'    <priority>{u.get("priority","0.8")}</priority>']
        if u.get("image_loc"):
            title_escaped = u["image_title"].replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
            parts.append('    <image:image>')
            parts.append(f'      <image:loc>{u["image_loc"]}</image:loc>')
            parts.append(f'      <image:title>{title_escaped}</image:title>')
            parts.append('    </image:image>')
        parts.append('  </url>')
        xml_lines.extend(parts)
    xml_lines.append("</urlset>")

    return "\n".join(xml_lines), 200, {"Content-Type": "application/xml; charset=utf-8"}


# ── API ────────────────────────────────────────────────────────────────────────

@app.route("/api/contacto", methods=["POST"])
@limiter.limit("5 per minute")
def api_contacto():
    data = request.get_json(silent=True) or request.form.to_dict()
    nombre   = data.get("nombre", "").strip()
    empresa  = data.get("empresa", "").strip()
    email    = data.get("email", "").strip()
    telefono = data.get("telefono", "").strip()
    tipo     = data.get("tipo", "").strip()
    mensaje  = data.get("mensaje", "").strip()
    pais     = data.get("pais", DEFAULT_COUNTRY)
    productos = data.get("productos", "")

    # Validación: todos los campos visibles deben llegar completos.
    # Una solicitud de cotización sin estos datos no es accionable para Ventas.
    required_fields = {
        "nombre":   nombre,
        "empresa":  empresa,
        "email":    email,
        "telefono": telefono,
        "tipo":     tipo,
        "mensaje":  mensaje,
        "pais":     pais,
    }
    faltantes = [k for k, v in required_fields.items() if not v]
    if faltantes:
        return jsonify({
            "ok": False,
            "error": "Campos requeridos incompletos",
            "campos_faltantes": faltantes,
        }), 400
    if "@" not in email or "." not in email.split("@")[-1]:
        return jsonify({"ok": False, "error": "Email inválido"}), 400

    conn = get_conn()
    conn.execute(
        "INSERT INTO cotizaciones (nombre,empresa,email,telefono,tipo,mensaje,pais,productos) VALUES (?,?,?,?,?,?,?,?)",
        (nombre, empresa, email, telefono, tipo, mensaje, pais, productos)
    )
    conn.commit()
    conn.close()

    # Email
    body = f"""<h2>Nueva cotización - CGM Rental</h2>
<p><b>Nombre:</b> {nombre}</p>
<p><b>Empresa:</b> {empresa}</p>
<p><b>Email:</b> {email}</p>
<p><b>Teléfono:</b> {telefono}</p>
<p><b>Tipo:</b> {tipo}</p>
<p><b>País:</b> {pais}</p>
<p><b>Productos:</b> {productos}</p>
<p><b>Mensaje:</b><br>{mensaje}</p>"""
    send_email(f"Nueva cotización de {nombre} — CGM Rental", body)

    return jsonify({"ok": True, "message": "Cotización enviada correctamente"})


# ── Helper: validar que el país del formulario coincida con el portal ─────────
def _validar_pais_portal(pais_form, pais_sitio):
    """Acepta solo el país del portal o 'Otro'. Devuelve None si es válido,
    o un mensaje de error si no lo es."""
    pais_form = (pais_form or "").strip()
    expected = {"pe": "Perú", "ar": "Argentina"}.get(pais_sitio, "")
    if not pais_form:
        return "Falta el país del proyecto."
    if pais_form != expected and pais_form != "Otro":
        return f"El país '{pais_form}' no corresponde al portal {pais_sitio.upper()}."
    return None


# ── Anti-spam: Cloudflare Turnstile (captcha invisible) ──────────────────────
CF_TURNSTILE_SITE_KEY = os.getenv("CF_TURNSTILE_SITE_KEY", "")
CF_TURNSTILE_SECRET   = os.getenv("CF_TURNSTILE_SECRET", "")

def _validar_turnstile(token, ip=None):
    """Verifica el token Turnstile contra la API de Cloudflare.
    Devuelve True si Cloudflare confirma que es humano, False si es bot o falla.
    Si no está configurado (variables vacías), permite el request (modo dev)."""
    if not CF_TURNSTILE_SECRET:
        app.logger.warning("Turnstile no configurado (CF_TURNSTILE_SECRET vacía) — permitiendo")
        return True
    if not token:
        return False
    try:
        body = urllib.parse.urlencode({
            "secret":   CF_TURNSTILE_SECRET,
            "response": token,
            "remoteip": ip or "",
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        return bool(result.get("success", False))
    except Exception as e:
        app.logger.error(f"Error verificando Turnstile: {e}")
        return False  # En caso de error de red, rechaza (fail-closed)


# ── Anti-spam: validación de contenido (anti-phishing / anti-bot) ─────────────
_SPAM_URL_RE = re.compile(
    r"(https?://|www\.|telegra\.ph|t\.me/|\.com/|\.net/|\.org/|\.ru/|\.cn/)",
    re.IGNORECASE,
)
_SPAM_KEYWORDS = {
    "crypto", "refund", "compensation", "inheritance", "bitcoin", "btc",
    "trx", "usdt", "ethereum", "lottery", "casino", "viagra", "loan",
    "investment opportunity", "make money", "click here", "telegra",
}

def _validar_lead_contenido(data):
    """Validación server-side estricta del contenido del lead.
    Devuelve None si está OK, o un mensaje de error."""
    nombre = (data.get("nombre_apellido") or "").strip()
    ruc    = (data.get("ruc_dni") or "").strip()
    email  = (data.get("email") or "").strip()
    cel    = (data.get("celular") or "").strip()
    equipo = (data.get("equipo_requerido") or "").strip()
    razon  = (data.get("razon_social") or "").strip()
    otro_p = (data.get("otro_pais") or "").strip()

    # 1. Nombre: SOLO letras y espacios, 3-100 chars
    # No se permiten números, puntos, guiones, símbolos, emojis ni caracteres especiales
    if not nombre or len(nombre) < 3 or len(nombre) > 100:
        return "Nombre fuera de rango (entre 3 y 100 caracteres)."
    if not re.match(r"^[A-Za-záéíóúüñÁÉÍÓÚÜÑ ]+$", nombre):
        return "El nombre solo puede contener letras y espacios."

    # 2. RUC/DNI: solo dígitos (o guiones para CUIT argentino)
    if ruc and not re.match(r"^[\d\-]{6,15}$", ruc):
        return "Documento de identidad inválido."

    # 3. Email: solo letras, números, puntos, guión bajo y @ (sin guiones, +, etc.)
    if not re.match(r"^[A-Za-z0-9._]+@[A-Za-z0-9.]+\.[A-Za-z]{2,}$", email):
        return "Email inválido. Solo se permiten letras, números, puntos, guión bajo y @."

    # 4. Celular: valida dígitos según el código de país seleccionado (ISO)
    cel_digits = re.sub(r"[^\d]", "", cel)
    iso_pais = (data.get("codigo_pais_iso") or "").strip().upper()
    if not iso_pais:
        # Fallback al portal si no se envió código (por compatibilidad)
        iso_pais = "PE" if (data.get("pais_sitio") or "pe").lower() != "ar" else "AR"
    err_cel = validar_celular(iso_pais, cel_digits)
    if err_cel:
        return err_cel

    # 5. Otro país: solo letras y espacios (como nombre)
    if otro_p and not re.match(r"^[A-Za-záéíóúüñÁÉÍÓÚÜÑ ]+$", otro_p):
        return "El campo 'Otro país' solo puede contener letras y espacios."

    # 6. Razón social: bloquear emojis y caracteres no imprimibles
    # (acepta letras, números, puntos, comas, ampersand, paréntesis, guiones — típicos en nombres de empresa)
    if razon and not re.match(r"^[A-Za-z0-9áéíóúüñÁÉÍÓÚÜÑ .,&\-()/'\"]+$", razon):
        return "Razón social contiene caracteres no permitidos."

    # 6b. Equipo requerido: solo letras, números y espacios (si está presente)
    if equipo and not re.match(r"^[A-Za-z0-9áéíóúüñÁÉÍÓÚÜÑ ]+$", equipo):
        return "El equipo requerido solo puede contener letras y números."

    # 7. Detección de URLs en campos donde no deberían existir
    for valor in (nombre, equipo, razon, otro_p):
        if _SPAM_URL_RE.search(valor):
            return "Contenido no permitido (URLs detectadas)."

    # 8. Detección de keywords típicas de spam/phishing
    blob = " ".join([nombre, equipo, razon, otro_p]).lower()
    for kw in _SPAM_KEYWORDS:
        if kw in blob:
            return "Contenido bloqueado por filtro anti-spam."

    return None


# ── Validación de documento (RUC/DNI/CUIT) según tipo de operación ──────────
# Reglas de negocio (Perú):
#   - Alquiler (B2B): SOLO RUC 20 (Persona Jurídica / empresa)
#   - Compra/Usados: DNI (8 díg) + RUC 10 (PN con negocio) + RUC 20 (empresa)
#
# Argentina: solo CUIT/CUIL (11 díg con prefijo válido). No hay "usados".
_RUC_PE_PREFIXES_ALQUILER = ('20',)              # B2B: solo personas jurídicas
_RUC_PE_PREFIXES_USADOS   = ('10', '20')         # Persona natural con negocio o empresa

# Prefijos válidos de CUIT/CUIL en Argentina (AFIP):
#   20, 23, 24      → Personas Naturales Masculinas
#   25, 26          → Extranjeros (M/F)
#   27              → Personas Naturales Femeninas
#   30, 33          → Personas Jurídicas (empresas, cooperativas, fundaciones)
#   34              → Personas Jurídicas Extranjeras
# En Argentina NO existe la operación "usados" (show_usados=False en countries.py),
# por lo que NO se acepta DNI: todo lead es alquiler → debe tener CUIT/CUIL.
_CUIT_AR_PREFIXES = ('20', '23', '24', '25', '26', '27', '30', '33', '34')

def _validar_documento(doc, tipo, country_code="pe"):
    """Valida ruc_dni según el tipo de operación y país.

    tipo ∈ {'alquiler', 'usados'} (también acepta 'compra' como alias de usados).
    country_code ∈ {'pe', 'ar'}.

    Devuelve None si es válido, o un string con el mensaje de error.
    """
    if not doc:
        return "El documento de identidad es obligatorio."

    # Normalizar: solo dígitos
    doc_clean = re.sub(r'[^\d]', '', doc)
    tipo = (tipo or '').lower()
    is_alquiler = (tipo == 'alquiler')

    if country_code == "ar":
        # Argentina: solo alquiler → solo CUIT/CUIL (11 dígitos con prefijo válido).
        # No se acepta DNI porque no hay operación de usados en AR.
        if len(doc_clean) != 11:
            return "Debe ingresar un CUIT/CUIL válido (11 dígitos)."
        if not doc_clean.startswith(_CUIT_AR_PREFIXES):
            return "CUIT/CUIL inválido. Debe iniciar con 20, 23, 24, 25, 26, 27, 30, 33 o 34."
        return None

    # Perú (default)
    if is_alquiler:
        # Solo RUC 20: 11 dígitos con prefijo 20 (empresa)
        if len(doc_clean) != 11:
            return "Para alquiler debe ingresar un RUC de empresa (11 dígitos, inicia con 20)."
        if not doc_clean.startswith(_RUC_PE_PREFIXES_ALQUILER):
            return "RUC inválido. Para alquiler debe ingresar un RUC de empresa (inicia con 20)."
    else:
        # Usados/Compra: DNI (8 díg) o RUC 10/20 (11 díg)
        if len(doc_clean) == 8:
            return None  # DNI válido
        if len(doc_clean) == 11:
            if not doc_clean.startswith(_RUC_PE_PREFIXES_USADOS):
                return "RUC inválido. Debe iniciar con 10 (persona natural con negocio) o 20 (empresa)."
            return None
        return "Documento inválido. Debe ser DNI (8 dígitos) o RUC (11 dígitos)."

    return None


# ── Construir texto de respuestas de las preguntas filtro ───────────────────
def _build_preguntas_filtro(data, is_alquiler):
    """Construye un string formateado con las respuestas a las preguntas filtro
    del paso 2 del formulario. Cada línea es 'Etiqueta: respuesta'.
    Devuelve None si no hay respuestas (no rompe el INSERT).
    """
    if is_alquiler:
        campos = [
            ("Plazo necesidad",  data.get("plazo_alquiler",  "").strip()),
            ("Etapa proyecto",   data.get("etapa_proyecto",  "").strip()),
            ("Tiempo estimado",  data.get("tiempo_alquiler", "").strip()),
        ]
    else:
        campos = [
            ("Plazo compra",     data.get("plazo_compra",    "").strip()),
            ("Presupuesto",      data.get("presupuesto",     "").strip()),
            ("Modalidad pago",   data.get("modalidad_compra","").strip()),
        ]
    lineas = [f"{etiqueta}: {valor}" for etiqueta, valor in campos if valor]
    return "\n".join(lineas) if lineas else None


# ── Normalización de texto para BD ───────────────────────────────────────────
def _normalizar(texto):
    """Convierte texto a MAYÚSCULAS sin tildes ni diacríticos para guardar en BD.
    Ej: 'García Ñúñez' → 'GARCIA NUNEZ'  |  '' / None → se devuelve tal cual."""
    if not texto:
        return texto
    nfkd = unicodedata.normalize('NFD', str(texto))
    sin_acento = ''.join(c for c in nfkd if unicodedata.category(c) != 'Mn')
    return sin_acento.upper()


# ── Mapeo unidad → sector_producto ───────────────────────────────────────────
_UNIDAD_TO_SECTOR = {
    "Construcción":    "CONSTRUCCIÓN",
    "Mediana Minería": "MINERÍA",
    "Agrícola":        "AGRÍCOLA",
    "Energía":         "ENERGÍA",
}

def _sector_desde_carrito(items_envio):
    """Determina sector_producto mayoritario de los ítems del carrito.
    Suma qty por sector; el mayor gana. Empate exacto → None."""
    if not items_envio:
        return None
    slugs = list(items_envio.keys())
    try:
        conn_sq = get_conn()
        placeholders = ",".join(["?"] * len(slugs))
        rows = conn_sq.execute(
            f"SELECT slug, unidad FROM products WHERE slug IN ({placeholders})",
            slugs
        ).fetchall()
        conn_sq.close()
    except Exception:
        return None
    unidad_map = {r["slug"]: (r["unidad"] or "") for r in rows}
    conteo = {}
    for slug, item in items_envio.items():
        # Tomar la primera unidad (puede ser pipe-separada, ej: "Construcción|Agrícola")
        u = (unidad_map.get(slug, "").split("|")[0]).strip()
        sector = _UNIDAD_TO_SECTOR.get(u)
        if sector:
            conteo[sector] = conteo.get(sector, 0) + item.get("qty", 1)
    if not conteo:
        return None
    max_qty = max(conteo.values())
    ganadores = [s for s, q in conteo.items() if q == max_qty]
    return ganadores[0] if len(ganadores) == 1 else None


# Tabla de keywords para detección de sector (módulo-nivel: se crea una sola vez).
# Frases específicas van antes que sus sub-palabras para que se consuman primero.
_SECTOR_MATCH_TABLE = [
        # ── AGRÍCOLA ─────────────────────────────────────────────────────────
        ("tractor agricola",     "AGRÍCOLA"),
        ("tractor agrícola",     "AGRÍCOLA"),
        ("tractor agric",        "AGRÍCOLA"),   # cubre cualquier variante
        ("agricola",             "AGRÍCOLA"),
        ("agrícola",             "AGRÍCOLA"),
        ("atomizador",           "AGRÍCOLA"),
        ("cosechadora",          "AGRÍCOLA"),
        ("sembradora",           "AGRÍCOLA"),
        ("irrigacion",           "AGRÍCOLA"),
        ("irrigación",           "AGRÍCOLA"),
        ("riego",                "AGRÍCOLA"),
        # ── MINERÍA ──────────────────────────────────────────────────────────
        ("topador",              "MINERÍA"),
        ("mineria",              "MINERÍA"),
        ("minería",              "MINERÍA"),
        ("minero",               "MINERÍA"),
        ("minera",               "MINERÍA"),
        # "mina" NO incluido: es substring de "iluminacion" → falso positivo MINERÍA
        ("perforadora",          "MINERÍA"),
        ("perforador",           "MINERÍA"),
        # ── ENERGÍA ──────────────────────────────────────────────────────────
        ("grupo electrogeno",    "ENERGÍA"),
        ("grupo electrógeno",    "ENERGÍA"),
        ("planta electrica",     "ENERGÍA"),
        ("planta eléctrica",     "ENERGÍA"),
        ("generador",            "ENERGÍA"),
        ("electrogeno",          "ENERGÍA"),
        ("electrógeno",          "ENERGÍA"),
        ("turbina",              "ENERGÍA"),
        # ── CONSTRUCCIÓN ─────────────────────────────────────────────────────
        ("tractor de orugas",    "CONSTRUCCIÓN"),
        ("tractor orugas",       "CONSTRUCCIÓN"),
        ("excavadora",           "CONSTRUCCIÓN"),
        ("cargador frontal",     "CONSTRUCCIÓN"),
        ("cargador",             "CONSTRUCCIÓN"),
        ("motoniveladora",       "CONSTRUCCIÓN"),
        ("niveladora",           "CONSTRUCCIÓN"),
        ("retroexcavadora",      "CONSTRUCCIÓN"),
        ("minicargador",         "CONSTRUCCIÓN"),
        ("rodillo compactador",  "CONSTRUCCIÓN"),
        ("rodillo",              "CONSTRUCCIÓN"),
        ("compactador",          "CONSTRUCCIÓN"),
        ("compactadora",         "CONSTRUCCIÓN"),
        ("aplanadora",           "CONSTRUCCIÓN"),
        ("aplanador",            "CONSTRUCCIÓN"),
        ("aplana",               "CONSTRUCCIÓN"),
        ("micropavimentadora",   "CONSTRUCCIÓN"),
        ("pavimentadora",        "CONSTRUCCIÓN"),
        ("autohormigonera",      "CONSTRUCCIÓN"),
        ("hormigonera",          "CONSTRUCCIÓN"),
        ("camion cisterna",      "CONSTRUCCIÓN"),
        ("cisterna",             "CONSTRUCCIÓN"),
        ("camion volquete",      "CONSTRUCCIÓN"),
        ("volquete",             "CONSTRUCCIÓN"),
        ("camion grua",          "CONSTRUCCIÓN"),
        ("camion",               "CONSTRUCCIÓN"),
        ("camión",               "CONSTRUCCIÓN"),
        ("grua",                 "CONSTRUCCIÓN"),
        ("grúa",                 "CONSTRUCCIÓN"),
        ("compresora",           "CONSTRUCCIÓN"),
        ("torre de iluminacion", "CONSTRUCCIÓN"),
        ("iluminacion",          "CONSTRUCCIÓN"),
        ("iluminación",          "CONSTRUCCIÓN"),
        ("martillo hidraulico",  "CONSTRUCCIÓN"),
        ("martillo",             "CONSTRUCCIÓN"),
        ("tren de chancado",     "CONSTRUCCIÓN"),
        ("chancadora",           "CONSTRUCCIÓN"),
        ("chancado",             "CONSTRUCCIÓN"),
        ("zaranda",              "CONSTRUCCIÓN"),
        ("faja transportadora",  "CONSTRUCCIÓN"),
        ("bulldozer",            "CONSTRUCCIÓN"),
        ("plancha compactadora", "CONSTRUCCIÓN"),
        ("plancha",              "CONSTRUCCIÓN"),
        ("aditamento",           "CONSTRUCCIÓN"),
]


def _detectar_sector_equipo(texto):
    """Detecta sector_producto por keyword matching sobre equipo_requerido (texto libre).

    Limpia conectores (y, o, e, comas) para tratar cada equipo por separado.
    Cada keyword suma 1 voto a su sector; se consume para evitar doble-conteo.
    Gana el sector con más votos. Empate → None.
    """
    if not texto:
        return None
    t = texto.lower()
    t = re.sub(r'\b(y|o|e)\b|[,;/]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()

    conteo = {}
    for keyword, sector in _SECTOR_MATCH_TABLE:
        if keyword in t:
            conteo[sector] = conteo.get(sector, 0) + 1
            # Consumir el match para no contar términos superpuestos
            t = t.replace(keyword, ' ')

    if not conteo:
        return None
    max_v = max(conteo.values())
    ganadores = [s for s, v in conteo.items() if v == max_v]
    return ganadores[0] if len(ganadores) == 1 else None


# ── Formulario Contacto → guardar lead en SQL Server (Azure) ─────────────────
@app.route("/api/guardar-contacto", methods=["POST"])
@limiter.limit("5 per minute")
def api_guardar_contacto():
    data        = request.form
    pais_sitio  = data.get("pais_sitio", "pe")

    # Anti-spam capa 1: Honeypot (campo oculto que humanos nunca llenan)
    if data.get("website", "").strip():
        security_logger.warning(f"Honeypot activado en guardar-contacto ip={_get_real_ip()}")
        # Devuelve 200 (engaño): el bot piensa que pasó pero no se guardó nada
        return redirect(f"/{pais_sitio}/gracias/")

    # Anti-spam capa 2: Cloudflare Turnstile
    cf_token = data.get("cf-turnstile-response", "")
    if not _validar_turnstile(cf_token, _get_real_ip()):
        security_logger.warning(f"Turnstile falló en guardar-contacto ip={_get_real_ip()}")
        return jsonify({"ok": False, "error": "Verificación de seguridad fallida. Recarga la página e intenta de nuevo."}), 403

    # Anti-spam capa 3: validación de contenido (formato + URLs + keywords)
    err = _validar_lead_contenido(data)
    if err:
        security_logger.warning(f"Lead bloqueado por contenido en guardar-contacto: {err}")
        return jsonify({"ok": False, "error": err}), 400

    # Defensa server-side contra envíos cruzados (manipulación del formulario)
    err = _validar_pais_portal(data.get("pais"), pais_sitio)
    if err:
        security_logger.warning(
            f"Envío cruzado bloqueado en /api/guardar-contacto: {err}"
        )
        return jsonify({"ok": False, "error": err}), 400

    # ── Validación de negocio: tipo seleccionado, documento y razón social ───
    is_alq  = bool(data.get("tipo_alquiler"))
    is_comp = bool(data.get("tipo_compra"))

    # 1) Al menos un tipo debe estar seleccionado (lead no es accionable sin esto)
    if not is_alq and not is_comp:
        # Mensaje contextual: en Argentina solo existe "Alquiler" (show_usados=False)
        if pais_sitio == 'ar':
            err_msg = 'Debes marcar la opción "Alquiler" para continuar.'
        else:
            err_msg = "Debes seleccionar al menos una opción: Alquiler o Compra."
        return jsonify({"ok": False, "error": err_msg}), 400

    # 2) Validar RUC/DNI según el tipo. Si hay alquiler, aplica la regla estricta
    #    (RUC obligatorio); si solo hay usados, acepta DNI también.
    tipo_doc = 'alquiler' if is_alq else 'usados'
    err_doc = _validar_documento(data.get("ruc_dni", "").strip(), tipo_doc, pais_sitio)
    if err_doc:
        return jsonify({"ok": False, "error": err_doc}), 400

    # 3) Razón social obligatoria cuando el documento es RUC/CUIT (11 dígitos).
    #    Si es DNI (8 dígitos), el cliente es persona natural y razón social no aplica.
    doc_clean_chk = re.sub(r'[^\d]', '', data.get("ruc_dni", "").strip())
    if len(doc_clean_chk) == 11 and not data.get("razon_social", "").strip():
        return jsonify({
            "ok": False,
            "error": "La razón social es obligatoria cuando se usa RUC.",
        }), 400

    try:
        conn   = db_sqlserver.get_conn()
        cursor = conn.cursor()
        # Código telefónico del país (ej. "+51") deducido del ISO seleccionado
        iso_pais_form = (data.get("codigo_pais_iso") or "").strip().upper()
        pais_obj = PAISES_POR_ISO.get(iso_pais_form)
        codigo_pais_val = pais_obj["code"] if pais_obj else ""
        # Celular se guarda solo con dígitos (sin código de país); el código va aparte
        cel_digits_clean = re.sub(r"[^\d]", "", data.get("celular", ""))

        cursor.execute("""
            INSERT INTO CGM_Contacto_Leads
              (pais_sitio, nombre_apellido, razon_social, ruc_dni, pais,
               departamento, otro_pais, email, codigo_pais, celular,
               equipo_requerido, sector_producto, tipo_alquiler, tipo_compra,
               plazo_alquiler, etapa_proyecto, tiempo_alquiler,
               plazo_compra, presupuesto, modalidad_compra,
               sf_enviado)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            pais_sitio,
            _normalizar(data.get("nombre_apellido", "").strip()),
            _normalizar(data.get("razon_social",    "").strip()),
            _normalizar(data.get("ruc_dni",         "").strip()),
            _normalizar(data.get("pais",            "").strip()),
            _normalizar(data.get("departamento",    "").strip()),
            _normalizar(data.get("otro_pais",       "").strip()),
            data.get("email",           "").strip(),
            codigo_pais_val,
            cel_digits_clean,
            _normalizar(data.get("equipo_requerido","").strip()),
            _detectar_sector_equipo(data.get("equipo_requerido", "")),
            1 if data.get("tipo_alquiler") else 0,
            1 if data.get("tipo_compra")   else 0,
            data.get("plazo_alquiler",   "").strip() or None,
            data.get("etapa_proyecto",   "").strip() or None,
            data.get("tiempo_alquiler",  "").strip() or None,
            data.get("plazo_compra",     "").strip() or None,
            data.get("presupuesto",      "").strip() or None,
            data.get("modalidad_compra", "").strip() or None,
            0,
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        app.logger.error(f"[guardar-contacto] SQL Server error: {e}")
    return redirect(f"/{pais_sitio}/gracias/")


# ── Formulario Cotización (carrito) → guardar lead en SQL Server (Azure) ──────
# Soporta flujo dual: si el carrito es mixto (alquiler + usados), envía solo
# los equipos del tipo indicado en `tipo_envio` y deja los otros en la session
# para una segunda cotización.
@app.route("/api/guardar-cotizacion", methods=["POST"])
@limiter.limit("8 per minute")
def api_guardar_cotizacion():
    data        = request.form
    pais_sitio  = data.get("pais_sitio", "pe")

    # Anti-spam capa 1: Honeypot
    if data.get("website", "").strip():
        security_logger.warning(f"Honeypot activado en guardar-cotizacion ip={_get_real_ip()}")
        return jsonify({"ok": True, "redirect": f"/{pais_sitio}/gracias/"}), 200

    # Anti-spam capa 2: Cloudflare Turnstile
    cf_token = data.get("cf-turnstile-response", "")
    if not _validar_turnstile(cf_token, _get_real_ip()):
        security_logger.warning(f"Turnstile falló en guardar-cotizacion ip={_get_real_ip()}")
        return jsonify({"ok": False, "error": "Verificación de seguridad fallida. Recarga la página e intenta de nuevo."}), 403

    # Anti-spam capa 3: validación de contenido
    err = _validar_lead_contenido(data)
    if err:
        security_logger.warning(f"Lead bloqueado por contenido en guardar-cotizacion: {err}")
        return jsonify({"ok": False, "error": err}), 400

    # Defensa server-side contra envíos cruzados
    err = _validar_pais_portal(data.get("pais"), pais_sitio)
    if err:
        security_logger.warning(
            f"Envío cruzado bloqueado en /api/guardar-cotizacion: {err}"
        )
        return jsonify({"ok": False, "error": err}), 400

    # ── Mitigación #2: Idempotency token (evita duplicados por reintento) ──────
    submission_id = (data.get("submission_id") or "").strip()
    if submission_id:
        seen = session.get("_cotiz_submissions", [])
        if submission_id in seen:
            app.logger.info(f"[guardar-cotizacion] Submission duplicado ignorado: {submission_id}")
            return jsonify({"ok": True, "duplicate": True, "mensaje": "Cotización ya recibida."}), 200

    # ── Mitigación #7: Validar tipo_envio y que existan equipos del tipo ───────
    tipo_envio = (data.get("tipo_envio") or "").strip().lower()
    if tipo_envio not in ("alquiler", "compra", "usados", ""):
        return jsonify({"ok": False, "error": "Tipo de operación inválido."}), 400

    # Normalizar: "compra" en el form = "usados" en el tag de productos
    tag_target = "usados" if tipo_envio == "compra" else (tipo_envio or "alquiler")

    # Leer carrito de la session y filtrar por tag
    cart_key = _cart_key(pais_sitio)
    cart = session.get(cart_key, {})
    items_envio = {slug: item for slug, item in cart.items()
                   if (item.get("tag") or "").lower() == tag_target}

    if not items_envio:
        # Si no quedan equipos del tipo, podría ser carrito vacío o desincronización
        if not cart:
            return jsonify({
                "ok": False,
                "error": "Tu carrito está vacío. Agrega equipos antes de cotizar.",
                "cart_vacio": True,
            }), 400
        return jsonify({
            "ok": False,
            "error": f"No tienes equipos de tipo '{tag_target}' en el carrito.",
        }), 400

    # ── Validación de negocio: documento y razón social ─────────────────────
    # Documento: si tag_target='alquiler' → RUC obligatorio (11 dig).
    #            si tag_target='usados'   → DNI (8) o RUC (11).
    err_doc = _validar_documento(data.get("ruc_dni", "").strip(), tag_target, pais_sitio)
    if err_doc:
        return jsonify({"ok": False, "error": err_doc}), 400

    # Razón social: obligatoria cuando el documento es RUC/CUIT (11 dígitos).
    # Si es DNI (8 dígitos), el cliente es persona natural y razón social no aplica.
    doc_clean_chk = re.sub(r'[^\d]', '', data.get("ruc_dni", "").strip())
    if len(doc_clean_chk) == 11 and not data.get("razon_social", "").strip():
        return jsonify({
            "ok": False,
            "error": "La razón social es obligatoria cuando se usa RUC.",
        }), 400

    # Construir detalle_equipos solo con los equipos del tipo enviado
    detalle = " | ".join([f"{item.get('qty', 1)} x {item.get('nombre', slug)}"
                          for slug, item in items_envio.items()])

    # Si eligió "Otro", combinamos pais + otro_pais
    pais_val = data.get("pais", "").strip()
    otro_pais_val = data.get("otro_pais", "").strip()
    if pais_val == "Otro" and otro_pais_val:
        pais_val = f"Otro: {otro_pais_val}"

    # Flags tipo_alquiler / tipo_compra según el tipo enviado
    is_alquiler = 1 if tag_target == "alquiler" else 0
    is_compra   = 1 if tag_target == "usados"   else 0

    # Código telefónico del país (ej. "+51") deducido del ISO seleccionado
    iso_pais_form = (data.get("codigo_pais_iso") or "").strip().upper()
    pais_obj = PAISES_POR_ISO.get(iso_pais_form)
    codigo_pais_val = pais_obj["code"] if pais_obj else ""
    # Celular solo con dígitos (el código de país va aparte)
    cel_digits_clean = re.sub(r"[^\d]", "", data.get("celular", ""))

    # Sector del producto: mayoría de unidades del carrito
    sector_producto_val = _sector_desde_carrito(items_envio)

    # ── Mitigación #3: try/finally para garantizar consistencia ────────────────
    insert_ok = False
    conn = None
    try:
        conn   = db_sqlserver.get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO CGM_Cotizaciones
              (pais_sitio, nombre_apellido, razon_social, ruc_dni, email,
               codigo_pais, celular, pais, departamento, tipo_alquiler,
               tipo_compra, detalle_equipos, sector_producto,
               plazo_alquiler, etapa_proyecto, tiempo_alquiler,
               plazo_compra, presupuesto, modalidad_compra,
               sf_enviado)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            pais_sitio,
            _normalizar(data.get("nombre_apellido", "").strip()),
            _normalizar(data.get("razon_social",    "").strip()),
            _normalizar(data.get("ruc_dni",         "").strip()),
            data.get("email",           "").strip(),
            codigo_pais_val,
            cel_digits_clean,
            _normalizar(pais_val),
            _normalizar(data.get("departamento",    "").strip()),
            is_alquiler,
            is_compra,
            _normalizar(detalle),
            sector_producto_val,
            data.get("plazo_alquiler",   "").strip() or None,
            data.get("etapa_proyecto",   "").strip() or None,
            data.get("tiempo_alquiler",  "").strip() or None,
            data.get("plazo_compra",     "").strip() or None,
            data.get("presupuesto",      "").strip() or None,
            data.get("modalidad_compra", "").strip() or None,
            0,
        ))
        conn.commit()
        insert_ok = True
        app.logger.info(f"[guardar-cotizacion] Lead OK tipo={tag_target} equipos={len(items_envio)}")
    except Exception as e:
        app.logger.error(f"[guardar-cotizacion] SQL Server error: {e}")
        return jsonify({
            "ok": False,
            "error": "No pudimos guardar tu cotización en este momento. Por favor intenta nuevamente.",
        }), 500
    finally:
        if conn:
            try: conn.close()
            except Exception: pass

    # ── Si el INSERT fue OK, limpiamos del carrito los equipos enviados ────────
    if insert_ok:
        try:
            for slug in items_envio.keys():
                cart.pop(slug, None)
            session[cart_key] = cart
            # Registrar submission_id como procesado (mitigación #2)
            if submission_id:
                seen = session.get("_cotiz_submissions", [])
                seen.append(submission_id)
                # Limitar tamaño (últimos 20)
                session["_cotiz_submissions"] = seen[-20:]
            session.modified = True
        except Exception as e:
            # Si la limpieza falla, el lead está guardado pero el carrito queda igual.
            # Loguear para diagnosticar pero no fallar la respuesta al usuario.
            app.logger.error(f"[guardar-cotizacion] No se pudo limpiar session: {e}")

    # Respuesta JSON: indica si quedan más equipos pendientes en el carrito
    cart_restante = session.get(cart_key, {})
    return jsonify({
        "ok": True,
        "mensaje": f"Cotización de {'alquiler' if tag_target == 'alquiler' else 'compra'} enviada correctamente.",
        "cart_restante": cart_restante,
        "tipos_restantes": sorted({(it.get("tag") or "").lower()
                                    for it in cart_restante.values() if it.get("tag")}),
    }), 200


@app.route("/api/cart/add", methods=["POST"])
def api_cart_add():
    data = request.get_json(silent=True) or {}
    slug    = data.get("slug", "").strip()
    nombre  = data.get("nombre", "").strip()
    imagen  = data.get("imagen", "").strip()
    tipo    = data.get("tipo", "").strip()
    tag     = data.get("tag", "").strip()
    country = data.get("country", "pe").lower()
    if not slug:
        return jsonify({"ok": False}), 400
    key  = _cart_key(country)
    cart = session.get(key, {})
    if slug in cart:
        cart[slug]["qty"] += 1
    else:
        cart[slug] = {"slug": slug, "nombre": nombre, "imagen": imagen, "tipo": tipo, "tag": tag, "qty": 1}
    session[key] = cart
    session.modified = True
    return jsonify({"ok": True, "count": cart_count(country)})


@app.route("/api/cart/qty", methods=["POST"])
def api_cart_qty():
    data    = request.get_json(silent=True) or {}
    slug    = data.get("slug", "").strip()
    qty     = int(data.get("qty", 1))
    country = data.get("country", "pe").lower()
    key     = _cart_key(country)
    cart    = session.get(key, {})
    if slug in cart:
        if qty < 1:
            del cart[slug]
        else:
            cart[slug]["qty"] = qty
    session[key] = cart
    session.modified = True
    return jsonify({"ok": True, "count": cart_count(country)})


@app.route("/api/cart", methods=["GET", "DELETE"])
def api_cart():
    country = request.args.get("country", "pe").lower()
    key     = _cart_key(country)
    if request.method == "DELETE":
        slug = request.args.get("slug")
        cart = session.get(key, {})
        if slug and slug in cart:
            del cart[slug]
        elif not slug:
            cart = {}
        session[key] = cart
        session.modified = True
        return jsonify({"ok": True, "count": cart_count(country)})
    return jsonify({"cart": session.get(key, {}), "count": cart_count(country)})


@app.route("/api/denuncia", methods=["POST"])
@limiter.limit("3 per minute")
def api_denuncia():
    data = request.get_json(silent=True) or request.form.to_dict()

    nombre_den  = data.get("nombre_denunciante", "Anónimo").strip()
    empresa_den = data.get("empresa_denunciante", "—").strip()
    email_den   = data.get("email_denunciante", "—").strip()
    descripcion = data.get("descripcion", "").strip()
    nombre_ddo  = data.get("nombre_denunciado", "—").strip()
    empresa_ddo = data.get("empresa_denunciado", "—").strip()
    tipo        = data.get("tipo", "—").strip()

    if not descripcion or not tipo:
        return jsonify({"ok": False, "error": "Campos requeridos"}), 400

    # Guardar en BD
    try:
        conn = get_conn()
        conn.execute(
            "INSERT INTO denuncias (tipo, descripcion) VALUES (?,?)",
            (tipo, descripcion)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

    # Email HTML corporativo
    body = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
      <div style="background:#004d3d;padding:28px 32px;">
        <h1 style="color:#fff;margin:0;font-size:22px;letter-spacing:1px;">CGM RENTAL</h1>
        <p style="color:#a8d5a2;margin:6px 0 0;font-size:13px;">Canal de Denuncias — Reporte confidencial</p>
      </div>

      <div style="padding:28px 32px;background:#fff;">
        <h2 style="color:#004d3d;font-size:16px;border-bottom:2px solid #C5E86C;
                   padding-bottom:8px;margin-bottom:16px;">Datos del Denunciante</h2>
        <table style="width:100%;font-size:14px;border-collapse:collapse;">
          <tr><td style="padding:6px 0;color:#666;width:160px;">Nombre:</td>
              <td style="padding:6px 0;color:#222;font-weight:600;">{nombre_den}</td></tr>
          <tr><td style="padding:6px 0;color:#666;">Empresa:</td>
              <td style="padding:6px 0;color:#222;">{empresa_den}</td></tr>
          <tr><td style="padding:6px 0;color:#666;">Email:</td>
              <td style="padding:6px 0;color:#222;">{email_den}</td></tr>
          <tr><td style="padding:6px 0;color:#666;vertical-align:top;">Descripción:</td>
              <td style="padding:6px 0;color:#222;">{descripcion}</td></tr>
        </table>

        <h2 style="color:#004d3d;font-size:16px;border-bottom:2px solid #C5E86C;
                   padding-bottom:8px;margin:24px 0 16px;">Datos del Denunciado</h2>
        <table style="width:100%;font-size:14px;border-collapse:collapse;">
          <tr><td style="padding:6px 0;color:#666;width:160px;">Nombre:</td>
              <td style="padding:6px 0;color:#222;font-weight:600;">{nombre_ddo}</td></tr>
          <tr><td style="padding:6px 0;color:#666;">Empresa:</td>
              <td style="padding:6px 0;color:#222;">{empresa_ddo}</td></tr>
        </table>

        <h2 style="color:#004d3d;font-size:16px;border-bottom:2px solid #C5E86C;
                   padding-bottom:8px;margin:24px 0 16px;">Tipo de Denuncia</h2>
        <p style="background:#f5f5f5;padding:12px 16px;border-radius:6px;
                  font-size:14px;color:#222;margin:0;">{tipo}</p>
      </div>

      <div style="background:#f0f0f0;padding:16px 32px;text-align:center;">
        <p style="margin:0;font-size:12px;color:#888;">
          CGM RENTAL — Reporte generado automáticamente desde el Canal de Denuncias
        </p>
      </div>
    </div>
    """

    send_email("Nueva denuncia recibida — Canal CGM Rental", body)
    return jsonify({"ok": True})


@app.route("/api/proveedor", methods=["POST"])
@limiter.limit("5 per minute")
def api_proveedor():
    data        = request.get_json(silent=True) or request.form.to_dict()
    ruc         = data.get("ruc", "").strip()
    razon_social= data.get("razon_social", "").strip()
    departamento= data.get("departamento", "").strip()
    direccion   = data.get("direccion", "").strip()
    contacto    = data.get("contacto", "").strip()
    email       = data.get("email", "").strip()
    celular     = data.get("celular", "").strip()
    categorias  = data.get("categorias", [])
    descripcion = data.get("descripcion", "").strip()
    if isinstance(categorias, str):
        categorias = [categorias]
    categorias_str = ", ".join(categorias)

    if not razon_social or not email:
        return jsonify({"ok": False, "error": "Campos requeridos"}), 400

    conn = get_conn()
    conn.execute(
        "INSERT INTO proveedores (empresa,ruc,contacto,email,telefono,rubro,descripcion) VALUES (?,?,?,?,?,?,?)",
        (razon_social, ruc, contacto, email, celular, categorias_str, descripcion)
    )
    conn.commit()
    conn.close()

    body = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
      <div style="background:#004d3d;padding:24px 32px;">
        <h1 style="color:#C5E86C;font-size:20px;margin:0;">Nuevo Proveedor Registrado</h1>
        <p style="color:#fff;font-size:13px;margin:6px 0 0;">Portal de Proveedores — CGM Rental</p>
      </div>
      <div style="padding:24px 32px;background:#fff;">
        <h2 style="color:#004d3d;font-size:16px;border-bottom:2px solid #C5E86C;padding-bottom:8px;margin:0 0 16px;">
          Datos del Proveedor
        </h2>
        <table style="width:100%;font-size:14px;border-collapse:collapse;">
          <tr><td style="padding:6px 0;color:#666;width:160px;">RUC:</td>
              <td style="padding:6px 0;color:#222;font-weight:600;">{ruc}</td></tr>
          <tr><td style="padding:6px 0;color:#666;">Razón Social:</td>
              <td style="padding:6px 0;color:#222;font-weight:600;">{razon_social}</td></tr>
          <tr><td style="padding:6px 0;color:#666;">Departamento:</td>
              <td style="padding:6px 0;color:#222;">{departamento}</td></tr>
          <tr><td style="padding:6px 0;color:#666;">Dirección:</td>
              <td style="padding:6px 0;color:#222;">{direccion}</td></tr>
        </table>

        <h2 style="color:#004d3d;font-size:16px;border-bottom:2px solid #C5E86C;
                   padding-bottom:8px;margin:24px 0 16px;">Información de Contacto</h2>
        <table style="width:100%;font-size:14px;border-collapse:collapse;">
          <tr><td style="padding:6px 0;color:#666;width:160px;">Nombre:</td>
              <td style="padding:6px 0;color:#222;">{contacto}</td></tr>
          <tr><td style="padding:6px 0;color:#666;">Email:</td>
              <td style="padding:6px 0;color:#222;">{email}</td></tr>
          <tr><td style="padding:6px 0;color:#666;">Celular:</td>
              <td style="padding:6px 0;color:#222;">{celular}</td></tr>
        </table>

        <h2 style="color:#004d3d;font-size:16px;border-bottom:2px solid #C5E86C;
                   padding-bottom:8px;margin:24px 0 16px;">Categorías</h2>
        <p style="background:#f5f5f5;padding:12px 16px;border-radius:6px;
                  font-size:14px;color:#222;margin:0 0 16px;">{categorias_str}</p>

        <h2 style="color:#004d3d;font-size:16px;border-bottom:2px solid #C5E86C;
                   padding-bottom:8px;margin:24px 0 16px;">Descripción</h2>
        <p style="font-size:14px;color:#222;margin:0;">{descripcion}</p>
      </div>
      <div style="background:#f0f0f0;padding:16px 32px;text-align:center;">
        <p style="margin:0;font-size:12px;color:#888;">
          CGM RENTAL — Registro generado automáticamente desde el Portal de Proveedores
        </p>
      </div>
    </div>
    """
    send_email(f"Nuevo proveedor registrado: {razon_social} — CGM Rental", body)
    return jsonify({"ok": True})


# ── RENIEC lookup vía eldni.com (DNI peruano) ────────────────────────────────
def _lookup_dni_eldni(dni):
    """Consulta eldni.com para obtener nombre completo del titular del DNI.

    Flujo:
      1. GET para obtener el CSRF token (_token) y las cookies de sesión.
      2. POST multipart/form-data con el DNI.
      3. Parsear la tabla dentro de <section id="dni-nombres"> en el HTML.

    Retorna {"nombre": "...", "fuente": "reniec"} si encontrado,
    o {"error": "...", "msg": "..."} en caso de error.
    """
    try:
        import requests as _req
        base = "https://eldni.com/pe/buscar-datos-por-dni"
        sess = _req.Session()
        sess.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        })

        # Paso 1: GET → obtener CSRF token y cookies
        r_get = sess.get(base, timeout=10, allow_redirects=True)
        if r_get.status_code not in (200, 302):
            return {"error": "sunat_no_disponible", "msg": "Servicio RENIEC no disponible."}
        tok_m = re.search(r'name="_token"\s+value="([^"]+)"', r_get.text)
        if not tok_m:
            return {"error": "sunat_no_disponible", "msg": "No se pudo obtener el token RENIEC."}

        # Paso 2: POST multipart/form-data (formato original del formulario)
        r_post = sess.post(
            base,
            files={"_token": (None, tok_m.group(1)), "dni": (None, dni)},
            headers={
                "Referer": base,
                "Origin": "https://eldni.com",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Dest": "document",
            },
            timeout=12,
            allow_redirects=True,
        )
        if r_post.status_code not in (200, 302):
            return {"error": "sunat_no_disponible", "msg": "Servicio RENIEC no disponible."}

        # Paso 3: extraer datos de la tabla en section#dni-nombres
        # Estructura esperada: DNI | Nombres | Apellido Paterno | Apellido Materno
        sec_m = re.search(
            r'<section[^>]+id=["\']dni-nombres["\'][^>]*>(.*?)</section>',
            r_post.text, re.DOTALL | re.IGNORECASE
        )
        if not sec_m:
            return {"error": "no_encontrado", "msg": "DNI no encontrado en RENIEC."}

        tds = re.findall(r'<td[^>]*>([^<]+)</td>', sec_m.group(1))
        if len(tds) >= 4:
            nombres = tds[1].strip()
            ap_pat  = tds[2].strip()
            ap_mat  = tds[3].strip()
            nombre  = " ".join(p for p in [nombres, ap_pat, ap_mat] if p)
            if nombre:
                return {"nombre": nombre, "fuente": "reniec"}

        return {"error": "no_encontrado", "msg": "DNI no encontrado en RENIEC."}

    except Exception as _e:
        app.logger.debug(f"_lookup_dni_eldni DNI={dni}: {_e}")
        return {"error": "sunat_no_disponible", "msg": "No se pudo conectar al servicio RENIEC."}


def _lookup_ruc_sunat(ruc):
    """Consulta e-consultaruc.sunat.gob.pe para obtener datos de un RUC.
    SUNAT usa reCAPTCHA v3 en el frontend pero NO lo valida en el backend,
    por lo que se puede enviar un token ficticio.
    """
    import html as _htmllib
    try:
        import requests as _req
        base = "https://e-consultaruc.sunat.gob.pe/cl-ti-itmrconsruc/jcrS00Alias"
        sess = _req.Session()
        sess.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "es-PE,es;q=0.9",
            "Origin": "https://e-consultaruc.sunat.gob.pe",
            "Referer": base,
        })
        sess.get(base, timeout=8)
        r = sess.post(base, data={
            "accion": "consPorRuc", "razSoc": "", "nroRuc": ruc,
            "nrodoc": "", "token": "x", "contexto": "ti-it",
            "modo": "1", "rbtnTipo": "1", "search1": ruc, "codigo": "",
        }, timeout=12)
        r.raise_for_status()
        html = r.content.decode("iso-8859-1", errors="replace")

        # Nombre: heading con formato '{RUC} - {NOMBRE}'
        m = re.search(
            re.escape(ruc) + r"\s*[-–—]\s*([^<]{5,100}?)\s*</h4>",
            html, re.IGNORECASE,
        )
        if not m:
            return {"error": "no_encontrado", "msg": "RUC no encontrado en SUNAT."}
        nombre = _htmllib.unescape(m.group(1)).strip()

        # Estado: <p class="list-group-item-text"> después de "Estado del Contribuyente"
        m_est = re.search(
            r"Estado del Contribuyente[^<]*</h4>.*?"
            r'<p[^>]*list-group-item-text[^>]*>\s*([^<]+)',
            html, re.DOTALL | re.IGNORECASE,
        )
        estado = _htmllib.unescape(m_est.group(1)).strip() if m_est else ""

        return {"nombre": nombre, "estado": estado, "fuente": "sunat"}
    except Exception as _e:
        app.logger.debug(f"_lookup_ruc_sunat RUC={ruc}: {_e}")
        return {"error": "sunat_no_disponible", "msg": "No se pudo conectar a SUNAT."}


# ── SUNAT / RENIEC lookup proxy ───────────────────────────────────────────────
@app.route("/api/sunat/<numero>")
@limiter.limit("20 per minute")
def api_sunat(numero):
    """Consulta RENIEC o SUNAT según la longitud del número.
    8 dígitos  → DNI: scraping eldni.com (RENIEC).
    11 dígitos → RUC: scraping directo e-consultaruc.sunat.gob.pe.
    """
    if not re.fullmatch(r"\d{8}|\d{11}", numero):
        return jsonify({"error": "formato_invalido",
                        "msg": "Se esperan 8 dígitos (DNI) o 11 (RUC)"}), 400

    if len(numero) == 8:
        return jsonify(_lookup_dni_eldni(numero))

    return jsonify(_lookup_ruc_sunat(numero))


if __name__ == "__main__":
    # Por defecto debug=False (producción). Para activarlo en local: FLASK_DEBUG=True en .env
    debug_mode = os.getenv("FLASK_DEBUG", "False").lower() in ("true", "1", "yes")
    app.run(debug=debug_mode, port=5000)

