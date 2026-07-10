<?php
declare(strict_types=1);

require '/www/wwwroot/geo.allgood.cn/api/common.php';

header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Headers: Authorization, Content-Type');
header('Access-Control-Allow-Methods: POST, OPTIONS');
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(204);
    exit;
}
if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    geo_json(['success' => false, 'message' => 'method not allowed'], 405);
}

$pdo = geo_pdo();
geo_ensure_schema($pdo);
geo_bootstrap($pdo);
$user = geo_auth_user($pdo);
if (!$user) {
    geo_json(['success' => false, 'message' => 'unauthorized'], 401);
}
if (strtolower(trim((string)($user['username'] ?? ''))) === 'tuke') {
    geo_json(['success' => false, 'message' => 'online demo is read-only'], 403);
}

function geo_assets_ensure_schema(PDO $pdo): void {
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
        UNIQUE KEY uniq_geo_asset_hash (cloud_user_id, install_id, kind, sha256),
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
        $installId = (string)($payload['install_id'] ?? '');
        $userKey = (string)($payload['user_key'] ?? '');
        if ($installId === '' || $userKey === '') {
            geo_json(['success' => false, 'message' => 'install_id and user_key are required'], 400);
        }
        $stmt = $pdo->prepare('INSERT INTO geo_sync_stats_snapshots (cloud_user_id,install_id,user_key,payload,created_at) VALUES (?,?,?,?,?)');
        $stmt->execute([$cloudUserId, $installId, $userKey, json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES), $now]);
        geo_json(['success' => true, 'stats' => $payload, 'id' => (int)$pdo->lastInsertId()]);
    }

    if ($kind !== 'screenshot') {
        geo_json(['success' => false, 'message' => 'unsupported asset kind'], 400);
    }
    if (empty($_FILES['file']) || !is_uploaded_file($_FILES['file']['tmp_name'])) {
        geo_json(['success' => false, 'message' => 'file is required'], 400);
    }

    $installId = (string)($body['install_id'] ?? '');
    $userKey = (string)($body['user_key'] ?? '');
    $localResultId = (int)($body['local_result_id'] ?? 0);
    $localTaskId = (int)($body['local_task_id'] ?? 0);
    if ($installId === '' || $userKey === '' || $localResultId <= 0) {
        geo_json(['success' => false, 'message' => 'install_id, user_key and local_result_id are required'], 400);
    }

    $tmp = $_FILES['file']['tmp_name'];
    $size = (int)($_FILES['file']['size'] ?? filesize($tmp));
    if ($size <= 0 || $size > 30 * 1024 * 1024) {
        geo_json(['success' => false, 'message' => 'file size is invalid or larger than 30MB'], 400);
    }
    $sha = hash_file('sha256', $tmp);
    $stmt = $pdo->prepare('SELECT id,public_url,file_size FROM geo_sync_assets WHERE cloud_user_id=? AND install_id=? AND kind=? AND sha256=? LIMIT 1');
    $stmt->execute([$cloudUserId, $installId, 'screenshot', $sha]);
    $existing = $stmt->fetch();
    if ($existing) {
        geo_json(['success' => true, 'deduped' => true, 'id' => (int)$existing['id'], 'url' => $existing['public_url'], 'size' => (int)$existing['file_size']]);
    }

    $original = (string)($_FILES['file']['name'] ?? 'screenshot.png');
    $ext = strtolower(pathinfo($original, PATHINFO_EXTENSION));
    if (!in_array($ext, ['png', 'jpg', 'jpeg', 'webp'], true)) {
        $ext = 'png';
    }
    $date = date('Ymd');
    $dir = "/www/wwwroot/geo.allgood.cn/storage/cloud-assets/{$cloudUserId}/{$date}";
    if (!is_dir($dir) && !@mkdir($dir, 0755, true) && !is_dir($dir)) {
        geo_json(['success' => false, 'message' => 'failed to create storage directory'], 500);
    }
    $name = geo_asset_safe_part((string)($body['platform'] ?? 'ai')) . '-' . $localResultId . '-' . substr($sha, 0, 16) . '.' . $ext;
    $path = $dir . '/' . $name;
    if (!move_uploaded_file($tmp, $path)) {
        geo_json(['success' => false, 'message' => 'failed to save uploaded file'], 500);
    }
    @chmod($path, 0644);
    $publicUrl = "https://geo.allgood.cn/storage/cloud-assets/{$cloudUserId}/{$date}/{$name}";
    $mime = (string)($_FILES['file']['type'] ?? 'image/png');
    $payload = $body;
    unset($payload['kind']);

    $stmt = $pdo->prepare('INSERT INTO geo_sync_assets (cloud_user_id,install_id,user_key,local_result_id,local_task_id,kind,platform,question,original_name,storage_path,public_url,mime_type,file_size,sha256,payload,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)');
    $stmt->execute([
        $cloudUserId,
        $installId,
        $userKey,
        $localResultId,
        $localTaskId ?: null,
        'screenshot',
        (string)($body['platform'] ?? ''),
        (string)($body['question'] ?? ''),
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
    geo_json(['success' => true, 'deduped' => false, 'id' => (int)$pdo->lastInsertId(), 'url' => $publicUrl, 'size' => $size, 'sha256' => $sha]);
} catch (Throwable $e) {
    geo_json(['success' => false, 'message' => 'asset upload failed', 'error' => $e->getMessage()], 500);
}
