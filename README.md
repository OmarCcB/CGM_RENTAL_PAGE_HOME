# CGM Rental — Sitio Web Corporativo

Plataforma web corporativa de **CGM Rental**, empresa líder en alquiler de maquinaria pesada en Perú y Argentina.

## Descripción

Aplicación web desarrollada en **Flask (Python)** que gestiona el catálogo de equipos, blog de novedades, formularios de cotización y un panel de administración completo para el equipo interno de CGM Rental.

El sitio opera bajo un sistema **multi-país** con vitrinas independientes para Perú (`/pe/`) y Argentina (`/ar/`), con detección automática de geolocalización vía Cloudflare.

## Stack tecnológico

| Capa | Tecnología |
|------|-----------|
| Backend | Python 3 / Flask 3.1 |
| Base de datos | SQLite (WAL mode) |
| Servidor WSGI | Gunicorn (4 workers, puerto 8015) |
| Frontend | Bootstrap 5.3 + Swiper 11 (assets locales) |
| Autenticación admin | Azure Active Directory (OAuth 2.0 / Microsoft 365) |
| Imágenes | Pillow — conversión automática a WebP |
| Hosting | Servidor Linux — `/var/www/cgmrental` |

## Módulos principales

- **Catálogo de equipos** — Construcción, Minería, Agrícola, Energía (PE y AR)
- **Panel de administración** (`/admin`) — CRUD de productos, banners, blog, sucursales y contacto
- **Blog / Novedades** — Posts con imagen, categoría y visibilidad por país
- **Formularios de cotización** — Integración con Salesforce Web-to-Lead
- **Capacitación** — Programas formativos con certificado CGM Rental
- **Nuestros locales** — Mapa interactivo con sucursales PE y AR
- **Leasing Operativo** — Página informativa del servicio financiero

## Estructura del proyecto

```
CGM_RENTAL_PAGE_HOME/
├── app.py                  # Aplicación principal Flask
├── database.py             # Conexión SQLite y migraciones
├── countries.py            # Configuración multi-país PE / AR
├── cache.py                # Cache en memoria con TTL
├── products.json           # Fuente de datos del catálogo
├── data/
│   └── cgm.db              # Base de datos SQLite
├── admin/
│   └── routes.py           # Blueprint del panel de administración
├── static/
│   ├── css/                # Estilos (cgm.css)
│   ├── js/                 # Scripts
│   ├── products/           # Imágenes de equipos por slug
│   └── images/             # Banners, logos, blog
└── templates/              # HTML Jinja2
    ├── pages/              # Páginas públicas
    └── admin/              # Vistas del panel admin
```

## Despliegue en producción

El proyecto corre en el servidor `mq-vtl-prd-cgm` bajo el usuario `admincgm`.

```bash
# Iniciar
sudo systemctl start cgmrental

# Reiniciar (después de subir cambios)
sudo systemctl restart cgmrental

# Ver estado
sudo systemctl status cgmrental

# Ver consola en vivo
screen -r cgmrental
```

## Variables de entorno requeridas

Crear un archivo `.env` en la raíz del proyecto con:

```
SECRET_KEY=...
AZURE_CLIENT_ID=...
AZURE_CLIENT_SECRET=...
AZURE_TENANT_ID=...
AZURE_REDIRECT_URI=...
ADMIN_ALLOWED_EMAILS=correo1@cgmrental.com,correo2@cgmrental.com
```

## Cliente

**CGM Rental** — [cgmrental.com](https://cgmrental.com)
