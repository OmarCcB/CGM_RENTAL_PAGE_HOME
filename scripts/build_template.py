#!/usr/bin/env python3
"""
Script para construir templates/categoria.html a partir del HTML original
y extraer datos de productos del HTML.
"""
import re
import json
import os

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(SCRIPTS_DIR)
SRC = os.path.join(SCRIPTS_DIR, "source_categoria.html")
DST = os.path.join(BASE, "templates", "categoria.html")
PRODUCTS_JSON = os.path.join(BASE, "products.json")

# ── 1. Leer el HTML fuente ──
with open(SRC, "r", encoding="utf-8") as f:
    html = f.read()

lines = html.split("\n")
print(f"Total de líneas: {len(lines)}")

# ── 2. Reemplazar <title> con marcador ──
html = re.sub(
    r"<title>[^<]*</title>",
    "<title>$CGM_TITULO$ - CGM RENTAL</title>",
    html,
    count=1
)

# ── 3. Reemplazar og:title ──
html = re.sub(
    r'<meta property="og:title" content="[^"]*">',
    '<meta property="og:title" content="$CGM_TITULO$ - CGM RENTAL">',
    html,
    count=1
)

# ── 4. Reemplazar body class term-* ──
html = re.sub(
    r'term-alquiler term-\d+',
    'term-$CGM_TERM$ term-0',
    html,
    count=1
)

# ── 5. Reemplazar data-current-taxterm ──
html = re.sub(
    r'data-current-taxterm="[^"]*"',
    'data-current-taxterm="$CGM_TAXTERM$"',
    html,
    count=1
)

# ── 6. Encontrar y reemplazar la zona de productos ──
# La zona va desde <div class="filtered-posts-cont"> hasta su cierre,
# incluyendo la paginación.
# Buscar desde la línea que contiene "filtered-posts-cont" hasta el cierre
# de todo el bloque de archive_loop

# Patrón: desde el div.filtered-posts-cont hasta el cierre del
# et_pb_de_mach_archive_loop (incluyendo paginación)
pattern_start = '<div class="filtered-posts-cont">'
pattern_end = '</div>\n\t\t\t\t</div>\n\t\t\t\t</div>'

start_idx = html.find(pattern_start)
if start_idx == -1:
    print("ERROR: No se encontró el inicio del grid de productos")
    exit(1)

# Buscar el cierre después de la paginación
# El patrón exacto es: </div>\n\t\t\t\t</div>\n\t\t\t\t</div> seguido de los divs de cierre
# Buscar después del "divi-filter-pagination"
pagination_end = html.find("</div>\n\t\t\t\t\t\n\t\t\t\t\t</div>", start_idx)
if pagination_end == -1:
    # Buscar patrón alternativo
    pagination_end = html.find('<div class="et_pb_row et_pb_row_2_tb_body">', start_idx)
    if pagination_end == -1:
        print("ERROR: No se encontró el fin del grid de productos")
        exit(1)
    # Retroceder para incluir los cierres de div
    end_idx = pagination_end
else:
    end_idx = pagination_end

# Encontrar la sección exacta
# Desde el div.filtered-posts-cont hasta antes de et_pb_row_2_tb_body
row2_marker = '<div class="et_pb_row et_pb_row_2_tb_body">'
end_idx = html.find(row2_marker, start_idx)
if end_idx == -1:
    print("ERROR: No se encontró et_pb_row_2_tb_body")
    exit(1)

# La sección a reemplazar incluye desde filtered-posts-cont
# hasta justo antes de et_pb_row_2_tb_body, pero necesitamos mantener
# los divs de cierre correctos
# Buscar hacia atrás desde end_idx para encontrar los cierres de div

# En realidad, reemplacemos toda la sección del archive_loop
archive_start = html.find('class="et_pb_module et_pb_de_mach_archive_loop et_pb_de_mach_archive_loop_0_tb_body')
if archive_start == -1:
    print("ERROR: No se encontró el archive loop")
    exit(1)

# Retroceder al inicio del div
archive_div_start = html.rfind("<div ", 0, archive_start)
section_start = archive_div_start

# El final es justo antes de et_pb_row_2_tb_body, incluyendo los
# divs de cierre del archive loop
section_end = end_idx

# Extraer la sección original para referencia
original_section = html[section_start:section_end]

# Reemplazar con marcador simple
replacement = '''<div class="et_pb_module et_pb_de_mach_archive_loop et_pb_de_mach_archive_loop_0_tb_body content_visibility_hover de_loop_product-default grid-layout-grid clearfix main-loop loadmore-align- main-archive-loop">
$CGM_PRODUCTOS$
				</div>
				</div>




				</div>'''

html = html[:section_start] + replacement + html[section_end:]

# ── 7. Limpiar referencias a admin-ajax.php (ya no necesarias) ──
# Reemplazar la URL de AJAX con una vacía para que no falle
html = html.replace(
    '"ajax_url":"https://cgmrental.com/wp-admin/admin-ajax.php"',
    '"ajax_url":""'
)

# ── 8. Agregar referencia a cotizador.js si no existe ──
if '/cotizador.js' not in html:
    html = html.replace('</body>', '<script src="/cotizador.js"></script>\n</body>')

# ── 9. Guardar template ──
os.makedirs(os.path.dirname(DST), exist_ok=True)
with open(DST, "w", encoding="utf-8") as f:
    f.write(html)

print(f"Template guardado en: {DST}")
print(f"Tamaño: {len(html):,} bytes")

# ── 10. Extraer datos de productos del HTML original ──
print("\n=== Extrayendo datos de productos ===")

with open(SRC, "r", encoding="utf-8") as f:
    src_html = f.read()

products = []

# Patrón para cada producto <li> con sus datos
product_pattern = re.compile(
    r'<li class="daf-template-loop[^"]*product_cat-([^\s"]*)[^"]*product_tag-([^\s"]*)[^"]*"'
    r'\s+data-cgm-tags="([^"]*)"'
    r'\s+data-cgm-tipo="([^"]*)">'
    r'.*?<a href="(/producto/[^"]*)"[^>]*>'
    r'.*?<img[^>]*(?:data-src|src)="([^"]*)"[^>]*>'
    r'.*?<h2 class="woocommerce-loop-product__title">([^<]*)</h2>'
    r'.*?<div class="product-category">([^<]*)</div>',
    re.DOTALL
)

for m in product_pattern.finditer(src_html):
    cats = m.group(1)
    tag_class = m.group(2)
    tags = m.group(3)
    tipo = m.group(4)
    url = m.group(5)
    img = m.group(6)
    nombre = m.group(7)
    marca = m.group(8)

    # Extraer slug del producto de la URL
    slug = url.strip("/").split("/")[-1] if "/index.html" not in url else url.strip("/").split("/")[-2]
    if url.endswith("/index.html"):
        slug = url.replace("/index.html", "").strip("/").split("/")[-1]

    products.append({
        "slug": slug,
        "nombre": nombre,
        "marca": marca,
        "tags": tags,
        "tipo": tipo,
        "url": url,
        "imagen": img,
        "categorias_css": cats
    })

print(f"Productos extraídos del HTML: {len(products)}")
for p in products:
    print(f"  - {p['nombre']} ({p['tags']}, {p['tipo']})")

# Guardar los productos extraídos
with open(PRODUCTS_JSON, "w", encoding="utf-8") as f:
    json.dump(products, f, ensure_ascii=False, indent=2)

print(f"\nProductos guardados en: {PRODUCTS_JSON}")
