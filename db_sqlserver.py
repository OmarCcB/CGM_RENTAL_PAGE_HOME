"""
db_sqlserver.py — Conexión a Azure SQL Server (CGMCOMERCIAL)
Usada para almacenar leads de contacto y cotizaciones del sitio web.
"""
import os
import pyodbc


def get_conn():
    """Abre y retorna una conexión a SQL Server. Cerrar manualmente tras usar."""
    driver   = os.getenv("ODBC_DRIVER", "ODBC Driver 18 for SQL Server")
    server   = os.getenv("SQL_SERVER",   "")
    database = os.getenv("SQL_DATABASE", "")
    user     = os.getenv("SQL_USER",     "")
    password = os.getenv("SQL_PASSWORD", "")

    conn_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={user};"
        f"PWD={password};"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
        "Connection Timeout=8;"
    )
    return pyodbc.connect(conn_str, autocommit=False)


def init_tables():
    """
    Crea las tablas CGM_Contacto_Leads y CGM_Cotizaciones si no existen.
    Llamar una sola vez al iniciar la app (si SQL_SERVER está configurado).
    """
    conn   = get_conn()
    cursor = conn.cursor()

    # ── Tabla 1: formulario de Contacto ──────────────────────────────────────
    cursor.execute("""
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_NAME = 'CGM_Contacto_Leads'
    )
    CREATE TABLE CGM_Contacto_Leads (
        id               INT           IDENTITY(1,1) PRIMARY KEY,
        fecha_envio      DATETIME2     DEFAULT GETDATE(),
        pais_sitio       VARCHAR(10)   NULL,
        nombre_apellido  NVARCHAR(200) NULL,
        razon_social     NVARCHAR(200) NULL,
        ruc_dni          VARCHAR(20)   NULL,
        pais             NVARCHAR(100) NULL,
        departamento     NVARCHAR(100) NULL,
        otro_pais        NVARCHAR(100) NULL,
        email            NVARCHAR(200) NULL,
        codigo_pais      VARCHAR(8)    NULL,
        celular          VARCHAR(30)   NULL,
        equipo_requerido NVARCHAR(500) NULL,
        sector_producto  NVARCHAR(100) NULL,
        tipo_alquiler    BIT           DEFAULT 0,
        tipo_compra      BIT           DEFAULT 0,
        preguntas_filtro NVARCHAR(MAX) NULL,
        sf_enviado       BIT           DEFAULT 0
    )
    """)

    # ── Tabla 2: formulario de Cotización (carrito) ───────────────────────────
    cursor.execute("""
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_NAME = 'CGM_Cotizaciones'
    )
    CREATE TABLE CGM_Cotizaciones (
        id               INT           IDENTITY(1,1) PRIMARY KEY,
        fecha_envio      DATETIME2     DEFAULT GETDATE(),
        pais_sitio       VARCHAR(10)   NULL,
        nombre_apellido  NVARCHAR(200) NULL,
        razon_social     NVARCHAR(200) NULL,
        ruc_dni          VARCHAR(20)   NULL,
        email            NVARCHAR(200) NULL,
        codigo_pais      VARCHAR(8)    NULL,
        celular          VARCHAR(30)   NULL,
        pais             NVARCHAR(100) NULL,
        departamento     NVARCHAR(100) NULL,
        tipo_alquiler    BIT           DEFAULT 0,
        tipo_compra      BIT           DEFAULT 0,
        detalle_equipos  NVARCHAR(MAX) NULL,
        sector_producto  NVARCHAR(100) NULL,
        preguntas_filtro NVARCHAR(MAX) NULL,
        sf_enviado       BIT           DEFAULT 0
    )
    """)

    conn.commit()
    conn.close()
