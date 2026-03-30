#!/usr/bin/env python3
"""
CGM Rental - Servidor Flask
Sirve el sitio cgmrental.com con filtrado dinámico de productos por categoría.
"""
import os
import json
import re
from flask import Flask, abort, request, send_from_directory, make_response
from flask_compress import Compress

# ── Configuración ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

app = Flask(__name__, static_folder=None)

# ── Compresión Gzip/Brotli automática ──
app.config["COMPRESS_REGISTER"] = True
app.config["COMPRESS_LEVEL"] = 6          # balance velocidad/compresión
app.config["COMPRESS_MIN_SIZE"] = 1000    # comprimir respuestas > 1 KB
Compress(app)

# ── Cargar datos ──
def _cargar_productos():
    path = os.path.join(BASE_DIR, "products.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

PRODUCTOS = _cargar_productos()

# CSS fix: Divi JS no corre bien en local, el header queda con gap.
# Usamos sticky en vez de fixed para evitar problemas de ancho.
_HEADER_FIX = """<style>
/* Fix: header fixed en todo el ancho - inmune a overflow:hidden/scroll de ancestros
   (position:sticky falla cuando Divi animation JS pone overflow-y:hidden en
   #page-container y overflow-x:hidden en body, como ocurre en la pagina nosotros) */
.et-l.et-l--header {
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    right: 0 !important;
    width: 100% !important;
    z-index: 99999 !important;
}
#page-container {
    padding-top: 0 !important;
}
/* Fix: desactivar el position:fixed que Divi JS pone en section_1 (barra blanca)
   de forma independiente; el header completo ya es fixed, no necesitamos que
   una seccion interna tambien lo sea (causaria doble fixed y romperia el layout). */
.et_pb_section_1_tb_header.et_pb_sticky {
    position: static !important;
    top: auto !important;
}
.et_pb_section_1_tb_header.et_pb_sticky_placeholder {
    display: none !important;
}

/* ── Filtros: toggle en pantallas < 981px ── */
@media (max-width: 980px) {
    /* Columna de filtros: colapsada por defecto, ocupa ancho completo */
    .et_pb_column_1_tb_body {
        width: 100% !important;
        max-height: 0;
        overflow: hidden;
        transition: max-height 0.35s ease;
        padding: 0 !important;
        margin: 0 !important;
    }
    /* Cuando está abierto */
    .et_pb_column_1_tb_body.cgm-filtros-visible {
        max-height: 1200px;
        padding: 16px 0 !important;
    }
    /* Columna de productos ocupa el 100% siempre */
    .et_pb_column_2_tb_body {
        width: 100% !important;
    }
    /* Botón toggle */
    #cgm-toggle-filtros {
        display: flex !important;
        align-items: center;
        gap: 8px;
        background: #02534c;
        color: #fff;
        border: none;
        border-radius: 6px;
        padding: 10px 20px;
        font-family: 'CGM BOLD', sans-serif;
        font-size: 15px;
        cursor: pointer;
        margin-bottom: 12px;
        width: fit-content;
    }
    #cgm-toggle-filtros .cgm-arrow {
        font-size: 11px;
        display: inline-block;
        transition: transform 0.25s;
    }
    #cgm-toggle-filtros.abierto .cgm-arrow {
        transform: rotate(-180deg);
    }
}
@media (min-width: 981px) {
    #cgm-toggle-filtros { display: none !important; }
    .et_pb_column_1_tb_body { max-height: none !important; overflow: visible !important; }
}
</style>
<script>
(function(){
    document.addEventListener('DOMContentLoaded', function(){
        /* ── Filtros toggle ── */
        var col = document.querySelector('.et_pb_column_1_tb_body');
        if (col) {
            var btn = document.createElement('button');
            btn.id = 'cgm-toggle-filtros';
            btn.innerHTML = '<span class="cgm-arrow">&#9660;</span> Filtrar';
            btn.addEventListener('click', function(){
                col.classList.toggle('cgm-filtros-visible');
                btn.classList.toggle('abierto');
            });
            col.parentNode.insertBefore(btn, col);
        }

        /* ── Fix: forzar position:fixed en el header usando inline !important
              (maxima prioridad CSS - supera CUALQUIER regla de hoja de estilos,
              incluido el ".et-l--header{position:relative}" de BerocketCommerce
              que esta en el <head> de nosotros.html y otras paginas).
              Un MutationObserver lo re-aplica si algun JS lo elimina. ── */
        var header = document.querySelector('.et-l.et-l--header');
        if (header) {
            var forceHeaderFixed = function() {
                header.style.setProperty('position', 'fixed', 'important');
                header.style.setProperty('top',      '0',     'important');
                header.style.setProperty('left',     '0',     'important');
                header.style.setProperty('right',    '0',     'important');
                header.style.setProperty('width',    '100%',  'important');
                header.style.setProperty('z-index',  '99999', 'important');
            };
            forceHeaderFixed();
            new MutationObserver(forceHeaderFixed).observe(header, {
                attributes: true, attributeFilter: ['style']
            });
        }

        /* ── Fix: compensar el espacio que ocupa el header fixed.
              Medimos la altura real del header y se la damos como padding-top
              a #et-main-area para que el contenido no quede tapado.
              Tambien lo re-calculamos al cargar imagenes (window.load) y al
              cambiar el tamaño de ventana (responsive / rotacion). ── */
        var mainArea = document.getElementById('et-main-area');
        if (header && mainArea) {
            var applyHeaderPadding = function() {
                mainArea.style.paddingTop = header.offsetHeight + 'px';
            };
            applyHeaderPadding();
            window.addEventListener('load',   applyHeaderPadding);
            window.addEventListener('resize', applyHeaderPadding);
        }

        /* ── Fix: Divi JS pone position:fixed !important inline en la barra blanca
              (section_1). Como el header completo ya es fixed, si section_1 tambien
              es fixed queda fuera del header y tapa la barra verde. Lo quitamos. ── */
        var sec1 = document.querySelector('.et_pb_section_1_tb_header');
        if (sec1) {
            var fixStickyInline = function() {
                if (sec1.style.getPropertyValue('position') === 'fixed') {
                    sec1.style.removeProperty('position');
                    sec1.style.removeProperty('top');
                    sec1.style.removeProperty('left');
                    sec1.style.removeProperty('width');
                    sec1.style.removeProperty('z-index');
                }
            };
            fixStickyInline();
            new MutationObserver(fixStickyInline).observe(sec1, {attributes:true, attributeFilter:['style']});
        }

        /* ── Fix: icono hamburguesa invertido. DIPI chequea el estado DESPUES
              de que Divi ya lo cambio, asi que is-active queda al reves.
              Observamos .mobile_nav y sincronizamos el icono. ── */
        var mobileNav = document.querySelector('.mobile_nav');
        var hamburger = document.querySelector('.dipi_hamburger');
        if (mobileNav && hamburger) {
            new MutationObserver(function() {
                var isOpen = mobileNav.classList.contains('opened');
                hamburger.classList.toggle('is-active', isOpen);
            }).observe(mobileNav, {attributes:true, attributeFilter:['class']});
        }
    });
})();
</script>
</head>"""

def _fix_nav_links(html):
    """Corrige los hrefs relativos del menú de navegación a rutas absolutas."""
    NAV_FIXES = [
        # Alquiler - sub-sub-categorías (más específicos primero)
        ('href="construccion-alquiler/excavadora/index.html"',
         'href="/categoria-producto/alquiler/construccion-alquiler/excavadora/"'),
        ('href="construccion-alquiler/cargador-frontal/index.html"',
         'href="/categoria-producto/alquiler/construccion-alquiler/cargador-frontal/"'),
        ('href="construccion-alquiler/tractor-de-orugas/index.html"',
         'href="/categoria-producto/alquiler/construccion-alquiler/tractor-de-orugas/"'),
        ('href="construccion-alquiler/rodillo-compactador/index.html"',
         'href="/categoria-producto/alquiler/construccion-alquiler/rodillo-compactador/"'),
        ('href="construccion-alquiler/motoniveladora/index.html"',
         'href="/categoria-producto/alquiler/construccion-alquiler/motoniveladora/"'),
        ('href="construccion-alquiler/retroexcavadora/index.html"',
         'href="/categoria-producto/alquiler/construccion-alquiler/retroexcavadora/"'),
        ('href="construccion-alquiler/minicargador/index.html"',
         'href="/categoria-producto/alquiler/construccion-alquiler/minicargador/"'),
        ('href="construccion-alquiler/camion-cisterna/index.html"',
         'href="/categoria-producto/alquiler/construccion-alquiler/camion-cisterna/"'),
        ('href="construccion-alquiler/compresora/index.html"',
         'href="/categoria-producto/alquiler/construccion-alquiler/compresora/"'),
        ('href="construccion-alquiler/torre-de-iluminacion-construccion-alquiler/index.html"',
         'href="/categoria-producto/alquiler/construccion-alquiler/torre-de-iluminacion-construccion-alquiler/"'),
        ('href="construccion-alquiler/aditamentos/index.html"',
         'href="/categoria-producto/alquiler/construccion-alquiler/aditamentos/"'),
        # Alquiler - sub-categorías
        ('href="construccion/index.html"',
         'href="/categoria-producto/alquiler/construccion/"'),
        ('href="mediana-mineria/index.html"',
         'href="/categoria-producto/alquiler/mediana-mineria/"'),
        ('href="energia/index.html"',
         'href="/categoria-producto/alquiler/energia/"'),
        # Energía > Aditamentos (ruta incorrecta)
        ('href="/energia/construccion-alquiler/aditamentos/index.html"',
         'href="/categoria-producto/alquiler/construccion-alquiler/aditamentos/"'),
    ]
    for old, new in NAV_FIXES:
        html = html.replace(old, new)

    # Fix sub-sub-categorías agrícolas (todas usan agricola/index.html)
    # Reemplazar por contexto de texto del link
    AGRICOLA_SUBS = [
        ("Tractores especializados", "Tractor Especializados"),
        ("Tractores Utilitarios", "Tractor Utilitarios"),
        ("Tractores grandes", "Tractor Grande"),
        ("Tractores medianos", "Tractor Mediano"),
    ]
    for text_match, maquinaria in AGRICOLA_SUBS:
        html = re.sub(
            rf'(<a\s+href=")agricola/index\.html("[^>]*>(?:<span>)?\s*{text_match})',
            rf'\g<1>/categoria-producto/alquiler/agricola/?maquinaria_={maquinaria}\g<2>',
            html
        )
    # Agrícola > Aditamentos (= Pulverizadora)
    html = re.sub(
        r'(<a\s+href=")agricola/index\.html("[^>]*>(?:<span>)?\s*Aditamentos)',
        r'\g<1>/categoria-producto/alquiler/agricola/?maquinaria_=Pulverizadora\g<2>',
        html
    )
    # Agrícola genérico (el que quede)
    html = html.replace('href="agricola/index.html"',
                         'href="/categoria-producto/alquiler/agricola/"')

    # Fix sub-sub-categorías de minería
    html = re.sub(
        r'(<a\s+href=")mediana-mineria/index\.html("[^>]*>(?:<span>)?\s*Excavadoras)',
        r'\g<1>/categoria-producto/alquiler/mediana-mineria/?maquinaria_=Excavadora\g<2>',
        html
    )

    # Fix "Alquiler" y "Camiones grúa" que usan href="index.html" genérico
    html = re.sub(
        r'(<a\s+href=")index\.html("[^>]*>(?:<span>)?\s*Alquiler)',
        r'\g<1>/categoria-producto/alquiler/\g<2>',
        html
    )
    html = re.sub(
        r'(<a\s+href=")index\.html("[^>]*>(?:<span>)?\s*Camiones)',
        r'\g<1>/categoria-producto/alquiler/construccion-alquiler/camion-grua/\g<2>',
        html
    )
    html = re.sub(
        r'(<a\s+href=")index\.html("[^>]*>(?:<span>)?\s*Aditamentos)',
        r'\g<1>/categoria-producto/alquiler/construccion-alquiler/aditamentos/\g<2>',
        html
    )
    # Fix hrefs="#" para Camiones grúa y Aditamentos
    html = re.sub(
        r'(<a\s+href=")#("[^>]*>(?:<span>)?\s*Camiones)',
        r'\g<1>/categoria-producto/alquiler/construccion-alquiler/camion-grua/\g<2>',
        html
    )
    html = re.sub(
        r'(<a\s+href=")#("[^>]*>(?:<span>)?\s*Aditamentos)',
        r'\g<1>/categoria-producto/alquiler/construccion-alquiler/aditamentos/\g<2>',
        html
    )
    # Limpiar query params de WooCommerce de links de categoría
    # Para links que tienen ruta propia en RUTAS, eliminar query params
    # Para links con ?maquinaria_=, convertir a ruta limpia + ?maquinaria_=
    def _clean_cat_link(m):
        base = m.group(1)  # ej: /categoria-producto/alquiler/agricola/
        params = m.group(2)  # ej: filter=true&maquinaria_=Tractor%20Grande&...
        # Extraer maquinaria_ si existe
        maq = re.search(r'maquinaria_=([^&"]*)', params)
        if maq:
            return f'{base}?maquinaria_={maq.group(1)}"'
        return f'{base}"'
    html = re.sub(
        r'(href="/categoria-producto/[^"?]*)\?([^"]*)"',
        _clean_cat_link,
        html
    )
    # Fix links externos a cgmrental.com → rutas locales
    html = html.replace('href="https://cgmrental.com/nosotros/"', 'href="/nosotros/index.html"')
    html = html.replace('href="https://cgmrental.com/novedades/"', 'href="/novedades/index.html"')
    html = html.replace('href="https://cgmrental.com/contacto/"', 'href="/contacto/index.html"')
    html = html.replace('href="https://cgmrental.com/leasing-operativo/"', 'href="/leasing-operativo/index.html"')
    # Fix Energía > Aditamentos ruta incorrecta
    html = html.replace(
        '/categoria-producto/energia/construccion-alquiler/aditamentos/',
        '/categoria-producto/alquiler/construccion-alquiler/aditamentos/'
    )
    # Fix: header fixed de Divi - el JS que agrega padding-top no corre
    html = html.replace("</head>", _HEADER_FIX, 1)
    return html

def _cargar_template(nombre="categoria.html"):
    path = os.path.join(TEMPLATES_DIR, nombre)
    with open(path, "r", encoding="utf-8") as f:
        return _fix_nav_links(f.read())

_CATEGORIA_TEMPLATE = _cargar_template("categoria.html")
_PRODUCTO_TEMPLATE = _cargar_template("producto.html")

# ── Caché en RAM para páginas estáticas ──
# Las páginas se leen del disco + _fix_nav_links() UNA sola vez y se guardan en RAM.
# En modo debug se desactiva para poder editar en vivo.
_PAGINAS_CACHE: dict[str, str] = {}

def _servir_pagina_cached(filename):
    if filename not in _PAGINAS_CACHE:
        filepath = os.path.join(STATIC_DIR, "pages", filename)
        if not os.path.exists(filepath):
            return abort(404)
        with open(filepath, "r", encoding="utf-8") as f:
            html = f.read()
        _PAGINAS_CACHE[filename] = _fix_nav_links(html)
    return _PAGINAS_CACHE[filename]

# ── Caché en RAM para las 21 páginas de categoría ──
# Se pre-generan al inicio. Son páginas estáticas (el catálogo no cambia en caliente).
_CATEGORIA_CACHE: dict[str, str] = {}

def _precalentar_categorias():
    """Pre-genera todas las páginas de categoría al arrancar el servidor."""
    for path, (tags, unidad, tipo, titulo, taxterm) in RUTAS.items():
        productos = _filtrar_productos(tags, unidad, tipo)
        html = _CATEGORIA_TEMPLATE
        html = html.replace("$CGM_TITULO$", titulo)
        html = html.replace("$CGM_TAXTERM$", taxterm if taxterm else path.split("/")[-1])
        html = html.replace("$CGM_TERM$", taxterm if taxterm else path.split("/")[-1])
        html = html.replace("$CGM_PRODUCTOS$", _generar_grilla(productos))
        html = html.replace("$CGM_BANNER$", _get_banner(path))
        _CATEGORIA_CACHE[path] = html
    print(f"Categorias precalentadas: {len(_CATEGORIA_CACHE)}")

# ── Caché en RAM para páginas de producto individual ──
_PRODUCTO_CACHE: dict[str, str] = {}

# Recargar datos en cada request en modo debug
@app.before_request
def _reload_data():
    global PRODUCTOS, _CATEGORIA_TEMPLATE, _PRODUCTO_TEMPLATE
    if app.debug:
        PRODUCTOS = _cargar_productos()
        _CATEGORIA_TEMPLATE = _cargar_template("categoria.html")
        _PRODUCTO_TEMPLATE = _cargar_template("producto.html")
        _PAGINAS_CACHE.clear()
        _CATEGORIA_CACHE.clear()
        _PRODUCTO_CACHE.clear()


# ══════════════════════════════════════════════════════════════════
# TABLA DE RUTAS - Reemplaza todo el parseo complejo
# Formato: path → (tags, unidad, tipo, titulo, taxterm)
# ══════════════════════════════════════════════════════════════════
RUTAS = {
    # ── Alquiler ──
    "alquiler":
        ("alquiler", None, None, "Alquiler", "alquiler"),
    "alquiler/construccion":
        ("alquiler", "Construcción", None, "Construcción", "construccion"),
    "alquiler/construccion-alquiler/excavadora":
        ("alquiler", "Construcción", "Excavadora", "Excavadoras", "excavadora"),
    "alquiler/construccion-alquiler/cargador-frontal":
        ("alquiler", "Construcción", "Cargador Frontal", "Cargadores Frontales", "cargador-frontal"),
    "alquiler/construccion-alquiler/tractor-de-orugas":
        ("alquiler", "Construcción", "Tractor de Orugas", "Tractores de Orugas", "tractor-de-orugas"),
    "alquiler/construccion-alquiler/rodillo-compactador":
        ("alquiler", "Construcción", "Rodillo Compactador", "Rodillos Compactador", "rodillo-compactador"),
    "alquiler/construccion-alquiler/motoniveladora":
        ("alquiler", "Construcción", "Motoniveladora", "Motoniveladoras", "motoniveladora"),
    "alquiler/construccion-alquiler/retroexcavadora":
        ("alquiler", "Construcción", "Retroexcavadora", "Retroexcavadoras", "retroexcavadora"),
    "alquiler/construccion-alquiler/minicargador":
        ("alquiler", "Construcción", "Minicargador", "Minicargadores", "minicargador"),
    "alquiler/construccion-alquiler/camion-cisterna":
        ("alquiler", "Construcción", "Camion Cisterna", "Camiones Cisternas", "camion-cisterna"),
    "alquiler/construccion-alquiler/camion-grua":
        ("alquiler", "Construcción", "Camion Grua", "Camiones Grúa", "camion-grua"),
    "alquiler/construccion-alquiler/compresora":
        ("alquiler", "Construcción", "Compresora", "Compresoras", "compresora"),
    "alquiler/construccion-alquiler/torre-de-iluminacion-construccion-alquiler":
        ("alquiler", "Construcción", "Torre de Iluminacion", "Torres de Iluminación", "torre-de-iluminacion"),
    "alquiler/construccion-alquiler/aditamentos":
        ("alquiler", "Construcción", "Aditamento", "Aditamentos", "aditamentos"),
    "alquiler/mediana-mineria":
        ("alquiler", "Mediana Minería", None, "Mediana Minería", "mediana-mineria"),
    "alquiler/agricola":
        ("alquiler", "Agrícola", None, "Agrícola", "agricola"),
    "alquiler/energia":
        ("alquiler", "Energía", None, "Energía", "energia"),
    # ── Usados ──
    "usados":
        ("usados", None, None, "Usados", "usados"),
    "usados/agricola-usados":
        ("usados", "Agrícola", None, "Agrícola - Usados", "agricola-usados"),
    "usados/construccion-usados":
        ("usados", "Construcción", None, "Construcción Usados", "construccion-usados"),
    "usados/energia-usados":
        ("usados", "Energía", None, "Energía Usados", "energia-usados"),
}


# ══════════════════════════════════════════════════════════════════
# FILTRADO DE PRODUCTOS
# ══════════════════════════════════════════════════════════════════
def _filtrar_productos(tags=None, unidad=None, tipo=None):
    """Filtra productos por tags, unidad de negocio y tipo de maquinaria."""
    resultado = PRODUCTOS
    if tags:
        resultado = [p for p in resultado if p.get("tags") == tags]
    if unidad:
        resultado = [p for p in resultado
                     if unidad in [u.strip() for u in p.get("unidad", "").split(",")]]
    if tipo:
        resultado = [p for p in resultado if p.get("tipo") == tipo]
    return resultado


# ══════════════════════════════════════════════════════════════════
# GENERACIÓN DE GRILLA HTML
# ══════════════════════════════════════════════════════════════════
def _generar_producto_html(p, idx, total):
    """Genera el HTML de un producto individual en la grilla."""
    pos_classes = []
    if idx == 0:
        pos_classes.append("first")
    elif (idx + 1) % 3 == 0:
        pos_classes.append("last")
    if idx == total - 1:
        pos_classes.append("last")

    pos_str = " ".join(pos_classes)

    slug = p["slug"]
    nombre = p["nombre"]
    marca = p["marca"]
    tags = p["tags"]
    tipo = p["tipo"]
    imagen = p["imagen"]

    desc_html = ""
    if p.get("descripcion"):
        items = "".join(f"<li>{item}</li>" for item in p["descripcion"])
        desc_html = f'<div class="card-text"><ul>{items}</ul></div>'

    return f'''<div class="grid-col dmach-grid-item product_type-simple product_tag-{tags} post_id_{idx}" data-id="{idx}" data-posttype="product">
    <div class="grid-item-cont">
    <li class="daf-template-loop daf-product-template daf-product-template-default grid-item product type-product status-publish {pos_str} instock product_tag-{tags} has-post-thumbnail shipping-taxable purchasable product-type-simple" data-cgm-tags="{tags}" data-cgm-tipo="{tipo}">
      <div class="grid-item-cont">
      <a href="/producto/{slug}/index.html" class="woocommerce-LoopProduct-link woocommerce-loop-product__link"><span class="et_shop_image"><img width="300" height="300" src="{imagen}" alt="{nombre}" decoding="async" loading="lazy" class="attachment-woocommerce_thumbnail size-woocommerce_thumbnail">
<span class="et_overlay"></span></span><h2 class="woocommerce-loop-product__title">{nombre}</h2><div class="product-category">{marca}</div><div class="woocommerce-product-details__short-description">{desc_html}</div></a><a href="/producto/{slug}/index.html" class="button view-product-button">COTIZAR</a>
        </div>
    </li>
    </div>
</div>'''


def _generar_grilla(productos):
    """Genera el HTML completo de la grilla de productos."""
    if not productos:
        return '<div class="filtered-posts-cont"><p class="no-results">No se encontraron productos.</p></div>'

    items_html = "\n".join(
        _generar_producto_html(p, i, len(productos))
        for i, p in enumerate(productos)
    )

    total = len(productos)
    result_text = (
        "Showing the single result" if total == 1
        else f"Showing all {total} results"
    )

    return f'''<div class="filtered-posts-cont">
    <div class="dmach-grid-sizes divi-filter-archive-loop main-loop grid"
         data-gridstyle="grid" data-columnscount="3" data-postnumber="{total}"
         data-current-page="1" data-max-page="1"
         style="grid-auto-rows: 1px;">
        <div class="divi-filter-loop-container default-layout col-desk-3 col-tab-2 col-mob-1">
        <div class="grid-posts loop-grid">
{items_html}
        </div>
        </div>
    </div>
</div>
<div class="dmach-after-posts"></div>
<p class="divi-filter-result-count result_count_right">{result_text}</p>'''


# ══════════════════════════════════════════════════════════════════
# UTILIDAD PARA SERVIR HTML ESTÁTICO
# ══════════════════════════════════════════════════════════════════

def _servir_pagina(filename):
    """Lee y devuelve un archivo HTML desde static/pages/ (con caché en RAM)."""
    return _servir_pagina_cached(filename)


# ══════════════════════════════════════════════════════════════════
# RUTAS DE FLASK
# ══════════════════════════════════════════════════════════════════

# ── Homepage ──
@app.route("/")
@app.route("/index.html")
def home():
    return _servir_pagina("index.html")


# ── Banners por categoría ──
BANNERS = {
    # Alquiler
    "alquiler":         "/images/banners/construccion.webp",
    "construccion":     "/images/banners/construccion.webp",
    "agricola":         "/images/banners/agricola.webp",
    "energia":          "/images/banners/energia.webp",
    "mediana-mineria":  "/images/banners/mediana-mineria.webp",
    # Usados
    "usados":              "/images/banners/usados.webp",
    "construccion-usados": "/images/banners/usados.webp",
    "agricola-usados":     "/images/banners/agricola-usados.webp",
    "energia-usados":      "/images/banners/energia-usados.webp",
}

def _get_banner(path):
    """Determina el banner correcto según la ruta de categoría."""
    parts = path.split("/")
    # usados con subcategorías
    if parts[0] == "usados":
        if len(parts) >= 2 and parts[1] in BANNERS:
            return BANNERS[parts[1]]
        return BANNERS["usados"]
    # alquiler con subcategorías
    if len(parts) >= 2:
        sub = parts[1].replace("-alquiler", "").replace("-usados", "")
        if sub in BANNERS:
            return BANNERS[sub]
    # alquiler raíz
    if parts[0] == "alquiler":
        return BANNERS["alquiler"]
    return BANNERS["alquiler"]


# ── Categorías de productos ──
@app.route("/categoria-producto/<path:cat_path>")
@app.route("/categoria-producto/<path:cat_path>/")
@app.route("/categoria-producto/<path:cat_path>/index.html")
def categoria_producto(cat_path):
    """Handler unificado para todas las categorías de productos."""
    path = cat_path.strip("/")
    path = re.sub(r'/page/\d+/?$', '', path)

    tipo_param = request.args.get("maquinaria_")

    # Usar caché si no hay filtro extra por query param
    if not tipo_param and path in _CATEGORIA_CACHE:
        return _CATEGORIA_CACHE[path]

    if path in RUTAS:
        tags, unidad, tipo, titulo, taxterm = RUTAS[path]
    else:
        base_path = "/".join(path.split("/")[:2]) if "/" in path else path
        if base_path in RUTAS:
            tags, unidad, _, titulo, taxterm = RUTAS[base_path]
            tipo = None
        else:
            return abort(404)

    if tipo_param:
        tipo = tipo_param
        titulo = tipo_param

    productos = _filtrar_productos(tags, unidad, tipo)

    html = _CATEGORIA_TEMPLATE
    html = html.replace("$CGM_TITULO$", titulo)
    html = html.replace("$CGM_TAXTERM$", taxterm if taxterm else path.split("/")[-1])
    html = html.replace("$CGM_TERM$", taxterm if taxterm else path.split("/")[-1])
    html = html.replace("$CGM_PRODUCTOS$", _generar_grilla(productos))
    html = html.replace("$CGM_BANNER$", _get_banner(path))

    return html


# ── Páginas de producto individual ──
@app.route("/producto/<slug>/")
@app.route("/producto/<slug>/index.html")
def producto(slug):
    """Página individual de producto - reutiliza el template de categoría."""
    if slug in _PRODUCTO_CACHE:
        return _PRODUCTO_CACHE[slug]

    prod = None
    for p in PRODUCTOS:
        if p["slug"] == slug:
            prod = p
            break

    if not prod:
        return abort(404)

    producto_html = _generar_detalle_producto(prod)

    html = _PRODUCTO_TEMPLATE
    html = html.replace("$CGM_NOMBRE$", prod["nombre"])
    html = html.replace("$CGM_PRODUCTO$", producto_html)

    _PRODUCTO_CACHE[slug] = html
    return html


def _generar_detalle_producto(prod):
    """Genera el HTML del detalle de producto usando las clases CSS del template original."""
    img_dir = os.path.join(STATIC_DIR, "images", prod["slug"])
    imagenes = []
    if os.path.isdir(img_dir):
        imagenes = sorted([
            f"/imagenes/{prod['slug']}/{f}"
            for f in os.listdir(img_dir)
            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))
        ])

    if not imagenes and prod.get("imagen"):
        imagenes = [prod["imagen"]]

    # ── Galería con Splide slider (igual al original) ──
    slides_primary = ""
    slides_thumb = ""
    for img in imagenes:
        slides_primary += (f'<li class="splide__slide">'
                          f'<img decoding="async" src="{img}" alt=""/>'
                          f'</li>')
        slides_thumb += (f'<li class="splide__slide">'
                        f'<img decoding="async" src="{img}" alt=""/>'
                        f'</li>')

    gallery_html = f'''<div class="thumbnail_slider">
<div id="primary_slider" class="splide"><div class="splide__track"><ul class="splide__list">
{slides_primary}
</ul></div></div>
<div id="thumbnail_slider" class="splide"><div class="splide__track"><ul class="splide__list">
{slides_thumb}
</ul></div></div>
</div>'''

    # ── Características (specs) ──
    specs_html = ""
    specs = prod.get("descripcion", [])
    if specs:
        items = "".join(f'<li class="punto-item">{s}</li>' for s in specs)
        specs_html = f'''<div class="description-box"><h2>Características</h2>
<div class="woocommerce-product-details__short-description">
<div class="card-text"><ul>{items}</ul></div></div></div>'''

    # ── Descripción + Ficha Técnica ──
    desc_html = ""
    desc_texto = prod.get("descripcion_texto", "")
    ficha_url = prod.get("ficha_tecnica", "")
    if desc_texto or ficha_url:
        ficha_btn = ""
        if ficha_url:
            ficha_btn = (f'<a href="{ficha_url}" target="_blank" rel="noopener">'
                        f'<button class="ver-ficha-tecnica">Ver Ficha Técnica</button></a>')
        desc_html = f'''<div class="description-box"><h2>Descripción</h2>
<div class="woocommerce-product-details__description">
<div class="descripcion-larga">
<p class="descripcion-larga-p">{desc_texto}</p>
{ficha_btn}
</div></div></div>'''

    # ── Tag/Marca meta ──
    tag_label = prod["tags"].capitalize()
    marca = prod.get("marca", "")

    # ── Botones (estructura original) ──
    botones_html = f'''<div class="button-container" style="display: flex; gap: 20px; margin-top: 20px;">
<div>
    <button type="button" class="cgm-add-to-cart button alt"
        data-slug="{prod['slug']}"
        data-nombre="{prod['nombre']}"
        data-imagen="{prod.get('imagen','')}"
        style="border-radius: 0px;background-color: #C5E86C; color: #004c3f;
        font-weight: bold; padding: 10px 50px; cursor:pointer; border:none;
        background: linear-gradient(58deg, transparent 4%, #C5E86C 0%, #C5E86C 96%, transparent 10%);
        font-family: 'CGM BOLD'">AÑADIR AL CARRITO</button>
</div>
<div>
    <a href="https://wa.me/51943567445?text=Hola! Estoy interesado en {prod['nombre']}" target="_blank">
    <button class="button" style="background-color: #004c3f; color: #ffffff;
        font-weight: bold; padding: 11px 20px; cursor:pointer; border:none;
        background: linear-gradient(58deg, transparent 4%, #0C534C 0%, #0C534C 96%, transparent 10%);
        font-family: 'CGM BOLD';border-radius:0px">COTIZAR</button></a>
</div>
</div>'''

    # ── Productos relacionados (escalonado: tipo → unidad → tags) ──
    max_rel = 5
    ya_usados = {prod["slug"]}

    # 1) Mismo tipo (ej: otras Excavadoras)
    relacionados = [p for p in PRODUCTOS
                    if p["tipo"] == prod["tipo"] and p["slug"] not in ya_usados
                    and p.get("activo", True)]
    ya_usados.update(p["slug"] for p in relacionados)

    # 2) Si faltan, completar con misma unidad (ej: otros equipos de Construcción)
    if len(relacionados) < max_rel:
        misma_unidad = [p for p in PRODUCTOS
                        if p.get("unidad") == prod.get("unidad")
                        and p["slug"] not in ya_usados
                        and p.get("activo", True)]
        relacionados.extend(misma_unidad[:max_rel - len(relacionados)])
        ya_usados.update(p["slug"] for p in misma_unidad)

    # 3) Si aún faltan, completar con mismo tag (alquiler/usados)
    if len(relacionados) < max_rel:
        mismo_tag = [p for p in PRODUCTOS
                     if p.get("tags") == prod.get("tags")
                     and p["slug"] not in ya_usados
                     and p.get("activo", True)]
        relacionados.extend(mismo_tag[:max_rel - len(relacionados)])

    relacionados = relacionados[:max_rel]
    rel_html = ""
    if relacionados:
        rel_items = ""
        for rp in relacionados:
            rp_specs = ""
            if rp.get("descripcion"):
                rp_specs = " | ".join(rp["descripcion"][:2])
            rel_items += f'''<div class="item">
<a href="/producto/{rp['slug']}/">
<img width="300" height="300" src="{rp['imagen']}"
     class="attachment-medium size-medium wp-post-image" alt="" decoding="async"/>
<h5>{rp['nombre']}</h5>
</a>
<p>{rp_specs}</p>
<a href="/producto/{rp['slug']}/" class="cotizar-button">Cotizar</a>
</div>'''

        rel_html = f'''
<style>
#carousel {{position:relative;width:100%;margin:0 auto;overflow:hidden}}
.carousel-inner {{display:flex;transition:transform 0.6s ease;justify-content:center;gap:10px}}
.carousel-inner .item {{flex:0 1 23%;margin:0 10px;text-align:center;box-sizing:border-box}}
.carousel-inner .item img {{max-width:100%;height:auto;border-radius:8px}}
.carousel-inner .item h5 {{font-family:CGMBOLD,sans-serif;color:#005335;font-size:14px;margin:8px 0 4px}}
.carousel-inner .item p {{font-size:12px;color:#666;margin:0 0 8px}}
.carousel-inner .item .cotizar-button {{display:inline-block;background:#005335;color:#fff;padding:8px 20px;
    border-radius:4px;text-decoration:none;font-family:CGMBOLD,sans-serif;font-size:12px}}
@media (max-width:480px) {{.carousel-inner .item {{flex:0 0 50%}}}}
</style>
<div class="et_pb_section et_pb_section_2_tb_body et_pb_with_background et_section_regular">
<div class="et_pb_row et_pb_row_1_tb_body">
<div class="et_pb_column et_pb_column_4_4 et_pb_column_4_tb_body et_pb_css_mix_blend_mode_passthrough et-last-child">
<div class="et_pb_module et_pb_text et_pb_text_1_tb_body et_pb_text_align_left et_pb_bg_layout_light">
<div class="et_pb_text_inner"><h3 style="text-align: center;">Maquinarias relacionados</h3></div>
</div>
<div class="et_pb_module et_pb_code et_pb_code_4_tb_body">
<div class="et_pb_code_inner">
<div id="carousel">
<div class="carousel-inner">{rel_items}</div>
</div>
</div></div></div></div></div>'''

    # ── CSS para elementos del producto ──
    product_css = '''<style>
.punto-item {list-style-type:disc;margin-left:20px;color:#333}
.description-box {background:#f7f7f7;border-radius:10px;padding:20px 25px;margin-bottom:15px}
.description-box h2 {font-family:CGMBOLD,Helvetica,sans-serif;color:#005335;font-size:18px;margin:0 0 10px}
.descripcion-larga-p {font-size:13px;color:#333;line-height:1.6}
.ver-ficha-tecnica {background-color:#0C534C;padding:15px 30px;margin-top:15px;color:#fff;font-size:17px;
    font-family:'CGM BOLD',Helvetica,sans-serif;
    background:linear-gradient(58deg,transparent 4%,#0C534C 0%,#0C534C 96%,transparent 10%);
    border:0;border-radius:0;cursor:pointer}
.thumbnail_slider {margin-top:10px}
</style>'''

    # ── Ensamblar producto completo ──
    return f'''{product_css}
<!-- Section 0: Título + Meta + Galería + Specs -->
<div class="et_pb_section et_pb_section_0_tb_body et_pb_with_background et_section_specialty">
<div class="et_pb_row">
<div class="et_pb_column et_pb_column_2_3 et_pb_column_0_tb_body et_pb_specialty_column et_pb_css_mix_blend_mode_passthrough">

<!-- Título -->
<div class="et_pb_row_inner et_pb_row_inner_0_tb_body">
<div class="et_pb_column et_pb_column_1_3 et_pb_column_inner et_pb_column_inner_0_tb_body">
<div class="et_pb_module et_pb_db_product_title et_pb_db_product_title_0_tb_body clearfix et_pb_text_align_left">
<div class="et_pb_module_inner">
<h1 itemprop="name" class="entry-title de_title_module product_title">{prod['nombre']}</h1>
</div></div>
<div class="et_pb_module et_pb_divider et_pb_divider_0_tb_body et_pb_divider_position_ et_pb_space">
<div class="et_pb_divider_internal"></div></div>
</div>
<div class="et_pb_column et_pb_column_1_3 et_pb_column_inner et_pb_column_inner_1_tb_body et-last-child">
<div class="et_pb_module et_pb_wc_meta et_pb_wc_meta_0_tb_body et_pb_bg_layout_ et_pb_wc_no_sku et_pb_wc_no_categories et_pb_wc_meta_layout_inline">
<div class="et_pb_module_inner">
<div class="product_meta">
<span class="category_wrapper"><span class="metatitle">Marca:</span> <span class="categories">{marca}</span></span>
<span class="tag_wrapper"><span class="metatitle">Tag:</span> <span class="tags">{tag_label}</span></span>
</div></div></div>
</div></div>

<!-- Galería -->
<div class="et_pb_row_inner et_pb_row_inner_1_tb_body">
<div class="et_pb_column et_pb_column_4_4 et_pb_column_inner et_pb_column_inner_2_tb_body et-last-child">
<div class="et_pb_module et_pb_code et_pb_code_0_tb_body">
<div class="et_pb_code_inner">{gallery_html}</div>
</div></div></div>

</div>

<!-- Columna derecha: Specs + Desc -->
<div class="et_pb_column et_pb_column_1_3 et_pb_column_1_tb_body et_pb_css_mix_blend_mode_passthrough">
<div class="et_pb_module et_pb_code et_pb_code_1_tb_body">
<div class="et_pb_code_inner">{specs_html}</div>
</div>
<div class="et_pb_module et_pb_code et_pb_code_2_tb_body">
<div class="et_pb_code_inner">{desc_html}</div>
</div>
</div>

</div></div>

<!-- Section 1: Botones -->
<div class="et_pb_section et_pb_section_1_tb_body et_pb_with_background et_section_regular">
<div class="et_pb_row et_pb_row_0_tb_body">
<div class="et_pb_with_border et_pb_column_2_3 et_pb_column et_pb_column_2_tb_body et_pb_css_mix_blend_mode_passthrough">
<div class="et_pb_module et_pb_code et_pb_code_3_tb_body">
<div class="et_pb_code_inner">{botones_html}</div>
</div></div></div></div>

<!-- Section 2: Relacionados -->
{rel_html}'''


# ── Página de Carrito / Cotizador con Salesforce ──
@app.route("/carrito/")
@app.route("/carrito/index.html")
@app.route("/carrito-2/")
@app.route("/carrito-2/index.html")
def carrito():
    """Página del carrito con formulario Salesforce Web-to-Lead.
    Usa carrito2.html original como base para mantener el banner y pasos."""
    path = os.path.join(STATIC_DIR, "pages", "carrito2.html")
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()
    html = _fix_nav_links(html)
    # Reemplazar la sección vacía de WooCommerce con nuestra tabla + formulario
    # La sección original: hidethis div + empty section + "Volver al inicio" button
    old_content = '''<div class="hidethis" style="display:none !important;"> <div class="woocommerce-notices-wrapper"></div><div class="wc-empty-cart-message">\t\t\t<div class="cart-empty woocommerce-info">
\t\t\t\tYour cart is currently empty.\t\t\t</div>
\t\t</div> </div> <div class="et_pb_section et_pb_section_2 et_section_regular">
\t\t\t\t
\t\t\t\t
\t\t\t\t
\t\t\t\t
\t\t\t\t
\t\t\t\t
\t\t\t\t
\t\t\t\t
\t\t\t\t
\t\t\t</div>
\t\t\t\t</div>
\t\t\t</div><div class="et_pb_button_module_wrapper et_pb_button_0_wrapper  et_pb_module ">
\t\t\t\t<a class="et_pb_button et_pb_button_0 et_pb_bg_layout_light" href="/">Volver al inicio</a>
\t\t\t</div>'''
    html = html.replace(old_content, _generar_pagina_carrito())
    return html


def _generar_pagina_carrito():
    """Genera el HTML del carrito + formulario Salesforce (diseño original carrito-2)."""
    return r'''
<style>
/* ── Layout principal: tabla + formulario ── */
.cgm-cart-layout {
    display: grid; grid-template-columns: 1fr 1fr;
    gap: 30px; max-width: 1100px; margin: 0 auto 40px; padding: 0 20px;
}
@media (max-width: 768px) {
    .cgm-cart-layout { grid-template-columns: 1fr; }
}

/* ── Tabla del carrito ── */
.cgm-cart-table-wrap {
    background: #fff; border-radius: 10px; padding: 25px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.08);
}
.cgm-cart-table {
    width: 100%; border-collapse: collapse;
    font-family: 'Open Sans', Arial, sans-serif; font-size: 14px;
}
.cgm-cart-table thead th {
    border-bottom: 2px solid #e0e0e0; padding: 10px 8px;
    text-align: left; color: #333; font-weight: 600; font-size: 13px;
}
.cgm-cart-table tbody tr { border-bottom: 1px solid #f0f0f0; }
.cgm-cart-table tbody td { padding: 12px 8px; vertical-align: middle; }
.cgm-cart-table .cart-remove {
    color: #c00; cursor: pointer; font-size: 16px; font-weight: bold;
    border: none; background: none; padding: 5px;
}
.cgm-cart-table .cart-remove:hover { color: #900; }
.cgm-cart-table .cart-thumb {
    width: 60px; height: 50px; object-fit: cover; border-radius: 4px;
}
.cgm-cart-table .cart-product-name {
    font-family: CGMBOLD, sans-serif; color: #333; font-size: 13px;
}
.cgm-cart-table .cart-qty {
    width: 50px; text-align: center; padding: 6px; border: 1px solid #ddd;
    border-radius: 4px; font-size: 14px;
}
.cgm-cart-empty {
    text-align: center; padding: 30px; color: #999; font-size: 15px;
}
.cgm-cart-empty a {
    display: inline-block; margin-top: 12px; padding: 10px 25px;
    background: #005335; color: #fff; text-decoration: none;
    border-radius: 4px; font-family: CGMBOLD, sans-serif; font-size: 13px;
}

/* ── Formulario Salesforce ── */
.cgm-sf-form {
    background: #fff; border-radius: 10px; padding: 25px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.08);
    font-family: CGMBOLD, Helvetica, sans-serif;
}
.cgm-sf-form .form-section-inline {
    display: flex; align-items: center; gap: 15px; margin-bottom: 15px;
}
.cgm-sf-form .form-section-inline label {
    color: #000; font-size: 14px;
}
.cgm-sf-form .form-section-inline input[type="checkbox"] {
    width: 18px; height: 18px; accent-color: #C5E86C;
}
.cgm-sf-form label {
    display: block; color: #000; font-size: 13px; margin-bottom: 4px;
    font-family: CGMBOLD, sans-serif;
}
.cgm-sf-form input[type="text"],
.cgm-sf-form select {
    padding: 14px; border: none; border-radius: 4px; font-size: 14px;
    background: #f0f0f0; color: #000; width: 100%; box-sizing: border-box;
    margin-bottom: 12px;
}
.cgm-sf-form .form-columns {
    display: grid; grid-template-columns: 1fr 1fr; gap: 15px;
}
@media (max-width: 768px) {
    .cgm-sf-form .form-columns { grid-template-columns: 1fr; }
}
.cgm-sf-form .form-terms {
    margin-top: 15px; font-size: 11px; color: #555;
}
.cgm-sf-form .form-terms input[type="checkbox"] {
    width: 16px; height: 16px; margin-right: 8px; accent-color: #C5E86C;
    vertical-align: middle;
}
.cgm-sf-form .form-terms label {
    display: flex; align-items: flex-start; gap: 8px; cursor: pointer;
    font-family: 'Open Sans', sans-serif; font-weight: normal;
}
.cgm-sf-form .campo {
    color: #C5E86C; font-size: 12px; margin-top: 8px;
}
.cgm-sf-form .sf-submit-container {
    display: flex; justify-content: flex-end; margin-top: 20px;
}
.cgm-sf-form input[type="submit"] {
    padding: 14px 30px; background-color: #C5E86C; border: none;
    border-radius: 4px; color: #005335; font-size: 15px; cursor: pointer;
    font-family: CGMBOLD, Helvetica, sans-serif; transition: opacity 0.3s;
    background: linear-gradient(58deg, transparent 4%, #C5E86C 0%, #C5E86C 96%, transparent 10%);
}
.cgm-sf-form input[type="submit"]:hover { opacity: 0.85; }

/* ── Modal éxito ── */
#modal-exito {
    position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    background: rgba(0,0,0,0.8); z-index: 99999;
    justify-content: center; align-items: center; display: none;
}
#modal-exito > div {
    background: #fff; padding: 40px 60px; border-radius: 10px; text-align: center;
}
#modal-exito h2 { color: #005335; font-size: 24px; margin-bottom: 10px; }
#modal-exito p { color: #333; font-size: 16px; }

</style>

<!-- Layout principal: tabla carrito + formulario -->
<div class="cgm-cart-layout">

    <!-- COLUMNA IZQUIERDA: Tabla del carrito -->
    <div class="cgm-cart-table-wrap">
        <table class="cgm-cart-table" id="cgm-cart-table">
            <thead>
                <tr>
                    <th></th>
                    <th></th>
                    <th>Product</th>
                    <th>Quantity</th>
                </tr>
            </thead>
            <tbody id="cgm-cart-tbody">
            </tbody>
        </table>
        <div class="cgm-cart-empty" id="cgm-cart-empty">
            <p>Tu carrito está vacío.</p>
            <a href="/categoria-producto/alquiler/">Ver Equipos</a>
        </div>
    </div>

    <!-- COLUMNA DERECHA: Formulario Salesforce -->
    <div id="cgm-form-container" style="display:none;">
        <form action="https://webto.salesforce.com/servlet/servlet.WebToLead?encoding=UTF-8&orgId=00D41000002lCbB"
              id="consulta-form" method="POST" class="cgm-sf-form">
            <input name="oid" type="hidden" value="00D41000002lCbB"/>
            <input name="retURL" type="hidden" value="http://localhost:5000/"/>
            <input type="hidden" name="debug" value="1"/>
            <input type="hidden" name="debugEmail" value="owenh.collazos@cgmrental.com"/>
            <input type="hidden" id="sf-last-name" name="last_name" value="Web Lead"/>

            <div class="form-section-inline">
                <label>Alquiler:</label>
                <input id="chk-alquiler" name="00NUU000001AZFF" type="checkbox" value="1"/>
                <label>Compra:</label>
                <input id="chk-compra" name="00NUU000001AZK5" type="checkbox" value="1"/>
            </div>

            <div>
                <label>Nombres y Apellidos</label>
                <input id="company" maxlength="40" name="company" placeholder="Nombres y Apellidos*" required type="text"/>
            </div>

            <div class="form-columns">
                <div>
                    <label>Razón Social:</label>
                    <input maxlength="55" name="00NUU000001uW6H" placeholder="Razón Social" required type="text"/>

                    <label>RUC/DNI:</label>
                    <input maxlength="11" name="00N4100000TT12H" placeholder="RUC/DNI*" required type="text"/>

                    <label>Email:</label>
                    <input maxlength="255" name="00NUU000001NBa5" placeholder="Email*" required type="text"/>

                    <label>Celular:</label>
                    <input maxlength="9" name="00NUU000001NBtR" placeholder="Celular*" required type="text"/>
                </div>
                <div>
                    <label>País:</label>
                    <select id="sf-pais" name="00NUU000001uSU5" required>
                        <option value="">--Ninguno--</option>
                        <option value="Perú">Perú</option>
                        <option value="Otro">Otro</option>
                    </select>

                    <label id="lbl-depto">Departamento:</label>
                    <select id="sf-depto" name="00NUU000001uSST" required>
                        <option value="">--Ninguno--</option>
                        <option value="Amazonas">Amazonas</option>
                        <option value="Áncash">Áncash</option>
                        <option value="Apurímac">Apurímac</option>
                        <option value="Arequipa">Arequipa</option>
                        <option value="Ayacucho">Ayacucho</option>
                        <option value="Cajamarca">Cajamarca</option>
                        <option value="Cusco">Cusco</option>
                        <option value="Huancavelica">Huancavelica</option>
                        <option value="Huánuco">Huánuco</option>
                        <option value="Ica">Ica</option>
                        <option value="Junín">Junín</option>
                        <option value="La Libertad">La Libertad</option>
                        <option value="Lambayeque">Lambayeque</option>
                        <option value="Lima">Lima</option>
                        <option value="Loreto">Loreto</option>
                        <option value="Madre de Dios">Madre de Dios</option>
                        <option value="Moquegua">Moquegua</option>
                        <option value="Pasco">Pasco</option>
                        <option value="Piura">Piura</option>
                        <option value="Puno">Puno</option>
                        <option value="San Martín">San Martín</option>
                        <option value="Tacna">Tacna</option>
                        <option value="Tumbes">Tumbes</option>
                        <option value="Ucayali">Ucayali</option>
                    </select>

                    <label id="lbl-otro-pais" style="display:none;">Otro País:</label>
                    <input id="sf-otro-pais" name="00NUU000001uS97" placeholder="Otro País"
                           type="text" style="display:none;"/>
                </div>
            </div>

            <input id="sf-info-carrito" name="00NUU000001NC4j" type="hidden"/>
            <input id="sf-equipo" name="00NUU000001HmSf" type="hidden"/>

            <div class="form-terms">
                <p class="campo">(*) Campos obligatorios</p>
                <label>
                    <input name="privacy_policy" required type="checkbox"/>
                    Acepto las Políticas de Privacidad y Términos y Condiciones de Tele Inmobiliaria.
                    Autorizo realizar actividades de prospección comercial y marketing
                    descritas en las Políticas de Privacidad
                </label>
            </div>

            <div class="sf-submit-container">
                <input type="submit" value="SOLICITAR INFORMACIÓN"/>
            </div>
        </form>
    </div>
</div>

<!-- Modal de éxito -->
<div id="modal-exito">
    <div>
        <h2>¡Envío exitoso!</h2>
        <p>Gracias por tu interés. Estamos procesando tu solicitud.</p>
    </div>
</div>

<script>
(function(){
    var STORAGE_KEY = "cgm_cotizador";
    var cart = [];
    try { cart = JSON.parse(localStorage.getItem(STORAGE_KEY)) || []; } catch(e){}

    var tbody = document.getElementById("cgm-cart-tbody");
    var emptyMsg = document.getElementById("cgm-cart-empty");
    var tableEl = document.getElementById("cgm-cart-table");
    var formContainer = document.getElementById("cgm-form-container");
    var sfInfoCarrito = document.getElementById("sf-info-carrito");
    var sfEquipo = document.getElementById("sf-equipo");

    function render(){
        try { cart = JSON.parse(localStorage.getItem(STORAGE_KEY)) || []; } catch(e){ cart=[]; }
        if(!tbody) return;
        tbody.innerHTML = "";

        if(cart.length === 0){
            emptyMsg.style.display = "block";
            tableEl.style.display = "none";
            formContainer.style.display = "none";
            return;
        }
        emptyMsg.style.display = "none";
        tableEl.style.display = "table";
        formContainer.style.display = "block";

        var equipoTexto = [];
        for(var i=0;i<cart.length;i++){
            var item = cart[i];
            var tag = item.tags ? " [" + item.tags.charAt(0).toUpperCase() + item.tags.slice(1) + "]" : "";
            var tr = document.createElement("tr");
            tr.innerHTML =
                '<td><button class="cart-remove" data-slug="'+item.slug+'" title="Eliminar">&times;</button></td>' +
                '<td>' + (item.imagen ? '<img class="cart-thumb" src="'+item.imagen+'" alt=""/>' : '') + '</td>' +
                '<td class="cart-product-name">' + item.nombre + tag + '</td>' +
                '<td><input class="cart-qty" type="text" value="1" readonly/></td>';
            tbody.appendChild(tr);
            equipoTexto.push("1 x " + item.nombre);
        }

        // Llenar campos ocultos de Salesforce
        var texto = equipoTexto.join("\n");
        if(sfInfoCarrito) sfInfoCarrito.value = texto;
        if(sfEquipo) sfEquipo.value = texto;
    }

    // Eliminar items
    if(tbody) tbody.addEventListener("click", function(e){
        var btn = e.target.closest(".cart-remove");
        if(!btn) return;
        var slug = btn.getAttribute("data-slug");
        cart = cart.filter(function(item){ return item.slug !== slug; });
        localStorage.setItem(STORAGE_KEY, JSON.stringify(cart));
        render();
        var counter = document.getElementById("woofc-cart-trigger-counter");
        if(counter) counter.textContent = cart.length;
    });

    // Sincronizar last_name con el campo company (Nombres y Apellidos)
    var companyField = document.getElementById("company");
    var lastNameField = document.getElementById("sf-last-name");
    if(companyField && lastNameField){
        companyField.addEventListener("input", function(){
            lastNameField.value = this.value || "Web Lead";
        });
    }

    // Checkboxes mutuamente excluyentes
    var chkAlq = document.getElementById("chk-alquiler");
    var chkCom = document.getElementById("chk-compra");
    if(chkAlq && chkCom){
        chkAlq.addEventListener("change", function(){ if(this.checked) chkCom.checked=false; });
        chkCom.addEventListener("change", function(){ if(this.checked) chkAlq.checked=false; });
    }

    // País → Departamento toggle
    var pais = document.getElementById("sf-pais");
    var depto = document.getElementById("sf-depto");
    var lblDepto = document.getElementById("lbl-depto");
    var otroPais = document.getElementById("sf-otro-pais");
    var lblOtro = document.getElementById("lbl-otro-pais");
    if(pais){
        pais.addEventListener("change", function(){
            if(this.value === "Otro"){
                depto.style.display="none"; lblDepto.style.display="none";
                depto.required=false; depto.value="";
                otroPais.style.display="block"; lblOtro.style.display="block";
                otroPais.required=true;
            } else if(this.value === "Perú"){
                depto.style.display="block"; lblDepto.style.display="block";
                depto.required=true;
                otroPais.style.display="none"; lblOtro.style.display="none";
                otroPais.required=false; otroPais.value="Perú";
            } else {
                depto.style.display="block"; lblDepto.style.display="block";
                otroPais.style.display="none"; lblOtro.style.display="none";
            }
        });
    }

    // Submit con modal
    var form = document.getElementById("consulta-form");
    var modal = document.getElementById("modal-exito");
    if(form){
        form.addEventListener("submit", function(e){
            e.preventDefault();
            render();
            modal.style.display = "flex";
            var f = this;
            setTimeout(function(){
                localStorage.removeItem(STORAGE_KEY);
                f.submit();
            }, 2000);
        });
    }

    render();
})();
</script>'''


# ── Páginas estáticas ──
PAGINAS_ESTATICAS = {
    "inicio": "inicio.html",
    "contacto": "contacto.html",
    "nosotros": "nosotros.html",
    "novedades": "novedades.html",
    "leasing-operativo": "leasing_operativo.html",
    # carrito y carrito-2 se manejan con ruta dedicada
}


@app.route("/<page>/")
@app.route("/<page>/index.html")
def pagina_estatica(page):
    """Servir páginas estáticas."""
    if page in PAGINAS_ESTATICAS:
        return _servir_pagina(PAGINAS_ESTATICAS[page])
    return abort(404)


# ── Novedades con paginación ──
@app.route("/novedades/page/<int:num>/")
@app.route("/novedades/page/<int:num>/index.html")
def novedades_paginacion(num):
    return _servir_pagina(f"novedades_page{num}.html")


# ── Blog/artículos por fecha ──
@app.route("/<int:year>/<int:month>/<int:day>/<slug>/")
@app.route("/<int:year>/<int:month>/<int:day>/<slug>/index.html")
def articulo(year, month, day, slug):
    filename = f"{year}-{month:02d}-{day:02d}-{slug}.html"
    filepath = os.path.join(STATIC_DIR, "blog", filename)
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    return abort(404)


# ── Categorías de blog ──
@app.route("/category/<cat>/")
@app.route("/category/<cat>/index.html")
def category_blog(cat):
    filepath = os.path.join(STATIC_DIR, "blog_categories", f"{cat}.html")
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    return abort(404)


# ── Utilidad: headers de caché para assets estáticos ──
_ONE_YEAR = 60 * 60 * 24 * 365  # 1 año en segundos
_ONE_WEEK = 60 * 60 * 24 * 7

def _cached(response, max_age=_ONE_YEAR):
    """Agrega Cache-Control a una respuesta de asset estático."""
    response.cache_control.max_age = max_age
    response.cache_control.public = True
    return response


# ── Archivos estáticos ──
@app.route("/wp-content/<path:filepath>")
def wp_content(filepath):
    return _cached(make_response(
        send_from_directory(os.path.join(STATIC_DIR, "wp-content"), filepath)
    ))


@app.route("/imagenes/<path:filepath>")
@app.route("/images/<path:filepath>")
def imagenes(filepath):
    return _cached(make_response(
        send_from_directory(os.path.join(STATIC_DIR, "images"), filepath)
    ))


@app.route("/static/pages-assets/<path:filepath>")
def pages_assets(filepath):
    return _cached(make_response(
        send_from_directory(os.path.join(STATIC_DIR, "pages-assets"), filepath)
    ))


@app.route("/cotizador.js")
def cotizador_js():
    return _cached(make_response(
        send_from_directory(os.path.join(STATIC_DIR, "js"), "cotizador.js",
                            mimetype="application/javascript")
    ), max_age=_ONE_WEEK)

@app.route("/static/js/<path:filename>")
def static_js(filename):
    return _cached(make_response(
        send_from_directory(os.path.join(STATIC_DIR, "js"), filename,
                            mimetype="application/javascript")
    ), max_age=_ONE_WEEK)


# ── Leasing operativo ──
@app.route("/leasing-operativo/")
@app.route("/leasing-operativo/index.html")
def leasing_operativo():
    return _servir_pagina("leasing_operativo.html")


# ══════════════════════════════════════════════════════════════════
# INICIO
# ══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print(f"CGM Rental - Servidor Flask")
    print(f"Productos cargados: {len(PRODUCTOS)}")
    print(f"Rutas de categoria: {len(RUTAS)}")
    print(f"Base dir: {BASE_DIR}")
    _precalentar_categorias()
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=5000, debug=debug_mode, threaded=True)
