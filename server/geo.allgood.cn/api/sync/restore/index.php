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

function geo_restore_payload(?string $payload): array {
    $data = json_decode((string)$payload, true);
    return is_array($data) ? $data : [];
}

function geo_restore_source_key(array $payload, string $installId, int $localId): string {
    $schedule = $payload['schedule_config'] ?? [];
    if (is_array($schedule) && !empty($schedule['cloud_source_install_id']) && !empty($schedule['cloud_source_local_id'])) {
        return (string)$schedule['cloud_source_install_id'] . ':' . (int)$schedule['cloud_source_local_id'];
    }
    return $installId . ':' . $localId;
}

function geo_restore_rows(PDO $pdo, string $table, int $cloudUserId): array {
    $stmt = $pdo->prepare("SELECT install_id, local_id, payload, synced_at FROM {$table} WHERE cloud_user_id = ? ORDER BY synced_at ASC, id ASC");
    $stmt->execute([$cloudUserId]);
    return $stmt->fetchAll() ?: [];
}

try {
    $cloudUserId = (int)$user['id'];

    $taskRows = [];
    $taskSources = [];
    foreach (geo_restore_rows($pdo, 'geo_sync_tasks', $cloudUserId) as $row) {
        $payload = geo_restore_payload($row['payload'] ?? '');
        $sourceKey = geo_restore_source_key($payload, (string)$row['install_id'], (int)$row['local_id']);
        $taskRows[$sourceKey] = [
            'install_id' => (string)$row['install_id'],
            'local_id' => (int)$row['local_id'],
            'source_install_id' => explode(':', $sourceKey, 2)[0],
            'source_local_id' => (int)explode(':', $sourceKey, 2)[1],
            'payload' => $payload,
            'synced_at' => $row['synced_at'],
        ];
        $taskSources[(string)$row['install_id'] . ':' . (int)$row['local_id']] = $sourceKey;
    }

    $resultRows = [];
    foreach (geo_restore_rows($pdo, 'geo_sync_results', $cloudUserId) as $row) {
        $payload = geo_restore_payload($row['payload'] ?? '');
        $installId = (string)$row['install_id'];
        $localTaskId = (int)($payload['local_task_id'] ?? $payload['task_id'] ?? 0);
        $taskSource = $taskSources[$installId . ':' . $localTaskId] ?? ($installId . ':' . $localTaskId);
        $resultKey = $taskSource . ':' . (int)$row['local_id'];
        $parts = explode(':', $taskSource, 2);
        $resultRows[$resultKey] = [
            'install_id' => $installId,
            'local_id' => (int)$row['local_id'],
            'source_install_id' => $parts[0] ?? $installId,
            'source_task_local_id' => (int)($parts[1] ?? $localTaskId),
            'source_local_id' => (int)$row['local_id'],
            'payload' => $payload,
            'synced_at' => $row['synced_at'],
        ];
    }

    $manuscriptRows = [];
    foreach (geo_restore_rows($pdo, 'geo_sync_manuscripts', $cloudUserId) as $row) {
        $payload = geo_restore_payload($row['payload'] ?? '');
        $key = (string)$row['install_id'] . ':' . (int)$row['local_id'];
        $manuscriptRows[$key] = [
            'install_id' => (string)$row['install_id'],
            'local_id' => (int)$row['local_id'],
            'source_install_id' => (string)$row['install_id'],
            'source_local_id' => (int)$row['local_id'],
            'payload' => $payload,
            'synced_at' => $row['synced_at'],
        ];
    }

    $configRows = [];
    foreach (geo_restore_rows($pdo, 'geo_sync_sentiment_configs', $cloudUserId) as $row) {
        $payload = geo_restore_payload($row['payload'] ?? '');
        $key = (string)$row['install_id'] . ':' . (int)$row['local_id'];
        $configRows[$key] = [
            'install_id' => (string)$row['install_id'],
            'local_id' => (int)$row['local_id'],
            'source_install_id' => (string)$row['install_id'],
            'source_local_id' => (int)$row['local_id'],
            'payload' => $payload,
            'synced_at' => $row['synced_at'],
        ];
    }

    $workspace = [
        'tasks' => array_values($taskRows),
        'results' => array_values($resultRows),
        'manuscripts' => array_values($manuscriptRows),
        'sentiment_configs' => array_values($configRows),
    ];
    geo_json([
        'success' => true,
        'workspace' => $workspace,
        'counts' => [
            'tasks' => count($workspace['tasks']),
            'results' => count($workspace['results']),
            'manuscripts' => count($workspace['manuscripts']),
            'sentiment_configs' => count($workspace['sentiment_configs']),
        ],
    ]);
} catch (Throwable $e) {
    geo_json(['success' => false, 'message' => 'restore failed', 'error' => $e->getMessage()], 500);
}
