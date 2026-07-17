<?php
declare(strict_types=1);

require_once dirname(__DIR__, 2) . '/common.php';

$geoAssetsSchemaOnly = defined('GEO_ASSETS_SCHEMA_ONLY') && GEO_ASSETS_SCHEMA_ONLY === true;
if (!$geoAssetsSchemaOnly) {
    header('Content-Type: application/json; charset=utf-8');
    header('Access-Control-Allow-Origin: *');
    header('Access-Control-Allow-Headers: Authorization, Content-Type');
    header('Access-Control-Allow-Methods: POST, OPTIONS');
}
if (!$geoAssetsSchemaOnly && $_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(204);
    exit;
}
if (!$geoAssetsSchemaOnly && $_SERVER['REQUEST_METHOD'] !== 'POST') {
    geo_json(['success' => false, 'message' => 'method not allowed'], 405);
}
if (!$geoAssetsSchemaOnly) {
    $requestSize = (int)($_SERVER['CONTENT_LENGTH'] ?? 0);
    if ($requestSize > 32 * 1024 * 1024) {
        geo_json(['success' => false, 'message' => 'request is larger than 32MB'], 413);
    }

    $pdo = geo_pdo();
    geo_ensure_schema($pdo);
    geo_bootstrap($pdo);
    $user = geo_auth_user($pdo);
    if (!$user) {
        geo_json(['success' => false, 'message' => 'unauthorized'], 401);
    }
    if (geo_is_demo_user($user)) {
        geo_json(['success' => false, 'message' => 'online demo is read-only'], 403);
    }
}

function geo_assets_ensure_schema(PDO $pdo): void {
    geo_run_schema_migration($pdo, 'sync_assets', 2026071602, function (PDO $pdo): void {
    $pdo->exec("CREATE TABLE IF NOT EXISTS geo_sync_assets (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        cloud_user_id BIGINT UNSIGNED NOT NULL,
        install_id VARCHAR(64) NOT NULL,
        user_key VARCHAR(255) NOT NULL,
        local_result_id INT NULL,
        local_task_id INT NULL,
        kind VARCHAR(40) NOT NULL,
        platform VARCHAR(80) NULL,
        question MEDIUMTEXT NULL,
        original_name VARCHAR(255) NULL,
        storage_path VARCHAR(800) NULL,
        public_url VARCHAR(1000) NULL,
        mime_type VARCHAR(120) NULL,
        file_size BIGINT UNSIGNED NOT NULL DEFAULT 0,
        sha256 CHAR(64) NULL,
        payload LONGTEXT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        UNIQUE KEY uniq_geo_asset_hash (cloud_user_id, install_id, local_result_id, kind, sha256),
        KEY idx_geo_asset_result (cloud_user_id, install_id, local_result_id),
        KEY idx_geo_asset_user (cloud_user_id, kind, updated_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
    $pdo->exec("CREATE TABLE IF NOT EXISTS geo_sync_stats_snapshots (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        cloud_user_id BIGINT UNSIGNED NOT NULL,
        install_id VARCHAR(64) NOT NULL,
        user_key VARCHAR(255) NOT NULL,
        payload LONGTEXT NOT NULL,
        created_at DATETIME NOT NULL,
        KEY idx_geo_stats_user (cloud_user_id, install_id, created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
    $indexStmt = $pdo->prepare('SELECT GROUP_CONCAT(column_name ORDER BY seq_in_index) FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name=? AND index_name=? GROUP BY index_name');
    $indexStmt->execute(['geo_sync_assets', 'uniq_geo_asset_hash']);
    $columns = strtolower((string)($indexStmt->fetchColumn() ?: ''));
    if ($columns !== 'cloud_user_id,install_id,local_result_id,kind,sha256') {
        geo_schema_exec($pdo, 'ALTER TABLE geo_sync_assets DROP INDEX uniq_geo_asset_hash', [1091]);
        geo_add_index($pdo, 'geo_sync_assets', 'uniq_geo_asset_hash', 'UNIQUE KEY uniq_geo_asset_hash (cloud_user_id, install_id, local_result_id, kind, sha256)');
    }
    });
}

if ($geoAssetsSchemaOnly) {
    return;
}

function geo_assets_mark_result_screenshot(PDO $pdo, int $cloudUserId, string $installId, int $localResultId): void {
    $stmt = $pdo->prepare('UPDATE geo_sync_results SET has_screenshot=1 WHERE cloud_user_id=? AND install_id=? AND local_id=?');
    $stmt->execute([$cloudUserId, $installId, $localResultId]);
}

function geo_assets_require_result(PDO $pdo, int $cloudUserId, string $installId, int $localResultId): void {
    $stmt = $pdo->prepare('SELECT id FROM geo_sync_results WHERE cloud_user_id=? AND install_id=? AND local_id=? LIMIT 1');
    $stmt->execute([$cloudUserId, $installId, $localResultId]);
    if (!$stmt->fetchColumn()) {
        geo_json(['success' => false, 'message' => '同步结果不存在，请先同步统计数据后再上传截图'], 409);
    }
}

function geo_assets_valid_install_id(string $value): bool {
    return (bool)preg_match('/^[A-Za-z0-9_-]{8,64}$/', $value);
}

function geo_asset_safe_part(string $value): string {
    $value = preg_replace('/[^A-Za-z0-9._-]+/', '-', $value);
    $value = trim((string)$value, '.-');
    return $value !== '' ? substr($value, 0, 120) : 'file';
}

function geo_assets_body(): array {
    $metadata = $_POST['metadata'] ?? '';
    if ($metadata !== '') {
        $data = json_decode((string)$metadata, true);
        return is_array($data) ? $data : [];
    }
    $data = json_decode(file_get_contents('php://input') ?: '', true);
    return is_array($data) ? $data : [];
}

geo_assets_ensure_schema($pdo);
$cloudUserId = (int)$user['id'];
$now = geo_now();
$body = geo_assets_body();
$kind = (string)($body['kind'] ?? '');

try {
    if ($kind === 'stats') {
        $payload = $body['payload'] ?? [];
        if (!is_array($payload)) {
            geo_json(['success' => false, 'message' => 'invalid stats payload'], 400);
        }
        $installId = trim((string)($payload['install_id'] ?? ''));
        $userKey = (string)$user['username'];
        if (!geo_assets_valid_install_id($installId)) {
            geo_json(['success' => false, 'message' => 'install_id is invalid'], 400);
        }
        $counts = is_array($payload['counts'] ?? null) ? $payload['counts'] : [];
        $payload = [
            'install_id' => $installId,
            'user_key' => $userKey,
            'generated_at' => mb_substr((string)($payload['generated_at'] ?? ''), 0, 40, 'UTF-8'),
            'counts' => [
                'tasks' => max(0, (int)($counts['tasks'] ?? 0)),
                'results' => max(0, (int)($counts['results'] ?? 0)),
                'brand_exposure_results' => max(0, (int)($counts['brand_exposure_results'] ?? 0)),
                'screenshots' => max(0, (int)($counts['screenshots'] ?? 0)),
                'platforms' => max(0, (int)($counts['platforms'] ?? 0)),
            ],
        ];
        $encodedPayload = json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        if ($encodedPayload === false || strlen($encodedPayload) > 65536) {
            geo_json(['success' => false, 'message' => 'stats payload is too large'], 413);
        }
        $pdo->prepare('DELETE FROM geo_sync_stats_snapshots WHERE cloud_user_id=? AND install_id=?')->execute([$cloudUserId, $installId]);
        $stmt = $pdo->prepare('INSERT INTO geo_sync_stats_snapshots (cloud_user_id,install_id,user_key,payload,created_at) VALUES (?,?,?,?,?)');
        $stmt->execute([$cloudUserId, $installId, $userKey, $encodedPayload, $now]);
        geo_json(['success' => true, 'stats' => $payload, 'id' => (int)$pdo->lastInsertId()]);
    }

    if ($kind !== 'screenshot') {
        geo_json(['success' => false, 'message' => 'unsupported asset kind'], 400);
    }
    if (empty($_FILES['file']) || (int)($_FILES['file']['error'] ?? UPLOAD_ERR_NO_FILE) !== UPLOAD_ERR_OK || !is_uploaded_file($_FILES['file']['tmp_name'])) {
        geo_json(['success' => false, 'message' => 'file is required'], 400);
    }

    $installId = trim((string)($body['install_id'] ?? ''));
    $userKey = (string)$user['username'];
    $localResultId = (int)($body['local_result_id'] ?? 0);
    $localTaskId = (int)($body['local_task_id'] ?? 0);
    if (!geo_assets_valid_install_id($installId) || $localResultId <= 0) {
        geo_json(['success' => false, 'message' => 'install_id and local_result_id are invalid'], 400);
    }

    $tmp = $_FILES['file']['tmp_name'];
    $size = (int)(filesize($tmp) ?: 0);
    if ($size <= 0 || $size > 30 * 1024 * 1024) {
        geo_json(['success' => false, 'message' => 'file size is invalid or larger than 30MB'], 400);
    }
    $imageInfo = @getimagesize($tmp);
    $allowedMimes = ['image/png' => 'png', 'image/jpeg' => 'jpg', 'image/webp' => 'webp'];
    $detectedMime = is_array($imageInfo) ? (string)($imageInfo['mime'] ?? '') : '';
    $width = is_array($imageInfo) ? (int)($imageInfo[0] ?? 0) : 0;
    $height = is_array($imageInfo) ? (int)($imageInfo[1] ?? 0) : 0;
    if (!isset($allowedMimes[$detectedMime]) || $width <= 0 || $height <= 0 || $width > 10000 || $height > 100000 || ($width * $height) > 120000000) {
        geo_json(['success' => false, 'message' => 'file is not a supported screenshot image'], 415);
    }
    geo_assets_require_result($pdo, $cloudUserId, $installId, $localResultId);
    $sha = hash_file('sha256', $tmp);
    $stmt = $pdo->prepare('SELECT id,public_url,file_size FROM geo_sync_assets WHERE cloud_user_id=? AND install_id=? AND local_result_id=? AND kind=? AND sha256=? LIMIT 1');
    $stmt->execute([$cloudUserId, $installId, $localResultId, 'screenshot', $sha]);
    $existing = $stmt->fetch();
    if ($existing) {
        geo_assets_mark_result_screenshot($pdo, $cloudUserId, $installId, $localResultId);
        $assetId = (int)$existing['id'];
        geo_json(['success' => true, 'deduped' => true, 'id' => $assetId, 'url' => "/api/dashboard/?action=asset&asset_id={$assetId}", 'size' => (int)$existing['file_size']]);
    }

    $original = mb_substr(basename((string)($_FILES['file']['name'] ?? 'screenshot.png')), 0, 255, 'UTF-8');
    $ext = $allowedMimes[$detectedMime];
    $date = date('Ymd');
    $dir = geo_storage_path("cloud-assets/{$cloudUserId}/{$date}");
    if (!is_dir($dir) && !@mkdir($dir, 0755, true) && !is_dir($dir)) {
        geo_json(['success' => false, 'message' => 'failed to create storage directory'], 500);
    }
    $name = geo_asset_safe_part((string)($body['platform'] ?? 'ai')) . '-' . $localResultId . '-' . substr($sha, 0, 16) . '.' . $ext;
    $path = $dir . '/' . $name;
    if (!move_uploaded_file($tmp, $path)) {
        geo_json(['success' => false, 'message' => 'failed to save uploaded file'], 500);
    }
    @chmod($path, 0644);
    $config = geo_config();
    $publicBaseUrl = rtrim((string)($config['public_base_url'] ?? 'https://geo.allgood.cn'), '/');
    $publicUrl = "{$publicBaseUrl}/storage/cloud-assets/{$cloudUserId}/{$date}/{$name}";
    $mime = $detectedMime;
    $payload = $body;
    unset($payload['kind']);
    unset($payload['original_path'], $payload['user_key']);
    $payload['platform'] = mb_substr((string)($payload['platform'] ?? ''), 0, 80, 'UTF-8');
    $payload['question'] = mb_substr((string)($payload['question'] ?? ''), 0, 2000, 'UTF-8');

    $stmt = $pdo->prepare('INSERT INTO geo_sync_assets (cloud_user_id,install_id,user_key,local_result_id,local_task_id,kind,platform,question,original_name,storage_path,public_url,mime_type,file_size,sha256,payload,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)');
    $stmt->execute([
        $cloudUserId,
        $installId,
        $userKey,
        $localResultId,
        $localTaskId ?: null,
        'screenshot',
        $payload['platform'],
        $payload['question'],
        $original,
        $path,
        $publicUrl,
        $mime,
        $size,
        $sha,
        json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
        $now,
        $now,
    ]);
    $assetId = (int)$pdo->lastInsertId();
    geo_assets_mark_result_screenshot($pdo, $cloudUserId, $installId, $localResultId);
    geo_json(['success' => true, 'deduped' => false, 'id' => $assetId, 'url' => "/api/dashboard/?action=asset&asset_id={$assetId}", 'size' => $size, 'sha256' => $sha]);
} catch (Throwable $e) {
    geo_internal_error('asset_upload', $e, '截图上传失败，客户端将自动重试');
}
