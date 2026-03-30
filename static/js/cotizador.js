/**
 * CGM Rental - Cotizador (carrito de cotización)
 * Reemplaza la funcionalidad WooCommerce del sitio original.
 * Maneja: agregar productos, panel flotante, envío por WhatsApp.
 */
(function () {
  "use strict";

  var STORAGE_KEY = "cgm_cotizador";
  var WA_NUMBER = "51943567445"; // Número de WhatsApp de CGM Rental

  // ── Estado ──
  var cart = loadCart();

  // ── Inicialización ──
  document.addEventListener("DOMContentLoaded", init);

  function init() {
    renderCart();
    updateCounter();
    bindTriggers();
    bindCotizarButtons();
    bindAddToCartButtons();
    bindRemoveButtons();
    bindCartActions();
  }

  // ── Persistencia ──
  function loadCart() {
    try {
      var data = localStorage.getItem(STORAGE_KEY);
      return data ? JSON.parse(data) : [];
    } catch (e) {
      return [];
    }
  }

  function saveCart() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(cart));
    } catch (e) {}
  }

  // ── Toggle del panel ──
  function bindTriggers() {
    var triggers = document.querySelectorAll("[data-woofc-trigger]");
    for (var i = 0; i < triggers.length; i++) {
      triggers[i].addEventListener("click", function (e) {
        e.preventDefault();
        toggleCart();
      });
    }
  }

  function toggleCart() {
    var panel = document.querySelector(".woofc-cart");
    if (panel) {
      panel.classList.toggle("woofc-cart--open");
    }
    var overlay = document.querySelector(".woofc-overlay");
    if (overlay) {
      overlay.classList.toggle("woofc-overlay--open");
    }
  }

  function openCart() {
    var panel = document.querySelector(".woofc-cart");
    if (panel) panel.classList.add("woofc-cart--open");
    var overlay = document.querySelector(".woofc-overlay");
    if (overlay) overlay.classList.add("woofc-overlay--open");
  }

  function closeCart() {
    var panel = document.querySelector(".woofc-cart");
    if (panel) panel.classList.remove("woofc-cart--open");
    var overlay = document.querySelector(".woofc-overlay");
    if (overlay) overlay.classList.remove("woofc-overlay--open");
  }

  // ── Botones COTIZAR en grilla de productos ──
  function bindCotizarButtons() {
    var buttons = document.querySelectorAll("a.view-product-button");
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].addEventListener("click", function (e) {
        e.preventDefault();
        var href = this.getAttribute("href") || "";
        var slug = extractSlug(href);
        var nombre = "";
        var imagen = "";

        // Buscar nombre, imagen y tags del producto en el card padre
        var tags = "";
        var card =
          this.closest(".daf-template-loop") ||
          this.closest(".grid-item-cont");
        if (card) {
          var h2 = card.querySelector(
            ".woocommerce-loop-product__title"
          );
          if (h2) nombre = h2.textContent.trim();
          var img = card.querySelector("img");
          if (img) imagen = img.getAttribute("src") || "";
          // Extraer tags del data attribute
          var li = card.closest("[data-cgm-tags]");
          if (li) tags = li.getAttribute("data-cgm-tags") || "";
        }

        if (!nombre) nombre = slug.replace(/-/g, " ").toUpperCase();

        addToCart({ slug: slug, nombre: nombre, imagen: imagen, url: href, tags: tags });
        // Redirigir al carrito de cotización
        window.location.href = "/carrito-2/";
      });
    }
  }

  function extractSlug(href) {
    // /producto/excavadora-hidraulica-210glc/index.html → excavadora-hidraulica-210glc
    var parts = href.replace(/\/index\.html$/, "").replace(/\/$/, "").split("/");
    return parts[parts.length - 1] || "";
  }

  // ── Botón AÑADIR AL CARRITO en página de producto ──
  function bindAddToCartButtons() {
    var buttons = document.querySelectorAll(".cgm-add-to-cart");
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].addEventListener("click", function (e) {
        e.preventDefault();
        var slug = this.getAttribute("data-slug") || "";
        var nombre = this.getAttribute("data-nombre") || slug.replace(/-/g, " ").toUpperCase();
        var imagen = this.getAttribute("data-imagen") || "";
        var url = "/producto/" + slug + "/";

        addToCart({ slug: slug, nombre: nombre, imagen: imagen, url: url });
        // Solo agregar, no redirigir
      });
    }
  }

  // ── Agregar al carrito ──
  function addToCart(item) {
    // Evitar duplicados
    for (var i = 0; i < cart.length; i++) {
      if (cart[i].slug === item.slug) {
        showNotice("Este equipo ya está en tu cotización");
        openCart();
        return;
      }
    }

    cart.push(item);
    saveCart();
    renderCart();
    updateCounter();
    openCart();
    showNotice("Equipo agregado al cotizador");
  }

  // ── Eliminar del carrito ──
  function removeFromCart(slug) {
    cart = cart.filter(function (item) {
      return item.slug !== slug;
    });
    saveCart();
    renderCart();
    updateCounter();
  }

  function bindRemoveButtons() {
    var body = document.getElementById("woofc-cart-body");
    if (!body) return;
    body.addEventListener("click", function (e) {
      var btn = e.target.closest(".woofc-item-remove");
      if (btn) {
        e.preventDefault();
        var slug = btn.getAttribute("data-slug");
        if (slug) removeFromCart(slug);
      }
    });
  }

  // ── Renderizar carrito ──
  function renderCart() {
    var body = document.getElementById("woofc-cart-body");
    if (!body) return;

    if (cart.length === 0) {
      body.innerHTML =
        '<div class="woofc-card"><div class="woofc-card__body">' +
        '<div class="woofc-cart-empty-message">Tu cotizador está vacío.</div>' +
        "</div></div>";
      return;
    }

    var html = "";
    for (var i = 0; i < cart.length; i++) {
      var item = cart[i];
      html +=
        '<div class="woofc-card">' +
        '<div class="woofc-card__body" style="display:flex;align-items:center;padding:10px;gap:10px;">' +
        (item.imagen
          ? '<img src="' + item.imagen + '" alt="" style="width:60px;height:60px;object-fit:cover;border-radius:4px;">'
          : "") +
        '<div style="flex:1;min-width:0;">' +
        '<div style="font-size:13px;font-weight:600;line-height:1.3;">' +
        escapeHtml(item.nombre) +
        "</div>" +
        "</div>" +
        '<div class="woofc-item-remove" data-slug="' + item.slug + '" ' +
        'style="cursor:pointer;color:#999;font-size:18px;padding:5px;" title="Eliminar">&times;</div>' +
        "</div></div>";
    }

    body.innerHTML = html;
  }

  // ── Actualizar contador ──
  function updateCounter() {
    var counter = document.getElementById("woofc-cart-trigger-counter");
    if (counter) {
      counter.textContent = cart.length;
    }
  }

  // ── Notificación ──
  function showNotice(msg) {
    var notice = document.querySelector(".woofc-cart-notice");
    if (!notice) return;
    notice.textContent = msg;
    notice.style.display = "block";
    notice.style.opacity = "1";
    setTimeout(function () {
      notice.style.opacity = "0";
      setTimeout(function () {
        notice.style.display = "none";
      }, 300);
    }, 2000);
  }

  // ── Botones Ver Carrito / Cotizar ──
  function bindCartActions() {
    // Interceptar los links de "Ver Carrito" y "Cotizar" en el footer del woofc
    var cartBtn = document.querySelector(".woofc-cart-cart");
    var checkoutBtn = document.querySelector(".woofc-cart-checkout");

    if (cartBtn) {
      cartBtn.addEventListener("click", function (e) {
        e.preventDefault();
        // Ya está abierto el panel, no hacer nada extra
      });
    }

    if (checkoutBtn) {
      checkoutBtn.addEventListener("click", function (e) {
        e.preventDefault();
        if (cart.length === 0) {
          showNotice("Agrega equipos antes de cotizar");
          return;
        }
        window.location.href = "/carrito-2/";
      });
    }
  }

  // ── Enviar cotización por WhatsApp ──
  function sendWhatsApp() {
    if (cart.length === 0) {
      showNotice("Agrega equipos antes de cotizar");
      return;
    }

    var msg = "Hola! Estoy interesado en cotizar los siguientes equipos:\n\n";
    for (var i = 0; i < cart.length; i++) {
      msg += "- " + cart[i].nombre + "\n";
    }
    msg += "\nPor favor envíenme más información. Gracias!";

    var url = "https://wa.me/" + WA_NUMBER + "?text=" + encodeURIComponent(msg);
    window.open(url, "_blank");
  }

  // ── Utilidades ──
  function escapeHtml(str) {
    var div = document.createElement("div");
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }
})();
