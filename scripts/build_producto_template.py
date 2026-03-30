#!/usr/bin/env python3
"""
Construir templates/producto.html a partir del HTML original de producto.
Reemplaza el contenido específico del producto con marcadores $CGM_*.
"""
import re
import os

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(SCRIPTS_DIR)
SRC = os.path.join(SCRIPTS_DIR, "source_producto.html")
DST = os.path.join(BASE, "templates", "producto.html")

with open(SRC, "r", encoding="utf-8") as f:
    html = f.read()

print(f"Source: {len(html):,} chars")

# ── 1. Reemplazar <title> ──
html = re.sub(
    r"<title>[^<]*</title>",
    "<title>$CGM_NOMBRE$ - CGM RENTAL</title>",
    html,
    count=1
)

# ── 2. Reemplazar og:title ──
html = re.sub(
    r'<meta property="og:title" content="[^"]*">',
    '<meta property="og:title" content="$CGM_NOMBRE$ - CGM RENTAL">',
    html,
    count=1
)

# ── 3. Encontrar las 3 secciones del body template ──
# section_0_tb_body: título + meta/tags
# section_1_tb_body: galería + specs + descripción + botones
# section_2_tb_body: productos relacionados
# Luego viene el footer (section_0_tb_footer)

s0_match = html.find('et_pb_section_0_tb_body')
s0_div = html.rfind('<div ', 0, s0_match)

footer_match = html.find('et_pb_section_0_tb_footer')
footer_div = html.rfind('<div ', 0, footer_match)

if s0_div < 0 or footer_div < 0:
    print("ERROR: No se encontraron las secciones del producto")
    exit(1)

print(f"Product content zone: {s0_div} to {footer_div} ({footer_div - s0_div:,} chars)")

# ── 4. Reemplazar toda la zona del producto con un marcador ──
product_replacement = """<div class="et_pb_section et_pb_section_0_tb_body et_section_regular" >
$CGM_PRODUCTO$
</div>
"""

html = html[:s0_div] + product_replacement + html[footer_div:]

# ── 5. Limpiar admin-ajax.php ──
html = html.replace(
    '"ajax_url":"https://cgmrental.com/wp-admin/admin-ajax.php"',
    '"ajax_url":""'
)

# ── 6. Agregar cotizador.js si no existe ──
if '/cotizador.js' not in html:
    html = html.replace('</body>', '<script src="/cotizador.js"></script>\n</body>')

# ── 7. Guardar template ──
os.makedirs(os.path.dirname(DST), exist_ok=True)
with open(DST, "w", encoding="utf-8") as f:
    f.write(html)

print(f"Template guardado: {DST}")
print(f"Tamaño: {len(html):,} chars")
print("[OK] templates/producto.html creado")
