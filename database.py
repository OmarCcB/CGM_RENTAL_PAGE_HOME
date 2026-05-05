import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "cgm.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def create_tables(conn):
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
        activo            INTEGER DEFAULT 1
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
        activo    INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS cotizaciones (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre   TEXT,
        empresa  TEXT,
        email    TEXT,
        telefono TEXT,
        tipo     TEXT,
        mensaje  TEXT,
        pais     TEXT,
        productos TEXT,
        fecha    TEXT DEFAULT (datetime('now'))
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
    conn.commit()


def init_db():
    conn = get_conn()
    create_tables(conn)
    # Migración: agrega columna si no existe (para DBs ya creadas)
    try:
        conn.execute("ALTER TABLE products ADD COLUMN descripcion_texto TEXT")
        conn.commit()
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE products ADD COLUMN show_arg INTEGER DEFAULT 0")
        conn.commit()
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE products ADD COLUMN a_solicitud INTEGER DEFAULT 0")
        conn.commit()
    except Exception:
        pass
    conn.close()
