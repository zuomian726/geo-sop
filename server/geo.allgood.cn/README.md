# GEO-SOP cloud application

This directory is the deployable source for `geo.allgood.cn`. It contains the
public site, account pages, cloud dashboard, synchronization API, remote task
API, Demo, migrations, and every static asset referenced by those pages.

## Runtime requirements

- Nginx or Apache with PHP 8.1+
- PHP extensions: PDO MySQL, cURL, mbstring, JSON, ZIP
- MySQL 5.7+ or MySQL 8
- HTTPS

Point the virtual host document root at this directory. The `storage` directory
must be writable by PHP because it stores synchronized screenshots and private
runtime state. Block direct access to PHP and configuration files under
`storage` at the web-server layer.

## Private configuration

Production credentials do not belong in Git. Copy
`storage/sync_config.example.php` to a private location outside the document
root and expose its absolute path as `GEO_SYNC_CONFIG` in the PHP-FPM pool.
Provide these environment variables to PHP-FPM:

```text
GEO_DB_HOST
GEO_DB_PORT
GEO_DB_NAME
GEO_DB_USER
GEO_DB_PASSWORD
GEO_LEGACY_SYNC_TOKEN
GEO_PUBLIC_BASE_URL
```

`GEO_LEGACY_SYNC_TOKEN` only supports older API clients. New desktop logins use
revocable tokens from `geo_cloud_tokens`. Generate it as a long random value;
never commit it or any resulting hash tied to a production account.

SMS and WeChat login are disabled by default. Enabling either requires an
explicit feature flag and provider credentials in the private configuration.

## Release checks

From the repository root:

```bash
python -m unittest discover -s tests -v
GEO_DEMO_USERNAME=... GEO_DEMO_PASSWORD=... \
  python tools/smoke_cloud_site.py https://geo.allgood.cn
```

The cloud smoke test verifies the public pages, release manifest, Demo login,
dashboard queries, Excel export, and the Demo read-only task boundary.
