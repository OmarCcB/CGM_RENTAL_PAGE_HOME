"""
cache.py — Caché en memoria con TTL para datos que raramente cambian.

Evita queries repetidas a SQLite en cada request para datos que raramente cambian:
  - get_banners()  → cachea {slot: filename} por país
  - get_country()  → cachea config del país (site_config + sucursales)

La invalidación es EXPLÍCITA: el admin llama invalidate() justo después
de guardar cambios → el siguiente request lee los datos frescos de la BD.
No hay riesgo de datos viejos: cualquier cambio del admin limpia el caché
en ese mismo momento.
"""

import time
import threading

# TTL en segundos. Con 60s, si por alguna razón la invalidación manual
# falla (bug, restart parcial), los datos se refrescan solos al minuto.
_TTL = 60

_lock = threading.Lock()
_store: dict = {}  # {"banners:pe": (timestamp, data), "country:ar": (ts, data), ...}


def get(key):
    """Devuelve (True, value) si hay un hit válido, (False, None) si miss/expirado."""
    with _lock:
        entry = _store.get(key)
        if entry and (time.time() - entry[0]) < _TTL:
            return True, entry[1]
    return False, None


def set(key, value):
    """Guarda value en el caché bajo key."""
    with _lock:
        _store[key] = (time.time(), value)


def invalidate(*prefixes):
    """Elimina todas las entradas cuya clave empiece con alguno de los prefijos.

    Ejemplos:
        invalidate("banners:")  → borra "banners:pe", "banners:ar", "banners:*"
        invalidate("country:")  → borra "country:pe", "country:ar"
        invalidate("banners:", "country:")  → borra ambos grupos
    """
    with _lock:
        to_del = [k for k in _store if any(k.startswith(p) for p in prefixes)]
        for k in to_del:
            del _store[k]


def clear():
    """Limpia todo el caché (reset completo)."""
    with _lock:
        _store.clear()
