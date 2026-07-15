<?php
declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Headers: Authorization, Content-Type');
header('Access-Control-Allow-Methods: POST, OPTIONS');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(204);
    exit;
}

function json_response(array $data, int $status = 200): void {
    http_response_code($status);
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}

function bearer_token(): string {
    $header = $_SERVER['HTTP_AUTHORIZATION'] ?? $_SERVER['REDIRECT_HTTP_AUTHORIZATION'] ?? '';
    if (stripos($header, 'Bearer ') === 0) {
        return trim(substr($header, 7));
    }
    return '';
}

function require_config(): array {
    $path = '/www/wwwroot/geo.allgood.cn/storage/sync_config.php';
    if (!is_file($path)) {
        json_response(['success' => false, 'message' => 'sync config missing'], 500);
    }
    return require $path;
}

function pdo_conn(array $config): PDO {
    $dsn = sprintf('mysql:host=%s;port=%d;dbname=%s;charset=utf8mb4', $config['db_host'], $config['db_port'], $config['db_name']);
    return new PDO($dsn, $config['db_user'], $config['db_pass'], [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        PDO::ATTR_EMULATE_PREPARES => false,
    ]);
}

function result_summary(array $result): array {
    $refs = $result['references'] ?? [];
    if (is_string($refs)) {
        $decoded = json_decode($refs, true);
        $refs = is_array($decoded) ? $decoded : [];
    }
    if (!is_array($refs)) $refs = [];

    $domains = [];
    foreach ($refs as $ref) {
        if (!is_array($ref)) continue;
        $url = trim((string)($ref['url'] ?? $ref['link'] ?? $ref['domain'] ?? ''));
        if ($url === '') continue;
        if (!preg_match('#^https?://#i', $url)) $url = 'https://' . $url;
        $host = strtolower((string)(parse_url($url, PHP_URL_HOST) ?: ''));
        $host = (string)preg_replace('/^www\./', '', $host);
        if ($host !== '') $domains[] = $host;
    }

    $screenshotPath = trim((string)($result['screenshot_path'] ?? ''));
    $screenshotUrl = trim((string)($result['screenshot_url'] ?? ''));
    return [
        'has_screenshot' => ($screenshotPath !== '' || $screenshotUrl !== '') ? 1 : 0,
        'reference_count' => count($refs),
        'reference_domains' => json_encode($domains, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
    ];
}

function ensure_schema(PDO $pdo): void {
    $sqls = [
        "CREATE TABLE IF NOT EXISTS geo_sync_users (
            id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
            cloud_user_id BIGINT UNSIGNED NULL,
            install_id VARCHAR(64) NOT NULL,
            local_id INT NOT NULL,
            user_key VARCHAR(255) NOT NULL,
            username VARCHAR(120) NOT NULL,
            email VARCHAR(255) NOT NULL,
            payload LONGTEXT NOT NULL,
            local_created_at DATETIME NULL,
            synced_at DATETIME NOT NULL,
            UNIQUE KEY uniq_install_user (install_id, local_id),
            KEY idx_user_key (user_key)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
        "CREATE TABLE IF NOT EXISTS geo_sync_tasks (
            id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
            cloud_user_id BIGINT UNSIGNED NULL,
            install_id VARCHAR(64) NOT NULL,
            local_id INT NOT NULL,
            local_user_id INT NOT NULL,
            user_key VARCHAR(255) NOT NULL,
            name VARCHAR(255) NOT NULL,
            status VARCHAR(40) NULL,
            payload LONGTEXT NOT NULL,
            local_created_at DATETIME NULL,
            local_updated_at DATETIME NULL,
            synced_at DATETIME NOT NULL,
            UNIQUE KEY uniq_install_task (install_id, local_id),
            KEY idx_user_task (install_id, user_key),
            KEY idx_status (status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
        "CREATE TABLE IF NOT EXISTS geo_sync_results (
            id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
            cloud_user_id BIGINT UNSIGNED NULL,
            install_id VARCHAR(64) NOT NULL,
            local_id INT NOT NULL,
            local_task_id INT NOT NULL,
            local_user_id INT NOT NULL,
            user_key VARCHAR(255) NOT NULL,
            platform VARCHAR(80) NOT NULL,
            question MEDIUMTEXT NOT NULL,
            has_brand_exposure TINYINT(1) NOT NULL DEFAULT 0,
            has_screenshot TINYINT(1) NOT NULL DEFAULT 0,
            reference_count INT UNSIGNED NOT NULL DEFAULT 0,
            reference_domains TEXT NULL,
            payload LONGTEXT NOT NULL,
            local_created_at DATETIME NULL,
            synced_at DATETIME NOT NULL,
            result_at DATETIME GENERATED ALWAYS AS (COALESCE(local_created_at, synced_at)) STORED,
            UNIQUE KEY uniq_install_result (install_id, local_id),
            KEY idx_user_result (install_id, user_key),
            KEY idx_task_result (install_id, local_task_id),
            KEY idx_platform (platform),
            KEY idx_results_user_time (cloud_user_id, result_at DESC, id DESC),
            KEY idx_results_user_task_time (cloud_user_id, local_task_id, result_at DESC, id DESC),
            KEY idx_results_user_platform_time (cloud_user_id, platform, result_at DESC, id DESC),
            KEY idx_results_user_task_platform_time (cloud_user_id, local_task_id, platform, result_at DESC, id DESC),
            KEY idx_results_user_exposed_time (cloud_user_id, has_brand_exposure, result_at DESC, id DESC),
            KEY idx_results_user_daily (cloud_user_id, result_at, has_brand_exposure)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
        "CREATE TABLE IF NOT EXISTS geo_sync_manuscripts (
            id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
            cloud_user_id BIGINT UNSIGNED NULL,
            install_id VARCHAR(64) NOT NULL,
            local_id INT NOT NULL,
            local_user_id INT NOT NULL,
            user_key VARCHAR(255) NOT NULL,
            title VARCHAR(255) NOT NULL,
            url TEXT NOT NULL,
            payload LONGTEXT NOT NULL,
            local_created_at DATETIME NULL,
            synced_at DATETIME NOT NULL,
            UNIQUE KEY uniq_install_manuscript (install_id, local_id),
            KEY idx_user_manuscript (install_id, user_key)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
        "CREATE TABLE IF NOT EXISTS geo_sync_sentiment_configs (
            id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
            cloud_user_id BIGINT UNSIGNED NULL,
            install_id VARCHAR(64) NOT NULL,
            local_id INT NOT NULL,
            local_user_id INT NOT NULL,
            user_key VARCHAR(255) NOT NULL,
            name VARCHAR(120) NOT NULL,
            is_default TINYINT(1) NOT NULL DEFAULT 0,
            payload LONGTEXT NOT NULL,
            local_created_at DATETIME NULL,
            local_updated_at DATETIME NULL,
            synced_at DATETIME NOT NULL,
            UNIQUE KEY uniq_install_config (install_id, local_id),
            KEY idx_user_config (install_id, user_key)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
        "CREATE TABLE IF NOT EXISTS geo_sync_runs (
            id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
            cloud_user_id BIGINT UNSIGNED NULL,
            install_id VARCHAR(64) NOT NULL,
            local_user_id INT NOT NULL,
            user_key VARCHAR(255) NOT NULL,
            status VARCHAR(40) NOT NULL,
            message TEXT NULL,
            counts_json LONGTEXT NULL,
            synced_at DATETIME NOT NULL,
            KEY idx_sync_run (install_id, user_key, synced_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
    ];
    foreach ($sqls as $sql) {
        $pdo->exec($sql);
    }
    foreach (['geo_sync_users', 'geo_sync_tasks', 'geo_sync_results', 'geo_sync_manuscripts', 'geo_sync_sentiment_configs', 'geo_sync_runs'] as $table) {
        try { $pdo->exec("ALTER TABLE {$table} ADD COLUMN cloud_user_id BIGINT UNSIGNED NULL AFTER id"); } catch (Throwable $e) {}
        try { $pdo->exec("ALTER TABLE {$table} ADD KEY idx_cloud_user (cloud_user_id)"); } catch (Throwable $e) {}
    }
    try { $pdo->exec("ALTER TABLE geo_sync_results ADD COLUMN result_at DATETIME GENERATED ALWAYS AS (COALESCE(local_created_at, synced_at)) STORED"); } catch (Throwable $e) {}
    try { $pdo->exec("ALTER TABLE geo_sync_results ADD COLUMN has_screenshot TINYINT(1) NOT NULL DEFAULT 0 AFTER has_brand_exposure"); } catch (Throwable $e) {}
    try { $pdo->exec("ALTER TABLE geo_sync_results ADD COLUMN reference_count INT UNSIGNED NOT NULL DEFAULT 0 AFTER has_screenshot"); } catch (Throwable $e) {}
    try { $pdo->exec("ALTER TABLE geo_sync_results ADD COLUMN reference_domains TEXT NULL AFTER reference_count"); } catch (Throwable $e) {}
    $resultIndexes = [
        'idx_results_user_time' => 'cloud_user_id, result_at DESC, id DESC',
        'idx_results_user_task_time' => 'cloud_user_id, local_task_id, result_at DESC, id DESC',
        'idx_results_user_platform_time' => 'cloud_user_id, platform, result_at DESC, id DESC',
        'idx_results_user_task_platform_time' => 'cloud_user_id, local_task_id, platform, result_at DESC, id DESC',
        'idx_results_user_exposed_time' => 'cloud_user_id, has_brand_exposure, result_at DESC, id DESC',
        'idx_results_user_daily' => 'cloud_user_id, result_at, has_brand_exposure',
    ];
    foreach ($resultIndexes as $name => $columns) {
        try { $pdo->exec("ALTER TABLE geo_sync_results ADD KEY {$name} ({$columns})"); } catch (Throwable $e) {}
    }

    $uniqueKeys = [
        'geo_sync_users' => 'uniq_install_user',
        'geo_sync_tasks' => 'uniq_install_task',
        'geo_sync_results' => 'uniq_install_result',
        'geo_sync_manuscripts' => 'uniq_install_manuscript',
        'geo_sync_sentiment_configs' => 'uniq_install_config',
    ];
    foreach ($uniqueKeys as $table => $index) {
        $stmt = $pdo->prepare('SELECT GROUP_CONCAT(column_name ORDER BY seq_in_index) AS columns FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name=? AND index_name=? GROUP BY index_name');
        $stmt->execute([$table, $index]);
        $columns = strtolower((string)($stmt->fetchColumn() ?: ''));
        if ($columns === 'cloud_user_id,install_id,local_id') {
            continue;
        }
        try { $pdo->exec("ALTER TABLE {$table} DROP INDEX {$index}"); } catch (Throwable $e) {}
        try { $pdo->exec("ALTER TABLE {$table} ADD UNIQUE KEY {$index} (cloud_user_id, install_id, local_id)"); } catch (Throwable $e) {}
    }
}

function cloud_user_id_for_token(PDO $pdo, array $config, string $token): int {
    $hash = hash('sha256', $token);
    $stmt = $pdo->prepare('SELECT id FROM geo_cloud_users WHERE api_token_hash = ? LIMIT 1');
    $stmt->execute([$hash]);
    $user = $stmt->fetch();
    if ($user) return (int)$user['id'];
    $stmt = $pdo->prepare('SELECT cloud_user_id FROM geo_cloud_tokens WHERE token_hash = ? AND revoked_at IS NULL LIMIT 1');
    $stmt->execute([$hash]);
    $tokenRow = $stmt->fetch();
    if ($tokenRow) {
        $pdo->prepare('UPDATE geo_cloud_tokens SET last_used_at=? WHERE token_hash=?')->execute([date('Y-m-d H:i:s'), $hash]);
        return (int)$tokenRow['cloud_user_id'];
    }
    if (hash_equals($config['token_sha256'], $hash)) {
        $stmt = $pdo->prepare('SELECT id FROM geo_cloud_users WHERE api_token_hash = ? LIMIT 1');
        $stmt->execute([$config['token_sha256']]);
        $user = $stmt->fetch();
        if ($user) return (int)$user['id'];
    }
    return 0;
}

function clean_ids(array $rows): array {
    $ids = [];
    foreach ($rows as $row) {
        if (isset($row['local_id'])) {
            $ids[] = (int) $row['local_id'];
        }
    }
    return $ids;
}

function delete_missing(PDO $pdo, string $table, int $cloudUserId, string $installId, string $userKey, array $keepIds): void {
    if ($keepIds) {
        $placeholders = implode(',', array_fill(0, count($keepIds), '?'));
        $sql = "DELETE FROM {$table} WHERE cloud_user_id = ? AND install_id = ? AND user_key = ? AND local_id NOT IN ({$placeholders})";
        $stmt = $pdo->prepare($sql);
        $stmt->execute(array_merge([$cloudUserId, $installId, $userKey], $keepIds));
    } else {
        $stmt = $pdo->prepare("DELETE FROM {$table} WHERE cloud_user_id = ? AND install_id = ? AND user_key = ?");
        $stmt->execute([$cloudUserId, $installId, $userKey]);
    }
}

function upsert(PDO $pdo, string $table, array $row, array $updateFields): void {
    $cols = array_keys($row);
    $placeholders = implode(',', array_fill(0, count($cols), '?'));
    $updates = implode(',', array_map(fn($field) => "{$field}=VALUES({$field})", $updateFields));
    $sql = "INSERT INTO {$table} (" . implode(',', $cols) . ") VALUES ({$placeholders}) ON DUPLICATE KEY UPDATE {$updates}";
    $stmt = $pdo->prepare($sql);
    $stmt->execute(array_values($row));
}

function payload_json(array $payload): string {
    return json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    json_response(['success' => false, 'message' => 'method not allowed'], 405);
}

$config = require_config();
$token = bearer_token();
$raw = file_get_contents('php://input');
$data = json_decode($raw ?: '', true);
if (!is_array($data)) {
    json_response(['success' => false, 'message' => 'invalid json'], 400);
}

$installId = (string)($data['install_id'] ?? '');
$userKey = (string)($data['user_key'] ?? '');
$user = $data['user'] ?? null;
if ($installId === '' || $userKey === '' || !is_array($user)) {
    json_response(['success' => false, 'message' => 'install_id, user_key and user are required'], 400);
}

$now = date('Y-m-d H:i:s');
$tasks = is_array($data['tasks'] ?? null) ? $data['tasks'] : [];
$results = is_array($data['results'] ?? null) ? $data['results'] : [];
$manuscripts = is_array($data['manuscripts'] ?? null) ? $data['manuscripts'] : [];
$configs = is_array($data['sentiment_configs'] ?? null) ? $data['sentiment_configs'] : [];
$localUserId = (int)($user['id'] ?? 0);

try {
    $pdo = pdo_conn($config);
    ensure_schema($pdo);
    $cloudUserId = cloud_user_id_for_token($pdo, $config, $token);
    if ($token === '' || $cloudUserId <= 0) {
        json_response(['success' => false, 'message' => 'unauthorized'], 401);
    }
    if ($cloudUserId === 16) {
        json_response(['success' => false, 'message' => 'online demo is read-only'], 403);
    }
    $pdo->beginTransaction();

    upsert($pdo, 'geo_sync_users', [
        'cloud_user_id' => $cloudUserId,
        'install_id' => $installId,
        'local_id' => $localUserId,
        'user_key' => $userKey,
        'username' => (string)($user['username'] ?? ''),
        'email' => (string)($user['email'] ?? ''),
        'payload' => payload_json($user),
        'local_created_at' => $user['created_at'] ?? null,
        'synced_at' => $now,
    ], ['cloud_user_id', 'user_key', 'username', 'email', 'payload', 'local_created_at', 'synced_at']);

    foreach ($tasks as $task) {
        upsert($pdo, 'geo_sync_tasks', [
            'cloud_user_id' => $cloudUserId,
            'install_id' => $installId,
            'local_id' => (int)($task['local_id'] ?? $task['id'] ?? 0),
            'local_user_id' => $localUserId,
            'user_key' => $userKey,
            'name' => (string)($task['name'] ?? ''),
            'status' => $task['status'] ?? null,
            'payload' => payload_json($task),
            'local_created_at' => $task['created_at'] ?? null,
            'local_updated_at' => $task['updated_at'] ?? null,
            'synced_at' => $now,
        ], ['cloud_user_id', 'local_user_id', 'user_key', 'name', 'status', 'payload', 'local_created_at', 'local_updated_at', 'synced_at']);
    }

    foreach ($results as $result) {
        $summary = result_summary($result);
        upsert($pdo, 'geo_sync_results', [
            'cloud_user_id' => $cloudUserId,
            'install_id' => $installId,
            'local_id' => (int)($result['local_id'] ?? $result['id'] ?? 0),
            'local_task_id' => (int)($result['local_task_id'] ?? $result['task_id'] ?? 0),
            'local_user_id' => $localUserId,
            'user_key' => $userKey,
            'platform' => (string)($result['platform'] ?? ''),
            'question' => (string)($result['question'] ?? ''),
            'has_brand_exposure' => !empty($result['has_brand_exposure']) ? 1 : 0,
            'has_screenshot' => $summary['has_screenshot'],
            'reference_count' => $summary['reference_count'],
            'reference_domains' => $summary['reference_domains'],
            'payload' => payload_json($result),
            'local_created_at' => $result['created_at'] ?? null,
            'synced_at' => $now,
        ], ['cloud_user_id', 'local_task_id', 'local_user_id', 'user_key', 'platform', 'question', 'has_brand_exposure', 'has_screenshot', 'reference_count', 'reference_domains', 'payload', 'local_created_at', 'synced_at']);
    }

    foreach ($manuscripts as $manuscript) {
        upsert($pdo, 'geo_sync_manuscripts', [
            'cloud_user_id' => $cloudUserId,
            'install_id' => $installId,
            'local_id' => (int)($manuscript['local_id'] ?? $manuscript['id'] ?? 0),
            'local_user_id' => $localUserId,
            'user_key' => $userKey,
            'title' => (string)($manuscript['title'] ?? ''),
            'url' => (string)($manuscript['url'] ?? ''),
            'payload' => payload_json($manuscript),
            'local_created_at' => $manuscript['created_at'] ?? null,
            'synced_at' => $now,
        ], ['cloud_user_id', 'local_user_id', 'user_key', 'title', 'url', 'payload', 'local_created_at', 'synced_at']);
    }

    foreach ($configs as $syncConfig) {
        upsert($pdo, 'geo_sync_sentiment_configs', [
            'cloud_user_id' => $cloudUserId,
            'install_id' => $installId,
            'local_id' => (int)($syncConfig['local_id'] ?? $syncConfig['id'] ?? 0),
            'local_user_id' => $localUserId,
            'user_key' => $userKey,
            'name' => (string)($syncConfig['name'] ?? ''),
            'is_default' => !empty($syncConfig['is_default']) ? 1 : 0,
            'payload' => payload_json($syncConfig),
            'local_created_at' => $syncConfig['created_at'] ?? null,
            'local_updated_at' => $syncConfig['updated_at'] ?? null,
            'synced_at' => $now,
        ], ['cloud_user_id', 'local_user_id', 'user_key', 'name', 'is_default', 'payload', 'local_created_at', 'local_updated_at', 'synced_at']);
    }

    delete_missing($pdo, 'geo_sync_tasks', $cloudUserId, $installId, $userKey, clean_ids($tasks));
    delete_missing($pdo, 'geo_sync_results', $cloudUserId, $installId, $userKey, clean_ids($results));
    delete_missing($pdo, 'geo_sync_manuscripts', $cloudUserId, $installId, $userKey, clean_ids($manuscripts));
    delete_missing($pdo, 'geo_sync_sentiment_configs', $cloudUserId, $installId, $userKey, clean_ids($configs));

    $counts = [
        'users' => 1,
        'tasks' => count($tasks),
        'results' => count($results),
        'manuscripts' => count($manuscripts),
        'sentiment_configs' => count($configs),
    ];
    $stmt = $pdo->prepare('INSERT INTO geo_sync_runs (cloud_user_id, install_id, local_user_id, user_key, status, message, counts_json, synced_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)');
    $stmt->execute([$cloudUserId, $installId, $localUserId, $userKey, 'success', 'workspace synced via api', payload_json($counts), $now]);

    $pdo->commit();
    json_response(['success' => true, 'install_id' => $installId, 'user_key' => $userKey, 'counts' => $counts, 'synced_at' => $now]);
} catch (Throwable $e) {
    if (isset($pdo) && $pdo->inTransaction()) {
        $pdo->rollBack();
    }
    json_response(['success' => false, 'message' => 'sync failed', 'error' => $e->getMessage()], 500);
}
