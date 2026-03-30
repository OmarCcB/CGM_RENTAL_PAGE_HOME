#!/usr/bin/env python3
"""Sincronizar products.json con datos reales de cgm.db."""
import sqlite3
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(os.path.dirname(BASE), "cgm.db")  # ../cgm.db
PRODUCTS_JSON = os.path.join(BASE, "products.json")

def _extract_marca(slug, nombre=""):
    """Deduce marca del slug/nombre."""
    marca_map = {
        "excavadora-hidraulica-zx": "HITACHI",
        "excavadora-hidraulica": "JOHN DEERE",
        "cargador-frontal": "JOHN DEERE",
        "camion-grua": "DAF / HYDROKHAN",
        "camiones-cisterna": "DAF",
        "generador-aksa": "AKSA",
        "generador-tk": "TEKSAN",
        "martillos-hidraulicos": "JCB",
        "minicargadores": "JOHN DEERE",
        "motoniveladora": "JOHN DEERE",
        "retroexcavadora": "JOHN DEERE",
        "rodillo": "JCB",
        "tractor-agricola": "JOHN DEERE",
        "tractor-de-orugas": "JOHN DEERE",
        "tractores": "JOHN DEERE",
        "torres-de-iluminacion": "AKSA",
        "atomizador": "GAMMA",
        "pulverizador": "GAMMA",
        "tableros": "CGM RENTAL",
        "tanques": "CGM RENTAL",
    }
    for prefix, marca in sorted(marca_map.items(), key=lambda x: len(x[0]), reverse=True):
        if slug.startswith(prefix):
            return marca
    return "CGM RENTAL"


conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT * FROM productos")
rows = cur.fetchall()

products = []
for r in rows:
    # Parse specs JSON
    specs = []
    if r["specs"]:
        try:
            specs = json.loads(r["specs"])
        except json.JSONDecodeError:
            specs = [r["specs"]]

    # Parse unidades JSON
    unidades_raw = r["unidades"] or "[]"
    try:
        unidades_list = json.loads(unidades_raw)
    except json.JSONDecodeError:
        unidades_list = [unidades_raw]

    # Map unidad
    unidad_map = {
        "construccion": "Construcción",
        "agricola": "Agrícola",
        "energia": "Energía",
        "usados": None,  # usados uses tags, not unidad
        "mineria": "Construcción",
    }
    unidad = None
    for u in unidades_list:
        u_lower = u.lower().strip()
        if u_lower in unidad_map and unidad_map[u_lower]:
            unidad = unidad_map[u_lower]
            break

    # If no unidad found from unidades field, derive from tipo
    if not unidad:
        tipo = r["tipo"] or ""
        tipo_unidad = {
            "Pulverizadora": "Agrícola",
            "Tractor Agrícola": "Agrícola",
            "Tractor Utilitarios": "Agrícola",
            "Tractor Especializados": "Agrícola",
            "Tractor Grande": "Agrícola",
            "Tractor Mediano": "Agrícola",
            "Generador": "Energía",
            "Torre de Iluminación": "Energía",
        }
        unidad = tipo_unidad.get(tipo, "Construcción")

    # Determine image - prefer /imagenes/ path, fallback to wp-content
    slug = r["slug"]
    img_dir = os.path.join(BASE, "static", "images", slug)
    if os.path.isdir(img_dir):
        imgs = sorted([f for f in os.listdir(img_dir)
                       if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))])
        imagen = f"/imagenes/{slug}/{imgs[0]}" if imgs else (r["imagen_principal"] or "")
    else:
        imagen = r["imagen_principal"] or ""

    products.append({
        "slug": slug,
        "nombre": r["nombre"] or "",
        "marca": _extract_marca(slug, r["nombre"] or ""),
        "descripcion_texto": r["descripcion"] or "",
        "descripcion": specs,
        "ficha_tecnica": r["ficha_tecnica_url"] or "",
        "tags": r["tags"] or "alquiler",
        "tipo": r["tipo"] or "",
        "unidad": unidad,
        "imagen": imagen,
        "activo": bool(r["activo"]),
    })

conn.close()

print(f"Total productos: {len(products)}")
print(f"Con specs: {sum(1 for p in products if p['descripcion'])}")
print(f"Con descripcion: {sum(1 for p in products if p['descripcion_texto'])}")
print(f"Con ficha técnica: {sum(1 for p in products if p['ficha_tecnica'])}")
print(f"Activos: {sum(1 for p in products if p['activo'])}")

print(f"\nPor tags:")
from collections import Counter
for tag, c in Counter(p["tags"] for p in products).most_common():
    print(f"  {tag}: {c}")

print(f"\nPor unidad:")
for u, c in Counter(p["unidad"] for p in products).most_common():
    print(f"  {u}: {c}")

with open(PRODUCTS_JSON, "w", encoding="utf-8") as f:
    json.dump(products, f, ensure_ascii=False, indent=2)

print(f"\n[OK] {len(products)} productos guardados en {PRODUCTS_JSON}")
