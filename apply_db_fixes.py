"""
EJECUTAR ESTE SCRIPT MANUALMENTE:
1. Detener Flask (Ctrl+C en la terminal donde corre)
2. Correr: python apply_db_fixes.py
3. Reiniciar Flask
"""
import sqlite3
import os
import sys
import shutil
import tempfile

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cgm.db")

# Usar carpeta temporal del usuario (siempre disponible en Windows)
TEMP_DIR = tempfile.gettempdir()
TMP_DB   = os.path.join(TEMP_DIR, "cgm_fix.db")
BAK_DB   = os.path.join(TEMP_DIR, "cgm_fix.bak")

print(f"DB original : {DB}")
print(f"DB temporal : {TMP_DB}")
print(f"Carpeta temp: {TEMP_DIR}")

# ── 1. Copiar DB original a carpeta temporal del usuario ─────────────────────
print("\n[1] Copiando DB a ubicacion temporal...")
try:
    shutil.copy2(DB, TMP_DB)
    shutil.copy2(DB, BAK_DB)
    print(f"    Copia OK  ({os.path.getsize(TMP_DB):,} bytes)")
    print(f"    Backup en: {BAK_DB}")
except Exception as e:
    print(f"    ERROR: {e}")
    sys.exit(1)

# ── 2. Aplicar fixes en la copia ─────────────────────────────────────────────
print("\n[2] Aplicando fixes en copia temporal...")
conn = sqlite3.connect(TMP_DB, timeout=30)
cur  = conn.cursor()

cur.execute("""
    UPDATE products
    SET unidad = 'Agrícola',
        tipo   = 'Atomizador'
    WHERE id IN (58, 59, 60, 61)
""")
print(f"    [FIX 1] Atomizadores -> Agrícola/Atomizador : {cur.rowcount} filas")

cur.execute("""
    UPDATE products
    SET descripcion = '91 HP @ 2,200 rpm|7,357 kg|Cuch. 1 m³ / Exc. 0.21 m³'
    WHERE slug = 'retroexcavadora-310p'
""")
print(f"    [FIX 2] retroexcavadora-310p descripcion    : {cur.rowcount} filas")

cur.execute("""
    UPDATE products
    SET descripcion = '98 HP @ 1,980 rpm|7,850 kg|Cuch. 1 m³ / Exc. 0.21 m³'
    WHERE slug = 'retroexcavadora-320p'
""")
print(f"    [FIX 3] retroexcavadora-320p descripcion    : {cur.rowcount} filas")

cur.execute("""
    UPDATE products
    SET descripcion = 'Hasta 200 HP|14,904 kg|Hoja: 12 ft / 3.66 m'
    WHERE slug = 'motoniveladora-620p'
""")
print(f"    [FIX 4] motoniveladora-620p descripcion     : {cur.rowcount} filas")

conn.commit()

# Verificacion
print("\n[3] Verificando datos en copia...")
cur.execute("SELECT id, slug, unidad, tipo FROM products WHERE id IN (58,59,60,61)")
for r in cur.fetchall():
    print(f"    ID={r[0]} {r[1]}: unidad={r[2]}, tipo={r[3]}")
cur.execute("SELECT slug, descripcion FROM products WHERE slug IN ('retroexcavadora-310p','retroexcavadora-320p','motoniveladora-620p')")
for r in cur.fetchall():
    print(f"    {r[0]}: {r[1]}")
conn.close()

# ── 3. Reemplazar el original (rename atomico en mismo volumen) ───────────────
print(f"\n[4] Reemplazando DB original...")
try:
    os.replace(TMP_DB, DB)
    print(f"    OK — DB actualizado")
except Exception as e:
    print(f"\n    os.replace fallo: {e}")
    print(f"\n    *** COPIA MANUAL REQUERIDA ***")
    print(f"    Ejecuta este comando en PowerShell:")
    print(f'    Move-Item -Path "{TMP_DB}" -Destination "{DB}" -Force')
    sys.exit(1)

print("\n=== LISTO! Puedes reiniciar Flask. ===")
print(f"(Backup guardado en: {BAK_DB})")
