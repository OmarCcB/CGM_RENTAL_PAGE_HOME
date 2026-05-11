"""
Sincronización de products.json con la base de datos.

CONTEXTO
--------
`app.py` ejecuta `seed_db()` al iniciar el servidor, que lee `products.json`
e inserta en la BD con `INSERT OR IGNORE`. Esto significa:
  - Si un producto fue ELIMINADO desde el admin, vuelve a aparecer al reiniciar.
  - Si un producto fue EDITADO desde el admin y la fila desaparece (por
    cualquier motivo), volvería con la versión vieja del JSON.

Para evitarlo, cada acción del admin (crear/editar/eliminar/toggle) debe
mantener `products.json` sincronizado con el estado real de la BD.

ESTRATEGIA
----------
- La BD es la fuente de verdad.
- `products.json` se actualiza después de cada cambio del admin.
- La identificación se hace por `slug` (UNIQUE en la BD).
- Las escrituras al JSON son atómicas (temp file + rename) para evitar
  corrupción si el proceso muere a mitad de escritura.
"""

import json
import os
import tempfile

# Campos que se persisten en products.json (los que lee seed_db en app.py)
JSON_FIELDS = (
    "id", "slug", "nombre", "marca", "descripcion", "descripcion_texto",
    "ficha_url", "tags", "tipo", "unidad", "imagen", "activo", "show_pe", "show_arg",
)


def _json_path():
    """Path absoluto de products.json (en la raíz del proyecto)."""
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "products.json",
    )


def _load():
    """Carga products.json o devuelve [] si no existe."""
    path = _json_path()
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_atomic(products):
    """Escribe products.json de forma atómica (temp + rename)."""
    path = _json_path()
    dir_ = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(prefix=".products_", suffix=".json.tmp", dir=dir_)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(products, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _row_to_dict(row_or_dict):
    """Convierte sqlite3.Row o dict al formato esperado en products.json."""
    if hasattr(row_or_dict, "keys"):
        d = {k: row_or_dict[k] for k in row_or_dict.keys()}
    else:
        d = dict(row_or_dict)
    # Filtrar solo a los campos esperados
    return {k: d.get(k) for k in JSON_FIELDS if k in d}


# ── API pública ─────────────────────────────────────────────────────────────
def sync_upsert(product):
    """Inserta o actualiza un producto en products.json identificado por slug.

    `product` puede ser un sqlite3.Row o un dict con al menos `slug`.
    """
    p_dict = _row_to_dict(product)
    slug = p_dict.get("slug")
    if not slug:
        return False

    products = _load()
    found = False
    for i, existing in enumerate(products):
        if existing.get("slug") == slug:
            # Conservar campos extra que no estén en JSON_FIELDS (como descripcion_texto antiguo)
            merged = dict(existing)
            merged.update({k: v for k, v in p_dict.items() if v is not None})
            products[i] = merged
            found = True
            break
    if not found:
        products.append(p_dict)

    _save_atomic(products)
    return True


def sync_delete(slug):
    """Elimina un producto de products.json identificado por slug."""
    if not slug:
        return False
    products = _load()
    new_products = [p for p in products if p.get("slug") != slug]
    if len(new_products) != len(products):
        _save_atomic(new_products)
        return True
    return False


def sync_set_field(slug, field, value):
    """Actualiza un solo campo (e.g. activo=1) en products.json."""
    if not slug or field not in JSON_FIELDS:
        return False
    products = _load()
    changed = False
    for p in products:
        if p.get("slug") == slug:
            p[field] = value
            changed = True
            break
    if changed:
        _save_atomic(products)
    return changed


def sync_full_rebuild_from_db(conn):
    """Reconstruye products.json a partir del estado actual de la BD.

    Útil como recuperación si el JSON queda desincronizado.
    """
    rows = conn.execute("SELECT * FROM products ORDER BY id").fetchall()
    products = [_row_to_dict(r) for r in rows]
    _save_atomic(products)
    return len(products)

