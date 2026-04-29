# -*- coding: utf-8 -*-
"""
Fix routing issues:
1. Atomizadores (IDs 58,59,60,61): wrong unidad=Mediana Minería → Agrícola, tipo → Atomizador
2. Clean descripcion for new retroexcavadora/motoniveladora products
"""
import sqlite3

DB = 'cgm.db'
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

changes = []

# ─── 1. FIX ATOMIZADORES ─────────────────────────────────────────────────────
# IDs 58,59,60 are active (tags=usados) and should be in usados/agricola
# ID 61 is inactive (tags=alquiler) — fix unidad too for consistency
cur.execute(
    "UPDATE products SET unidad='Agrícola', tipo='Atomizador' WHERE id IN (58,59,60,61)"
)
print(f"Fixed {cur.rowcount} atomizadores → unidad=Agrícola, tipo=Atomizador")
changes.append(f"Atomizadores (58,59,60,61): unidad Mediana Minería→Agrícola, tipo→Atomizador")

# ─── 2. CLEAN DESCRIPCION: retroexcavadora-310p ──────────────────────────────
cur.execute("""
    UPDATE products SET descripcion='91 HP @ 2,200 rpm|7,357 kg|Cucharón 1 m³ / Exc. 0.21 m³'
    WHERE slug='retroexcavadora-310p'
""")
if cur.rowcount:
    print("Fixed descripcion: retroexcavadora-310p")
    changes.append("retroexcavadora-310p: descripcion limpiada a 3 campos")

# ─── 3. CLEAN DESCRIPCION: retroexcavadora-320p ──────────────────────────────
cur.execute("""
    UPDATE products SET descripcion='98 HP @ 1,980 rpm|7,850 kg|Cucharón 1 m³ / Exc. 0.21 m³'
    WHERE slug='retroexcavadora-320p'
""")
if cur.rowcount:
    print("Fixed descripcion: retroexcavadora-320p")
    changes.append("retroexcavadora-320p: descripcion limpiada a 3 campos")

# ─── 4. CLEAN DESCRIPCION: motoniveladora-620p ───────────────────────────────
cur.execute("""
    UPDATE products SET descripcion='Hasta 200 HP|14,904 kg|Hoja: 12 ft / 3.66 m'
    WHERE slug='motoniveladora-620p'
""")
if cur.rowcount:
    print("Fixed descripcion: motoniveladora-620p")
    changes.append("motoniveladora-620p: descripcion limpiada a 3 campos")

# ─── VERIFY ROUTING AFTER FIX ────────────────────────────────────────────────
print("\n=== VERIFICATION ===")
VALID_ROUTES = [
    ('alquiler','Construcción','Excavadora'),
    ('alquiler','Construcción','Cargador Frontal'),
    ('alquiler','Construcción','Tractor de Orugas'),
    ('alquiler','Construcción','Rodillo Compactador'),
    ('alquiler','Construcción','Motoniveladora'),
    ('alquiler','Construcción','Retroexcavadora'),
    ('alquiler','Construcción','Minicargador'),
    ('alquiler','Construcción','Camión Cisterna'),
    ('alquiler','Construcción','Camión Grúa'),
    ('alquiler','Construcción','Compresora'),
    ('alquiler','Construcción','Torre de Iluminación'),
    ('alquiler','Construcción','Aditamento'),
    ('alquiler','Construcción','Camión Volquete'),
    ('alquiler','Construcción','Micropavimentadora'),
    ('alquiler','Construcción','Pavimentadora'),
    ('alquiler','Construcción','Autohormigonera'),
    ('alquiler','Construcción','Tren de Chancado'),
    ('alquiler','Mediana Minería', None),
    ('alquiler','Agrícola', None),
    ('alquiler','Energía', None),
    ('alquiler','Energía','Generador'),
    ('alquiler','Energía','Compresora'),
    ('alquiler','Energía','Aditamento'),
    ('alquiler','Agrícola','Aditamento'),
    ('usados','Construcción', None),
    ('usados','Agrícola', None),
    ('usados','Energía', None),
]

cur.execute("SELECT id,slug,nombre,tags,unidad,tipo,activo FROM products WHERE activo=1")
rows = cur.fetchall()
issues = 0
for r in rows:
    found = any(
        ct == r['tags'] and cu == r['unidad'] and (ctyp is None or ctyp == r['tipo'])
        for ct, cu, ctyp in VALID_ROUTES
    )
    if not found:
        print(f"  STILL BAD: ID={r['id']} {r['nombre']} tags={r['tags']} unidad={r['unidad']} tipo={r['tipo']}")
        issues += 1

if issues == 0:
    print("  All active products have valid routing!")
else:
    print(f"  {issues} products still have routing issues")

# Print final counts per route
print("\n=== ACTIVE PRODUCTS PER CATEGORY ===")
cur.execute("""
    SELECT tags, unidad, tipo, COUNT(*) as cnt
    FROM products WHERE activo=1
    GROUP BY tags, unidad, tipo
    ORDER BY unidad, tags, tipo
""")
for r in cur.fetchall():
    print(f"  {r['tags']:8} | {r['unidad']:20} | {str(r['tipo']):25} | {r['cnt']} productos")

conn.commit()
conn.close()
print(f"\nDone. {len(changes)} change groups applied.")
