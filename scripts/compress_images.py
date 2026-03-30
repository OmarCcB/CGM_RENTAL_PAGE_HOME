#!/usr/bin/env python3
"""
Convierte todas las imágenes de static/images/ a WebP y actualiza products.json.
- Mantiene los originales (no los borra)
- Actualiza el campo "imagen" en products.json si apuntaba a jpg/png
- Calcula el ahorro total
"""
import os
import json
from pathlib import Path
from PIL import Image

BASE_DIR = Path(__file__).parent.parent
IMAGES_DIR = BASE_DIR / "static" / "images"
PRODUCTS_FILE = BASE_DIR / "products.json"

QUALITY = 82          # 80-85 es el punto óptimo calidad/peso para WebP
MAX_WIDTH = 1200      # máximo ancho para fotos de producto
BANNER_MAX_WIDTH = 1600

EXTS = {".jpg", ".jpeg", ".png"}

def convert_to_webp(src: Path, quality: int, max_width: int) -> tuple[int, int]:
    """Convierte una imagen a WebP. Devuelve (bytes_antes, bytes_despues)."""
    dest = src.with_suffix(".webp")
    if dest.exists():
        # Ya convertida, reportar tamaños
        return src.stat().st_size, dest.stat().st_size

    try:
        with Image.open(src) as img:
            # Convertir RGBA/P a RGB si es necesario (PNG con transparencia)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGBA")
            elif img.mode != "RGB":
                img = img.convert("RGB")

            # Redimensionar si es demasiado grande
            if img.width > max_width:
                ratio = max_width / img.width
                new_h = int(img.height * ratio)
                img = img.resize((max_width, new_h), Image.LANCZOS)

            save_kwargs = {"quality": quality, "method": 6}
            if img.mode == "RGBA":
                save_kwargs["lossless"] = False
            img.save(dest, "WEBP", **save_kwargs)

        return src.stat().st_size, dest.stat().st_size
    except Exception as e:
        print(f"  ERROR {src.name}: {e}")
        return 0, 0


def main():
    total_before = 0
    total_after = 0
    converted = 0
    skipped = 0

    all_images = []
    for root, dirs, files in os.walk(IMAGES_DIR):
        for fname in files:
            fpath = Path(root) / fname
            if fpath.suffix.lower() in EXTS:
                all_images.append(fpath)

    print(f"Imágenes encontradas: {len(all_images)}")
    print("-" * 50)

    for img_path in sorted(all_images):
        is_banner = "banners" in img_path.parts
        max_w = BANNER_MAX_WIDTH if is_banner else MAX_WIDTH
        before, after = convert_to_webp(img_path, QUALITY, max_w)
        if after > 0:
            saving_pct = (1 - after / before) * 100 if before > 0 else 0
            status = "ya existía" if (img_path.with_suffix(".webp").stat().st_mtime
                                       < img_path.stat().st_mtime + 1
                                       and img_path.with_suffix(".webp").exists()
                                       and before == img_path.stat().st_size) else "convertida"
            print(f"  {img_path.relative_to(BASE_DIR)}  {before//1024}KB -> {after//1024}KB  (-{saving_pct:.0f}%)")
            total_before += before
            total_after += after
            converted += 1
        else:
            skipped += 1

    print("-" * 50)
    print(f"Total convertidas: {converted}  |  Errores: {skipped}")
    if total_before > 0:
        print(f"Peso antes:  {total_before/1024/1024:.1f} MB")
        print(f"Peso después:{total_after/1024/1024:.1f} MB")
        print(f"Ahorro:      {(total_before-total_after)/1024/1024:.1f} MB  ({(1-total_after/total_before)*100:.0f}%)")

    # Actualizar products.json: cambiar .jpg/.png → .webp en campo "imagen"
    print("\nActualizando products.json...")
    with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
        products = json.load(f)

    updated = 0
    for p in products:
        img = p.get("imagen", "")
        # Solo actualizar si apunta a static/images/ (no wp-content ni externas)
        if img and any(img.endswith(ext) for ext in [".jpg", ".jpeg", ".png"]):
            if img.startswith("/imagenes/") or img.startswith("/images/"):
                # Verificar que existe el .webp correspondiente
                rel = img.lstrip("/").replace("imagenes/", "images/", 1)
                webp_path = BASE_DIR / "static" / rel
                webp_path = webp_path.with_suffix(".webp")
                if webp_path.exists():
                    # Reconstruir URL con .webp
                    base, _ = img.rsplit(".", 1)
                    p["imagen"] = base + ".webp"
                    updated += 1

    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

    print(f"  {updated} productos actualizados en products.json")
    print("\nDone.")


if __name__ == "__main__":
    main()
