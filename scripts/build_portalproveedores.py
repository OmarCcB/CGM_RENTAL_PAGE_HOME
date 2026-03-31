#!/usr/bin/env python3
"""
Construye portalproveedores.html:
  - Base visual: nosotros.html (head + header + hero + footer)
  - Elimina: Nuestra Historia, Politica Integrada, Sucursales, Socios, Testimonios
  - Agrega: seccion con info empresa (izq) + Vue SPA del formulario DIRECTO (der)
  - El Vue SPA se incrusta directamente (sin iframe) para que sea 100% funcional
"""

import sys, re, os, shutil
sys.stdout.reconfigure(encoding="utf-8")

NOSOTROS    = "static/pages/nosotros.html"
FORM_SPA    = "static/pages/portalproveedores-form.html"
OUTPUT      = "static/pages/portalproveedores.html"

# ─── 1. Leer archivos ────────────────────────────────────────────────────────
print("Leyendo nosotros.html ...")
with open(NOSOTROS, "r", encoding="utf-8") as f:
    nos = f.read()

print("Leyendo portalproveedores-form.html (Vue SPA) ...")
with open(FORM_SPA, "r", encoding="utf-8") as f:
    spa = f.read()

# ─── 2. Extraer partes del Vue SPA ──────────────────────────────────────────
# --- Head del SPA (scripts + styles de Vue/Quasar) ---
spa_head_start = spa.find("<head>") + len("<head>")
spa_head_end   = spa.find("</head>")
spa_head       = spa[spa_head_start:spa_head_end]

# --- Quasar CSS vars del <body> ---
spa_body_tag   = spa[spa.find("<body"):spa.find(">", spa.find("<body"))+1]
quasar_style   = ""
style_m        = re.search(r'style="([^"]*--q-[^"]*)"', spa_body_tag)
if style_m:
    quasar_style = style_m.group(1)

# --- div#app hasta </body> (incluye scripts de hidratacion) ---
app_start  = spa.find('<div id="app" data-v-app="">')
body_end   = spa.rfind("</body>")
spa_app    = spa[app_start:body_end]   # div#app + trailing scripts

# ─── 3. Extraer partes de nosotros.html ─────────────────────────────────────
# Head completo de nosotros
nos_head_end   = nos.find("</head>")
nos_head       = nos[:nos_head_end + len("</head>")]

# Desde </head> hasta section_1: contiene body tag, header nav, wrappers y hero
section1_start = nos.find('<div class="et_pb_section et_pb_section_1 et_section_regular">')
full_header_region = nos[nos_head_end + len("</head>"):section1_start]

# Separar: (1) solo la navegacion/header, (2) los divs wrapper, (3) el hero
header_tpl_end   = full_header_region.rfind("</header>")
nos_nav_header   = full_header_region[:header_tpl_end + len("</header>")]  # <body> + <header>...</header>
after_header_str = full_header_region[header_tpl_end + len("</header>"):]

# Los divs wrapper (et-main-area, main-content, article, entry-content, etc.)
# terminan ANTES del et_pb_section_0 (hero/LA EVOLUCION que queremos omitir)
section0_in_ah = after_header_str.find('<div class="et_pb_section et_pb_section_0')
nos_wrappers   = after_header_str[:section0_in_ah]   # solo los divs abrientes, sin el hero

# Footer: desde <footer class="et-l et-l--footer"> hasta el final
footer_start = nos.find('<footer class="et-l et-l--footer">')
nos_footer   = nos[footer_start:]

# ─── 4. Topbar CGM ──────────────────────────────────────────────────────────
TOPBAR = '''<div id="cgm-topbar" style="background:#0c534c;color:white;padding:8px 20px;display:flex;justify-content:space-between;align-items:center;font-family:Arial,sans-serif;font-size:13px;flex-wrap:wrap;gap:8px;position:relative;z-index:99999;">
  <div style="display:flex;align-items:center;gap:24px;">
    <span style="display:flex;align-items:center;gap:6px;">
      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="white" viewBox="0 0 448 512"><path d="M380.9 97.1C339 55.1 283.2 32 223.9 32c-122.4 0-222 99.6-222 222 0 39.1 10.2 77.3 29.6 111L0 480l117.7-30.9c32.4 17.7 68.9 27 106.1 27h.1c122.3 0 224.1-99.6 224.1-222 0-59.3-25.2-115-67.1-157zm-157 341.6c-33.2 0-65.7-8.9-94-25.7l-6.7-4-69.8 18.3L72 359.2l-4.4-7c-18.5-29.4-28.2-63.3-28.2-98.2 0-101.7 82.8-184.5 184.6-184.5 49.3 0 95.6 19.2 130.4 54.1 34.8 34.9 56.2 81.2 56.1 130.5 0 101.8-84.9 184.6-186.6 184.6zm101.2-138.2c-5.5-2.8-32.8-16.2-37.9-18-5.1-1.9-8.8-2.8-12.5 2.8-3.7 5.6-14.3 18-17.6 21.8-3.2 3.7-6.5 4.2-12 1.4-32.6-16.3-54-29.1-75.5-66-5.7-9.8 5.7-9.1 16.3-30.3 1.8-3.7.9-6.9-.5-9.7-1.4-2.8-12.5-30.1-17.1-41.2-4.5-10.8-9.1-9.3-12.5-9.5-3.2-.2-6.9-.2-10.6-.2-3.7 0-9.7 1.4-14.8 6.9-5.1 5.6-19.4 19-19.4 46.3 0 27.3 19.9 53.7 22.6 57.4 2.8 3.7 39.1 59.7 94.8 83.8 35.2 15.2 49 16.5 66.6 13.9 10.7-1.6 32.8-13.4 37.4-26.4 4.6-13 4.6-24.1 3.2-26.4-1.3-2.5-5-3.9-10.5-6.6z"/></svg>
      <a href="https://wa.link/sht6gi" style="color:white;text-decoration:none;font-weight:600;">943567445</a>
    </span>
    <span style="display:flex;align-items:center;gap:6px;">
      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="white" viewBox="0 0 512 512"><path d="M48 64C21.5 64 0 85.5 0 112c0 15.1 7.1 29.3 19.2 38.4L236.8 313.6c11.4 8.5 27 8.5 38.4 0L492.8 150.4c12.1-9.1 19.2-23.3 19.2-38.4c0-26.5-21.5-48-48-48H48zM0 176V384c0 35.3 28.7 64 64 64H448c35.3 0 64-28.7 64-64V176L294.4 339.2c-22.8 17.1-54 17.1-76.8 0L0 176z"/></svg>
      <a href="mailto:inteligenciacomercial@cgmrental.com" style="color:white;text-decoration:none;font-weight:600;">inteligenciacomercial@cgmrental.com</a>
    </span>
  </div>
  <div style="display:flex;align-items:center;gap:4px;">
    <a href="https://www.facebook.com/CGMRENTAL/" target="_blank" style="display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;background:rgba(0,0,0,0.3);color:white;border-radius:3px;text-decoration:none;"><svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" fill="white" viewBox="0 0 320 512"><path d="M279.14 288l14.22-92.66h-88.91v-60.13c0-25.35 12.42-50.06 52.24-50.06h40.42V6.26S260.43 0 225.36 0c-73.22 0-121.08 44.38-121.08 124.72v70.62H22.89V288h81.39v224h100.17V288z"/></svg></a>
    <a href="https://www.instagram.com/cgmrental/" target="_blank" style="display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;background:rgba(0,0,0,0.3);color:white;border-radius:3px;text-decoration:none;"><svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" fill="white" viewBox="0 0 448 512"><path d="M224.1 141c-63.6 0-114.9 51.3-114.9 114.9s51.3 114.9 114.9 114.9S339 319.5 339 255.9 287.7 141 224.1 141zm0 189.6c-41.1 0-74.7-33.5-74.7-74.7s33.5-74.7 74.7-74.7 74.7 33.5 74.7 74.7-33.6 74.7-74.7 74.7zm146.4-194.3c0 14.9-12 26.8-26.8 26.8-14.9 0-26.8-12-26.8-26.8s12-26.8 26.8-26.8 26.8 12 26.8 26.8zm76.1 27.2c-1.7-35.9-9.9-67.7-36.2-93.9-26.2-26.2-58-34.4-93.9-36.2-37-2.1-147.9-2.1-184.9 0-35.8 1.7-67.6 9.9-93.9 36.1s-34.4 58-36.2 93.9c-2.1 37-2.1 147.9 0 184.9 1.7 35.9 9.9 67.7 36.2 93.9s58 34.4 93.9 36.2c37 2.1 147.9 2.1 184.9 0 35.9-1.7 67.7-9.9 93.9-36.2 26.2-26.2 34.4-58 36.2-93.9 2.1-37 2.1-147.8 0-184.8zM398.8 388c-7.8 19.6-22.9 34.7-42.6 42.6-29.5 11.7-99.5 9-132.1 9s-102.7 2.6-132.1-9c-19.6-7.8-34.7-22.9-42.6-42.6-11.7-29.5-9-99.5-9-132.1s-2.6-102.7 9-132.1c7.8-19.6 22.9-34.7 42.6-42.6 29.5-11.7 99.5-9 132.1-9s102.7-2.6 132.1 9c19.6 7.8 34.7 22.9 42.6 42.6 11.7 29.5 9 99.5 9 132.1s2.7 102.7-9 132.1z"/></svg></a>
    <a href="https://www.linkedin.com/company/cgm-rental/" target="_blank" style="display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;background:rgba(0,0,0,0.3);color:white;border-radius:3px;text-decoration:none;"><svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" fill="white" viewBox="0 0 448 512"><path d="M100.28 448H7.4V148.9h92.88zM53.79 108.1C24.09 108.1 0 83.5 0 53.8a53.79 53.79 0 0 1 107.58 0c0 29.7-24.1 54.3-53.79 54.3zM447.9 448h-92.68V302.4c0-34.7-.7-79.2-48.29-79.2-48.29 0-55.69 37.7-55.69 76.7V448h-92.78V148.9h89.08v40.8h1.3c12.4-23.5 42.69-48.3 87.88-48.3 94 0 111.28 61.9 111.28 142.3V448z"/></svg></a>
    <a href="https://www.youtube.com/@cgmrental" target="_blank" style="display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;background:rgba(0,0,0,0.3);color:white;border-radius:3px;text-decoration:none;"><svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" fill="white" viewBox="0 0 576 512"><path d="M549.655 124.083c-6.281-23.65-24.787-42.276-48.284-48.597C458.781 64 288 64 288 64S117.22 64 74.629 75.486c-23.497 6.322-42.003 24.947-48.284 48.597-11.412 42.867-11.412 132.305-11.412 132.305s0 89.438 11.412 132.305c6.281 23.65 24.787 41.5 48.284 47.821C117.22 448 288 448 288 448s170.78 0 213.371-11.486c23.497-6.322 42.003-24.171 48.284-47.821 11.412-42.867 11.412-132.305 11.412-132.305s0-89.438-11.412-132.305zm-317.51 213.508V175.185l142.739 81.205-142.739 81.201z"/></svg></a>
  </div>
</div>'''

# ─── 5. Nueva seccion de contenido ──────────────────────────────────────────
NEW_SECTION = f'''
<!-- ╔══ PORTAL DE PROVEEDORES ══╗ -->
<div id="cgm-proveedores-page">
<style>
  /* ── Quasar CSS vars (necesarios para los componentes Vue) ── */
  #cgm-proveedores-page {{
    {quasar_style};
  }}

  /* ── Layout principal ── */
  #cgm-pp-wrapper {{
    background: #f0f2f4;
    padding: 36px 20px 60px;
  }}
  #cgm-pp-inner {{
    max-width: 1200px;
    margin: 0 auto;
    display: flex;
    gap: 28px;
    align-items: flex-start;
    flex-wrap: wrap;
  }}

  /* ── Panel izquierdo: info empresa ── */
  #cgm-pp-info {{
    flex: 0 0 320px;
    max-width: 320px;
    background: white;
    border-radius: 8px;
    padding: 28px 24px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.08);
  }}
  #cgm-pp-info h2 {{
    font-size: 19px;
    font-weight: 700;
    color: #111;
    margin: 0 0 5px;
    letter-spacing: 1px;
    font-family: inherit;
  }}
  .cgm-pp-divline {{
    width: 38px; height: 3px;
    background: linear-gradient(90deg, #0c534c 55%, #bed46e 100%);
    margin-bottom: 16px;
  }}
  #cgm-pp-info p {{
    font-size: 13.5px;
    color: #444;
    line-height: 1.7;
    margin-bottom: 10px;
    font-family: inherit;
  }}
  #cgm-pp-iso {{
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    justify-content: center;
    margin: 16px 0 22px;
  }}
  #cgm-pp-iso img {{
    width: 68px;
    height: auto;
    /* SIN animacion */
    transition: none !important;
    transform: none !important;
    animation: none !important;
  }}
  #cgm-pp-info h3 {{
    font-size: 15px;
    font-weight: 700;
    color: #111;
    letter-spacing: 1px;
    margin: 0 0 5px;
    font-family: inherit;
  }}

  /* ── Mapa sucursales SIN animacion ── */
  #cgm-pp-mapwrap {{
    display: flex;
    justify-content: center;
    align-items: flex-start;
    gap: 2px;
    margin-top: 10px;
  }}
  #cgm-pp-mapwrap .mpcol {{
    display: flex;
    flex-direction: column;
    gap: 4px;
    justify-content: center;
  }}
  #cgm-pp-mapwrap .mpcol img,
  #cgm-pp-mapwrap .mpcenter img {{
    /* BLOQUEAR animaciones de nosotros.html */
    transition: none !important;
    transform: none !important;
    animation: none !important;
    pointer-events: none;
  }}
  #cgm-pp-mapwrap .mpcol img   {{ width: 86px;  height: auto; }}
  #cgm-pp-mapwrap .mpcenter img {{ width: 128px; height: auto; }}

  /* ── Panel derecho: formulario Vue ── */
  #cgm-pp-form {{
    flex: 1 1 500px;
    min-width: 300px;
    background: transparent;
  }}

  /* ── Overrides del Vue SPA embebido ── */
  /* Ocultar partes del SPA que no necesitamos */
  #cgm-proveedores-page #cgm-topbar,
  #cgm-proveedores-page .header-container,
  #cgm-proveedores-page .back-button-container,
  #cgm-proveedores-page .left-column,
  #cgm-proveedores-page .footer {{
    display: none !important;
  }}
  /* El contenedor del formulario ocupa todo el ancho disponible */
  #cgm-proveedores-page .registro-proveedores {{
    padding: 0 !important;
    background: transparent !important;
    min-height: unset !important;
  }}
  #cgm-proveedores-page .container {{
    padding: 0 !important;
    max-width: 100% !important;
  }}
  #cgm-proveedores-page .main-row {{
    display: block !important;
    padding: 0 !important;
  }}
  #cgm-proveedores-page .right-column {{
    width: 100% !important;
    max-width: 100% !important;
    flex: 1 1 auto !important;
    padding: 0 !important;
  }}
  #cgm-proveedores-page .form-container {{
    max-width: 100% !important;
    border-radius: 8px;
  }}

  /* ── Responsive ── */
  @media (max-width: 820px) {{
    #cgm-pp-info  {{ flex: 1 1 100%; max-width: 100%; }}
    #cgm-pp-form  {{ flex: 1 1 100%; }}
  }}

  /* ── Boton volver ── */
  #cgm-pp-back {{
    max-width: 1200px;
    margin: 0 auto 16px;
    padding: 0 20px;
  }}
  #cgm-pp-back a {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    color: #0c534c;
    font-family: inherit;
    font-size: 13px;
    text-decoration: none;
    font-weight: 600;
    background: white;
    padding: 7px 14px;
    border-radius: 4px;
    box-shadow: 0 1px 5px rgba(0,0,0,0.1);
  }}
</style>

<div id="cgm-pp-wrapper">

  <!-- Boton volver -->
  <div id="cgm-pp-back">
    <a href="https://peru.cgmrental.com.pe/">
      <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" fill="#0c534c" viewBox="0 0 448 512"><path d="M9.4 233.4c-12.5 12.5-12.5 32.8 0 45.3l160 160c12.5 12.5 32.8 12.5 45.3 0s12.5-32.8 0-45.3L109.2 288 416 288c17.7 0 32-14.3 32-32s-14.3-32-32-32l-306.7 0 105.4-105.4c12.5-12.5 12.5-32.8 0-45.3s-32.8-12.5-45.3 0l-160 160z"/></svg>
      Regresar a la p&aacute;gina principal
    </a>
  </div>

  <div id="cgm-pp-inner">

    <!-- ── Columna izquierda: info empresa ── -->
    <div id="cgm-pp-info">

      <h2>NOSOTROS</h2>
      <div class="cgm-pp-divline"></div>
      <p>Somos una empresa especializada en alquiler de maquinaria y venta de equipos usados. Poseemos una flota amplia con marcas reconocidas en el mercado.</p>
      <p>CGM Rental, empresa cuatrinorma, cuenta con las certificaciones de calidad ISO&nbsp;9001, de gesti&oacute;n ambiental ISO&nbsp;14001, de salud ocupacional ISO&nbsp;45001 y antisoborno ISO&nbsp;37001.</p>

      <div id="cgm-pp-iso">
        <a href="https://cgmrentalsocac-my.sharepoint.com/:b:/g/personal/diego_hinojosa_cgmrental_com_pe/Ea6-_Dkh879IvujtrR7TfTEBGGNrgpV1ppT_jb0D6xB5Ug" target="_blank"><img src="/static/pages-assets/nosotros/img_003_fb545bc7c7f8.svg" alt="ISO 9001"></a>
        <a href="https://cgmrentalsocac-my.sharepoint.com/:b:/g/personal/diego_hinojosa_cgmrental_com_pe/EYH1CuY98idFmskstpnLA7UBiA0rdxfuqisnWkJB6N3Eow" target="_blank"><img src="/static/pages-assets/nosotros/img_004_dfefff5967a2.svg" alt="ISO 14001"></a>
        <a href="https://cgmrentalsocac-my.sharepoint.com/:b:/g/personal/diego_hinojosa_cgmrental_com_pe/ETUgIbCZ515DqB6rs3k-66gBbCfANnlJAUicKYOPOq2Pfw" target="_blank"><img src="/static/pages-assets/nosotros/img_005_ad79e3b0e4c0.svg" alt="ISO 45001"></a>
        <a href="https://drive.google.com/file/d/19qnIJfz98Cf2zVgtVmsQVreEnNjTSpJC/view" target="_blank"><img src="/static/pages-assets/nosotros/img_006_6952da2acf22.svg" alt="ISO 37001"></a>
      </div>

      <h3>SUCURSALES</h3>
      <div class="cgm-pp-divline"></div>
      <div id="cgm-pp-mapwrap">
        <div class="mpcol">
          <img src="/static/pages-assets/nosotros/img_007_9ea763ca75c0.svg" alt="Piura">
          <img src="/static/pages-assets/nosotros/img_008_4b79c0e906c2.svg" alt="Pucallpa">
          <img src="/static/pages-assets/nosotros/img_009_b1753af0d05e.svg" alt="Ica">
        </div>
        <div class="mpcol mpcenter">
          <img src="/static/pages-assets/nosotros/img_010_781146d1ab62.svg" alt="Mapa Peru">
        </div>
        <div class="mpcol">
          <img src="/static/pages-assets/nosotros/img_011_955fa2bcc966.svg" alt="Pucallpa">
          <img src="/static/pages-assets/nosotros/img_012_8a4583c34ffa.svg" alt="Cusco">
          <img src="/static/pages-assets/nosotros/img_013_8919a1947859.svg" alt="Arequipa">
        </div>
      </div>

    </div><!-- /cgm-pp-info -->

    <!-- ── Columna derecha: Vue SPA directo ── -->
    <div id="cgm-pp-form">
      {spa_app}
    </div><!-- /cgm-pp-form -->

  </div><!-- /cgm-pp-inner -->
</div><!-- /cgm-pp-wrapper -->
</div><!-- /cgm-proveedores-page -->
<!-- ╚══ FIN PORTAL DE PROVEEDORES ══╝ -->
'''

# ─── 6. Ensamblar pagina final ───────────────────────────────────────────────
# Head: nosotros + scripts Vue/Quasar
nos_head_with_spa = nos_head + "\n<!-- Vue/Quasar scripts -->\n" + spa_head + "\n</head>"

# Inyectar topbar antes de <div id="page-container"> (esta dentro de nos_nav_header)
PAGE_CONTAINER = '<div id="page-container">'
nos_nav_header = nos_nav_header.replace(PAGE_CONTAINER, TOPBAR + "\n" + PAGE_CONTAINER, 1)

final_page = (
    nos_head_with_spa
    + "\n"
    + nos_nav_header       # <body> + <header> nav (SIN hero/LA EVOLUCION)
    + "\n"
    + nos_wrappers         # divs abrientes: et-main-area, main-content, article, entry-content...
    + "\n"
    + NEW_SECTION          # nuestro contenido: info empresa + formulario Vue
    + "\n"
    + nos_footer           # footer con divs cerrantes + </html>
)

# ─── 7. Guardar ─────────────────────────────────────────────────────────────
with open(OUTPUT, "w", encoding="utf-8") as f:
    f.write(final_page)

size_mb = os.path.getsize(OUTPUT) / 1024 / 1024
print(f"portalproveedores.html guardado: {size_mb:.1f} MB")
print("LISTO - Vue SPA incrustado directamente, sin iframe")
