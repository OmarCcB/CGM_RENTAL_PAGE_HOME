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
    ]:
        try:
            conn.execute(sql)
        except Exception:
            pass
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
    """)
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
