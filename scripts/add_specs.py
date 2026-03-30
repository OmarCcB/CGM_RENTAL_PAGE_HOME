#!/usr/bin/env python3
"""Agregar especificaciones técnicas a products.json."""
import json
import re
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(BASE, "products.json"), "r", encoding="utf-8") as f:
    products = json.load(f)

SPECS = {
    "camion-grua": ["Capacidad de carga: 10 Ton", "Motor: PACCAR", "Grúa hidráulica telescópica"],
    "camiones-cisterna": ["Capacidad: 5,000 Gal", "Motor: PACCAR", "Bomba de agua incluida"],
    "cargador-frontal-644k": ["Potencia: 173 HP", "Capacidad balde: 2.7 m³", "Peso operativo: 15,800 kg"],
    "cargador-frontal-744k-ii-744l": ["Potencia: 249 HP", "Capacidad balde: 4.0 m³", "Peso operativo: 22,000 kg"],
    "cargador-frontal-744k": ["Potencia: 249 HP", "Capacidad balde: 4.0 m³", "Peso operativo: 22,000 kg"],
    "excavadora-hidraulica-210glc": ["Potencia: 159 HP", "Peso operativo: 21,500 kg", "Prof. excavación: 6.7 m"],
    "excavadora-hidraulica-250g": ["Potencia: 188 HP", "Peso operativo: 25,700 kg", "Prof. excavación: 7.0 m"],
    "excavadora-hidraulica-350g": ["Potencia: 271 HP", "Peso operativo: 36,100 kg", "Prof. excavación: 7.6 m"],
    "excavadora-hidraulica-870g": ["Potencia: 512 HP", "Peso operativo: 80,200 kg", "Prof. excavación: 8.5 m"],
    "excavadora-hidraulica-zx1200": ["Potencia: 763 HP", "Peso operativo: 117,000 kg", "Capacidad balde: 6.7 m³"],
    "excavadora-hidraulica-zx210": ["Potencia: 159 HP", "Peso operativo: 21,300 kg", "Prof. excavación: 6.6 m"],
    "excavadora-hidraulica-zx350": ["Potencia: 271 HP", "Peso operativo: 35,200 kg", "Prof. excavación: 7.4 m"],
    "excavadora-hidraulica-zx870lc-5": ["Potencia: 512 HP", "Peso operativo: 82,800 kg", "Capacidad balde: 4.5 m³"],
    "motoniveladora-670g": ["Potencia: 195 HP", "Vertedera: 3.66 m", "Peso operativo: 17,300 kg"],
    "retroexcavadora-310-sl-310-l": ["Potencia: 93 HP", "Prof. excavación: 4.3 m", "Peso operativo: 7,600 kg"],
    "minicargadores-320-324g": ["Potencia: 65 HP", "Carga nominal: 900 kg", "Peso operativo: 3,400 kg"],
    "tractor-de-orugas-850j-ii": ["Potencia: 160 HP", "Peso operativo: 16,300 kg", "Hoja: 3.25 m"],
    "tractor-de-orugas-850j": ["Potencia: 160 HP", "Peso operativo: 16,300 kg", "Hoja: 3.25 m"],
    "rodillo-3411": ["Peso operativo: 11,000 kg", "Tambor: 2.13 m", "Vibración: 1.8 mm"],
    "rodillo-3412-ht": ["Peso operativo: 12,000 kg", "Tambor: 2.13 m", "Fuerza: 257 kN"],
    "rodillo-3520-ht": ["Peso operativo: 20,000 kg", "Tambor: 2.13 m", "Fuerza: 360 kN"],
    "rodillo-compactador-3520-ht": ["Peso operativo: 20,000 kg", "Tambor: 2.13 m", "Fuerza: 360 kN"],
    "rodillo-tandem-hd-12-vv": ["Peso operativo: 2,700 kg", "Tambor: 1.20 m", "Tándem vibratorio"],
    "torres-de-iluminacion": ["Potencia: 9 kW", "Altura mástil: 9 m", "4 reflectores LED"],
    "tableros-de-barras": ["Tipo: Aditamento", "Compatible: Minicargador", "Acero reforzado"],
    "tanques-de-combustible": ["Capacidad: 1,000 Gal", "Material: Acero", "Bomba de transferencia"],
    "martillos-hidraulicos-excavadora": ["Compatible: Excavadoras 20-35 Ton", "Tipo: Hidráulico", "400-700 BPM"],
    "martillos-hidraulicos-minicargador": ["Compatible: Minicargadores", "Tipo: Hidráulico", "500-900 BPM"],
    "martillos-hidraulicos-retroexcavadora": ["Compatible: Retroexcavadoras", "Tipo: Hidráulico", "400-700 BPM"],
    "pulverizador": ["Tanque: 2,000 L", "Ancho aplicación: 14 m", "Autopropulsado"],
    "atomizador-citrus-torre-2000": ["Tanque: 2,000 L", "Torre de aplicación", "Tipo: Citrus"],
    "tractor-agricola-3036en": ["Potencia: 36 HP", "Tracción: 4WD", "Transmisión: 8F/4R"],
    "tractor-agricola-5076ef": ["Potencia: 76 HP", "Tracción: 4WD", "Transmisión: 12F/12R"],
    "tractor-agricola-5090en": ["Potencia: 90 HP", "Tracción: 4WD", "Transmisión: 12F/12R"],
    "tractores-5090en": ["Potencia: 90 HP", "Tracción: 4WD", "Transmisión: 12F/12R"],
    "tractor-agricola-6110d": ["Potencia: 110 HP", "Tracción: 4WD", "Transmisión: PowrQuad"],
    "tractor-agricola-6125e": ["Potencia: 125 HP", "Tracción: 4WD", "Transmisión: PowrQuad"],
    "tractor-agricola-6403": ["Potencia: 105 HP", "Tracción: 4WD", "Especializado"],
    "tractor-agricola-6603": ["Potencia: 120 HP", "Tracción: 4WD", "Especializado"],
    "tractor-agricola-7230j": ["Potencia: 230 HP", "Tracción: 4WD", "Transmisión: IVT"],
    "tractor-agricola-serie-6j": ["Potencia: 130 HP", "Tracción: 4WD", "PowrQuad Plus"],
    "generador-aksa-ak55cust": ["Potencia: 55 kVA", "Motor: Cummins", "220/380V"],
    "generador-aksa-ak85cust": ["Potencia: 85 kVA", "Motor: Cummins", "220/380V"],
    "generador-aksa-ak100cust": ["Potencia: 100 kVA", "Motor: Cummins", "220/380V"],
    "generador-aksa-ak120cust": ["Potencia: 120 kVA", "Motor: Cummins", "220/380V"],
    "generador-aksa-ak160cust": ["Potencia: 160 kVA", "Motor: Cummins", "220/380V"],
    "generador-aksa-ak220cust": ["Potencia: 220 kVA", "Motor: Cummins", "220/380V"],
    "generador-aksa-ak360cust": ["Potencia: 360 kVA", "Motor: Cummins", "220/380V"],
    "generador-aksa-ak450cust": ["Potencia: 450 kVA", "Motor: Cummins", "220/380V"],
    "generador-aksa-ak505volst": ["Potencia: 505 kVA", "Motor: Volvo", "220/380V"],
    "generador-tk90pels": ["Potencia: 90 kVA", "Motor: Perkins", "220/380V"],
    "generador-tk120pels": ["Potencia: 120 kVA", "Motor: Perkins", "220/380V"],
    "generador-tk225pels": ["Potencia: 225 kVA", "Motor: Perkins", "220/380V"],
    "generador-tk360pels": ["Potencia: 360 kVA", "Motor: Perkins", "220/380V"],
    "generador-tk470pels": ["Potencia: 470 kVA", "Motor: Perkins", "220/380V"],
    "generador-tk550pels": ["Potencia: 550 kVA", "Motor: Perkins", "220/380V"],
}

updated = 0
for p in products:
    slug = p["slug"]
    if slug in SPECS:
        p["descripcion"] = SPECS[slug]
        updated += 1
    else:
        # Try removing CIP suffix
        base = re.sub(r"-cip.*$", "", slug)
        if base in SPECS:
            p["descripcion"] = SPECS[base]
            updated += 1
        else:
            # Try prefix match
            for key in sorted(SPECS.keys(), key=len, reverse=True):
                if slug.startswith(key):
                    p["descripcion"] = SPECS[key]
                    updated += 1
                    break

print(f"Updated {updated}/{len(products)} products with specs")
without = [p["slug"] for p in products if "descripcion" not in p]
if without:
    print(f"Without specs ({len(without)}): {without}")

with open(os.path.join(BASE, "products.json"), "w", encoding="utf-8") as f:
    json.dump(products, f, ensure_ascii=False, indent=2)

print("[OK] products.json updated")
