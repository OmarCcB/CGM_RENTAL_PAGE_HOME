/* ═══════════════════════════════════════════════
   CGM RENTAL — main.js
   Vanilla JS — sin jQuery
   ═══════════════════════════════════════════════ */

/* ── Header scroll compacto ─────────────────── */
(function () {
  const header = document.getElementById('cgmHeader');
  if (!header) return;
  const onScroll = () => header.classList.toggle('scrolled', window.scrollY > 10);
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
})();

/* ── Dropdown hover (desktop grande ≥1200px) ── */
(function () {
  if (window.innerWidth < 1200) return;
  document.querySelectorAll('.cgm-dropdown').forEach(li => {
    li.addEventListener('mouseenter', () => li.classList.add('show'));
    li.addEventListener('mouseleave', () => li.classList.remove('show'));
  });
  document.querySelectorAll('.dropdown-submenu').forEach(sub => {
    sub.addEventListener('mouseenter', () => sub.classList.add('show'));
    sub.addEventListener('mouseleave', () => sub.classList.remove('show'));
  });
})();

/* ── Dropdown click (tablet 768–1199px) ─────── */
(function () {
  if (window.innerWidth < 768 || window.innerWidth >= 1200) return;

  // Click en ALQUILER / USADOS → abre/cierra
  document.querySelectorAll('.cgm-dropdown > .cgm-nav-link').forEach(link => {
    link.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      const li = this.closest('.cgm-dropdown');
      const isOpen = li.classList.contains('show');
      // Cierra todos primero
      document.querySelectorAll('.cgm-dropdown').forEach(d => d.classList.remove('show'));
      document.querySelectorAll('.dropdown-submenu').forEach(s => s.classList.remove('show'));
      if (!isOpen) li.classList.add('show');
    });
  });

  // Click en Construcción / Minería / etc. → abre/cierra sub-drop
  document.querySelectorAll('.dropdown-submenu > .cgm-drop-item.has-submenu').forEach(link => {
    link.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      const sub = this.closest('.dropdown-submenu');
      const isOpen = sub.classList.contains('show');
      // Cierra otros sub-drops del mismo nivel
      sub.closest('.cgm-drop').querySelectorAll('.dropdown-submenu').forEach(s => s.classList.remove('show'));
      if (!isOpen) sub.classList.add('show');
    });
  });

  // Cierra todo al hacer click fuera
  document.addEventListener('click', function () {
    document.querySelectorAll('.cgm-dropdown').forEach(d => d.classList.remove('show'));
    document.querySelectorAll('.dropdown-submenu').forEach(s => s.classList.remove('show'));
  });
})();

/* ── Mobile dropdown click (acordeón ≤767px) ── */
(function () {
  document.querySelectorAll('.cgm-dropdown > .cgm-nav-link').forEach(link => {
    link.addEventListener('click', function (e) {
      if (window.innerWidth >= 768) return;
      e.preventDefault();
      const li = this.closest('.cgm-dropdown');
      li.classList.toggle('show');
    });
  });
  document.querySelectorAll('.dropdown-submenu > .cgm-drop-item.has-submenu').forEach(link => {
    link.addEventListener('click', function (e) {
      if (window.innerWidth >= 768) return;
      e.preventDefault();
      this.closest('.dropdown-submenu').classList.toggle('show');
    });
  });
})();

/* ── Selector de país (click) ───────────────── */
(function () {
  const sel = document.querySelector('.cgm-country-sel');
  if (!sel) return;
  const btn = sel.querySelector('.cgm-country-btn');
  const menu = sel.querySelector('.cgm-drop');
  if (!btn || !menu) return;

  btn.addEventListener('click', function (e) {
    e.stopPropagation();
    const open = menu.classList.contains('show');
    menu.classList.toggle('show', !open);
    btn.setAttribute('aria-expanded', String(!open));
  });

  // Cerrar al hacer click fuera
  document.addEventListener('click', function () {
    menu.classList.remove('show');
    btn.setAttribute('aria-expanded', 'false');
  });
})();

/* ── Sidebar filtro mobile toggle ───────────── */
(function () {
  const btn = document.getElementById('sidebarToggleBtn');
  const col = document.getElementById('sidebarCollapse');
  if (!btn || !col) return;
  btn.addEventListener('click', () => {
    col.classList.toggle('open');
    btn.querySelector('.sidebar-arrow').style.transform =
      col.classList.contains('open') ? 'rotate(180deg)' : '';
  });
})();

/* ── Fade-in on scroll (IntersectionObserver) ─ */
(function () {
  const els = document.querySelectorAll('.fade-up');
  if (!els.length) return;
  const obs = new IntersectionObserver((entries) => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        e.target.classList.add('visible');
        obs.unobserve(e.target);
      }
    });
  }, { threshold: 0.12 });
  els.forEach(el => obs.observe(el));
})();

/* ── Slide-in ¿Por qué elegirnos? ──────────── */
(function () {
  const els = document.querySelectorAll('.cgm-porque-item');
  if (!els.length) return;
  const obs = new IntersectionObserver((entries) => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        e.target.classList.add('cgm-visible');
        obs.unobserve(e.target);
      }
    });
  }, { threshold: 0.15 });
  els.forEach(el => obs.observe(el));
})();

/* ── Blog filtro por categoría ─────────────── */
(function () {
  const pills = document.querySelectorAll('.cgm-filter-pill');
  if (!pills.length) return;
  pills.forEach(pill => {
    pill.addEventListener('click', function () {
      pills.forEach(p => p.classList.remove('active'));
      this.classList.add('active');
      const cat = this.dataset.cat || '';
      const url = new URL(window.location.href);
      if (cat) url.searchParams.set('cat', cat);
      else url.searchParams.delete('cat');
      window.location.href = url.toString();
    });
  });
})();

/* ── Toast helper ────────────────────────────── */
function cgmToast(msg, type = 'success') {
  let container = document.getElementById('cgmToastContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'cgmToastContainer';
    container.style.cssText = 'position:fixed;top:80px;right:20px;z-index:99999;display:flex;flex-direction:column;gap:8px;';
    document.body.appendChild(container);
  }
  const t = document.createElement('div');
  t.className = `toast align-items-center border-0 show text-bg-${type === 'success' ? 'success' : 'danger'}`;
  t.setAttribute('role', 'alert');
  t.innerHTML = `<div class="d-flex"><div class="toast-body">${msg}</div>
    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>`;
  container.appendChild(t);
  t.querySelector('button').addEventListener('click', () => t.remove());
  setTimeout(() => t.remove(), 3500);
}

/* ── Formulario de contacto AJAX ─────────────── */
(function () {
  const form = document.getElementById('cgmContactForm');
  if (!form) return;
  form.addEventListener('submit', async function (e) {
    e.preventDefault();
    const btn = form.querySelector('[type=submit]');
    const origText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Enviando…';
    const data = Object.fromEntries(new FormData(form));
    try {
      const resp = await fetch('/api/contacto', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
      const json = await resp.json();
      if (json.ok) {
        cgmToast('¡Mensaje enviado! Nos comunicaremos contigo pronto.');
        form.reset();
      } else {
        cgmToast(json.error || 'Error al enviar el formulario.', 'error');
      }
    } catch {
      cgmToast('Error de conexión. Intenta nuevamente.', 'error');
    } finally {
      btn.disabled = false;
      btn.innerHTML = origText;
    }
  });
})();

/* ── Formulario denuncia AJAX ────────────────── */
(function () {
  const form = document.getElementById('cgmDenunciaForm');
  if (!form) return;
  form.addEventListener('submit', async function (e) {
    e.preventDefault();
    const btn = form.querySelector('[type=submit]');
    btn.disabled = true;
    const origText = btn.innerHTML;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Enviando…';
    const data = Object.fromEntries(new FormData(form));
    try {
      const resp = await fetch('/api/denuncia', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
      const json = await resp.json();
      if (json.ok) {
        document.getElementById('denunciaSuccess').style.display = 'block';
        form.style.display = 'none';
      } else {
        cgmToast(json.error || 'Error al enviar.', 'error');
      }
    } catch {
      cgmToast('Error de conexión.', 'error');
    } finally {
      btn.disabled = false;
      btn.innerHTML = origText;
    }
  });
})();

/* ── Formulario proveedor AJAX ───────────────── */
(function () {
  const form = document.getElementById('cgmProveedorForm');
  if (!form) return;
  form.addEventListener('submit', async function (e) {
    e.preventDefault();
    const btn = form.querySelector('[type=submit]');
    btn.disabled = true;
    const origText = btn.innerHTML;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Enviando…';
    const data = Object.fromEntries(new FormData(form));
    try {
      const resp = await fetch('/api/proveedor', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
      const json = await resp.json();
      if (json.ok) {
        document.getElementById('proveedorSuccess').style.display = 'block';
        form.style.display = 'none';
      } else {
        cgmToast(json.error || 'Error al enviar.', 'error');
      }
    } catch {
      cgmToast('Error de conexión.', 'error');
    } finally {
      btn.disabled = false;
      btn.innerHTML = origText;
    }
  });
})();
