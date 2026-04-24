# Configuración GeoIP — Redirección automática PE / AR

## Cómo funciona
Cuando alguien entra a `cgmrental.com/`:
- IP de **Perú** → redirige a `/pe/`
- IP de **Argentina** → redirige a `/ar/`
- Cualquier otro país → redirige a `/pe/` (default)
- IPs locales (127.x, 192.168.x) → no redirige (muestra `/pe/` para desarrollo)

---

## Instalación en el servidor (Azure VPS)

### 1. Instalar la librería Python

```bash
cd /var/www/cgmrental
source venv/bin/activate
pip install geoip2
```

### 2. Descargar la base de datos MaxMind GeoLite2 (GRATIS)

1. Crear cuenta gratis en: https://www.maxmind.com/en/geolite2/signup
2. Ir a "Download Files" → descargar **GeoLite2-Country** (.mmdb)
3. Subir el archivo al servidor:

```bash
# Desde tu PC local (reemplaza usuario e IP de tu VPS)
scp GeoLite2-Country.mmdb usuario@IP_VPS:/var/www/cgmrental/GeoLite2-Country.mmdb
```

### 3. Reiniciar la aplicación

```bash
sudo systemctl restart cgmrental
# o si usas gunicorn directo:
pkill gunicorn
cd /var/www/cgmrental
source venv/bin/activate
gunicorn -w 4 -b 0.0.0.0:8015 app:app --daemon
```

### 4. Configurar Nginx para pasar la IP real

Asegúrate de que tu Nginx tenga estas líneas en el bloque `location /`:

```nginx
location / {
    proxy_pass         http://127.0.0.1:8015;
    proxy_set_header   Host              $host;
    proxy_set_header   X-Real-IP         $remote_addr;
    proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header   X-Forwarded-Proto $scheme;
}
```

---

## Alternativa: Redirección en Nginx (sin Python, más rápido)

Si prefieres que Nginx haga la redirección antes de llegar a Flask:

```bash
# Instalar módulo GeoIP2 para Nginx
sudo apt install libnginx-mod-http-geoip2 libmaxminddb0 libmaxminddb-dev

# Crear carpeta para la base de datos
sudo mkdir -p /etc/nginx/geoip
sudo cp GeoLite2-Country.mmdb /etc/nginx/geoip/
```

Agrega en `/etc/nginx/nginx.conf` (dentro del bloque `http {}`):

```nginx
geoip2 /etc/nginx/geoip/GeoLite2-Country.mmdb {
    $geoip2_country_code default=PE country iso_code;
}

map $geoip2_country_code $cgm_country_path {
    AR  /ar/;
    PE  /pe/;
    default /pe/;
}
```

Y en el bloque `server`, antes del `location /`:

```nginx
# Redirigir raíz según país
location = / {
    return 302 $cgm_country_path;
}
```

---

## Probar en local (sin base de datos)
Sin el archivo `GeoLite2-Country.mmdb`, la app funciona normal:
- `http://127.0.0.1:5000/` → va a `/pe/` (DEFAULT_COUNTRY)
- No hay errores ni excepciones
