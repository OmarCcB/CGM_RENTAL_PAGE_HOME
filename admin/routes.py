"""
Admin panel routes for CGM Rental.
Blueprint: 'admin', url_prefix='/admin'
"""
import os
import re
import json
import shutil
from datetime import datetime

from flask import (
    Blueprint, render_template, redirect, url_for, request,
    session, jsonify, flash, current_app,
)
from werkzeug.utils import secure_filename

from database import get_conn, upsert_site_config
import cache as _cache
from admin.auth import admin_required, get_auth_url, get_token_from_code, get_user_info, azure_configured
from admin.products_sync import sync_upsert, sync_delete, sync_set_field, sync_full_rebuild_from_db

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# ── Allowed upload types ──────────────────────────────────────────────────────
ALLOWED_IMAGE_EXT = {"webp", "jpg", "jpeg", "png"}
ALLOWED_PDF_EXT = {"pdf"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


def _allowed(filename, allowed_exts):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_exts


def _slugify(text):
    """Convert text to URL-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[àáâãäå]", "a", text)
    text = re.sub(r"[èéêë]", "e", text)
    text = re.sub(r"[ìíîï]", "i", text)
    text = re.sub(r"[òóôõö]", "o", text)
    text = re.sub(r"[ùúûü]", "u", text)
    text = re.sub(r"[ñ]", "n", text)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text


def _slug_en_uso(conn, candidate, excluir_pid=None):
    """Devuelve la fila (id, nombre) del producto que ya usa ese slug, o None si está libre."""
    query = "SELECT id, nombre FROM products WHERE slug=?"
    params = [candidate]
    if excluir_pid is not None:
        query += " AND id != ?"
        params.append(excluir_pid)
    return conn.execute(query, params).fetchone()


# ── Audit helper ──────────────────────────────────────────────────────────────
def log_action(usuario, accion, detalle=""):
    conn = get_conn()
    conn.execute(
        "INSERT INTO audit_log (usuario, accion, detalle) VALUES (?, ?, ?)",
        (usuario, accion, detalle),
    )
    conn.commit()
    conn.close()


def current_user():
    return session.get("admin_user", {})


# ── Auth routes ───────────────────────────────────────────────────────────────
@admin_bp.route("/")
def index():
    if session.get("admin_user"):
        return redirect(url_for("admin.dashboard"))
    return redirect(url_for("admin.login"))


@admin_bp.route("/login")
def login():
    auth_url = get_auth_url()
    configured = azure_configured()
    return render_template("admin/login.html", auth_url=auth_url, configured=configured)


@admin_bp.route("/auth/callback")
def auth_callback():
    code = request.args.get("code")
    error = request.args.get("error")
    if error or not code:
        flash(f"Error de autenticación: {error or 'sin código'}", "danger")
        return redirect(url_for("admin.login"))
    token = get_token_from_code(code)
    if not token:
        flash("No se pudo obtener el token. Verifica la configuración de Azure AD.", "danger")
        return redirect(url_for("admin.login"))
    user = get_user_info(token)
    if not user:
        flash("No se pudo obtener la información del usuario.", "danger")
        return redirect(url_for("admin.login"))

    allowed_raw = os.getenv("ADMIN_ALLOWED_EMAILS", "")
    allowed = {e.strip().lower() for e in allowed_raw.split(",") if e.strip()}
    user_email = (user.get("email") or "").strip().lower()
    if allowed and user_email not in allowed:
        log_action(user_email or "?", "login_denegado",
                   f"Email no autorizado intentó ingresar: {user_email}")
        flash("Tu correo no tiene permisos para acceder al panel.", "danger")
        return redirect(url_for("admin.login"))

    # A01 — Prevención de session fixation: regenerar sesión tras login
    session.clear()
    session["admin_user"] = user
    session.permanent = True
    log_action(user.get("email", "?"), "login", "Inicio de sesión exitoso")
    flash(f"Bienvenido, {user['name']}", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/logout")
def logout():
    user = current_user()
    if user:
        log_action(user.get("email", "?"), "logout", "Sesión cerrada")
    session.pop("admin_user", None)
    flash("Sesión cerrada.", "info")
    return redirect(url_for("admin.login"))


# ── Dashboard ─────────────────────────────────────────────────────────────────
@admin_bp.route("/dashboard")
@admin_required
def dashboard():
    conn = get_conn()

    # ── KPIs Equipos ──────────────────────────────────────────────────────────
    total     = conn.execute("SELECT COUNT(*) as c FROM products").fetchone()["c"]
    activos   = conn.execute("SELECT COUNT(*) as c FROM products WHERE activo=1").fetchone()["c"]
    inactivos = total - activos
    con_imagen = conn.execute("SELECT COUNT(*) as c FROM products WHERE imagen IS NOT NULL AND imagen != ''").fetchone()["c"]
    activos_sin_imagen = conn.execute("SELECT COUNT(*) as c FROM products WHERE activo=1 AND (imagen IS NULL OR imagen = '')").fetchone()["c"]

    # ── KPIs Blog ─────────────────────────────────────────────────────────────
    total_posts  = conn.execute("SELECT COUNT(*) as c FROM blog_posts").fetchone()["c"]
    posts_activos = conn.execute("SELECT COUNT(*) as c FROM blog_posts WHERE activo=1").fetchone()["c"]

    # ── KPIs Sucursales ───────────────────────────────────────────────────────
    suc_pe = conn.execute("SELECT COUNT(*) as c FROM sucursales_db WHERE country_code='pe'").fetchone()["c"]
    suc_ar = conn.execute("SELECT COUNT(*) as c FROM sucursales_db WHERE country_code='ar'").fetchone()["c"]

    # ── Equipos por sector ────────────────────────────────────────────────────
    sector_rows = conn.execute(
        "SELECT unidad, COUNT(*) as c FROM products WHERE activo=1 GROUP BY unidad ORDER BY c DESC"
    ).fetchall()
    sector_labels = [r["unidad"] or "Sin sector" for r in sector_rows]
    sector_data   = [r["c"] for r in sector_rows]
    sector_inactive = []
    for label in sector_labels:
        n = conn.execute(
            "SELECT COUNT(*) as c FROM products WHERE activo=0 AND unidad=?", (label,)
        ).fetchone()["c"]
        sector_inactive.append(n)

    # ── Equipos por país ──────────────────────────────────────────────────────
    pe_count = conn.execute("SELECT COUNT(*) as c FROM products WHERE activo=1 AND show_pe=1").fetchone()["c"]
    ar_count = conn.execute("SELECT COUNT(*) as c FROM products WHERE activo=1 AND show_arg=1").fetchone()["c"]

    # ── Equipos por tipo (tags) ───────────────────────────────────────────────
    alquiler_c = conn.execute("SELECT COUNT(*) as c FROM products WHERE activo=1 AND tags LIKE '%alquiler%' AND tags NOT LIKE '%venta%' AND tags NOT LIKE '%usados%'").fetchone()["c"]
    venta_c    = conn.execute("SELECT COUNT(*) as c FROM products WHERE activo=1 AND (tags LIKE '%venta%' OR tags LIKE '%usados%') AND tags NOT LIKE '%alquiler%'").fetchone()["c"]

    # ── Blog por categoría ────────────────────────────────────────────────────
    blog_cat = conn.execute(
        "SELECT categoria, COUNT(*) as c FROM blog_posts WHERE activo=1 GROUP BY categoria"
    ).fetchall()
    blog_cat_labels = [(r["categoria"] or "sin categoría").capitalize() for r in blog_cat]
    blog_cat_data   = [r["c"] for r in blog_cat]

    # ── Blog posts por mes (últimos 6 meses) ──────────────────────────────────
    posts_mes = conn.execute(
        """SELECT substr(fecha, 1, 7) AS mes, COUNT(*) AS c
           FROM blog_posts WHERE activo=1 AND fecha IS NOT NULL AND fecha != ''
           GROUP BY substr(fecha, 1, 7) ORDER BY mes DESC LIMIT 6"""
    ).fetchall()
    posts_mes_labels = [r["mes"] for r in reversed(posts_mes)]
    posts_mes_data   = [r["c"] for r in reversed(posts_mes)]

    # ── Actividad reciente ────────────────────────────────────────────────────
    audit_rows = conn.execute(
        "SELECT * FROM audit_log ORDER BY id DESC LIMIT 12"
    ).fetchall()
    conn.close()

    return render_template(
        "admin/dashboard.html",
        user=current_user(),
        # equipos
        total=total, activos=activos, inactivos=inactivos, con_imagen=con_imagen, activos_sin_imagen=activos_sin_imagen,
        # blog
        total_posts=total_posts, posts_activos=posts_activos,
        # sucursales
        suc_pe=suc_pe, suc_ar=suc_ar,
        # charts equipos
        sector_labels=json.dumps(sector_labels),
        sector_data=json.dumps(sector_data),
        sector_inactive=json.dumps(sector_inactive),
        pe_count=pe_count, ar_count=ar_count,
        alquiler_c=alquiler_c, venta_c=venta_c,
        # charts blog
        blog_cat_labels=json.dumps(blog_cat_labels),
        blog_cat_data=json.dumps(blog_cat_data),
        posts_mes_labels=json.dumps(posts_mes_labels),
        posts_mes_data=json.dumps(posts_mes_data),
        # log
        audit_rows=audit_rows,
    )


@admin_bp.route("/dashboard/data")
@admin_required
def dashboard_data():
    """Devuelve métricas del dashboard filtradas por país (all / pe / ar)."""
    country = request.args.get("country", "all")
    conn = get_conn()

    # ── Cláusula de filtro por país ───────────────────────────────────────
    if country == "pe":
        pf = " AND show_pe=1"
        bf = " AND show_pe=1"
    elif country == "ar":
        pf = " AND show_arg=1"
        bf = " AND show_arg=1"
    else:
        pf = ""
        bf = ""

    # ── KPIs Equipos ──────────────────────────────────────────────────────
    total     = conn.execute(f"SELECT COUNT(*) as c FROM products WHERE 1=1{pf}").fetchone()["c"]
    activos   = conn.execute(f"SELECT COUNT(*) as c FROM products WHERE activo=1{pf}").fetchone()["c"]
    inactivos = total - activos
    con_imagen = conn.execute(f"SELECT COUNT(*) as c FROM products WHERE imagen IS NOT NULL AND imagen != ''{pf}").fetchone()["c"]
    activos_sin_imagen = conn.execute(f"SELECT COUNT(*) as c FROM products WHERE activo=1 AND (imagen IS NULL OR imagen = ''){pf}").fetchone()["c"]

    # ── KPIs Blog ─────────────────────────────────────────────────────────
    total_posts   = conn.execute(f"SELECT COUNT(*) as c FROM blog_posts WHERE 1=1{bf}").fetchone()["c"]
    posts_activos = conn.execute(f"SELECT COUNT(*) as c FROM blog_posts WHERE activo=1{bf}").fetchone()["c"]

    # ── Sucursales ────────────────────────────────────────────────────────
    suc_pe = conn.execute("SELECT COUNT(*) as c FROM sucursales_db WHERE country_code='pe'").fetchone()["c"]
    suc_ar = conn.execute("SELECT COUNT(*) as c FROM sucursales_db WHERE country_code='ar'").fetchone()["c"]
    if country == "pe":
        suc_show = suc_pe
    elif country == "ar":
        suc_show = suc_ar
    else:
        suc_show = suc_pe + suc_ar

    # ── Equipos por sector ────────────────────────────────────────────────
    sector_rows = conn.execute(
        f"SELECT unidad, COUNT(*) as c FROM products WHERE activo=1{pf} GROUP BY unidad ORDER BY c DESC"
    ).fetchall()
    sector_labels   = [r["unidad"] or "Sin sector" for r in sector_rows]
    sector_active   = [r["c"] for r in sector_rows]
    sector_inactive = []
    for label in sector_labels:
        n = conn.execute(
            f"SELECT COUNT(*) as c FROM products WHERE activo=0 AND unidad=?{pf}", (label,)
        ).fetchone()["c"]
        sector_inactive.append(n)

    # ── País distribution (solo para "all") ───────────────────────────────
    pe_count = conn.execute("SELECT COUNT(*) as c FROM products WHERE activo=1 AND show_pe=1").fetchone()["c"]
    ar_count = conn.execute("SELECT COUNT(*) as c FROM products WHERE activo=1 AND show_arg=1").fetchone()["c"]

    # ── Tipo de operación ─────────────────────────────────────────────────
    alquiler_c = conn.execute(f"SELECT COUNT(*) as c FROM products WHERE activo=1 AND tags LIKE '%alquiler%' AND tags NOT LIKE '%venta%' AND tags NOT LIKE '%usados%'{pf}").fetchone()["c"]
    venta_c    = conn.execute(f"SELECT COUNT(*) as c FROM products WHERE activo=1 AND (tags LIKE '%venta%' OR tags LIKE '%usados%') AND tags NOT LIKE '%alquiler%'{pf}").fetchone()["c"]

    # ── Blog por categoría ────────────────────────────────────────────────
    blog_cat = conn.execute(
        f"SELECT categoria, COUNT(*) as c FROM blog_posts WHERE activo=1{bf} GROUP BY categoria"
    ).fetchall()

    # ── Blog por mes (últimos 6) ──────────────────────────────────────────
    posts_mes = conn.execute(
        f"""SELECT substr(fecha, 1, 7) AS mes, COUNT(*) AS c
            FROM blog_posts WHERE activo=1 AND fecha IS NOT NULL AND fecha != ''{bf}
            GROUP BY substr(fecha, 1, 7) ORDER BY mes DESC LIMIT 6"""
    ).fetchall()
    conn.close()

    return jsonify({
        # KPIs
        "total": total, "activos": activos, "inactivos": inactivos, "con_imagen": con_imagen, "activos_sin_imagen": activos_sin_imagen,
        "total_posts": total_posts, "posts_activos": posts_activos,
        "suc_pe": suc_pe, "suc_ar": suc_ar, "suc_show": suc_show,
        # charts equipos
        "sector_labels": sector_labels,
        "sector_active": sector_active,
        "sector_inactive": sector_inactive,
        "pe_count": pe_count, "ar_count": ar_count,
        "alquiler_c": alquiler_c, "venta_c": venta_c,
        # charts blog
        "blog_cat_labels": [(r["categoria"] or "sin categoría").capitalize() for r in blog_cat],
        "blog_cat_data":   [r["c"] for r in blog_cat],
        "posts_mes_labels": [r["mes"] for r in reversed(posts_mes)],
        "posts_mes_data":   [r["c"] for r in reversed(posts_mes)],
    })


# ── Productos ─────────────────────────────────────────────────────────────────
PER_PAGE = 20


@admin_bp.route("/productos")
@admin_required
def productos():
    q = request.args.get("q", "").strip()
    pais = request.args.get("pais", "")
    sector = request.args.get("sector", "")
    estado = request.args.get("estado", "")
    page = max(1, int(request.args.get("page", 1)))

    conn = get_conn()
    clauses = []
    params = []

    if q:
        clauses.append("(nombre LIKE ? OR marca LIKE ? OR slug LIKE ?)")
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]
    if pais == "pe":
        clauses.append("show_pe=1")
    elif pais == "ar":
        clauses.append("show_arg=1")
    if sector:
        clauses.append("unidad=?")
        params.append(sector)
    if estado == "activo":
        clauses.append("activo=1")
    elif estado == "inactivo":
        clauses.append("activo=0")

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    total = conn.execute(f"SELECT COUNT(*) as c FROM products {where}", params).fetchone()["c"]
    offset = (page - 1) * PER_PAGE
    rows = conn.execute(
        f"SELECT * FROM products {where} ORDER BY id DESC LIMIT ? OFFSET ?",
        params + [PER_PAGE, offset],
    ).fetchall()

    sectores = [r["unidad"] for r in conn.execute(
        "SELECT DISTINCT unidad FROM products WHERE unidad IS NOT NULL ORDER BY unidad"
    ).fetchall()]
    conn.close()

    # El template ya antepone /static/products/ al campo imagen.
    # La BD almacena el valor correcto (ej. "excavadora-hidraulica-210glc/1.webp"),
    # así que solo convertimos cada row a dict sin tocar el campo imagen.
    productos_list = [dict(r) for r in rows]

    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    return render_template(
        "admin/productos.html",
        user=current_user(),
        productos=productos_list,
        q=q,
        pais=pais,
        sector=sector,
        estado=estado,
        page=page,
        total_pages=total_pages,
        total=total,
        sectores=sectores,
    )


@admin_bp.route("/productos/nuevo", methods=["GET", "POST"])
@admin_required
def producto_nuevo():
    if request.method == "POST":
        return _save_producto(None)
    return render_template("admin/producto_form.html", user=current_user(), producto=None, modo="nuevo")


def _listar_imagenes_producto(slug, producto=None):
    """Devuelve lista ordenada de imágenes del producto: [{filename, url}, ...].
    Si el producto tiene imagenes_orden en BD, respeta ese orden.
    Fallback: orden natural (numérico o alfabético)."""
    if not slug:
        return []
    folder = os.path.join(current_app.root_path, "static", "products", slug)
    if not os.path.isdir(folder):
        return []
    files = [
        f for f in os.listdir(folder)
        if f.lower().endswith((".webp", ".jpg", ".jpeg", ".png"))
    ]
    # Intentar respetar imagenes_orden de la BD
    orden = []
    if producto:
        raw = producto["imagenes_orden"] if producto["imagenes_orden"] else None
        if raw:
            try:
                orden = json.loads(raw)
            except Exception:
                orden = []
    if orden:
        files_set = set(files)
        ordered   = [f for f in orden if f in files_set]
        remaining = sorted([f for f in files if f not in set(orden)])
        files = ordered + remaining
    else:
        def _sort_key(name):
            base = os.path.splitext(name)[0]
            try:
                return (0, int(base))
            except ValueError:
                return (1, base.lower())
        files.sort(key=_sort_key)
    return [
        {"filename": f, "url": f"/static/products/{slug}/{f}"}
        for f in files
    ]


@admin_bp.route("/productos/<int:pid>/editar", methods=["GET", "POST"])
@admin_required
def producto_editar(pid):
    conn = get_conn()
    producto = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    conn.close()
    if not producto:
        flash("Producto no encontrado.", "danger")
        return redirect(url_for("admin.productos"))
    if request.method == "POST":
        return _save_producto(pid)
    imagenes = _listar_imagenes_producto(producto["slug"], producto)
    return render_template(
        "admin/producto_form.html",
        user=current_user(),
        producto=producto,
        modo="editar",
        imagenes=imagenes,
    )


def _save_producto(pid):
    f = request.form
    nombre = f.get("nombre", "").strip()
    slug = f.get("slug", "").strip() or _slugify(nombre)
    marca = f.get("marca", "").strip()
    descripcion = f.get("descripcion", "").strip()
    descripcion_texto = f.get("descripcion_texto", "").strip()
    sector = f.get("sector", "").strip()
    tipo = f.get("tipo", "").strip()
    unidad = f.get("unidad", "").strip()
    activo = 1 if f.get("activo") else 0
    show_pe  = 1 if f.get("show_pe")  else 0
    show_arg = 1 if f.get("show_arg") else 0
    a_solicitud = 1 if f.get("a_solicitud") else 0
    ficha_url = f.get("ficha_url", "").strip() or None
    tags_list = f.getlist("tags")
    tags = ",".join(tags_list)

    if not nombre:
        flash("El nombre es obligatorio.", "danger")
        return redirect(request.referrer or url_for("admin.productos"))

    if not show_pe and not show_arg:
        flash("Advertencia: el producto no tiene ningún país seleccionado y no será visible en ningún sitio.", "warning")

    conn = get_conn()

    # Si el slug generado ya lo usa OTRO producto (típico cuando dos equipos
    # comparten el mismo nombre base y solo se diferencian por el código CIP),
    # no bloqueamos: se resuelve solo agregando un sufijo único al slug.
    conflicto = _slug_en_uso(conn, slug, excluir_pid=pid)

    if pid is None:
        # Producto nuevo: todavía no existe un ID para desambiguar, así que si
        # hay choque se inserta primero con un slug temporal único, y apenas
        # SQLite asigna el ID real se renombra a "slug-ID".
        insert_slug = slug if not conflicto else f"{slug}-{os.urandom(4).hex()}"
        conn.execute(
            """INSERT INTO products
               (slug, nombre, marca, descripcion, descripcion_texto, tags, tipo, unidad, activo, show_pe, show_arg, a_solicitud, ficha_url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (insert_slug, nombre, marca, descripcion, descripcion_texto, tags, tipo, unidad, activo, show_pe, show_arg, a_solicitud, ficha_url),
        )
        conn.commit()
        pid = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        if conflicto:
            slug = f"{slug}-{pid}"
            conn.execute("UPDATE products SET slug=? WHERE id=?", (slug, pid))
            conn.commit()
            flash(
                f"Nota: el nombre ya lo usaba el producto \"{conflicto['nombre']}\" "
                f"(ID {conflicto['id']}), así que a este se le asignó el slug "
                f"\"{slug}\" para diferenciarlos.",
                "warning",
            )
        # Releer la fila completa para sincronizar con el JSON
        new_row = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        conn.close()
        # Sincronizar products.json para que no se reseteé al reiniciar
        try:
            sync_upsert(new_row)
        except Exception as e:
            current_app.logger.warning(f"sync_upsert (crear) fallo: {e}")
        log_action(current_user().get("email", "?"), "crear_producto", f"ID={pid} nombre={nombre}")
        flash("Producto creado exitosamente.", "success")
    else:
        if conflicto:
            slug_alterno = f"{slug}-{pid}"
            if _slug_en_uso(conn, slug_alterno, excluir_pid=pid):
                # Caso extremadamente raro: hasta el slug con sufijo de ID choca.
                conn.close()
                flash(
                    f"No se pudo guardar: el nombre ya lo usa el producto "
                    f"\"{conflicto['nombre']}\" (ID {conflicto['id']}) y no fue posible "
                    f"generar un slug único automáticamente. Edita el campo Slug manualmente.",
                    "danger",
                )
                return redirect(url_for("admin.producto_editar", pid=pid))
            slug = slug_alterno
            flash(
                f"Nota: el nombre ya lo usaba el producto \"{conflicto['nombre']}\" "
                f"(ID {conflicto['id']}), así que se le asignó el slug "
                f"\"{slug}\" a este para diferenciarlos.",
                "warning",
            )

        # Leer slug ANTERIOR antes de actualizar
        old_row = conn.execute("SELECT slug, imagen, ficha_url FROM products WHERE id=?", (pid,)).fetchone()
        old_slug = old_row["slug"] if old_row else None
        old_imagen = old_row["imagen"] if old_row else None

        # Si el slug cambió, renombrar carpeta de imágenes y actualizar campo imagen
        nueva_imagen = old_imagen
        if old_slug and old_slug != slug:
            products_dir = os.path.join(current_app.root_path, "static", "products")
            old_folder = os.path.join(products_dir, old_slug)
            new_folder = os.path.join(products_dir, slug)
            if os.path.isdir(old_folder) and not os.path.exists(new_folder):
                shutil.move(old_folder, new_folder)
                current_app.logger.info(f"Carpeta renombrada: {old_slug}/ -> {slug}/")
            # Actualizar campo imagen reemplazando el prefijo del slug viejo
            if old_imagen and old_imagen.startswith(old_slug + "/"):
                nueva_imagen = slug + "/" + old_imagen[len(old_slug) + 1:]

        ficha_url_final = ficha_url if ficha_url else (old_row["ficha_url"] if old_row else None)
        conn.execute(
            """UPDATE products SET slug=?, nombre=?, marca=?, descripcion=?, descripcion_texto=?,
               tags=?, tipo=?, unidad=?, activo=?, show_pe=?, show_arg=?, a_solicitud=?, imagen=?, ficha_url=? WHERE id=?""",
            (slug, nombre, marca, descripcion, descripcion_texto, tags, tipo, unidad, activo, show_pe, show_arg, a_solicitud, nueva_imagen, ficha_url_final, pid),
        )
        conn.commit()
        updated_row = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        conn.close()
        try:
            # Si el slug cambió, eliminar la entrada vieja del JSON antes de insertar la nueva
            if old_slug and old_slug != slug:
                sync_delete(old_slug)
            sync_upsert(updated_row)
        except Exception as e:
            current_app.logger.warning(f"sync_upsert (editar) fallo: {e}")
        log_action(current_user().get("email", "?"), "editar_producto", f"ID={pid} nombre={nombre} slug={slug}")
        flash("Producto actualizado.", "success")
    return redirect(url_for("admin.producto_editar", pid=pid))


@admin_bp.route("/productos/<int:pid>/toggle", methods=["POST"])
@admin_required
def producto_toggle(pid):
    conn = get_conn()
    producto = conn.execute("SELECT slug, activo FROM products WHERE id=?", (pid,)).fetchone()
    if not producto:
        conn.close()
        return jsonify({"ok": False, "error": "no encontrado"}), 404
    nuevo = 0 if producto["activo"] else 1
    slug_prod = producto["slug"]
    conn.execute("UPDATE products SET activo=? WHERE id=?", (nuevo, pid))
    conn.commit()
    conn.close()
    # Sincronizar el campo activo en products.json
    try:
        sync_set_field(slug_prod, "activo", nuevo)
    except Exception as e:
        current_app.logger.warning(f"sync_set_field (toggle) fallo: {e}")
    log_action(current_user().get("email", "?"), "toggle_producto", f"ID={pid} activo={nuevo}")
    return jsonify({"ok": True, "activo": nuevo})


@admin_bp.route("/productos/sync-json", methods=["POST"])
@admin_required
def productos_sync_json():
    """Reconstruye products.json a partir del estado actual de la BD.

    Útil si el JSON se desincroniza (por ediciones manuales, scripts auxiliares,
    o cambios hechos en producción que no pasaron por el admin).
    """
    conn = get_conn()
    try:
        n = sync_full_rebuild_from_db(conn)
        log_action(current_user().get("email", "?"), "rebuild_products_json", f"{n} productos")
        flash(f"products.json reconstruido con {n} productos desde la base de datos.", "success")
    except Exception as e:
        flash(f"Error al reconstruir products.json: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for("admin.productos"))


@admin_bp.route("/productos/<int:pid>/imagen/eliminar", methods=["POST"])
@admin_required
def producto_imagen_eliminar(pid):
    """Borra una imagen del folder static/products/<slug>/."""
    conn = get_conn()
    producto = conn.execute("SELECT slug FROM products WHERE id=?", (pid,)).fetchone()
    conn.close()
    if not producto:
        flash("Producto no encontrado.", "danger")
        return redirect(url_for("admin.productos"))
    slug = producto["slug"]
    filename = secure_filename(request.form.get("filename", ""))
    if not filename:
        flash("Sin nombre de archivo.", "warning")
        return redirect(url_for("admin.producto_editar", pid=pid))
    folder = os.path.join(current_app.root_path, "static", "products", slug)
    full = os.path.join(folder, filename)
    if os.path.isfile(full):
        os.remove(full)
        conn2 = get_conn()
        prod_row = conn2.execute("SELECT imagen, imagenes_orden FROM products WHERE id=?", (pid,)).fetchone()
        if prod_row:
            # Actualizar imagenes_orden: quitar el archivo eliminado
            raw_orden = prod_row["imagenes_orden"] if prod_row["imagenes_orden"] else "[]"
            try:
                orden = json.loads(raw_orden)
            except Exception:
                orden = []
            orden = [f for f in orden if f != filename]
            # Determinar nueva imagen principal
            if prod_row["imagen"] == f"{slug}/{filename}":
                nueva_imagen = f"{slug}/{orden[0]}" if orden else None
            else:
                nueva_imagen = prod_row["imagen"]
            conn2.execute(
                "UPDATE products SET imagen=?, imagenes_orden=? WHERE id=?",
                (nueva_imagen, json.dumps(orden), pid)
            )
            conn2.commit()
            updated_row = conn2.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
            conn2.close()
            try:
                sync_upsert(updated_row)
            except Exception as e:
                current_app.logger.warning(f"sync_upsert (eliminar imagen) fallo: {e}")
        else:
            conn2.close()
        log_action(current_user().get("email", "?"), "eliminar_imagen_producto",
                   f"ID={pid} slug={slug} file={filename}")
        flash(f"Imagen '{filename}' eliminada.", "success")
    else:
        flash("Imagen no encontrada.", "warning")
    return redirect(url_for("admin.producto_editar", pid=pid))


@admin_bp.route("/productos/<int:pid>/imagenes/reordenar", methods=["POST"])
@admin_required
def producto_imagenes_reordenar(pid):
    """Guarda el nuevo orden de imágenes en imagenes_orden y actualiza imagen principal."""
    data  = request.get_json(silent=True) or {}
    orden = data.get("orden", [])
    if not isinstance(orden, list):
        return jsonify({"ok": False, "error": "orden debe ser lista"}), 400
    conn = get_conn()
    prod = conn.execute("SELECT slug FROM products WHERE id=?", (pid,)).fetchone()
    if not prod:
        conn.close()
        return jsonify({"ok": False, "error": "Producto no encontrado"}), 404
    slug = prod["slug"]
    conn.execute("UPDATE products SET imagenes_orden=? WHERE id=?", (json.dumps(orden), pid))
    if orden:
        conn.execute("UPDATE products SET imagen=? WHERE id=?", (f"{slug}/{orden[0]}", pid))
    conn.commit()
    try:
        updated_row = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        sync_upsert(updated_row)
    except Exception as e:
        current_app.logger.warning(f"sync_upsert (reordenar) fallo: {e}")
    conn.close()
    log_action(current_user().get("email", "?"), "reordenar_imagenes", f"ID={pid} slug={slug}")
    return jsonify({"ok": True})


@admin_bp.route("/productos/<int:pid>/eliminar", methods=["POST"])
@admin_required
def producto_eliminar(pid):
    conn = get_conn()
    producto = conn.execute("SELECT nombre, slug FROM products WHERE id=?", (pid,)).fetchone()
    nombre_prod = producto["nombre"] if producto else None
    slug_prod = producto["slug"] if producto else None
    if producto:
        conn.execute("DELETE FROM products WHERE id=?", (pid,))
        conn.commit()
    conn.close()
    # Sincronizar: eliminar también de products.json para que seed_db no lo recree
    if slug_prod:
        try:
            sync_delete(slug_prod)
        except Exception as e:
            current_app.logger.warning(f"sync_delete fallo: {e}")
    if nombre_prod:
        log_action(current_user().get("email", "?"), "eliminar_producto", f"ID={pid} nombre={nombre_prod}")
        flash(f"Producto '{nombre_prod}' eliminado.", "success")
    return redirect(url_for("admin.productos"))


# ── Upload de archivos ────────────────────────────────────────────────────────
@admin_bp.route("/upload", methods=["POST"])
@admin_required
def upload():
    f = request.files.get("file")
    slug = request.form.get("slug", "general")
    dest_type = request.form.get("type", "product")  # 'product' or 'banner'

    if not f or not f.filename:
        return jsonify({"ok": False, "error": "Sin archivo"}), 400

    filename = secure_filename(f.filename)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if dest_type == "banner":
        if ext not in ALLOWED_IMAGE_EXT:
            return jsonify({"ok": False, "error": "Tipo no permitido"}), 400
        dest_dir = os.path.join(current_app.root_path, "static", "images", "banners")
    elif ext in ALLOWED_PDF_EXT:
        dest_dir = os.path.join(current_app.root_path, "static", "products", slug)
    elif ext in ALLOWED_IMAGE_EXT:
        dest_dir = os.path.join(current_app.root_path, "static", "products", slug)
    else:
        return jsonify({"ok": False, "error": "Tipo no permitido (webp/jpg/jpeg/png/pdf)"}), 400

    # Check size
    f.seek(0, 2)
    size = f.tell()
    f.seek(0)
    if size > MAX_UPLOAD_BYTES:
        return jsonify({"ok": False, "error": "Archivo mayor a 10 MB"}), 400

    os.makedirs(dest_dir, exist_ok=True)

    # Para imágenes de PRODUCTO: convertir a webp conservando el nombre original.
    is_product_image = (dest_type != "banner") and (ext in ALLOWED_IMAGE_EXT)
    if is_product_image:
        # Construir nombre: stem original + .webp (sin números forzados)
        stem = os.path.splitext(secure_filename(f.filename))[0].lower().replace(" ", "-")
        new_filename = f"{stem}.webp"
        # Evitar sobreescribir si ya existe: agregar sufijo -2, -3, ...
        counter = 2
        while os.path.exists(os.path.join(dest_dir, new_filename)):
            new_filename = f"{stem}-{counter}.webp"
            counter += 1
        save_path = os.path.join(dest_dir, new_filename)

        if ext == "webp":
            f.save(save_path)
        else:
            # Convertir a webp con Pillow
            tmp_path = os.path.join(dest_dir, f"_tmp_upload.{ext}")
            f.save(tmp_path)
            try:
                from PIL import Image
                with Image.open(tmp_path) as img:
                    if img.mode in ("RGBA", "LA", "P"):
                        img.save(save_path, "WEBP", quality=88, lossless=False)
                    else:
                        img.convert("RGB").save(save_path, "WEBP", quality=88)
            except Exception as e:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                return jsonify({"ok": False, "error": f"No se pudo convertir a webp: {e}"}), 500
            finally:
                if os.path.isfile(tmp_path):
                    os.remove(tmp_path)
        filename = new_filename
    else:
        save_path = os.path.join(dest_dir, filename)
        f.save(save_path)

    # ── Para banners: convertir a WebP + generar versión mobile (800px) ──────
    if dest_type == "banner":
        try:
            from PIL import Image as _PILImage
            import os as _os
            stem_b, ext_b = _os.path.splitext(save_path)
            # Convertir a WebP si no lo es ya
            if ext.lower() != "webp":
                webp_path = stem_b + ".webp"
                with _PILImage.open(save_path) as _img:
                    _img.convert("RGB").save(webp_path, "WEBP", quality=80)
                _os.remove(save_path)
                save_path = webp_path
                filename = _os.path.basename(webp_path)
            # Generar _mobile.webp (800px ancho)
            mobile_path = stem_b + "_mobile.webp"
            with _PILImage.open(save_path) as _img:
                _w, _h = _img.size
                _mh = int(1200 * _h / _w) if _w > 1200 else _h
                _mw = min(_w, 1200)
                _mob = _img.resize((_mw, _mh), _PILImage.LANCZOS)
                _mob.convert("RGB").save(mobile_path, "WEBP", quality=78)
        except Exception as _e:
            current_app.logger.warning(f"banner mobile generation failed: {_e}")

    if dest_type == "banner":
        url = f"/static/images/banners/{filename}"
    else:
        url = f"/static/products/{slug}/{filename}"
        # Si es PDF de producto, actualizar ficha_url en BD + JSON automáticamente
        if ext in ALLOWED_PDF_EXT:
            try:
                conn = get_conn()
                producto = conn.execute("SELECT * FROM products WHERE slug=?", (slug,)).fetchone()
                if producto:
                    conn.execute("UPDATE products SET ficha_url=? WHERE slug=?", (url, slug))
                    conn.commit()
                    updated_row = conn.execute("SELECT * FROM products WHERE slug=?", (slug,)).fetchone()
                    conn.close()
                    try:
                        sync_upsert(updated_row)
                    except Exception as e:
                        current_app.logger.warning(f"sync_upsert (pdf upload) fallo: {e}")
                else:
                    conn.close()
            except Exception as e:
                current_app.logger.warning(f"update ficha_url en upload fallo: {e}")
        # Si es imagen de producto: actualizar imagenes_orden e imagen principal en BD
        if is_product_image:
            try:
                conn = get_conn()
                producto = conn.execute("SELECT * FROM products WHERE slug=?", (slug,)).fetchone()
                if producto:
                    # Actualizar imagenes_orden: agregar al final
                    raw_orden = producto["imagenes_orden"] if producto["imagenes_orden"] else "[]"
                    try:
                        orden = json.loads(raw_orden)
                    except Exception:
                        orden = []
                    if filename not in orden:
                        orden.append(filename)
                    # Si no tiene imagen principal, asignar esta
                    nueva_imagen = producto["imagen"] or f"{slug}/{orden[0]}"
                    conn.execute(
                        "UPDATE products SET imagenes_orden=?, imagen=? WHERE slug=?",
                        (json.dumps(orden), nueva_imagen, slug)
                    )
                    conn.commit()
                    updated_row = conn.execute("SELECT * FROM products WHERE slug=?", (slug,)).fetchone()
                    conn.close()
                    try:
                        sync_upsert(updated_row)
                    except Exception as e:
                        current_app.logger.warning(f"sync_upsert (imagen upload) fallo: {e}")
                else:
                    conn.close()
            except Exception as e:
                current_app.logger.warning(f"update imagenes_orden en upload fallo: {e}")

    log_action(current_user().get("email", "?"), "subir_archivo", f"{url}")
    return jsonify({"ok": True, "url": url, "filename": filename})


# ── Banners ───────────────────────────────────────────────────────────────────
def _convert_to_webp_in_place(src_path):
    """Convierte un archivo de imagen a .webp en su misma carpeta y borra el original.
    Devuelve el path final (.webp). Si ya es .webp lo deja igual."""
    from PIL import Image
    base, ext = os.path.splitext(src_path)
    ext = ext.lower()
    if ext == ".webp":
        return src_path
    dst = base + ".webp"
    with Image.open(src_path) as img:
        if img.mode in ("RGBA", "LA", "P"):
            img.save(dst, "WEBP", quality=88, lossless=False)
        else:
            img.convert("RGB").save(dst, "WEBP", quality=88)
    if src_path != dst:
        try:
            os.remove(src_path)
        except OSError:
            pass
    return dst


def _get_registered_filenames_db(conn):
    """Devuelve set de filenames registrados en banners_config."""
    rows = conn.execute("SELECT filename FROM banners_config").fetchall()
    return {r["filename"] for r in rows}


def _make_country_filename(global_filename, country_code):
    """Deriva el filename para una versión país a partir del filename global.
    Ejemplo: 'home-cards/construccion.webp' + 'pe' → 'home-cards/pe/construccion.webp'
    """
    parts = global_filename.rsplit("/", 1)
    if len(parts) == 2:
        return f"{parts[0]}/{country_code}/{parts[1]}"
    return f"{country_code}/{global_filename}"


# Tamaños recomendados por tipo de banner. Se derivan del filename.
# Cada entrada: (prefijo, "ancho × alto px (descripción del formato)")
_BANNER_SIZE_RULES = (
    ("hero/",                          "1920 × 730 px",   "panorámica ~2.6:1"),
    ("categorias/",                    "1600 × 600 px",   "panorámica 8:3"),
    ("home-cards/leasing-operativo",   "1400 × 580 px",   "rectangular 8:3"),
    ("home-cards/",                    "800 × 700 px",    "casi cuadrada 1.15:1"),
    ("otros/contacto-banner",          "1920 × 730 px",   "panorámica ~2.6:1"),
    ("otros/contacto-lateral",         "1100 × 800 px",   "rectangular 1.4:1"),
    ("otros/carrito",                  "1400 × 580 px",   "rectangular 8:3"),
    ("otros/portal-bg",                "1100 × 800 px",   "rectangular 1.4:1"),
)


def _recommended_size_for(filename):
    """Devuelve dict {size, ratio_label} con la dimensión recomendada para ese banner."""
    for prefix, size, ratio in _BANNER_SIZE_RULES:
        if filename.startswith(prefix):
            return {"size": size, "ratio": ratio}
    return {"size": "—", "ratio": ""}


def _get_banners_by_slot(conn, banners_dir):
    """Devuelve ({group_name: [slot_data]}, group_order).
    Cada slot_data agrupa todas las variantes de país del mismo slot.
    """
    import json as _json
    rows = conn.execute(
        "SELECT * FROM banners_config ORDER BY group_name, slot, country_code"
    ).fetchall()

    groups = {}      # group_name → {slot → slot_data}
    group_order = []

    for r in rows:
        r = dict(r)
        g, s, cc = r["group_name"], r["slot"], r["country_code"]
        if g not in groups:
            groups[g] = {}
            group_order.append(g)
        if s not in groups[g]:
            try:
                pages_list = _json.loads(r.get("pages") or "[]")
            except Exception:
                pages_list = []
            rec = _recommended_size_for(r["filename"])
            groups[g][s] = {
                "slot": s, "label": r["label"], "description": r["description"],
                "orden": r["orden"], "pages_list": pages_list, "entries": {},
                "recommended_size": rec["size"], "recommended_ratio": rec["ratio"],
            }
        full = os.path.join(banners_dir, r["filename"].replace("/", os.sep))
        # Dimension real del archivo (si existe), para mostrar al admin
        actual_size = ""
        if os.path.isfile(full):
            try:
                from PIL import Image
                with Image.open(full) as _img:
                    actual_size = f"{_img.size[0]} × {_img.size[1]} px"
            except Exception:
                pass
        groups[g][s]["entries"][cc] = {
            "country_code": cc, "filename": r["filename"], "activo": r["activo"],
            "url": f"/static/images/banners/{r['filename']}",
            "exists": os.path.isfile(full), "actual_size": actual_size,
        }

    result = {}
    for g in group_order:
        result[g] = sorted(groups[g].values(), key=lambda x: (x["orden"], x["slot"]))
    return result, group_order


@admin_bp.route("/banners")
@admin_required
def banners():
    banners_dir = os.path.join(current_app.root_path, "static", "images", "banners")
    os.makedirs(banners_dir, exist_ok=True)

    conn = get_conn()
    grouped, group_order = _get_banners_by_slot(conn, banners_dir)
    registered = _get_registered_filenames_db(conn)
    conn.close()

    # Detectar archivos huérfanos
    huerfanos = []
    for d, _, files in os.walk(banners_dir):
        for f in files:
            rel = os.path.relpath(os.path.join(d, f), banners_dir).replace(os.sep, "/")
            if rel not in registered:
                ext = f.rsplit(".", 1)[-1].lower() if "." in f else ""
                if ext in ALLOWED_IMAGE_EXT:
                    huerfanos.append({"filename": rel, "url": f"/static/images/banners/{rel}"})

    return render_template(
        "admin/banners.html",
        user=current_user(),
        grouped=grouped,
        group_order=group_order,
        huerfanos=huerfanos,
    )


@admin_bp.route("/banners/replace", methods=["POST"])
@admin_required
def banners_replace():
    """Reemplaza el archivo de un banner registrado en banners_config.
    El nombre de archivo (filename) se conserva — nunca cambia.
    Si se sube JPG/PNG se convierte automáticamente a WebP.
    """
    slot         = request.form.get("slot", "").strip()
    country_code = request.form.get("country_code", "*").strip()
    f = request.files.get("file")

    conn = get_conn()
    row = conn.execute(
        "SELECT filename, label FROM banners_config WHERE slot=? AND country_code=?",
        (slot, country_code)
    ).fetchone()
    conn.close()

    if not row:
        flash("Banner no reconocido en la base de datos.", "danger")
        return redirect(url_for("admin.banners"))
    if not f or not f.filename:
        flash("No se eligió ningún archivo.", "danger")
        return redirect(url_for("admin.banners"))

    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in ALLOWED_IMAGE_EXT:
        flash("Solo se permiten imágenes (webp/jpg/jpeg/png).", "danger")
        return redirect(url_for("admin.banners"))

    target        = row["filename"]   # e.g. "hero/pe/slide-1.webp"
    banners_dir   = os.path.join(current_app.root_path, "static", "images", "banners")
    target_path   = os.path.join(banners_dir, target.replace("/", os.sep))
    os.makedirs(os.path.dirname(target_path), exist_ok=True)

    target_base = os.path.splitext(target_path)[0]
    if ext == "webp":
        f.save(target_path)
    else:
        tmp_path = target_base + "." + ext
        f.save(tmp_path)
        try:
            from PIL import Image
            with Image.open(tmp_path) as img:
                if img.mode in ("RGBA", "LA", "P"):
                    img.save(target_path, "WEBP", quality=88, lossless=False)
                else:
                    img.convert("RGB").save(target_path, "WEBP", quality=88)
        finally:
            if os.path.isfile(tmp_path) and tmp_path != target_path:
                os.remove(tmp_path)

    log_action(current_user().get("email", "?"), "reemplazar_banner",
               f"{slot} [{country_code}] → {target}")
    _cache.invalidate("banners:")  # el archivo cambió → forzar recarga en la web
    flash(f"Banner «{row['label']}» actualizado correctamente.", "success")
    return redirect(url_for("admin.banners"))


@admin_bp.route("/banners/country-upload", methods=["POST"])
@admin_required
def banners_country_upload():
    """Crea o reemplaza una versión país-específica de un slot que actualmente es global (*)."""
    slot         = request.form.get("slot", "").strip()
    country_code = request.form.get("country_code", "").strip()   # 'pe' o 'ar'
    f = request.files.get("file")

    if country_code not in ("pe", "ar"):
        flash("País inválido.", "danger")
        return redirect(url_for("admin.banners"))
    if not f or not f.filename:
        flash("No se eligió ningún archivo.", "danger")
        return redirect(url_for("admin.banners"))
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in ALLOWED_IMAGE_EXT:
        flash("Solo se permiten imágenes (webp/jpg/jpeg/png).", "danger")
        return redirect(url_for("admin.banners"))

    conn = get_conn()
    # Obtener la entrada global (*) para heredar metadatos
    global_row = conn.execute(
        "SELECT * FROM banners_config WHERE slot=? AND country_code='*'",
        (slot,)
    ).fetchone()
    # Si ya existe una entrada para este país, la usamos
    existing = conn.execute(
        "SELECT * FROM banners_config WHERE slot=? AND country_code=?",
        (slot, country_code)
    ).fetchone()

    # Fallback: si no hay global ni entrada para este país, usar otra variante
    # del mismo slot (cualquier otro country_code) como template para la metadata.
    # Esto permite subir variantes a slots que NO tienen versión global (caso
    # típico de los slots del carrusel hero creados con cc='pe' o 'ar').
    fallback_row = None
    if not global_row and not existing:
        fallback_row = conn.execute(
            "SELECT * FROM banners_config WHERE slot=? AND country_code != ? "
            "ORDER BY id ASC LIMIT 1",
            (slot, country_code)
        ).fetchone()
        if not fallback_row:
            conn.close()
            flash("Slot no encontrado.", "danger")
            return redirect(url_for("admin.banners"))

    # Determinar el filename de destino
    if existing:
        target = existing["filename"]
        label  = existing["label"]
    elif global_row:
        target = _make_country_filename(global_row["filename"], country_code)
        label  = global_row["label"]
    else:
        # Usar fallback_row: limpiar su prefijo de país y aplicar el del cc actual
        base_fn = fallback_row["filename"]
        old_cc  = fallback_row["country_code"]
        if old_cc not in ("*", "") and f"/{old_cc}/" in base_fn:
            base_fn = base_fn.replace(f"/{old_cc}/", "/", 1)
        target = _make_country_filename(base_fn, country_code)
        label  = fallback_row["label"]

    banners_dir = os.path.join(current_app.root_path, "static", "images", "banners")
    target_path = os.path.join(banners_dir, target.replace("/", os.sep))
    os.makedirs(os.path.dirname(target_path), exist_ok=True)

    target_base = os.path.splitext(target_path)[0]
    if ext == "webp":
        f.save(target_path)
    else:
        tmp_path = target_base + "." + ext
        f.save(tmp_path)
        try:
            from PIL import Image
            with Image.open(tmp_path) as img:
                if img.mode in ("RGBA", "LA", "P"):
                    img.save(target_path, "WEBP", quality=88, lossless=False)
                else:
                    img.convert("RGB").save(target_path, "WEBP", quality=88)
        finally:
            if os.path.isfile(tmp_path) and tmp_path != target_path:
                os.remove(tmp_path)

    if not existing:
        # Crear nueva entrada en BD copiando metadatos del global o del fallback.
        base = dict(global_row or fallback_row)
        conn.execute(
            """INSERT OR IGNORE INTO banners_config
                   (slot, country_code, group_name, label, description, filename, orden, pages, activo)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (slot, country_code, base["group_name"], base["label"],
             base["description"], target, base["orden"], base["pages"]),
        )
    conn.commit()
    conn.close()

    cc_label = "Perú" if country_code == "pe" else "Argentina"
    log_action(current_user().get("email", "?"), "subir_banner_pais",
               f"{slot} [{country_code}] → {target}")
    _cache.invalidate("banners:")  # nuevo banner por país → forzar recarga en la web
    flash(f"Versión específica para {cc_label} del banner «{label}» guardada.", "success")
    return redirect(url_for("admin.banners"))


@admin_bp.route("/banners/country-remove", methods=["POST"])
@admin_required
def banners_country_remove():
    """Elimina la versión país-específica de un slot y vuelve a usar la global."""
    slot         = request.form.get("slot", "").strip()
    country_code = request.form.get("country_code", "").strip()

    if country_code in ("*", ""):
        flash("No se puede eliminar la versión global.", "warning")
        return redirect(url_for("admin.banners"))

    conn = get_conn()
    row = conn.execute(
        "SELECT filename, label FROM banners_config WHERE slot=? AND country_code=?",
        (slot, country_code)
    ).fetchone()
    if not row:
        conn.close()
        flash("Versión país no encontrada.", "danger")
        return redirect(url_for("admin.banners"))

    # Borrar archivo de disco (si existe)
    banners_dir = os.path.join(current_app.root_path, "static", "images", "banners")
    filepath = os.path.join(banners_dir, row["filename"].replace("/", os.sep))
    if os.path.isfile(filepath):
        os.remove(filepath)

    conn.execute("DELETE FROM banners_config WHERE slot=? AND country_code=?",
                 (slot, country_code))
    conn.commit()
    conn.close()

    cc_label = "Perú" if country_code == "pe" else "Argentina"
    log_action(current_user().get("email", "?"), "eliminar_banner_pais",
               f"{slot} [{country_code}]")
    _cache.invalidate("banners:")  # banner eliminado → forzar recarga en la web
    flash(f"Versión para {cc_label} eliminada. Ahora se usa la imagen global.", "success")
    return redirect(url_for("admin.banners"))


@admin_bp.route("/banners/delete-orphan", methods=["POST"])
@admin_required
def banners_delete_orphan():
    """Solo permite borrar archivos huérfanos (que no están en banners_config)."""
    filename = request.form.get("filename", "").strip()
    conn = get_conn()
    registered = _get_registered_filenames_db(conn)
    conn.close()
    if not filename or filename in registered:
        flash("No se puede eliminar un banner registrado (solo reemplazar).", "warning")
        return redirect(url_for("admin.banners"))
    safe = filename.replace("..", "").lstrip("/").replace("\\", "/")
    filepath = os.path.join(current_app.root_path, "static", "images", "banners",
                            safe.replace("/", os.sep))
    if os.path.isfile(filepath):
        os.remove(filepath)
        log_action(current_user().get("email", "?"), "eliminar_banner_huerfano", safe)
        flash(f"Archivo huérfano '{safe}' eliminado.", "success")
    else:
        flash("Archivo no encontrado.", "danger")
    return redirect(url_for("admin.banners"))


# ── Gestión dinámica de slots del carrusel hero ──────────────────────────────
@admin_bp.route("/banners/hero-add", methods=["POST"])
@admin_required
def banners_hero_add():
    """Agrega un nuevo slot al carrusel hero del home. Detecta el siguiente
    número disponible de slide y replica la metadata del primer slot del grupo
    (incluyendo el country_code dominante) para que el slot nuevo se vea
    exactamente igual que los originales en el panel admin."""
    group_name = request.form.get("group_name", "").strip()
    if not group_name:
        flash("Falta el nombre del grupo.", "danger")
        return redirect(url_for("admin.banners"))

    conn = get_conn()

    # Buscar el último número de slide en este grupo
    rows = conn.execute(
        "SELECT slot FROM banners_config "
        "WHERE group_name = ? AND slot LIKE 'hero/slide-%'",
        (group_name,)
    ).fetchall()
    existing_nums = []
    for r in rows:
        num_str = r["slot"].split("-")[-1]
        if num_str.isdigit():
            existing_nums.append(int(num_str))
    next_num = max(existing_nums) + 1 if existing_nums else 1
    new_slot = f"hero/slide-{next_num}"

    # Asegurar que el slot no colisione con otro grupo
    used = {r["slot"] for r in conn.execute(
        "SELECT slot FROM banners_config WHERE slot LIKE 'hero/slide-%'"
    ).fetchall()}
    while new_slot in used:
        next_num += 1
        new_slot = f"hero/slide-{next_num}"

    # Detectar el country_code DOMINANTE del grupo (qué variante usan los otros
    # slots). Excluimos la versión global '*' porque los slots originales NO la
    # tienen — sólo tienen rows por país (pe o ar).
    cc_row = conn.execute(
        "SELECT country_code, COUNT(*) AS n FROM banners_config "
        "WHERE group_name = ? AND country_code != '*' "
        "GROUP BY country_code ORDER BY n DESC LIMIT 1",
        (group_name,)
    ).fetchone()
    primary_cc = cc_row["country_code"] if cc_row else "*"

    # Replicar metadata del primer slot del grupo (pages, etc.)
    template = conn.execute(
        "SELECT pages FROM banners_config "
        "WHERE group_name = ? "
        "ORDER BY orden ASC, id ASC LIMIT 1",
        (group_name,)
    ).fetchone()
    pages = template["pages"] if template else '["home"]'

    # Filename: si hay country_code específico, lo metemos en el path:
    # ej. hero/pe/slide-5.webp ; si es global, hero/slide-5.webp
    if primary_cc != "*":
        new_filename = f"hero/{primary_cc}/slide-{next_num}.webp"
    else:
        new_filename = f"{new_slot}.webp"

    conn.execute(
        """INSERT INTO banners_config
               (slot, country_code, group_name, label, description,
                filename, orden, pages, activo)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
        (new_slot, primary_cc, group_name, f"Slide {next_num}",
         f"Slide {next_num} del carrusel hero de la home",
         new_filename, next_num, pages)
    )
    conn.commit()
    conn.close()

    _cache.invalidate("banners:")
    log_action(current_user().get("email", "?"), "agregar_slot_hero",
               f"{new_slot} [{group_name}] cc={primary_cc}")
    flash(f"Slide {next_num} agregado al carrusel. Ahora podés subir su imagen.",
          "success")
    return redirect(url_for("admin.banners"))


@admin_bp.route("/banners/hero-remove", methods=["POST"])
@admin_required
def banners_hero_remove():
    """Elimina un slot completo del carrusel hero (todas sus variantes de país
    y los archivos asociados del disco)."""
    slot = request.form.get("slot", "").strip()
    if not slot.startswith("hero/slide-"):
        flash("Slot inválido.", "danger")
        return redirect(url_for("admin.banners"))

    conn = get_conn()
    rows = conn.execute(
        "SELECT filename FROM banners_config WHERE slot=?", (slot,)
    ).fetchall()
    if not rows:
        conn.close()
        flash("Slot no encontrado.", "danger")
        return redirect(url_for("admin.banners"))

    # Borrar archivos del disco (todas las variantes país)
    banners_dir = os.path.join(current_app.root_path, "static", "images", "banners")
    for r in rows:
        filepath = os.path.join(banners_dir, r["filename"].replace("/", os.sep))
        if os.path.isfile(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass

    # Eliminar todas las filas del slot
    conn.execute("DELETE FROM banners_config WHERE slot=?", (slot,))
    conn.commit()
    conn.close()

    _cache.invalidate("banners:")
    log_action(current_user().get("email", "?"), "eliminar_slot_hero", slot)
    flash(f"Slot «{slot}» eliminado del carrusel.", "success")
    return redirect(url_for("admin.banners"))


# ── Contacto / site_config ────────────────────────────────────────────────────
keyS = [
    "telefono", "whatsapp_link", "email", "facebook",
    "instagram", "linkedin", "youtube", "direccion", "ciudad_principal",
    "youtube_video",
]


def _extract_youtube_id(value):
    """Extrae el video ID de cualquier formato de URL de YouTube.
    Acepta:
      - https://www.youtube.com/watch?v=XXXX
      - https://youtu.be/XXXX
      - https://www.youtube.com/embed/XXXX
      - Directo: XXXX (solo el ID)
    """
    if not value:
        return value
    value = value.strip()
    # youtube.com/watch?v=ID (con o sin parámetros extra)
    m = re.search(r'[?&]v=([A-Za-z0-9_-]{11})', value)
    if m:
        return m.group(1)
    # youtu.be/ID
    m = re.search(r'youtu\.be/([A-Za-z0-9_-]{11})', value)
    if m:
        return m.group(1)
    # youtube.com/embed/ID
    m = re.search(r'youtube\.com/embed/([A-Za-z0-9_-]{11})', value)
    if m:
        return m.group(1)
    # Si ya es un ID puro (11 caracteres alfanuméricos + guiones)
    if re.fullmatch(r'[A-Za-z0-9_-]{11}', value):
        return value
    # Devolver tal cual si no coincide (el usuario sabrá)
    return value


@admin_bp.route("/contacto", methods=["GET", "POST"])
@admin_required
def contacto():
    conn = get_conn()
    if request.method == "POST":
        pais = request.form.get("pais", "pe")
        for key in keyS:
            value = request.form.get(f"{pais}_{key}", "")
            if key == "youtube_video":
                value = _extract_youtube_id(value)
            upsert_site_config(conn, pais, key, value)
            # Si se actualiza la dirección, sincronizar con la sucursal principal
            if key == "direccion" and value:
                conn.execute(
                    "UPDATE sucursales_db SET direccion=? WHERE country_code=? AND tipo='principal'",
                    (value, pais),
                )
        conn.commit()
        conn.close()
        _cache.invalidate("country:")  # site_config cambió → forzar recarga en la web
        log_action(current_user().get("email", "?"), "actualizar_contacto", f"pais={pais}")
        flash("Configuración guardada.", "success")
        return redirect(url_for("admin.contacto"))

    config = {}
    for code in ("pe", "ar"):
        config[code] = {}
        rows = conn.execute(
            "SELECT key, value FROM site_config WHERE country_code=?", (code,)
        ).fetchall()
        for r in rows:
            config[code][r["key"]] = r["value"]
    conn.close()
    return render_template("admin/contacto.html", user=current_user(), config=config, keys=keyS)


# ── Sucursales ────────────────────────────────────────────────────────────────
@admin_bp.route("/sucursales")
@admin_required
def sucursales():
    conn = get_conn()
    suc_pe = [dict(s) for s in conn.execute(
        "SELECT * FROM sucursales_db WHERE country_code='pe' ORDER BY orden"
    ).fetchall()]
    suc_ar = [dict(s) for s in conn.execute(
        "SELECT * FROM sucursales_db WHERE country_code='ar' ORDER BY orden"
    ).fetchall()]
    conn.close()
    return render_template(
        "admin/sucursales.html", user=current_user(), suc_pe=suc_pe, suc_ar=suc_ar
    )


@admin_bp.route("/sucursales/guardar", methods=["POST"])
@admin_required
def sucursales_guardar():
    f = request.form
    sid = f.get("id", "").strip()
    country_code = f.get("country_code", "pe")
    nombre = f.get("nombre", "").strip()
    tipo = f.get("tipo", "sucursal")
    direccion = f.get("direccion", "").strip()
    maps_url = f.get("maps_url", "").strip()
    telefono = f.get("telefono", "").strip()
    orden = int(f.get("orden", 0) or 0)
    try:
        lat = float(f.get("lat") or 0)
    except ValueError:
        lat = 0.0
    try:
        lng = float(f.get("lng") or 0)
    except ValueError:
        lng = 0.0

    conn = get_conn()
    if sid:
        conn.execute(
            """UPDATE sucursales_db SET nombre=?, tipo=?, direccion=?, lat=?, lng=?,
               maps_url=?, telefono=?, orden=? WHERE id=?""",
            (nombre, tipo, direccion, lat, lng, maps_url, telefono, orden, int(sid)),
        )
        # Si es la sucursal principal, sincronizar dirección en site_config
        if tipo == "principal" and direccion:
            upsert_site_config(conn, country_code, "direccion", direccion)
        conn.commit()
        conn.close()
        _cache.invalidate("country:")  # sucursales cambiaron → forzar recarga en la web
        log_action(current_user().get("email", "?"), "editar_sucursal", f"ID={sid} nombre={nombre}")
    else:
        conn.execute(
            """INSERT INTO sucursales_db (country_code, nombre, tipo, direccion, lat, lng, maps_url, telefono, orden)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (country_code, nombre, tipo, direccion, lat, lng, maps_url, telefono, orden),
        )
        # Si es la sucursal principal, sincronizar dirección en site_config
        if tipo == "principal" and direccion:
            upsert_site_config(conn, country_code, "direccion", direccion)
        conn.commit()
        conn.close()
        _cache.invalidate("country:")  # sucursales cambiaron → forzar recarga en la web
        log_action(current_user().get("email", "?"), "crear_sucursal", f"nombre={nombre} country={country_code}")
    flash("Sucursal guardada.", "success")
    return redirect(url_for("admin.sucursales"))


@admin_bp.route("/sucursales/<int:sid>/eliminar", methods=["POST"])
@admin_required
def sucursales_eliminar(sid):
    conn = get_conn()
    conn.execute("DELETE FROM sucursales_db WHERE id=?", (sid,))
    conn.commit()
    conn.close()
    _cache.invalidate("country:")  # sucursal eliminada → forzar recarga en la web
    log_action(current_user().get("email", "?"), "eliminar_sucursal", f"ID={sid}")
    flash("Sucursal eliminada.", "success")
    return redirect(url_for("admin.sucursales"))


# ── Blog ──────────────────────────────────────────────────────────────────────
@admin_bp.route("/blog")
@admin_required
def blog_list():
    conn = get_conn()
    posts = conn.execute("SELECT * FROM blog_posts ORDER BY fecha DESC").fetchall()
    conn.close()
    return render_template("admin/blog_list.html", user=current_user(), posts=posts)


@admin_bp.route("/blog/nuevo", methods=["GET", "POST"])
@admin_required
def blog_nuevo():
    if request.method == "POST":
        return _save_blog(None)
    return render_template("admin/blog_form.html", user=current_user(), post=None)


@admin_bp.route("/blog/<int:pid>/editar", methods=["GET", "POST"])
@admin_required
def blog_editar(pid):
    conn = get_conn()
    post = conn.execute("SELECT * FROM blog_posts WHERE id=?", (pid,)).fetchone()
    conn.close()
    if not post:
        flash("Post no encontrado.", "danger")
        return redirect(url_for("admin.blog_list"))
    if request.method == "POST":
        return _save_blog(pid)
    return render_template("admin/blog_form.html", user=current_user(), post=dict(post))


def _save_blog(pid):
    f = request.form
    titulo    = f.get("titulo", "").strip()
    slug      = f.get("slug", "").strip() or _slugify(titulo)
    categoria = f.get("categoria", "articulos").strip()
    fecha     = f.get("fecha", "").strip()
    extracto  = f.get("extracto", "").strip()
    contenido = f.get("contenido", "").strip()
    video_url = f.get("video_url", "").strip()
    activo    = 1 if f.get("activo") else 0
    show_pe   = 1 if f.get("show_pe") else 0
    show_arg  = 1 if f.get("show_arg") else 0

    if not titulo:
        flash("El título es obligatorio.", "danger")
        return redirect(request.referrer or url_for("admin.blog_list"))

    if not show_pe and not show_arg:
        flash("Advertencia: el post no tiene ningún país seleccionado y no será visible en ningún sitio.", "warning")

    if activo and not show_pe and not show_arg:
        flash("El post está activo pero sin país asignado — no aparecerá en la web.", "warning")

    conn = get_conn()

    # Manejar imagen subida
    imagen_actual = f.get("imagen_actual", "").strip()
    imagen = imagen_actual
    file = request.files.get("imagen_file")
    if file and file.filename:
        blog_dir = os.path.join(current_app.root_path, "static", "images", "blog")
        os.makedirs(blog_dir, exist_ok=True)
        ext = file.filename.rsplit(".", 1)[-1].lower()
        filename = f"{slug}.{ext}"
        filepath = os.path.join(blog_dir, filename)
        file.save(filepath)
        # Convertir a webp si no lo es
        if ext != "webp":
            try:
                from PIL import Image as PILImage
                img = PILImage.open(filepath).convert("RGB")
                webp_path = os.path.join(blog_dir, f"{slug}.webp")
                img.save(webp_path, "WEBP", quality=85)
                os.remove(filepath)
                filename = f"{slug}.webp"
            except Exception:
                pass
        imagen = f"blog/{filename}"

    if pid is None:
        conn.execute(
            """INSERT INTO blog_posts (slug, titulo, categoria, fecha, imagen, extracto, contenido, video_url, activo, show_pe, show_arg)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (slug, titulo, categoria, fecha, imagen, extracto, contenido, video_url, activo, show_pe, show_arg),
        )
        conn.commit()
        pid = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        log_action(current_user().get("email", "?"), "crear_blog", f"slug={slug}")
        flash("Post creado exitosamente.", "success")
    else:
        conn.execute(
            """UPDATE blog_posts SET slug=?, titulo=?, categoria=?, fecha=?, imagen=?,
               extracto=?, contenido=?, video_url=?, activo=?, show_pe=?, show_arg=? WHERE id=?""",
            (slug, titulo, categoria, fecha, imagen, extracto, contenido, video_url, activo, show_pe, show_arg, pid),
        )
        conn.commit()
        log_action(current_user().get("email", "?"), "editar_blog", f"ID={pid} slug={slug}")
        flash("Post actualizado.", "success")
    conn.close()
    return redirect(url_for("admin.blog_editar", pid=pid))


@admin_bp.route("/blog/<int:pid>/toggle", methods=["POST"])
@admin_required
def blog_toggle(pid):
    conn = get_conn()
    post = conn.execute("SELECT activo FROM blog_posts WHERE id=?", (pid,)).fetchone()
    if not post:
        conn.close()
        return jsonify({"ok": False}), 404
    nuevo = 0 if post["activo"] else 1
    conn.execute("UPDATE blog_posts SET activo=? WHERE id=?", (nuevo, pid))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "activo": nuevo})


@admin_bp.route("/blog/<int:pid>/eliminar", methods=["POST"])
@admin_required
def blog_eliminar(pid):
    conn = get_conn()
    post = conn.execute("SELECT slug FROM blog_posts WHERE id=?", (pid,)).fetchone()
    if post:
        conn.execute("DELETE FROM blog_posts WHERE id=?", (pid,))
        conn.commit()
        log_action(current_user().get("email", "?"), "eliminar_blog", f"ID={pid} slug={post['slug']}")
    conn.close()
    flash("Post eliminado.", "success")
    return redirect(url_for("admin.blog_list"))


# ── Historial ─────────────────────────────────────────────────────────────────
@admin_bp.route("/historial")
@admin_required
def historial():
    usuario_filter = request.args.get("usuario", "").strip()
    page = max(1, int(request.args.get("page", 1)))

    conn = get_conn()
    clauses = []
    params = []
    if usuario_filter:
        clauses.append("usuario LIKE ?")
        params.append(f"%{usuario_filter}%")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    total = conn.execute(f"SELECT COUNT(*) as c FROM audit_log {where}", params).fetchone()["c"]
    offset = (page - 1) * PER_PAGE
    rows = conn.execute(
        f"SELECT * FROM audit_log {where} ORDER BY id DESC LIMIT ? OFFSET ?",
        params + [PER_PAGE, offset],
    ).fetchall()
    conn.close()
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    return render_template(
        "admin/historial.html",
        user=current_user(),
        rows=rows,
        usuario_filter=usuario_filter,
        page=page,
        total_pages=total_pages,
        total=total,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORÍAS
# ═══════════════════════════════════════════════════════════════════════════════

# Unidades disponibles (estáticas — la estructura de secciones no cambia)
UNIDADES_OPCIONES = [
    ("alquiler", "Construcción",    "construccion"),
    ("alquiler", "Mediana Minería", "mineria"),
    ("alquiler", "Agrícola",        "agricola"),
    ("alquiler", "Energía",         "energia"),
    ("usados",   "Construcción",    "construccion"),
    ("usados",   "Agrícola",        "agricola"),
    ("usados",   "Energía",         "energia"),
]


@admin_bp.route("/categorias")
@admin_required
def categorias():
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM categorias ORDER BY tag, unidad_slug, orden, tipo"
    ).fetchall()
    conn.close()
    return render_template(
        "admin/categorias.html",
        user=current_user(),
        rows=[dict(r) for r in rows],
        unidades=UNIDADES_OPCIONES,
    )


@admin_bp.route("/categorias/nueva", methods=["POST"])
@admin_required
def categoria_nueva():
    tag        = request.form.get("tag", "").strip()
    unidad     = request.form.get("unidad", "").strip()
    unidad_slug= request.form.get("unidad_slug", "").strip()
    tipo       = request.form.get("tipo", "").strip()
    tipo_titulo= request.form.get("tipo_titulo", "").strip()
    slug_sub_raw = request.form.get("slug_sub", "").strip()
    show_pe    = 1 if request.form.get("show_pe") else 0
    show_ar    = 1 if request.form.get("show_ar") else 0

    # ── Fix 1: orden seguro ────────────────────────────────────────────────
    try:
        orden = int(request.form.get("orden") or 99)
    except (ValueError, TypeError):
        orden = 99

    # ── Slug siempre obligatorio: si no viene, se genera desde tipo ───────
    if slug_sub_raw:
        slug_sub = re.sub(r'[^a-z0-9-]', '-', slug_sub_raw.lower())
        slug_sub = re.sub(r'-+', '-', slug_sub).strip('-')
    else:
        slug_sub = None
    if not slug_sub:                           # fallback: generar desde tipo
        _t = tipo.lower()
        for a, b in [('á','a'),('é','e'),('í','i'),('ó','o'),('ú','u'),('ñ','n')]:
            _t = _t.replace(a, b)
        slug_sub = re.sub(r'[^a-z0-9]+', '-', _t).strip('-') or 'tipo'

    # ── Fix 2: validación de campos obligatorios ───────────────────────────
    if not (tag and unidad and unidad_slug and tipo and tipo_titulo):
        flash("Faltan campos obligatorios.", "danger")
        return redirect(url_for("admin.categorias"))

    # ── Fix 5: validar tag/unidad/unidad_slug contra whitelist ────────────
    valid_combos = {(t, u, s) for t, u, s in UNIDADES_OPCIONES}
    if (tag, unidad, unidad_slug) not in valid_combos:
        flash("Sección no válida.", "danger")
        return redirect(url_for("admin.categorias"))

    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO categorias (tag, unidad, unidad_slug, tipo, tipo_titulo,
               slug_sub, orden, show_pe, show_ar, activo)
               VALUES (?,?,?,?,?,?,?,?,?,1)""",
            (tag, unidad, unidad_slug, tipo, tipo_titulo, slug_sub, orden, show_pe, show_ar),
        )
        conn.commit()
        _cache.invalidate("nav_categorias")
        log_action(current_user().get("name","admin"), "categoria_nueva",
                   f"{tag}/{unidad_slug}/{tipo}")
        flash(f"Categoría '{tipo_titulo}' creada.", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    conn.close()
    return redirect(url_for("admin.categorias"))


@admin_bp.route("/categorias/<int:cid>/editar", methods=["POST"])
@admin_required
def categoria_editar(cid):
    tipo_titulo = request.form.get("tipo_titulo", "").strip()
    slug_sub_raw= request.form.get("slug_sub", "").strip()
    show_pe     = 1 if request.form.get("show_pe") else 0
    show_ar     = 1 if request.form.get("show_ar") else 0
    activo      = 1 if request.form.get("activo") else 0

    # ── Fix 1: orden seguro ────────────────────────────────────────────────
    try:
        orden = int(request.form.get("orden") or 99)
    except (ValueError, TypeError):
        orden = 99

    # ── Fix 2: tipo_titulo requerido ───────────────────────────────────────
    if not tipo_titulo:
        flash("El título del menú no puede estar vacío.", "danger")
        return redirect(url_for("admin.categorias"))

    # ── Slug siempre obligatorio (igual que en nueva) ──────────────────────
    if slug_sub_raw:
        slug_sub = re.sub(r'[^a-z0-9-]', '-', slug_sub_raw.lower())
        slug_sub = re.sub(r'-+', '-', slug_sub).strip('-')
    else:
        slug_sub = None
    if not slug_sub:                           # obtener tipo actual para fallback
        try:
            _conn_tmp = get_conn()
            _row_tmp  = _conn_tmp.execute("SELECT tipo FROM categorias WHERE id=?", (cid,)).fetchone()
            _conn_tmp.close()
            _t = (_row_tmp["tipo"] if _row_tmp else "tipo").lower()
            for a, b in [('á','a'),('é','e'),('í','i'),('ó','o'),('ú','u'),('ñ','n')]:
                _t = _t.replace(a, b)
            slug_sub = re.sub(r'[^a-z0-9]+', '-', _t).strip('-') or 'tipo'
        except Exception:
            slug_sub = 'tipo'

    conn = get_conn()
    conn.execute(
        """UPDATE categorias SET tipo_titulo=?, slug_sub=?, show_pe=?, show_ar=?,
           orden=?, activo=? WHERE id=?""",
        (tipo_titulo, slug_sub, show_pe, show_ar, orden, activo, cid),
    )
    conn.commit()
    _cache.invalidate("nav_categorias")
    log_action(current_user().get("name","admin"), "categoria_editar", f"id={cid}")
    conn.close()
    flash("Categoría actualizada.", "success")
    return redirect(url_for("admin.categorias"))


@admin_bp.route("/categorias/<int:cid>/toggle", methods=["POST"])
@admin_required
def categoria_toggle(cid):
    conn = get_conn()
    conn.execute("UPDATE categorias SET activo = 1 - activo WHERE id=?", (cid,))
    conn.commit()
    _cache.invalidate("nav_categorias")
    conn.close()
    return jsonify({"ok": True})


@admin_bp.route("/categorias/<int:cid>/eliminar", methods=["POST"])
@admin_required
def categoria_eliminar(cid):
    conn = get_conn()
    conn.execute("DELETE FROM categorias WHERE id=?", (cid,))
    conn.commit()
    _cache.invalidate("nav_categorias")
    log_action(current_user().get("name","admin"), "categoria_eliminar", f"id={cid}")
    conn.close()
    flash("Categoría eliminada.", "warning")
    return redirect(url_for("admin.categorias"))


# ═══════════════════════════════════════════════════════════════════════════════
# POPUPS
# ═══════════════════════════════════════════════════════════════════════════════

POPUP_IMAGES_DIR = "static/images/popups"


@admin_bp.route("/popups")
@admin_required
def popups_list():
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM popups ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return render_template("admin/popups_list.html", user=current_user(), popups=[dict(r) for r in rows])


@admin_bp.route("/popups/nuevo", methods=["GET", "POST"])
@admin_required
def popup_nuevo():
    if request.method == "POST":
        return _save_popup(None)
    return render_template("admin/popup_form.html", user=current_user(), popup=None)


@admin_bp.route("/popups/<int:pid>/editar", methods=["GET", "POST"])
@admin_required
def popup_editar(pid):
    conn = get_conn()
    row = conn.execute("SELECT * FROM popups WHERE id=?", (pid,)).fetchone()
    conn.close()
    if not row:
        flash("Popup no encontrado.", "danger")
        return redirect(url_for("admin.popups_list"))
    if request.method == "POST":
        return _save_popup(pid)
    return render_template("admin/popup_form.html", user=current_user(), popup=dict(row))


def _save_popup(pid):
    f = request.form
    titulo              = f.get("titulo", "").strip()
    link_url            = f.get("link_url", "").strip() or None
    abrir_nueva_ventana = 1 if f.get("abrir_nueva_ventana") else 0
    fecha_inicio        = f.get("fecha_inicio", "").strip()
    fecha_fin           = f.get("fecha_fin", "").strip()
    activo              = 1 if f.get("activo") else 0
    imagen_fit          = f.get("imagen_fit", "cover").strip()
    boton_activo        = 1 if f.get("boton_activo") else 0
    boton_texto         = f.get("boton_texto", "Ver más").strip() or "Ver más"
    boton_color_fondo   = f.get("boton_color_fondo", "#02534C").strip()
    boton_color_texto   = f.get("boton_color_texto", "#ffffff").strip()
    boton_tamano        = f.get("boton_tamano", "md").strip()
    frecuencia          = f.get("frecuencia", "siempre").strip()
    pais_filtro         = f.get("pais_filtro", "todos").strip()
    animacion           = f.get("animacion", "fade").strip()
    overlay_activo      = 1 if f.get("overlay_activo") else 0
    overlay_titulo      = f.get("overlay_titulo", "").strip()
    overlay_subtitulo   = f.get("overlay_subtitulo", "").strip()
    overlay_color_fondo = f.get("overlay_color_fondo", "rgba(0,0,0,0.55)").strip()
    overlay_color_texto = f.get("overlay_color_texto", "#ffffff").strip()
    overlay_posicion    = f.get("overlay_posicion", "bottom").strip()
    try:
        boton_pos_x  = int(f.get("boton_pos_x", 50))
        boton_pos_y  = int(f.get("boton_pos_y", 85))
        delay_ms     = max(0, min(10000, int(f.get("delay_ms", 800) or 800)))
        imagen_altura = max(0, min(600, int(f.get("imagen_altura", 0) or 0)))
    except (ValueError, TypeError):
        boton_pos_x, boton_pos_y, delay_ms, imagen_altura = 50, 85, 800, 0

    if not fecha_inicio or not fecha_fin:
        flash("Las fechas de inicio y fin son obligatorias.", "danger")
        return redirect(request.referrer or url_for("admin.popups_list"))

    conn = get_conn()

    # Manejar imagen subida
    imagen_actual = f.get("imagen_actual", "").strip() or None
    imagen = imagen_actual
    file = request.files.get("imagen_file")
    if file and file.filename:
        popups_dir = os.path.join(current_app.root_path, POPUP_IMAGES_DIR)
        os.makedirs(popups_dir, exist_ok=True)
        ext = file.filename.rsplit(".", 1)[-1].lower()
        base_name = f"popup_{pid or 'new'}_{int(datetime.now().timestamp())}"
        filename = f"{base_name}.{ext}"
        filepath = os.path.join(popups_dir, filename)
        file.save(filepath)
        if ext != "webp":
            try:
                from PIL import Image as PILImage
                img = PILImage.open(filepath).convert("RGB")
                webp_path = os.path.join(popups_dir, f"{base_name}.webp")
                img.save(webp_path, "WEBP", quality=90)
                os.remove(filepath)
                filename = f"{base_name}.webp"
            except Exception:
                pass
        imagen = filename

    if pid is None:
        conn.execute(
            """INSERT INTO popups
               (titulo, imagen, link_url, abrir_nueva_ventana, fecha_inicio, fecha_fin, activo,
                imagen_fit, imagen_altura, boton_activo, boton_texto, boton_color_fondo, boton_color_texto,
                boton_tamano, boton_pos_x, boton_pos_y, frecuencia, delay_ms, pais_filtro, animacion,
                overlay_activo, overlay_titulo, overlay_subtitulo, overlay_color_fondo,
                overlay_color_texto, overlay_posicion)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (titulo or None, imagen, link_url, abrir_nueva_ventana, fecha_inicio, fecha_fin, activo,
             imagen_fit, imagen_altura, boton_activo, boton_texto, boton_color_fondo, boton_color_texto,
             boton_tamano, boton_pos_x, boton_pos_y, frecuencia, delay_ms, pais_filtro, animacion,
             overlay_activo, overlay_titulo, overlay_subtitulo, overlay_color_fondo,
             overlay_color_texto, overlay_posicion),
        )
        conn.commit()
        pid = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        if imagen and "popup_new_" in imagen:
            old_path = os.path.join(current_app.root_path, POPUP_IMAGES_DIR, imagen)
            new_name = imagen.replace("popup_new_", f"popup_{pid}_")
            new_path = os.path.join(current_app.root_path, POPUP_IMAGES_DIR, new_name)
            if os.path.exists(old_path):
                os.rename(old_path, new_path)
                imagen = new_name
                conn.execute("UPDATE popups SET imagen=? WHERE id=?", (imagen, pid))
                conn.commit()
        log_action(current_user().get("email", "?"), "crear_popup", f"ID={pid}")
        flash("Popup creado exitosamente.", "success")
    else:
        conn.execute(
            """UPDATE popups SET titulo=?, imagen=?, link_url=?, abrir_nueva_ventana=?,
               fecha_inicio=?, fecha_fin=?, activo=?,
               imagen_fit=?, imagen_altura=?, boton_activo=?, boton_texto=?, boton_color_fondo=?,
               boton_color_texto=?, boton_tamano=?, boton_pos_x=?, boton_pos_y=?,
               frecuencia=?, delay_ms=?, pais_filtro=?, animacion=?,
               overlay_activo=?, overlay_titulo=?, overlay_subtitulo=?, overlay_color_fondo=?,
               overlay_color_texto=?, overlay_posicion=?
               WHERE id=?""",
            (titulo or None, imagen, link_url, abrir_nueva_ventana, fecha_inicio, fecha_fin, activo,
             imagen_fit, imagen_altura, boton_activo, boton_texto, boton_color_fondo, boton_color_texto,
             boton_tamano, boton_pos_x, boton_pos_y, frecuencia, delay_ms, pais_filtro, animacion,
             overlay_activo, overlay_titulo, overlay_subtitulo, overlay_color_fondo,
             overlay_color_texto, overlay_posicion, pid),
        )
        conn.commit()
        log_action(current_user().get("email", "?"), "editar_popup", f"ID={pid}")
        flash("Popup actualizado.", "success")
    conn.close()
    return redirect(url_for("admin.popup_editar", pid=pid))


@admin_bp.route("/popups/<int:pid>/duplicar", methods=["POST"])
@admin_required
def popup_duplicar(pid):
    conn = get_conn()
    row = conn.execute("SELECT * FROM popups WHERE id=?", (pid,)).fetchone()
    if row:
        d = dict(row)
        conn.execute(
            """INSERT INTO popups
               (titulo, imagen, link_url, abrir_nueva_ventana, fecha_inicio, fecha_fin, activo,
                imagen_fit, imagen_altura, boton_activo, boton_texto, boton_color_fondo, boton_color_texto,
                boton_tamano, boton_pos_x, boton_pos_y, frecuencia, delay_ms, pais_filtro, animacion,
                overlay_activo, overlay_titulo, overlay_subtitulo, overlay_color_fondo,
                overlay_color_texto, overlay_posicion)
               VALUES (?,?,?,?,?,?,0,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (f"Copia de {d.get('titulo') or 'Popup'}",
             d.get('imagen'), d.get('link_url'), d.get('abrir_nueva_ventana', 1),
             d.get('fecha_inicio'), d.get('fecha_fin'),
             d.get('imagen_fit', 'cover'), d.get('imagen_altura', 0),
             d.get('boton_activo', 0), d.get('boton_texto', 'Ver más'),
             d.get('boton_color_fondo', '#02534C'), d.get('boton_color_texto', '#ffffff'),
             d.get('boton_tamano', 'md'), d.get('boton_pos_x', 50), d.get('boton_pos_y', 85),
             d.get('frecuencia', 'siempre'), d.get('delay_ms', 800),
             d.get('pais_filtro', 'todos'), d.get('animacion', 'fade'),
             d.get('overlay_activo', 0), d.get('overlay_titulo', ''),
             d.get('overlay_subtitulo', ''), d.get('overlay_color_fondo', 'rgba(0,0,0,0.55)'),
             d.get('overlay_color_texto', '#ffffff'), d.get('overlay_posicion', 'bottom')),
        )
        conn.commit()
        new_pid = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        log_action(current_user().get("email", "?"), "duplicar_popup", f"orig={pid} copia={new_pid}")
        flash("Popup duplicado (inactivo). Edítalo y actívalo cuando esté listo.", "success")
    conn.close()
    return redirect(url_for("admin.popups_list"))


@admin_bp.route("/popups/<int:pid>/estadisticas")
@admin_required
def popup_estadisticas(pid):
    conn = get_conn()
    popup = conn.execute("SELECT * FROM popups WHERE id=?", (pid,)).fetchone()
    conn.close()
    if not popup:
        flash("Popup no encontrado.", "danger")
        return redirect(url_for("admin.popups_list"))
    return render_template("admin/popup_stats.html", popup=dict(popup))


@admin_bp.route("/popups/<int:pid>/stats-data")
@admin_required
def popup_stats_data(pid):
    conn = get_conn()
    rows = conn.execute(
        """SELECT fecha, vistas, clics FROM popup_stats
           WHERE popup_id=? ORDER BY fecha DESC LIMIT 30""",
        (pid,),
    ).fetchall()
    conn.close()
    data = [{"fecha": r["fecha"], "vistas": r["vistas"], "clics": r["clics"]}
            for r in reversed(rows)]
    return jsonify(data)


@admin_bp.route("/popups/<int:pid>/toggle", methods=["POST"])
@admin_required
def popup_toggle(pid):
    conn = get_conn()
    conn.execute("UPDATE popups SET activo = 1 - activo WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@admin_bp.route("/popups/<int:pid>/eliminar", methods=["POST"])
@admin_required
def popup_eliminar(pid):
    conn = get_conn()
    row = conn.execute("SELECT imagen FROM popups WHERE id=?", (pid,)).fetchone()
    if row and row["imagen"]:
        img_path = os.path.join(current_app.root_path, POPUP_IMAGES_DIR, row["imagen"])
        if os.path.exists(img_path):
            os.remove(img_path)
    conn.execute("DELETE FROM popups WHERE id=?", (pid,))
    conn.commit()
    log_action(current_user().get("email", "?"), "eliminar_popup", f"ID={pid}")
    conn.close()
    flash("Popup eliminado.", "success")
    return redirect(url_for("admin.popups_list"))
