"""
database.py — Capa de acceso a datos sobre SQLite local.

Uso:
    conn = get_conn()
    row  = conn.execute("SELECT * FROM products WHERE slug=?", (slug,)).fetchone()
    row["nombre"]   # acceso por nombre de columna
    conn.commit(); conn.close()

Dentro de un request Flask se reutiliza la misma conexión (via g) para
no abrir/cerrar múltiples veces por request. El teardown_appcontext de
app.py se encarga de cerrarla al final.
"""

import os
import sqlite3

# La BD vive en data/cgm.db (carpeta separada del código)
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "cgm.db")


# ── Proxy para request Flask (close() es no-op) ──────────────────────────────
class _ReqConn:
    """Proxy de conexión SQLite para uso dentro de un Flask request.
    close() es no-op: la cierra teardown_appcontext al terminar el request.
    """
    __slots__ = ("_conn",)

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        if params is None:
            return self._conn.execute(sql)
        return self._conn.execute(sql, params)

    def executemany(self, sql, seq):
        return self._conn.executemany(sql, seq)

    def cursor(self):
        return self._conn.cursor()

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        pass  # no-op: gestionado por teardown_appcontext

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            try:
                self.commit()
            except Exception:
                pass


# ── Conexión real ─────────────────────────────────────────────────────────────
def _make_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # mejor concurrencia lectores/escritores
    conn.execute("PRAGMA synchronous=NORMAL") # más rápido que FULL, seguro
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_conn():
    """Devuelve una conexión a SQLite.

    Dentro de un request Flask reutiliza la misma conexión almacenada en
    g._db_conn (una sola apertura por request). Fuera de request context
    (startup, scripts) crea una conexión normal.
    """
    try:
        from flask import g, has_request_context
        if has_request_context():
            if not hasattr(g, '_db_conn'):
                g._db_conn = _make_conn()
            return _ReqConn(g._db_conn)
    except RuntimeError:
        pass
    return _make_conn()


# ── Inicialización ────────────────────────────────────────────────────────────
def init_db():
    """Crea las tablas principales si no existen y aplica migraciones."""
    conn = _make_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS products (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        slug              TEXT UNIQUE NOT NULL,
        nombre            TEXT NOT NULL,
        marca             TEXT,
        descripcion       TEXT,
        descripcion_texto TEXT,
        ficha_url         TEXT,
        tags              TEXT,
        tipo              TEXT,
        unidad            TEXT,
        imagen            TEXT,
        activo            INTEGER DEFAULT 1,
        show_pe           INTEGER DEFAULT 1,
        show_arg          INTEGER DEFAULT 0,
        a_solicitud       INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS blog_posts (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        slug      TEXT UNIQUE NOT NULL,
        titulo    TEXT NOT NULL,
        categoria TEXT,
        fecha     TEXT,
        imagen    TEXT,
        extracto  TEXT,
        contenido TEXT,
        video_url TEXT,
        activo    INTEGER DEFAULT 1,
        show_arg  INTEGER DEFAULT 0,
        show_pe   INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS cotizaciones (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre    TEXT,
        empresa   TEXT,
        email     TEXT,
        telefono  TEXT,
        tipo      TEXT,
        mensaje   TEXT,
        pais      TEXT,
        productos TEXT,
        fecha     TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS proveedores (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        empresa     TEXT,
        ruc         TEXT,
        contacto    TEXT,
        email       TEXT,
        telefono    TEXT,
        rubro       TEXT,
        descripcion TEXT,
        fecha       TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS denuncias (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo        TEXT,
        descripcion TEXT,
        fecha       TEXT DEFAULT (datetime('now'))
    );
    """)
    # Migraciones de columnas (para DBs ya existentes)
    for sql in [
        "ALTER TABLE products ADD COLUMN descripcion_texto TEXT",
        "ALTER TABLE products ADD COLUMN show_pe INTEGER DEFAULT 1",
        "ALTER TABLE products ADD COLUMN show_arg INTEGER DEFAULT 0",
        "ALTER TABLE products ADD COLUMN a_solicitud INTEGER DEFAULT 0",
        "ALTER TABLE blog_posts ADD COLUMN show_arg INTEGER DEFAULT 0",
        "ALTER TABLE blog_posts ADD COLUMN show_pe INTEGER DEFAULT 1",
        "ALTER TABLE products ADD COLUMN imagenes_orden TEXT",
    ]:
        try:
            conn.execute(sql)
        except Exception:
            pass

    # Tabla de categorías dinámica
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS categorias (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        tag          TEXT NOT NULL,
        unidad       TEXT NOT NULL,
        unidad_slug  TEXT NOT NULL,
        tipo         TEXT NOT NULL,
        tipo_titulo  TEXT NOT NULL,
        slug_sub     TEXT,
        orden        INTEGER DEFAULT 0,
        show_pe      INTEGER DEFAULT 1,
        show_ar      INTEGER DEFAULT 0,
        activo       INTEGER DEFAULT 1,
        UNIQUE(tag, unidad_slug, tipo)
    );
    """)

    conn.commit()
    conn.close()
    seed_categorias()
    migrate_categorias_slugs()


def _slugify_tipo(texto):
    """Convierte un nombre de tipo a slug URL: 'Tractor Grande' → 'tractor-grande'."""
    import re
    t = texto.lower().strip()
    for a, b in [('á','a'),('é','e'),('í','i'),('ó','o'),('ú','u'),
                 ('ñ','n'),('ü','u'),('ã','a'),('â','a')]:
        t = t.replace(a, b)
    t = re.sub(r'[^a-z0-9]+', '-', t)
    t = re.sub(r'-+', '-', t).strip('-')
    return t


def migrate_categorias_slugs():
    """Rellena slug_sub en filas que tienen NULL, generándolo desde el tipo."""
    conn = _make_conn()
    try:
        rows = conn.execute(
            "SELECT id, tipo FROM categorias WHERE slug_sub IS NULL OR slug_sub = ''"
        ).fetchall()
        for row in rows:
            slug = _slugify_tipo(row[1])
            conn.execute("UPDATE categorias SET slug_sub=? WHERE id=?", (slug, row[0]))
        if rows:
            conn.commit()
    except Exception:
        pass
    conn.close()


def seed_categorias():
    """Siembra las categorías iniciales SOLO si la tabla está vacía."""
    conn = _make_conn()
    count = conn.execute("SELECT COUNT(*) FROM categorias").fetchone()[0]
    if count > 0:
        conn.close()
        return

    rows = [
        # tag, unidad, unidad_slug, tipo, tipo_titulo, slug_sub, orden, show_pe, show_ar
        # ── Alquiler / Construcción ───────────────────────────────────────────
        ("alquiler","Construcción","construccion","Excavadora","Excavadoras","excavadora",1,1,1),
        ("alquiler","Construcción","construccion","Cargador Frontal","Cargadores Frontales","cargador-frontal",2,1,1),
        ("alquiler","Construcción","construccion","Tractor de Orugas","Tractores de Orugas","tractor-de-orugas",3,1,0),
        ("alquiler","Construcción","construccion","Rodillo Compactador","Rodillos Compactadores","rodillo-compactador",4,1,1),
        ("alquiler","Construcción","construccion","Motoniveladora","Motoniveladoras","motoniveladora",5,1,1),
        ("alquiler","Construcción","construccion","Retroexcavadora","Retroexcavadoras","retroexcavadora",6,1,1),
        ("alquiler","Construcción","construccion","Minicargador","Minicargadores","minicargador",7,1,1),
        ("alquiler","Construcción","construccion","Camión Cisterna","Camiones Cisterna","camion-cisterna",8,1,1),
        ("alquiler","Construcción","construccion","Camión Grúa","Camiones Grúa","camion-grua",9,1,0),
        ("alquiler","Construcción","construccion","Compresora","Compresoras","compresora",10,1,0),
        ("alquiler","Construcción","construccion","Torre de Iluminación","Torres de Iluminación","torre-de-iluminacion",11,1,1),
        ("alquiler","Construcción","construccion","Aditamento","Aditamentos","aditamentos",12,1,0),
        ("alquiler","Construcción","construccion","Topador","Topadores","topador",13,0,1),
        ("alquiler","Construcción","construccion","Camión Volquete","Camiones Volquete","camion-volquete",14,1,0),
        ("alquiler","Construcción","construccion","Micropavimentadora","Micropavimentadoras","micropavimentadora",15,1,0),
        ("alquiler","Construcción","construccion","Pavimentadora","Pavimentadoras","pavimentadora",16,1,0),
        ("alquiler","Construcción","construccion","Autohormigonera","Autohormigoneras","autohormigonera",17,1,0),
        ("alquiler","Construcción","construccion","Tren de Chancado","Tren de Chancado","tren-de-chancado",18,1,0),
        # ── Alquiler / Mediana Minería ────────────────────────────────────────
        ("alquiler","Mediana Minería","mineria","Excavadora","Excavadoras","excavadora",1,1,1),
        ("alquiler","Mediana Minería","mineria","Topador","Topadores","topador",2,0,1),
        ("alquiler","Mediana Minería","mineria","Aditamento","Aditamentos","aditamento",3,1,0),
        # ── Alquiler / Agrícola ───────────────────────────────────────────────
        ("alquiler","Agrícola","agricola","Tractor Especializados","Tractores Especializados/Fruteros","tractor-especializados",1,1,0),
        ("alquiler","Agrícola","agricola","Tractor Utilitarios","Tractores Utilitarios de 75 a 100 HP","tractor-utilitarios",2,1,0),
        ("alquiler","Agrícola","agricola","Tractor Grande","Tractores Grandes 150 HP a Más","tractor-grande",3,1,0),
        ("alquiler","Agrícola","agricola","Tractor Mediano","Tractores Medianos de 100 a 150 HP","tractor-mediano",4,1,0),
        ("alquiler","Agrícola","agricola","Aditamento","Aditamentos","aditamento",5,1,0),
        # ── Alquiler / Energía ────────────────────────────────────────────────
        ("alquiler","Energía","energia","Generador","Grupos Electrógenos","grupo-electrogeno",1,1,0),
        ("alquiler","Energía","energia","Compresora","Compresoras","compresora",2,1,0),
        ("alquiler","Energía","energia","Aditamento","Aditamentos","aditamento",3,1,0),
        # ── Usados / Energía ──────────────────────────────────────────────────
        ("usados","Energía","energia","Generador","Grupos Electrógenos","generador",1,1,0),
        ("usados","Energía","energia","Aditamento","Aditamentos","aditamento",2,1,0),
    ]

    conn.executemany(
        """INSERT OR IGNORE INTO categorias
           (tag, unidad, unidad_slug, tipo, tipo_titulo, slug_sub, orden, show_pe, show_ar)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        rows
    )
    conn.commit()
    conn.close()


def init_admin_tables(conn=None):
    """Crea las tablas del panel admin si no existen."""
    close_after = conn is None
    if conn is None:
        conn = _make_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS site_config (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        country_code TEXT NOT NULL,
        key          TEXT NOT NULL,
        value        TEXT,
        UNIQUE(country_code, key)
    );

    CREATE TABLE IF NOT EXISTS sucursales_db (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        country_code TEXT NOT NULL,
        nombre       TEXT,
        tipo         TEXT DEFAULT 'sucursal',
        direccion    TEXT,
        lat          REAL,
        lng          REAL,
        maps_url     TEXT,
        telefono     TEXT,
        orden        INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS audit_log (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario TEXT,
        accion  TEXT,
        detalle TEXT,
        fecha   TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS banners_config (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        slot         TEXT NOT NULL,
        country_code TEXT NOT NULL DEFAULT '*',
        group_name   TEXT,
        label        TEXT,
        description  TEXT,
        filename     TEXT,
        orden        INTEGER DEFAULT 0,
        pages        TEXT,
        activo       INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS popups (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        titulo              TEXT,
        imagen              TEXT,
        link_url            TEXT,
        abrir_nueva_ventana INTEGER DEFAULT 1,
        fecha_inicio        TEXT NOT NULL,
        fecha_fin           TEXT NOT NULL,
        activo              INTEGER DEFAULT 1,
        fecha_creacion      TEXT DEFAULT (datetime('now')),
        imagen_fit          TEXT DEFAULT 'cover',
        boton_activo        INTEGER DEFAULT 0,
        boton_texto         TEXT DEFAULT 'Ver más',
        boton_color_fondo   TEXT DEFAULT '#02534C',
        boton_color_texto   TEXT DEFAULT '#ffffff',
        boton_tamano        TEXT DEFAULT 'md',
        boton_pos_x         INTEGER DEFAULT 50,
        boton_pos_y         INTEGER DEFAULT 85,
        frecuencia          TEXT DEFAULT 'siempre',
        delay_ms            INTEGER DEFAULT 800,
        pais_filtro         TEXT DEFAULT 'todos',
        animacion           TEXT DEFAULT 'fade',
        total_vistas        INTEGER DEFAULT 0,
        total_clics         INTEGER DEFAULT 0
    );
    """)
    conn.commit()
    # Migraciones para popups ya existentes
    for sql in [
        "ALTER TABLE popups ADD COLUMN imagen_fit TEXT DEFAULT 'cover'",
        "ALTER TABLE popups ADD COLUMN boton_activo INTEGER DEFAULT 0",
        "ALTER TABLE popups ADD COLUMN boton_texto TEXT DEFAULT 'Ver más'",
        "ALTER TABLE popups ADD COLUMN boton_color_fondo TEXT DEFAULT '#02534C'",
        "ALTER TABLE popups ADD COLUMN boton_color_texto TEXT DEFAULT '#ffffff'",
        "ALTER TABLE popups ADD COLUMN boton_tamano TEXT DEFAULT 'md'",
        "ALTER TABLE popups ADD COLUMN boton_pos_x INTEGER DEFAULT 50",
        "ALTER TABLE popups ADD COLUMN boton_pos_y INTEGER DEFAULT 85",
        "ALTER TABLE popups ADD COLUMN frecuencia TEXT DEFAULT 'siempre'",
        "ALTER TABLE popups ADD COLUMN delay_ms INTEGER DEFAULT 800",
        "ALTER TABLE popups ADD COLUMN pais_filtro TEXT DEFAULT 'todos'",
        "ALTER TABLE popups ADD COLUMN animacion TEXT DEFAULT 'fade'",
        "ALTER TABLE popups ADD COLUMN total_vistas INTEGER DEFAULT 0",
        "ALTER TABLE popups ADD COLUMN total_clics INTEGER DEFAULT 0",
    ]:
        try:
            conn.execute(sql)
        except Exception:
            pass
    conn.commit()
    if close_after:
        conn.close()


# ── Helper UPSERT site_config ─────────────────────────────────────────────────
def upsert_site_config(conn, country_code, key, value):
    """Inserta o actualiza un valor en site_config."""
    conn.execute(
        """INSERT INTO site_config (country_code, key, value) VALUES (?, ?, ?)
           ON CONFLICT(country_code, key) DO UPDATE SET value=excluded.value""",
        (country_code, key, value),
    )
