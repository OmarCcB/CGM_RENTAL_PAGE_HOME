import os
import json
import smtplib
from datetime import datetime
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
from dotenv import load_dotenv

from countries import COUNTRIES, DEFAULT_COUNTRY
from database import get_conn, init_db, init_admin_tables
import cache as _cache
import db_sqlserver

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "cgm-dev-secret")
Compress(app)

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


with app.app_context():
    init_db()
    seed_db()
    _admin_conn = get_conn()
    init_admin_tables(_admin_conn)
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
    show_country_filter = "AND show_arg=1" if country == 'ar' else "AND show_pe=1"
    all_featured = conn.execute(
        f"SELECT * FROM products WHERE activo=1 AND tags LIKE '%alquiler%' {show_country_filter}"
    ).fetchall()
    import random as _random
    featured = _random.sample(all_featured, min(6, len(all_featured)))
    # Últimas 6 noticias
    country_filter = " AND show_arg=1" if country == 'ar' else " AND show_pe=1"
    posts = conn.execute(
        f"SELECT * FROM blog_posts WHERE activo=1{country_filter} ORDER BY fecha DESC"
    ).fetchall()
    conn.close()
    return render_template("pages/home.html",
                           country=c, country_code=country,
                           featured=[dict(r) for r in featured],
                           posts=[dict(r) for r in posts])


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
@app.route("/<country>/categoria-producto/<path:cat_path>/")
def categoria(country=None, cat_path=""):
    if country is None:
        country = DEFAULT_COUNTRY
    if country not in COUNTRIES:
        return redirect(f"/{DEFAULT_COUNTRY}/categoria-producto/{cat_path}/")
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
@app.route("/<country>/producto/<slug>/")
def producto(slug, country=None):
    if country is None:
        country = DEFAULT_COUNTRY
    if country not in COUNTRIES:
        return redirect(f"/{DEFAULT_COUNTRY}/producto/{slug}/")
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
@app.route("/<country>/producto/<slug>/ficha/")
def ficha_tecnica(slug, country=None):
    import os as _os
    if country is None:
        country = DEFAULT_COUNTRY
    if country not in COUNTRIES:
        return redirect(f"/{DEFAULT_COUNTRY}/producto/{slug}/ficha/")
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


# ── Formulario Contacto → SQL Server (reemplaza Salesforce) ──────────────────
@app.route("/api/guardar-contacto", methods=["POST"])
def api_guardar_contacto():
    data        = request.form
    pais_sitio  = data.get("pais_sitio", "pe")
    try:
        conn   = db_sqlserver.get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO CGM_Contacto_Leads
              (pais_sitio, nombre_apellido, razon_social, ruc_dni, pais,
               departamento, otro_pais, email, celular, equipo_requerido,
               tipo_alquiler, tipo_compra, ip_cliente)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            pais_sitio,
            data.get("nombre_apellido", "").strip(),
            data.get("razon_social",    "").strip(),
            data.get("ruc_dni",         "").strip(),
            data.get("pais",            "").strip(),
            data.get("departamento",    "").strip(),
            data.get("otro_pais",       "").strip(),
            data.get("email",           "").strip(),
            data.get("celular",         "").strip(),
            data.get("equipo_requerido","").strip(),
            1 if data.get("tipo_alquiler") else 0,
            1 if data.get("tipo_compra")   else 0,
            request.remote_addr,
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        app.logger.error(f"[guardar-contacto] SQL Server error: {e}")
    return redirect(f"/{pais_sitio}/gracias/")


# ── Formulario Cotización (carrito) → SQL Server (reemplaza Salesforce) ───────
@app.route("/api/guardar-cotizacion", methods=["POST"])
def api_guardar_cotizacion():
    data        = request.form
    pais_sitio  = data.get("pais_sitio", "pe")
    try:
        conn   = db_sqlserver.get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO CGM_Cotizaciones
              (pais_sitio, nombre_apellido, razon_social, ruc_dni, email,
               celular, pais, departamento, tipo_alquiler, tipo_compra,
               detalle_equipos, ip_cliente)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            pais_sitio,
            data.get("nombre_apellido", "").strip(),
            data.get("razon_social",    "").strip(),
            data.get("ruc_dni",         "").strip(),
            data.get("email",           "").strip(),
            data.get("celular",         "").strip(),
            data.get("pais",            "").strip(),
            data.get("departamento",    "").strip(),
            1 if data.get("tipo_alquiler") else 0,
            1 if data.get("tipo_compra")   else 0,
            data.get("detalle_equipos",  "").strip(),
            request.remote_addr,
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        app.logger.error(f"[guardar-cotizacion] SQL Server error: {e}")
    return redirect(f"/{pais_sitio}/gracias/")


@app.route("/api/cart/add", methods=["POST"])
def api_cart_add():
    data = request.get_json(silent=True) or {}
    slug    = data.get("slug", "").strip()
    nombre  = data.get("nombre", "").strip()
    imagen  = data.get("imagen", "").strip()
    tipo    = data.get("tipo", "").strip()
    country = data.get("country", "pe").lower()
    if not slug:
        return jsonify({"ok": False}), 400
    key  = _cart_key(country)
    cart = session.get(key, {})
    if slug in cart:
        cart[slug]["qty"] += 1
    else:
        cart[slug] = {"slug": slug, "nombre": nombre, "imagen": imagen, "tipo": tipo, "qty": 1}
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


if __name__ == "__main__":
    # Por defecto debug=False (producción). Para activarlo en local: FLASK_DEBUG=True en .env
    debug_mode = os.getenv("FLASK_DEBUG", "False").lower() in ("true", "1", "yes")
    app.run(debug=debug_mode, port=5000)

