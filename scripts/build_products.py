#!/usr/bin/env python3
"""
Extraer datos de productos del HTML y completar con los directorios de imágenes.
"""
import re
import json
import os

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(SCRIPTS_DIR)
SRC = os.path.join(SCRIPTS_DIR, "source_categoria.html")
IMAGES_DIR = os.path.join(BASE, "static", "images")
PRODUCTS_JSON = os.path.join(BASE, "products.json")

with open(SRC, "r", encoding="utf-8") as f:
    src_html = f.read()

# ── Extraer los 12 productos visibles del HTML ──
products = []

# Buscar cada bloque de producto
li_pattern = re.compile(
    r'<li class="daf-template-loop[^"]*"'
    r'\s+data-cgm-tags="([^"]*)"'
    r'\s+data-cgm-tipo="([^"]*)">'
    r'(.*?)</li>',
    re.DOTALL
)

for m in li_pattern.finditer(src_html):
    tags = m.group(1)
    tipo = m.group(2)
    block = m.group(3)

    # URL del producto
    url_m = re.search(r'href="(/producto/[^"]*)"', block)
    url = url_m.group(1) if url_m else ""

    # Nombre
    name_m = re.search(r'<h2 class="woocommerce-loop-product__title">([^<]*)</h2>', block)
    nombre = name_m.group(1) if name_m else ""

    # Marca
    marca_m = re.search(r'<div class="product-category">([^<]*)</div>', block)
    marca = marca_m.group(1) if marca_m else ""

    # Slug
    slug = url.replace("/producto/", "").replace("/index.html", "").strip("/")

    # Unidad de negocio (deducir del tipo de maquinaria)
    unidad = deducir_unidad(tipo, tags) if False else None

    products.append({
        "slug": slug,
        "nombre": nombre,
        "marca": marca,
        "tags": tags,
        "tipo": tipo,
        "imagen": f"/imagenes/{slug}/1.jpg",
        "visible": True
    })

print(f"Productos extraídos del HTML: {len(products)}")
extracted_slugs = {p["slug"] for p in products}

# ── Completar con directorios de imágenes no vistos ──
# Mapeo de slug a tipo de maquinaria y tags basado en el nombre
TIPO_MAP = {
    "atomizador": "Pulverizadora",
    "pulverizador": "Pulverizadora",
    "camion-grua": "Camion Grua",
    "camiones-cisterna": "Camión Cisterna",
    "cargador-frontal": "Cargador Frontal",
    "excavadora": "Excavadora",
    "generador": "Generador",
    "martillos-hidraulicos": "Martillos Hidráulicos",
    "minicargadores": "Minicargador",
    "minicargador": "Minicargador",
    "motoniveladora": "Motoniveladora",
    "retroexcavadora": "Retroexcavadora",
    "rodillo": "Rodillo Compactador",
    "tableros": "Aditamento",
    "tanques": "Aditamento",
    "torres-de-iluminacion": "Torre de Iluminación",
    "tractor-de-orugas": "Tractor de Orugas",
    "tractores": "Tractor Agrícola",
}

# Mapeo más específico de tractores agrícolas a subtipos
TRACTOR_SUBTIPO = {
    "tractor-agricola-3036en": "Tractor Utilitarios",      # 36HP - utilitario
    "tractor-agricola-5076ef": "Tractor Utilitarios",      # 76HP - utilitario
    "tractor-agricola-5090en": "Tractor Utilitarios",      # 90HP - utilitario
    "tractor-agricola-6110d": "Tractor Mediano",           # 110HP - mediano
    "tractor-agricola-6125e": "Tractor Mediano",           # 125HP - mediano
    "tractor-agricola-6403": "Tractor Especializados",     # especializado
    "tractor-agricola-6603": "Tractor Especializados",     # especializado
    "tractor-agricola-7230j": "Tractor Grande",            # 230HP - grande
    "tractor-agricola-serie-6j": "Tractor Grande",         # serie 6J - grande
}

UNIDAD_MAP = {
    "Pulverizadora": "Agrícola",
    "Tractor Agrícola": "Agrícola",
    "Tractor Utilitarios": "Agrícola",
    "Tractor Especializados": "Agrícola",
    "Tractor Grande": "Agrícola",
    "Tractor Mediano": "Agrícola",
    "Tractor de Orugas": "Construcción",
    "Excavadora": "Construcción",
    "Cargador Frontal": "Construcción",
    "Camion Grua": "Construcción",
    "Camión Cisterna": "Construcción",
    "Generador": "Energía",
    "Martillos Hidráulicos": "Construcción",
    "Minicargador": "Construcción",
    "Motoniveladora": "Construcción",
    "Retroexcavadora": "Construcción",
    "Rodillo Compactador": "Construcción",
    "Torre de Iluminación": "Energía",
    "Aditamento": "Construcción",
}

MARCA_MAP = {
    "excavadora-hidraulica-210glc": "JOHN DEERE",
    "excavadora-hidraulica-250g": "JOHN DEERE",
    "excavadora-hidraulica-350g": "JOHN DEERE",
    "excavadora-hidraulica-350g-lc": "JOHN DEERE",
    "excavadora-hidraulica-870g": "JOHN DEERE",
    "excavadora-hidraulica-zx1200": "HITACHI",
    "excavadora-hidraulica-zx210": "HITACHI",
    "excavadora-hidraulica-zx350": "HITACHI",
    "excavadora-hidraulica-zx870lc-5": "HITACHI",
    "cargador-frontal-644k": "JOHN DEERE",
    "cargador-frontal-744k": "JOHN DEERE",
    "camion-grua": "DAF / HYDROKHAN",
    "camiones-cisterna": "DAF / HITACHI",
    "generador-aksa": "AKSA",
    "generador-tk": "TEKSAN",
    "martillos-hidraulicos": "JCB",
    "minicargadores-320": "JOHN DEERE",
    "motoniveladora-670g": "JOHN DEERE",
    "retroexcavadora-310": "JOHN DEERE",
    "rodillo": "JCB",
    "tractor-agricola": "JOHN DEERE",
    "tractor-de-orugas": "JOHN DEERE",
    "torres-de-iluminacion": "AKSA",
    "atomizador": "GAMMA",
    "pulverizador": "GAMMA",
}


def slug_to_nombre(slug):
    """Convertir slug a nombre legible."""
    nombre = slug.replace("-", " ").upper()
    # Limpiar CIP codes
    nombre = re.sub(r'\s+CIP\s+', ' CIP: ', nombre)
    return nombre


def get_tipo(slug):
    """Deducir tipo de maquinaria del slug."""
    # Primero verificar subtipos de tractor
    for prefix, subtipo in TRACTOR_SUBTIPO.items():
        if slug.startswith(prefix):
            return subtipo
    # Si es tractor-agricola genérico (con CIP u otra variante)
    if slug.startswith("tractor-agricola"):
        return "Tractor Utilitarios"  # default para tractores no mapeados
    for prefix, tipo in TIPO_MAP.items():
        if slug.startswith(prefix):
            return tipo
    return "Otro"


def get_marca(slug):
    """Deducir marca del slug."""
    for prefix, marca in MARCA_MAP.items():
        if slug.startswith(prefix):
            return marca
    return "CGM RENTAL"


def get_tags(slug):
    """Deducir si es alquiler o usados del slug."""
    # Los que tienen CIP son usados generalmente
    if "cip" in slug.lower():
        return "usados"
    # Los usados tienen sufijos como cip-mXXXXXX
    if re.search(r'cip-[a-z]?\d+$', slug):
        return "usados"
    return "alquiler"


if os.path.isdir(IMAGES_DIR):
    for dirname in sorted(os.listdir(IMAGES_DIR)):
        dirpath = os.path.join(IMAGES_DIR, dirname)
        if not os.path.isdir(dirpath):
            continue
        if dirname in extracted_slugs:
            continue

        # Verificar que hay imágenes
        images = [f for f in os.listdir(dirpath) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
        if not images:
            continue

        tipo = get_tipo(dirname)
        unidad = UNIDAD_MAP.get(tipo, "Construcción")
        tags = get_tags(dirname)
        marca = get_marca(dirname)

        products.append({
            "slug": dirname,
            "nombre": slug_to_nombre(dirname),
            "marca": marca,
            "tags": tags,
            "tipo": tipo,
            "unidad": unidad,
            "imagen": f"/imagenes/{dirname}/{images[0]}",
            "visible": False
        })

# Agregar unidad a los productos extraídos del HTML que no la tienen
for p in products:
    if "unidad" not in p:
        p["unidad"] = UNIDAD_MAP.get(p["tipo"], "Construcción")

print(f"Total productos (HTML + imágenes): {len(products)}")
print(f"\nPor tags:")
from collections import Counter
tag_counts = Counter(p["tags"] for p in products)
for tag, count in tag_counts.most_common():
    print(f"  {tag}: {count}")

print(f"\nPor tipo:")
tipo_counts = Counter(p["tipo"] for p in products)
for tipo, count in tipo_counts.most_common():
    print(f"  {tipo}: {count}")

print(f"\nPor unidad:")
unidad_counts = Counter(p["unidad"] for p in products)
for unidad, count in unidad_counts.most_common():
    print(f"  {unidad}: {count}")

# Guardar
with open(PRODUCTS_JSON, "w", encoding="utf-8") as f:
    json.dump(products, f, ensure_ascii=False, indent=2)

print(f"\n[OK] {len(products)} productos guardados en {PRODUCTS_JSON}")
