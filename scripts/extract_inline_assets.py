#!/usr/bin/env python3
"""
Extrae bloques CSS y JS inline repetidos en todas las páginas HTML
y los reemplaza con <link> / <script src=""> externos cacheables.

Por qué importa:
  - CSS/JS inline NO puede ser cacheado por el browser
  - Con archivos externos, el browser los descarga UNA VEZ y los cachea 1 año
  - 1.67 MB de CSS + 1.62 MB de JS compartidos en 9 páginas = 8+ MB redundantes eliminados

Resultado esperado:
  - index.html:    7 MB  →  ~1.5 MB
  - Resto de pages: 5 MB →  ~1.5 MB
  - Segunda visita: páginas pesan ~200 KB (solo HTML)
"""
import re
import hashlib
from pathlib import Path
from collections import Counter

BASE_DIR = Path(__file__).parent.parent
PAGES_DIR = BASE_DIR / "static" / "pages"
SHARED_DIR = BASE_DIR / "static" / "shared"

# Todas las páginas a procesar (incluyendo templates)
PAGES = [p for p in PAGES_DIR.glob("*.html")]
TEMPLATES = [
    BASE_DIR / "templates" / "categoria.html",
    BASE_DIR / "templates" / "producto.html",
]

# Un bloque debe aparecer en al menos este número de archivos para ser extraído
MIN_APPEARANCES = 2


def get_tagged_blocks(filepath: Path, tag: str) -> list[tuple[str, str]]:
    """Devuelve lista de (full_match, inner_content) para cada bloque <tag>."""
    content = filepath.read_text(encoding="utf-8", errors="replace")
    pattern = rf'(<{tag}[^>]*>)(.*?)(</{tag}>)'
    return [(m.group(0), m.group(2)) for m in re.finditer(pattern, content, re.DOTALL)]


def find_shared_blocks(all_files: list[Path], tag: str, min_appearances: int) -> dict[str, str]:
    """
    Devuelve dict {hash: content} de bloques que aparecen en >= min_appearances archivos.
    Solo considera el bloque si tiene contenido sustancial (>500 chars).
    """
    hash_to_content: dict[str, str] = {}
    file_hashes: list[set[str]] = []

    for filepath in all_files:
        blocks = get_tagged_blocks(filepath, tag)
        file_set = set()
        for full, inner in blocks:
            if len(inner.strip()) < 500:
                continue
            h = hashlib.md5(inner.encode()).hexdigest()
            hash_to_content[h] = inner
            file_set.add(h)
        file_hashes.append(file_set)

    # Contar en cuántos archivos aparece cada bloque
    counter = Counter(h for file_set in file_hashes for h in file_set)
    return {h: hash_to_content[h] for h, count in counter.items() if count >= min_appearances}


def replace_shared_in_file(filepath: Path, shared_css: dict, shared_js: dict,
                            css_url: str, js_url: str):
    """Reemplaza bloques compartidos con referencias externas."""
    content = filepath.read_text(encoding="utf-8", errors="replace")
    original_size = len(content.encode("utf-8"))

    css_injected = False
    js_injected = False

    def replace_style(m):
        nonlocal css_injected
        inner = m.group(2)
        h = hashlib.md5(inner.encode()).hexdigest()
        if h in shared_css:
            if not css_injected:
                css_injected = True
                return f'<link rel="stylesheet" href="{css_url}">'
            else:
                return ""  # Eliminar duplicados
        return m.group(0)

    def replace_script(m):
        nonlocal js_injected
        attrs = m.group(1)
        inner = m.group(2)
        # No tocar scripts con src externo
        if "src=" in attrs:
            return m.group(0)
        h = hashlib.md5(inner.encode()).hexdigest()
        if h in shared_js:
            if not js_injected:
                js_injected = True
                return f'<script src="{js_url}"></script>'
            else:
                return ""  # Eliminar duplicados
        return m.group(0)

    content = re.sub(
        r'(<style[^>]*>)(.*?)(</style>)',
        replace_style,
        content,
        flags=re.DOTALL
    )
    content = re.sub(
        r'(<script([^>]*)>)(.*?)(</script>)',
        lambda m: replace_script(
            type('M', (), {
                'group': lambda self, n: [m.group(0), m.group(1), m.group(3), ''][n]
            })()
        ),
        content,
        flags=re.DOTALL
    )

    # Reescribir con función corregida
    content_orig = filepath.read_text(encoding="utf-8", errors="replace")
    css_done = False
    js_done = False

    def rep_style2(m):
        nonlocal css_done
        inner = m.group(2)
        h = hashlib.md5(inner.encode()).hexdigest()
        if h in shared_css:
            if not css_done:
                css_done = True
                return f'<link rel="stylesheet" href="{css_url}">'
            return ""
        return m.group(0)

    def rep_script2(m):
        nonlocal js_done
        full_open = m.group(1)
        inner = m.group(2)
        close = m.group(3)
        if 'src=' in full_open:
            return m.group(0)
        h = hashlib.md5(inner.encode()).hexdigest()
        if h in shared_js:
            if not js_done:
                js_done = True
                return f'<script src="{js_url}"></script>'
            return ""
        return m.group(0)

    content = re.sub(r'(<style[^>]*>)(.*?)(</style>)', rep_style2, content_orig, flags=re.DOTALL)
    content = re.sub(r'(<script[^>]*>)(.*?)(</script>)', rep_script2, content, flags=re.DOTALL)

    filepath.write_text(content, encoding="utf-8")
    final_size = len(content.encode("utf-8"))
    reduction = (1 - final_size / original_size) * 100 if original_size else 0
    print(f"  {filepath.name}: {original_size//1024} KB -> {final_size//1024} KB  (-{reduction:.0f}%)")


def main():
    SHARED_DIR.mkdir(parents=True, exist_ok=True)

    all_files = PAGES + TEMPLATES
    all_files = [f for f in all_files if f.exists()]

    print(f"Analizando {len(all_files)} archivos...")

    # ── Encontrar bloques compartidos ──
    print("\nBuscando CSS compartido...")
    shared_css = find_shared_blocks(all_files, "style", MIN_APPEARANCES)
    total_css_kb = sum(len(v) for v in shared_css.values()) // 1024
    print(f"  {len(shared_css)} bloques unicos, {total_css_kb} KB total")

    print("Buscando JS compartido...")
    shared_js = find_shared_blocks(all_files, "script", MIN_APPEARANCES)
    total_js_kb = sum(len(v) for v in shared_js.values()) // 1024
    print(f"  {len(shared_js)} bloques unicos, {total_js_kb} KB total")

    if not shared_css and not shared_js:
        print("No se encontraron bloques compartidos.")
        return

    # ── Escribir archivos externos ──
    css_path = SHARED_DIR / "divi.css"
    js_path = SHARED_DIR / "divi.js"

    if shared_css:
        # Ordenar por longitud desc para que el CSS más grande quede primero
        css_content = "\n".join(v for v in sorted(shared_css.values(), key=len, reverse=True))
        css_path.write_text(css_content, encoding="utf-8")
        print(f"\nEscrito: {css_path.relative_to(BASE_DIR)} ({css_path.stat().st_size//1024} KB)")

    if shared_js:
        js_content = "\n".join(v for v in sorted(shared_js.values(), key=len, reverse=True))
        js_path.write_text(js_content, encoding="utf-8")
        print(f"Escrito: {js_path.relative_to(BASE_DIR)} ({js_path.stat().st_size//1024} KB)")

    css_url = "/static/shared/divi.css"
    js_url = "/static/shared/divi.js"

    # ── Reemplazar en todos los archivos ──
    print("\nReemplazando en archivos:")
    for filepath in all_files:
        replace_shared_in_file(filepath, shared_css, shared_js, css_url, js_url)

    print("\n=== RESUMEN ===")
    print(f"CSS externo: {css_path.stat().st_size//1024} KB (se cachea 1 ano en el browser)")
    print(f"JS externo:  {js_path.stat().st_size//1024} KB (se cachea 1 ano en el browser)")
    print("Segunda visita: el browser usa cache, descarga 0 KB de CSS/JS")


if __name__ == "__main__":
    main()
