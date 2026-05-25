/* ═══════════════════════════════════════════════
   CGM RENTAL — cart.js
   ═══════════════════════════════════════════════ */

/* País activo */
function _cc() { return window.CGM_COUNTRY || 'pe'; }

/* CSRF token helper */
function _csrfToken() {
  var m = document.querySelector('meta[name="csrf-token"]');
  return m ? m.getAttribute('content') : '';
}

/* Actualizar badges (header + flotante) */
function updateCartBadge(count) {
  document.querySelectorAll('#cartBadge,#cartFloatBadge').forEach(el => el.textContent = count);
}

/* ── Cargar y renderizar items en el modal cotizador ── */
async function loadCartModal() {
  try {
    const resp  = await fetch(`/api/cart?country=${_cc()}`);
    const json  = await resp.json();
    const cart  = json.cart || {};
    const items = Object.values(cart);
    const body  = document.getElementById('cartModalBody');
    if (!body) return;

    const total = items.reduce((s, i) => s + (i.qty || 1), 0);
    updateCartBadge(total);

    if (items.length === 0) {
      body.innerHTML = '<p class="cgm-cotiz-empty">El carrito está vacío.</p>';
      return;
    }

    body.innerHTML = items.map(it => {
      const imgSrc = it.imagen
        ? `/static/products/${it.imagen}`
        : '/static/images/placeholder.png';
      const tipo = it.tipo ? `(${it.tipo})` : '';
      return `
      <div class="cgm-cotiz-item" id="citem-${it.slug}">
        <button class="cgm-cotiz-remove" onclick="cartRemoveItem('${it.slug}')" title="Eliminar">×</button>
        <img src="${imgSrc}" alt="${it.nombre}"
             onerror="this.src='/static/images/placeholder.png'">
        <div class="cgm-cotiz-info">
          <div class="cgm-cotiz-name">${it.nombre} <span class="cgm-cotiz-tipo">${tipo}</span></div>
          <div class="cgm-cotiz-qty">
            <button onclick="cartChangeQty('${it.slug}',-1)">−</button>
            <span id="qty-${it.slug}">${it.qty || 1}</span>
            <button onclick="cartChangeQty('${it.slug}',1)">+</button>
          </div>
        </div>
      </div>`;
    }).join('');
  } catch (e) { console.error(e); }
}

/* Cambiar cantidad desde el modal */
async function cartChangeQty(slug, delta) {
  const qtyEl = document.getElementById(`qty-${slug}`);
  const current = parseInt(qtyEl?.textContent || '1');
  const next = current + delta;
  if (next < 1) { cartRemoveItem(slug); return; }

  await fetch('/api/cart/qty', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _csrfToken() },
    body: JSON.stringify({ slug, qty: next, country: _cc() })
  });
  if (qtyEl) qtyEl.textContent = next;
  const total = Array.from(document.querySelectorAll('[id^="qty-"]'))
    .reduce((s, el) => s + parseInt(el.textContent || 0), 0);
  updateCartBadge(total);
}

/* Eliminar item desde el modal */
async function cartRemoveItem(slug) {
  const resp = await fetch(`/api/cart?slug=${encodeURIComponent(slug)}&country=${_cc()}`, { method: 'DELETE', headers: { 'X-CSRFToken': _csrfToken() } });
  const json = await resp.json();
  updateCartBadge(json.count);
  const el = document.getElementById(`citem-${slug}`);
  if (el) el.remove();
  const body = document.getElementById('cartModalBody');
  if (body && !body.querySelector('.cgm-cotiz-item')) {
    body.innerHTML = '<p class="cgm-cotiz-empty">El carrito está vacío.</p>';
  }
  /* también actualizar página carrito si está abierta */
  const row = document.getElementById(`cart-row-${slug}`);
  if (row) row.remove();
}

/* Agregar al carrito */
async function addToCart(slug, nombre, imagen = '', tipo = '', tag = '') {
  try {
    const resp = await fetch('/api/cart/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _csrfToken() },
      body: JSON.stringify({ slug, nombre, imagen, tipo, tag, country: _cc() })
    });
    const json = await resp.json();
    if (json.ok) {
      updateCartBadge(json.count);
      /* abrir modal cotizador */
      openCotizador();
      if (typeof cgmToast === 'function') {
        cgmToast(`<strong>${nombre}</strong> agregado al carrito`);
      }
    }
  } catch (err) { console.error('Error al agregar al carrito', err); }
}

/* Cotizar: agrega al carrito y redirige a la página del carrito.
   Si el carrito estaba vacío antes del click → muestra formulario simple (?simple=1).
   Si ya tenía equipos → redirige normalmente con el stepper. */
async function cotizarProduct(slug, nombre, imagen, tipo, cartUrl, tag = '') {
  try {
    /* 1. Ver si el carrito estaba vacío ANTES de agregar */
    let wasEmpty = true;
    try {
      const check = await fetch(`/api/cart?country=${_cc()}`);
      const checkJson = await check.json();
      wasEmpty = Object.keys(checkJson.cart || {}).length === 0;
    } catch (e) {}

    /* 2. Agregar el equipo */
    await fetch('/api/cart/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _csrfToken() },
      body: JSON.stringify({ slug, nombre, imagen, tipo, tag, country: _cc() })
    });

    /* 3. Redirigir según estado previo */
    window.location.href = wasEmpty ? cartUrl + '?simple=1' : cartUrl;
  } catch (err) {
    console.error('Error al cotizar', err);
    window.location.href = cartUrl;
  }
}

/* Abrir / cerrar el panel cotizador */
function openCotizador() {
  const panel = document.getElementById('cgmCotizModal');
  if (panel) { panel.classList.add('open'); loadCartModal(); }
}
function closeCotizador() {
  const panel = document.getElementById('cgmCotizModal');
  if (panel) panel.classList.remove('open');
}

/* Eliminar del carrito (página carrito clásica) */
async function removeFromCart(slug) {
  try {
    const resp = await fetch(`/api/cart?slug=${encodeURIComponent(slug)}&country=${_cc()}`, { method: 'DELETE', headers: { 'X-CSRFToken': _csrfToken() } });
    const json = await resp.json();
    if (json.ok) {
      updateCartBadge(json.count);
      const row = document.getElementById(`cart-row-${slug}`);
      if (row) row.remove();
      const table = document.getElementById('cartTable');
      if (table && !table.querySelector('tr')) {
        const empty = document.getElementById('cartEmpty');
        if (empty) empty.style.display = 'block';
        table.closest('div').style.display = 'none';
      }
    }
  } catch (err) { console.error(err); }
}

/* Limpiar carrito completo */
async function clearCart() {
  try { await fetch(`/api/cart?country=${_cc()}`, { method: 'DELETE', headers: { 'X-CSRFToken': _csrfToken() } }); location.reload(); }
  catch (err) { console.error(err); }
}

/* ── Init ── */
document.addEventListener('DOMContentLoaded', function () {

  /* Botón flotante → toggle panel */
  const floatBtn  = document.getElementById('cartFloatBtn');
  const floatWrap = document.getElementById('cgmCotizFloat');
  if (floatBtn) {
    floatBtn.addEventListener('click', e => {
      e.stopPropagation();
      const panel = document.getElementById('cgmCotizModal');
      if (!panel) return;
      const isOpen = panel.classList.toggle('open');
      if (isOpen) loadCartModal();
    });
  }
  /* Cerrar al click fuera del widget */
  document.addEventListener('click', e => {
    if (floatWrap && !floatWrap.contains(e.target)) closeCotizador();
  });

  /* Badge inicial */
  fetch(`/api/cart?country=${_cc()}`).then(r => r.json()).then(j => {
    const cart  = j.cart || {};
    const total = Object.values(cart).reduce((s, i) => s + (i.qty || 1), 0);
    updateCartBadge(total);
  }).catch(() => {});
});
