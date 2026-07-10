<?php
declare(strict_types=1);

require '/www/wwwroot/geo.allgood.cn/api/common.php';

header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Headers: Authorization, Content-Type');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(204);
    exit;
}

$pdo = geo_pdo();
geo_ensure_schema($pdo);
geo_bootstrap($pdo);
$user = geo_auth_user($pdo);
if (!$user) {
    geo_json(['success' => false, 'message' => 'unauthorized'], 401);
}

function geo_remote_ensure_schema(PDO $pdo): void {
    $pdo->exec("CREATE TABLE IF NOT EXISTS geo_desktop_clients (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        cloud_user_id BIGINT UNSIGNED NOT NULL,
        install_id VARCHAR(64) NOT NULL,
        user_key VARCHAR(255) NOT NULL,
        status VARCHAR(40) NOT NULL DEFAULT 'offline',
        message TEXT NULL,
        payload LONGTEXT NULL,
        last_seen_at DATETIME NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        UNIQUE KEY uniq_geo_desktop_client (cloud_user_id, install_id, user_key),
        KEY idx_geo_desktop_seen (cloud_user_id, last_seen_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
    geo_add_column($pdo, 'geo_remote_tasks', 'started_at', "DATETIME NULL");
    geo_add_column($pdo, 'geo_remote_tasks', 'finished_at', "DATETIME NULL");
    geo_add_column($pdo, 'geo_remote_tasks', 'last_status_message', "TEXT NULL");
    geo_add_column($pdo, 'geo_remote_tasks', 'status_payload', "LONGTEXT NULL");
}

function geo_remote_body(): array {
    $data = json_decode(file_get_contents('php://input') ?: '', true);
    if (!is_array($data)) {
        geo_json(['success' => false, 'message' => 'invalid json'], 400);
    }
    return $data;
}

function geo_remote_route(): string {
    $path = parse_url($_SERVER['REQUEST_URI'] ?? '', PHP_URL_PATH) ?: '';
    if (str_contains($path, '/remote-tasks/ack')) return 'ack';
    if (str_contains($path, '/remote-tasks/status')) return 'status';
    if (str_contains($path, '/remote-tasks/heartbeat')) return 'heartbeat';
    return 'base';
}

function geo_remote_task_row(PDO $pdo, int $cloudUserId, int $remoteTaskId): ?array {
    $stmt = $pdo->prepare('SELECT * FROM geo_remote_tasks WHERE id=? AND cloud_user_id=? LIMIT 1');
    $stmt->execute([$remoteTaskId, $cloudUserId]);
    $row = $stmt->fetch();
    return $row ?: null;
}

geo_remote_ensure_schema($pdo);

$route = geo_remote_route();
$cloudUserId = (int)$user['id'];
$isDemoUser = strtolower(trim((string)($user['username'] ?? ''))) === 'tuke';

if ($isDemoUser && $_SERVER['REQUEST_METHOD'] === 'POST') {
    geo_json(['success' => false, 'message' => 'online demo is read-only'], 403);
}

if ($_SERVER['REQUEST_METHOD'] === 'GET' && $route === 'base') {
    $installId = trim((string)($_GET['install_id'] ?? ''));
    $userKey = trim((string)($_GET['user_key'] ?? ''));
    $sql = "SELECT id,name,payload,status,created_at FROM geo_remote_tasks
            WHERE cloud_user_id=? AND status='pending'
              AND (assigned_install_id IS NULL OR assigned_install_id='' OR assigned_install_id=?)
            ORDER BY id ASC LIMIT 20";
    $stmt = $pdo->prepare($sql);
    $stmt->execute([$cloudUserId, $installId]);
    $rows = [];
    foreach ($stmt->fetchAll() as $row) {
        $row['payload'] = json_decode((string)$row['payload'], true) ?: [];
        $rows[] = $row;
    }
    geo_json(['success' => true, 'tasks' => $rows, 'install_id' => $installId, 'user_key' => $userKey]);
}

if ($_SERVER['REQUEST_METHOD'] === 'POST' && $route === 'heartbeat') {
    $data = geo_remote_body();
    $installId = trim((string)($data['install_id'] ?? ''));
    $userKey = trim((string)($data['user_key'] ?? ''));
    if ($installId === '' || $userKey === '') {
        geo_json(['success' => false, 'message' => 'install_id and user_key required'], 400);
    }
    $now = geo_now();
    $status = substr((string)($data['status'] ?? 'online'), 0, 40);
    $message = (string)($data['message'] ?? '');
    $payload = json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    $stmt = $pdo->prepare("INSERT INTO geo_desktop_clients
        (cloud_user_id, install_id, user_key, status, message, payload, last_seen_at, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?)
        ON DUPLICATE KEY UPDATE status=VALUES(status), message=VALUES(message), payload=VALUES(payload), last_seen_at=VALUES(last_seen_at), updated_at=VALUES(updated_at)");
    $stmt->execute([$cloudUserId, $installId, $userKey, $status, $message, $payload, $now, $now, $now]);
    geo_json(['success' => true, 'message' => 'heartbeat ok']);
}

if ($_SERVER['REQUEST_METHOD'] === 'POST' && $route === 'ack') {
    $data = geo_remote_body();
    $installId = trim((string)($data['install_id'] ?? ''));
    $userKey = trim((string)($data['user_key'] ?? ''));
    $now = geo_now();
    $imported = is_array($data['imported'] ?? null) ? $data['imported'] : [];
    $updated = [];
    foreach ($imported as $item) {
        $remoteTaskId = (int)($item['remote_task_id'] ?? 0);
        $localTaskId = (int)($item['local_task_id'] ?? 0);
        if ($remoteTaskId <= 0 || !geo_remote_task_row($pdo, $cloudUserId, $remoteTaskId)) {
            continue;
        }
        $stmt = $pdo->prepare("UPDATE geo_remote_tasks
            SET status='imported', assigned_install_id=?, assigned_user_key=?, local_task_id=?, pulled_at=?, updated_at=?, last_status_message=?
            WHERE id=? AND cloud_user_id=?");
        $stmt->execute([$installId, $userKey, $localTaskId ?: null, $now, $now, '客户端已导入任务', $remoteTaskId, $cloudUserId]);
        $updated[] = $remoteTaskId;
    }
    geo_json(['success' => true, 'updated' => $updated]);
}

if ($_SERVER['REQUEST_METHOD'] === 'POST' && $route === 'status') {
    $data = geo_remote_body();
    $remoteTaskId = (int)($data['remote_task_id'] ?? 0);
    $localTaskId = (int)($data['local_task_id'] ?? 0);
    $installId = trim((string)($data['install_id'] ?? ''));
    $userKey = trim((string)($data['user_key'] ?? ''));
    $status = substr((string)($data['status'] ?? ''), 0, 40);
    if ($remoteTaskId <= 0 || $status === '') {
        geo_json(['success' => false, 'message' => 'remote_task_id and status required'], 400);
    }
    if (!geo_remote_task_row($pdo, $cloudUserId, $remoteTaskId)) {
        geo_json(['success' => false, 'message' => 'remote task not found'], 404);
    }
    $allowed = ['imported', 'queued', 'running', 'completed', 'failed', 'stopped', 'skipped'];
    if (!in_array($status, $allowed, true)) {
        geo_json(['success' => false, 'message' => 'invalid status'], 400);
    }
    $now = geo_now();
    $message = (string)($data['message'] ?? '');
    $payload = json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    $startedAt = $status === 'running' ? $now : null;
    $finishedAt = in_array($status, ['completed', 'failed', 'stopped', 'skipped'], true) ? $now : null;
    $stmt = $pdo->prepare("UPDATE geo_remote_tasks
        SET status=?, assigned_install_id=COALESCE(NULLIF(?, ''), assigned_install_id),
            assigned_user_key=COALESCE(NULLIF(?, ''), assigned_user_key),
            local_task_id=COALESCE(?, local_task_id),
            started_at=COALESCE(?, started_at),
            finished_at=COALESCE(?, finished_at),
            last_status_message=?, status_payload=?, updated_at=?
        WHERE id=? AND cloud_user_id=?");
    $stmt->execute([
        $status,
        $installId,
        $userKey,
        $localTaskId ?: null,
        $startedAt,
        $finishedAt,
        $message,
        $payload,
        $now,
        $remoteTaskId,
        $cloudUserId,
    ]);
    geo_json(['success' => true, 'id' => $remoteTaskId, 'status' => $status]);
}

if ($_SERVER['REQUEST_METHOD'] === 'POST' && $route === 'base') {
    $data = geo_remote_body();
    $payload = $data['payload'] ?? $data;
    if (!is_array($payload)) {
        geo_json(['success' => false, 'message' => 'payload required'], 400);
    }
    $name = (string)($payload['name'] ?? '远程采集任务');
    $now = geo_now();
    $stmt = $pdo->prepare('INSERT INTO geo_remote_tasks (cloud_user_id,name,payload,status,created_at,updated_at) VALUES (?,?,?,?,?,?)');
    $stmt->execute([$cloudUserId, $name, json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES), 'pending', $now, $now]);
    geo_json(['success' => true, 'id' => (int)$pdo->lastInsertId()]);
}

geo_json(['success' => false, 'message' => 'method not allowed'], 405);
