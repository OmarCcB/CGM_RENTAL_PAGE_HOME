/* ═══════════════════════════════════════════════
   CGM RENTAL — cotizador.js
   Pre-carga productos del carrito en el formulario
   de cotización en la página de contacto
   ═══════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', async function () {
  const productosInput = document.getElementById('cotizadorProductos');
  if (!productosInput) return;

  try {
    const resp = await fetch('/api/cart');
    const json = await resp.json();
    const cart  = json.cart || {};
    const items = Object.values(cart);
    if (items.length > 0) {
      const lista = items.map(i => `${i.qty} x ${i.nombre.toUpperCase()}`).join('<br>');
      productosInput.value = lista;
      const notice = document.getElementById('cotizadorNotice');
      if (notice) {
        notice.textContent = `Equipos del carrito pre-cargados: ${lista}`;
        notice.style.display = 'block';
      }
    }
  } catch (e) {
    // silencioso
  }
});
