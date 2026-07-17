<?php
declare(strict_types=1);

if (!defined('GEO_SYNC_SCHEMA_ONLY')) define('GEO_SYNC_SCHEMA_ONLY', true);
require_once __DIR__ . '/sync/index.php';

if (!defined('GEO_ASSETS_SCHEMA_ONLY')) define('GEO_ASSETS_SCHEMA_ONLY', true);
require_once __DIR__ . '/sync/assets/index.php';

if (!defined('GEO_REMOTE_SCHEMA_ONLY')) define('GEO_REMOTE_SCHEMA_ONLY', true);
require_once __DIR__ . '/remote-tasks/index.php';

function geo_ensure_workspace_schema(PDO $pdo): void {
    geo_sync_ensure_schema($pdo);
    geo_assets_ensure_schema($pdo);
    geo_remote_ensure_schema($pdo);
}
