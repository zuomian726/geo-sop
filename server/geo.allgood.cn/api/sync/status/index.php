<?php
declare(strict_types=1);

require '/www/wwwroot/geo.allgood.cn/api/common.php';

header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Headers: Authorization, Content-Type');
header('Access-Control-Allow-Methods: GET, OPTIONS');
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(204);
    exit;
}
if ($_SERVER['REQUEST_METHOD'] !== 'GET') {
    geo_json(['success' => false, 'message' => 'method not allowed'], 405);
}

$pdo = geo_pdo();
geo_ensure_schema($pdo);
geo_bootstrap($pdo);
$user = geo_auth_user($pdo);
if (!$user) {
    geo_json(['success' => false, 'message' => 'unauthorized'], 401);
}

$installId = trim((string)($_GET['install_id'] ?? ''));
$userKey = trim((string)($_GET['user_key'] ?? ''));
$cloudUserId = (int)$user['id'];
$where = ['cloud_user_id=?'];
$params = [$cloudUserId];
if ($installId !== '') {
    $where[] = 'install_id=?';
    $params[] = $installId;
}
if ($userKey !== '') {
    $where[] = 'user_key=?';
    $params[] = $userKey;
}

$stmt = $pdo->prepare('SELECT install_id,user_key,status,message,counts_json,synced_at FROM geo_sync_runs WHERE ' . implode(' AND ', $where) . ' ORDER BY synced_at DESC, id DESC LIMIT 1');
$stmt->execute($params);
$row = $stmt->fetch() ?: null;
$counts = $row ? json_decode((string)($row['counts_json'] ?? ''), true) : null;

geo_json([
    'success' => true,
    'cloud_sync' => [
        'enabled' => true,
        'install_id' => $row['install_id'] ?? $installId,
        'user_key' => $row['user_key'] ?? $userKey,
        'last_status' => $row['status'] ?? null,
        'last_message' => $row['message'] ?? null,
        'last_counts' => is_array($counts) ? $counts : null,
        'last_synced_at' => $row['synced_at'] ?? null,
    ],
]);
