#!/usr/bin/env python3
"""Reemplaza la barra superior del Portal de Proveedores con el diseño correcto."""

import re

TOPBAR = '''<div id="cgm-topbar" style="background:#0c534c;color:white;padding:8px 20px;display:flex;justify-content:space-between;align-items:center;font-family:Arial,sans-serif;font-size:13px;flex-wrap:wrap;gap:8px;">
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
    <a href="https://www.facebook.com/CGMRENTAL/" target="_blank" style="display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;background:rgba(0,0,0,0.3);color:white;border-radius:3px;text-decoration:none;">
      <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" fill="white" viewBox="0 0 320 512"><path d="M279.14 288l14.22-92.66h-88.91v-60.13c0-25.35 12.42-50.06 52.24-50.06h40.42V6.26S260.43 0 225.36 0c-73.22 0-121.08 44.38-121.08 124.72v70.62H22.89V288h81.39v224h100.17V288z"/></svg>
    </a>
    <a href="https://www.instagram.com/cgmrental/" target="_blank" style="display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;background:rgba(0,0,0,0.3);color:white;border-radius:3px;text-decoration:none;">
      <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" fill="white" viewBox="0 0 448 512"><path d="M224.1 141c-63.6 0-114.9 51.3-114.9 114.9s51.3 114.9 114.9 114.9S339 319.5 339 255.9 287.7 141 224.1 141zm0 189.6c-41.1 0-74.7-33.5-74.7-74.7s33.5-74.7 74.7-74.7 74.7 33.5 74.7 74.7-33.6 74.7-74.7 74.7zm146.4-194.3c0 14.9-12 26.8-26.8 26.8-14.9 0-26.8-12-26.8-26.8s12-26.8 26.8-26.8 26.8 12 26.8 26.8zm76.1 27.2c-1.7-35.9-9.9-67.7-36.2-93.9-26.2-26.2-58-34.4-93.9-36.2-37-2.1-147.9-2.1-184.9 0-35.8 1.7-67.6 9.9-93.9 36.1s-34.4 58-36.2 93.9c-2.1 37-2.1 147.9 0 184.9 1.7 35.9 9.9 67.7 36.2 93.9s58 34.4 93.9 36.2c37 2.1 147.9 2.1 184.9 0 35.9-1.7 67.7-9.9 93.9-36.2 26.2-26.2 34.4-58 36.2-93.9 2.1-37 2.1-147.8 0-184.8zM398.8 388c-7.8 19.6-22.9 34.7-42.6 42.6-29.5 11.7-99.5 9-132.1 9s-102.7 2.6-132.1-9c-19.6-7.8-34.7-22.9-42.6-42.6-11.7-29.5-9-99.5-9-132.1s-2.6-102.7 9-132.1c7.8-19.6 22.9-34.7 42.6-42.6 29.5-11.7 99.5-9 132.1-9s102.7-2.6 132.1 9c19.6 7.8 34.7 22.9 42.6 42.6 11.7 29.5 9 99.5 9 132.1s2.7 102.7-9 132.1z"/></svg>
    </a>
    <a href="https://www.linkedin.com/company/cgm-rental/" target="_blank" style="display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;background:rgba(0,0,0,0.3);color:white;border-radius:3px;text-decoration:none;">
      <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" fill="white" viewBox="0 0 448 512"><path d="M100.28 448H7.4V148.9h92.88zM53.79 108.1C24.09 108.1 0 83.5 0 53.8a53.79 53.79 0 0 1 107.58 0c0 29.7-24.1 54.3-53.79 54.3zM447.9 448h-92.68V302.4c0-34.7-.7-79.2-48.29-79.2-48.29 0-55.69 37.7-55.69 76.7V448h-92.78V148.9h89.08v40.8h1.3c12.4-23.5 42.69-48.3 87.88-48.3 94 0 111.28 61.9 111.28 142.3V448z"/></svg>
    </a>
    <a href="https://www.youtube.com/@cgmrental" target="_blank" style="display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;background:rgba(0,0,0,0.3);color:white;border-radius:3px;text-decoration:none;">
      <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" fill="white" viewBox="0 0 576 512"><path d="M549.655 124.083c-6.281-23.65-24.787-42.276-48.284-48.597C458.781 64 288 64 288 64S117.22 64 74.629 75.486c-23.497 6.322-42.003 24.947-48.284 48.597-11.412 42.867-11.412 132.305-11.412 132.305s0 89.438 11.412 132.305c6.281 23.65 24.787 41.5 48.284 47.821C117.22 448 288 448 288 448s170.78 0 213.371-11.486c23.497-6.322 42.003-24.171 48.284-47.821 11.412-42.867 11.412-132.305 11.412-132.305s0-89.438-11.412-132.305zm-317.51 213.508V175.185l142.739 81.205-142.739 81.201z"/></svg>
    </a>
  </div>
</div>'''

filepath = "static/pages/portalproveedores.html"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Eliminar topbar anterior si existe
content = re.sub(r'<div id="cgm-topbar".*?</div>\n', '', content, flags=re.DOTALL)

# Inyectar nuevo topbar antes del <div id="app" data-v-app="">
content = content.replace('<div id="app" data-v-app="">', TOPBAR + '\n    <div id="app" data-v-app="">', 1)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("OK - topbar actualizado correctamente")
