#!/usr/bin/env python3
"""
Extrae todas las imágenes base64 embebidas en las páginas HTML estáticas,
las guarda como archivos WebP y reemplaza el base64 con la ruta del archivo.

Maneja:
  - src="data:image/...;base64,..."
  - srcset="data:image/...;base64,... Xw, ..."  (múltiples)

Resultado: páginas de 30 MB quedan en 1-3 MB.
"""
import os
import re
import base64
import hashlib
from pathlib import Path
from io import BytesIO
from PIL import Image

BASE_DIR = Path(__file__).parent.parent
PAGES_DIR = BASE_DIR / "static" / "pages"
ASSETS_DIR = BASE_DIR / "static" / "pages-assets"

# Páginas a procesar (las más pesadas primero)
PAGES = [
    "leasing_operativo.html",
    "index.html",
    "nosotros.html",
    "novedades.html",
    "novedades_page2.html",
    "contacto.html",
    "inicio.html",
    "carrito2.html",
    "carrito.html",
]

# SVG pequeños (<2 KB) los dejamos inline (son iconos)
SVG_INLINE_THRESHOLD = 2048
# Imágenes pequeñas (<500 bytes) también las dejamos inline
MIN_SIZE_TO_EXTRACT = 500


def decode_b64(b64_str: str) -> bytes:
    # Limpiar whitespace
    b64_str = b64_str.strip().replace(" ", "").replace("\n", "")
    # Padding
    pad = len(b64_str) % 4
    if pad:
        b64_str += "=" * (4 - pad)
    return base64.b64decode(b64_str)


def save_as_webp(raw: bytes, img_type: str, dest_dir: Path, name_hint: str) -> Path | None:
    """Convierte bytes de imagen a WebP y guarda. Devuelve la ruta del archivo."""
    try:
        if img_type == "svg+xml":
            # SVG → guardar como .svg si es grande, si no dejar inline
            if len(raw) < SVG_INLINE_THRESHOLD:
                return None
            dest = dest_dir / f"{name_hint}.svg"
            dest.write_bytes(raw)
            return dest

        with Image.open(BytesIO(raw)) as img:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGBA")
            elif img.mode != "RGB":
                img = img.convert("RGB")

            dest = dest_dir / f"{name_hint}.webp"
            save_kwargs = {"quality": 82, "method": 6}
            img.save(dest, "WEBP", **save_kwargs)
            return dest
    except Exception as e:
        print(f"    WARN: no se pudo convertir {name_hint}: {e}")
        return None


def extract_page(page_file: Path):
    """Procesa una página HTML extrayendo todas las imágenes base64."""
    page_name = page_file.stem
    assets_dir = ASSETS_DIR / page_name
    assets_dir.mkdir(parents=True, exist_ok=True)

    content = page_file.read_text(encoding="utf-8", errors="replace")
    original_size = len(content.encode("utf-8"))

    # Cache: hash → ruta guardada (evitar guardar la misma imagen 2 veces)
    hash_cache: dict[str, str] = {}
    counter = [0]
    replaced = [0]
    saved_bytes = [0]

    def get_asset_path(img_type: str, b64_data: str) -> str | None:
        """Devuelve la URL relativa del asset extraído, o None si se deja inline."""
        raw_bytes = decode_b64(b64_data)
        if len(raw_bytes) < MIN_SIZE_TO_EXTRACT:
            return None  # dejar inline
        if img_type == "svg+xml" and len(raw_bytes) < SVG_INLINE_THRESHOLD:
            return None  # SVG pequeño → inline

        h = hashlib.md5(raw_bytes).hexdigest()[:12]
        if h in hash_cache:
            return hash_cache[h]

        counter[0] += 1
        name_hint = f"img_{counter[0]:03d}_{h}"
        dest_path = save_as_webp(raw_bytes, img_type, assets_dir, name_hint)
        if dest_path is None:
            return None

        # URL relativa desde /static/pages-assets/<page>/
        url = f"/static/pages-assets/{page_name}/{dest_path.name}"
        hash_cache[h] = url
        saved_bytes[0] += len(raw_bytes) - dest_path.stat().st_size
        replaced[0] += 1
        return url

    # ── Paso 1: Reemplazar src="data:image/...;base64,..." ──
    def replace_src(m):
        img_type = m.group(1)
        b64_data = m.group(2)
        url = get_asset_path(img_type, b64_data)
        if url is None:
            return m.group(0)
        return f'src="{url}"'

    content = re.sub(
        r'src="data:image/([^;]+);base64,([A-Za-z0-9+/=\s]+?)"',
        replace_src,
        content
    )

    # ── Paso 2: Reemplazar srcset con base64 ──
    # srcset puede tener: "data:image/webp;base64,XXXXX 300w, data:image/jpeg;base64,YYYY 600w"
    def replace_srcset(m):
        srcset_val = m.group(1)
        # Procesar cada entrada del srcset
        def replace_srcset_entry(em):
            img_type = em.group(1)
            b64_data = em.group(2)
            descriptor = em.group(3) or ""
            url = get_asset_path(img_type, b64_data)
            if url is None:
                return em.group(0)
            return f"{url}{descriptor}"

        new_srcset = re.sub(
            r'data:image/([^;]+);base64,([A-Za-z0-9+/=\s]+?)(\s+\d+[wx])?(?=\s*,|\s*")',
            replace_srcset_entry,
            srcset_val
        )
        return f'srcset="{new_srcset}"'

    content = re.sub(
        r'srcset="([^"]*data:image[^"]*)"',
        replace_srcset,
        content
    )

    # ── Paso 3: Reemplazar background en style inline ──
    def replace_bg(m):
        img_type = m.group(1)
        b64_data = m.group(2)
        url = get_asset_path(img_type, b64_data)
        if url is None:
            return m.group(0)
        return f"url('{url}')"

    # Sin comillas
    content = re.sub(
        r"url\(data:image/([^;]+);base64,([A-Za-z0-9+/=\s]+?)\)",
        replace_bg,
        content
    )
    # Con comillas dobles: url("data:...")
    def replace_bg_dq(m):
        img_type = m.group(1)
        b64_data = m.group(2)
        url = get_asset_path(img_type, b64_data)
        if url is None:
            return m.group(0)
        return f"url('{url}')"

    content = re.sub(
        r'url\("data:image/([^;]+);base64,([A-Za-z0-9+/=\s]+?)"\)',
        replace_bg_dq,
        content
    )
    # Con comillas simples: url('data:...')
    content = re.sub(
        r"url\('data:image/([^;]+);base64,([A-Za-z0-9+/=\s]+?)'\)",
        replace_bg,
        content
    )

    # Guardar
    page_file.write_text(content, encoding="utf-8")
    final_size = len(content.encode("utf-8"))

    reduction = (1 - final_size / original_size) * 100 if original_size > 0 else 0
    print(f"\n{page_file.name}:")
    print(f"  {original_size//1024//1024} MB -> {final_size//1024//1024} MB  (-{reduction:.0f}%)")
    print(f"  {replaced[0]} imagenes extraidas, ~{saved_bytes[0]//1024//1024} MB ahorrados")
    print(f"  Assets en: static/pages-assets/{page_name}/  ({counter[0]} archivos)")


def main():
    print("Extrayendo imagenes base64 de paginas HTML...")
    print("=" * 60)

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    total_before = 0
    total_after = 0

    for page_name in PAGES:
        page_file = PAGES_DIR / page_name
        if not page_file.exists():
            print(f"  SKIP (no existe): {page_name}")
            continue
        before = page_file.stat().st_size
        extract_page(page_file)
        after = page_file.stat().st_size
        total_before += before
        total_after += after

    print("\n" + "=" * 60)
    print(f"TOTAL antes:  {total_before//1024//1024} MB")
    print(f"TOTAL despues:{total_after//1024//1024} MB")
    if total_before > 0:
        print(f"Ahorro HTML:  {(total_before-total_after)//1024//1024} MB  ({(1-total_after/total_before)*100:.0f}%)")

    # Tamaño de los assets generados
    if ASSETS_DIR.exists():
        asset_size = sum(f.stat().st_size for f in ASSETS_DIR.rglob("*") if f.is_file())
        print(f"Assets WebP:  {asset_size//1024//1024} MB (cacheados por el browser)")

    print("\nDone.")


if __name__ == "__main__":
    main()
