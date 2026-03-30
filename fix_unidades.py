import json, sys
sys.stdout.reconfigure(encoding="utf-8")

with open("products.json", "r", encoding="utf-8") as f:
    products = json.load(f)

changes = 0
for p in products:
    n = p.get("nombre", "")
    # Excavadoras de mineria -> Mediana Mineria
    if any(x in n for x in ["870G", "ZX1200", "ZX870LC-5"]) and p.get("tags") == "alquiler":
        if p.get("unidad") != "Mediana Minería":
            print(f"FIX {n}: unidad '{p['unidad']}' -> 'Mediana Minería'")
            p["unidad"] = "Mediana Minería"
            changes += 1

    # Atomizadores usados -> sin sub-categoria (unidad vacia o general)
    # En la oficial aparecen solo en USADOS general, no en USADOS>Agricola
    if "ATOMIZADOR" in n and p.get("tags") == "usados":
        if p.get("unidad") != "":
            print(f"FIX {n}: unidad '{p['unidad']}' -> '' (solo USADOS general)")
            p["unidad"] = ""
            changes += 1

with open("products.json", "w", encoding="utf-8") as f:
    json.dump(products, f, ensure_ascii=False, indent=2)

print(f"\n{changes} cambios guardados")
