# -*- coding: utf-8 -*-
"""
Duplica 5 productos para Argentina con nombres corregidos.
- Copia carpetas de imágenes
- Copia fichas PDF donde corresponde
- Bloquea los originales en Argentina (show_arg=0)
- Activa los duplicados solo en Argentina (show_arg=1)
"""
import sqlite3, json, os, shutil, sys
sys.stdout.reconfigure(encoding="utf-8")

BASE    = os.path.dirname(os.path.abspath(__file__))
DB      = os.path.join(BASE, "cgm.db")
JFILE   = os.path.join(BASE, "products.json")
PROD    = os.path.join(BASE, "static", "products")
FICHAS  = os.path.join(BASE, "static", "docs", "fichas")

# ──────────────────────────────────────────────────────────────
# MAPA: original_slug → (nuevo_slug, nuevo_nombre, conserva_ficha)
# ──────────────────────────────────────────────────────────────
DUPES = [
    # (original,                    nuevo_slug,                       nuevo_nombre,                     ficha?)
    ("cargador-frontal-644k",       "cargador-frontal-644p",          "CARGADOR FRONTAL 644P",          False),
    ("excavadora-hidraulica-210glc","excavadora-hidraulica-210p",     "EXCAVADORA HIDRÁULICA 210P",     False),
    ("minicargadores-320-324g",     "minicargadores-324g",            "MINICARGADORES 324G",            True),
    ("rodillo-hc-100",              "rodillo-compactador-hc110",      "RODILLO COMPACTADOR HC110",      False),
    ("excavadora-hidraulica-350p",  "excavadora-hidraulica-350p-ar",  "EXCAVADORA HIDRÁULICA 350 P",    True),
]

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur  = conn.cursor()

with open(JFILE, encoding="utf-8") as f:
    products_json = json.load(f)
json_by_slug = {p["slug"]: p for p in products_json}

# ──────────────────────────────────────────────────────────────
print("=== 1. Copiar carpetas de imágenes ===")
for orig, nuevo, *_ in DUPES:
    src = os.path.join(PROD, orig)
    dst = os.path.join(PROD, nuevo)
    if os.path.isdir(src):
        if os.path.isdir(dst):
            print(f"  SKIP (ya existe): {nuevo}/")
        else:
            shutil.copytree(src, dst)
            print(f"  COPIADO: {orig}/ → {nuevo}/")
    else:
        print(f"  NO ENCONTRADO: {orig}/")

# ──────────────────────────────────────────────────────────────
print("\n=== 2. Copiar fichas PDF donde corresponde ===")
for orig, nuevo, _, conserva_ficha in DUPES:
    if not conserva_ficha:
        print(f"  SIN FICHA: {nuevo}")
        continue
    src_pdf = os.path.join(FICHAS, f"{orig}.pdf")
    dst_pdf = os.path.join(FICHAS, f"{nuevo}.pdf")
    if os.path.isfile(src_pdf):
        if os.path.isfile(dst_pdf):
            print(f"  SKIP (ya existe): {nuevo}.pdf")
        else:
            shutil.copy2(src_pdf, dst_pdf)
            print(f"  COPIADO: {orig}.pdf → {nuevo}.pdf")
    else:
        print(f"  NO ENCONTRADO PDF: {orig}.pdf")

# ──────────────────────────────────────────────────────────────
print("\n=== 3. Insertar duplicados en DB y products.json ===")
for orig, nuevo, nombre, conserva_ficha in DUPES:
    # Leer original de la DB
    row = cur.execute("SELECT * FROM products WHERE slug=?", (orig,)).fetchone()
    if not row:
        print(f"  ORIGINAL NO ENCONTRADO EN DB: {orig}")
        continue

    r = dict(row)

    # Construir imagen del nuevo
    new_folder = os.path.join(PROD, nuevo)
    imgs = sorted([f for f in os.listdir(new_folder)
                   if f.lower().endswith((".webp",".png",".jpg",".jpeg",".avif"))
                   and not f.startswith(".")])
    imagen = f"{nuevo}/{imgs[0]}" if imgs else r["imagen"].replace(orig, nuevo)

    # Ficha URL
    if conserva_ficha:
        new_pdf = os.path.join(FICHAS, f"{nuevo}.pdf")
        if os.path.isfile(new_pdf):
            ficha_url = f"fichas/{nuevo}.pdf"
        else:
            ficha_url = r["ficha_url"]   # Google Drive link
    else:
        ficha_url = ""

    # Insertar en DB
    check = cur.execute("SELECT id FROM products WHERE slug=?", (nuevo,)).fetchone()
    if check:
        print(f"  SKIP DB (ya existe): {nuevo}")
    else:
        cur.execute("""
            INSERT INTO products
              (slug,nombre,marca,descripcion,ficha_url,tags,tipo,unidad,imagen,activo,descripcion_texto,show_arg)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            nuevo, nombre, r["marca"], r["descripcion"],
            ficha_url, r["tags"], r["tipo"], r["unidad"],
            imagen, 1, r.get("descripcion_texto",""), 1
        ))
        print(f"  INSERT DB: {nuevo} | ficha={ficha_url or 'ninguna'}")

    # Insertar en products.json
    if nuevo in json_by_slug:
        print(f"  SKIP JSON (ya existe): {nuevo}")
    else:
        orig_json = json_by_slug.get(orig, {})
        products_json.append({
            "slug":      nuevo,
            "nombre":    nombre,
            "marca":     r["marca"],
            "descripcion": r["descripcion"] or "",
            "ficha_url": ficha_url,
            "tags":      r["tags"],
            "tipo":      r["tipo"],
            "unidad":    r["unidad"],
            "imagen":    imagen,
            "activo":    1,
            "show_arg":  1,
        })
        json_by_slug[nuevo] = products_json[-1]
        print(f"  INSERT JSON: {nuevo}")

# ──────────────────────────────────────────────────────────────
print("\n=== 4. Bloquear originales en Argentina (show_arg=0) ===")
for orig, *_ in DUPES:
    cur.execute("UPDATE products SET show_arg=0 WHERE slug=?", (orig,))
    print(f"  show_arg=0: {orig}")
    # Actualizar en JSON
    if orig in json_by_slug:
        json_by_slug[orig]["show_arg"] = 0

# ──────────────────────────────────────────────────────────────
conn.commit()
conn.close()

with open(JFILE, "w", encoding="utf-8") as f:
    json.dump(products_json, f, ensure_ascii=False, indent=2)

print("\n✅ Listo!")
