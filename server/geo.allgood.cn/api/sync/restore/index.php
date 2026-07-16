<?php
declare(strict_types=1);

require dirname(__DIR__, 2) . '/common.php';

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

function geo_restore_config_payload(array $payload): array {
    // API keys stay on the desktop that entered them and are never restored from cloud storage.
    $payload['ai_api_key'] = null;
    unset($payload['api_key'], $payload['key']);
    return $payload;
}

function geo_restore_source_key(array $payload, string $installId, int $localId): string {
    $schedule = $payload['schedule_config'] ?? [];
    if (is_array($schedule) && !empty($schedule['cloud_source_install_id']) && !empty($schedule['cloud_source_local_id'])) {
        return (string)$schedule['cloud_source_install_id'] . ':' . (int)$schedule['cloud_source_local_id'];
    }
    return $installId . ':' . $localId;
}

function geo_restore_task_fingerprint(array $payload): string {
    return hash('sha256', mb_strtolower(trim((string)($payload['name'] ?? '')), 'UTF-8') . '|' . trim((string)($payload['created_at'] ?? '')));
}

function geo_restore_result_fingerprint(string $taskSource, array $payload): string {
    return hash('sha256', implode('|', [
        $taskSource,
        mb_strtolower(trim((string)($payload['platform'] ?? '')), 'UTF-8'),
        trim((string)($payload['question'] ?? '')),
        trim((string)($payload['created_at'] ?? '')),
        trim((string)($payload['answer'] ?? '')),
    ]));
}

function geo_restore_manuscript_fingerprint(array $payload): string {
    return hash('sha256', mb_strtolower(trim((string)($payload['title'] ?? '')), 'UTF-8') . '|' . trim((string)($payload['url'] ?? '')));
}

function geo_restore_rows(PDO $pdo, string $table, int $cloudUserId, int $cursor = 0, int $limit = 0, string $cursorTime = ''): array {
    $columns = $table === 'geo_sync_results'
        ? 'id, install_id, local_id, local_task_id, payload, synced_at'
        : 'id, install_id, local_id, payload, synced_at';
    $sql = "SELECT {$columns} FROM {$table} WHERE cloud_user_id = ?";
    $params = [$cloudUserId];
    if ($table === 'geo_sync_results' && $cursorTime !== '') {
        $sql .= ' AND (synced_at > ? OR (synced_at = ? AND id > ?))';
        $params[] = $cursorTime;
        $params[] = $cursorTime;
        $params[] = $cursor;
    } elseif ($table === 'geo_sync_results' && $cursor > 0) {
        $sql .= ' AND id > ?';
        $params[] = $cursor;
    }
    $sql .= $table === 'geo_sync_results' ? ' ORDER BY synced_at ASC, id ASC' : ' ORDER BY id ASC';
    if ($table === 'geo_sync_results' && $limit > 0) {
        $sql .= ' LIMIT ' . max(1, min(250, $limit));
    }
    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    return $stmt->fetchAll() ?: [];
}

try {
    $cloudUserId = (int)$user['id'];
    $resultCursor = max(0, (int)($_GET['cursor'] ?? 0));
    $resultCursorTime = trim((string)($_GET['cursor_time'] ?? ''));
    $resultLimit = max(1, min(250, (int)($_GET['limit'] ?? 100)));
    // Newer clients request workspace metadata only on the first page. Keep the
    // default enabled so older clients retain their existing response contract.
    $includeMetadata = !isset($_GET['include_metadata'])
        || !in_array(strtolower(trim((string)$_GET['include_metadata'])), ['0', 'false', 'no'], true);

    $taskRows = [];
    $taskSources = [];
    $taskFingerprints = [];
    // Result-to-task mapping is still required on every page, but payload-heavy
    // task rows only need to be returned once per restore session.
    foreach (geo_restore_rows($pdo, 'geo_sync_tasks', $cloudUserId) as $row) {
        $payload = geo_restore_payload($row['payload'] ?? '');
        $sourceKey = geo_restore_source_key($payload, (string)$row['install_id'], (int)$row['local_id']);
        $fingerprint = geo_restore_task_fingerprint($payload);
        $canonicalSource = $taskFingerprints[$fingerprint] ?? $sourceKey;
        $taskFingerprints[$fingerprint] = $canonicalSource;
        if ($includeMetadata) {
            $taskRows[$canonicalSource] = [
                'install_id' => (string)$row['install_id'],
                'local_id' => (int)$row['local_id'],
                'source_install_id' => explode(':', $canonicalSource, 2)[0],
                'source_local_id' => (int)explode(':', $canonicalSource, 2)[1],
                'payload' => $payload,
                'synced_at' => $row['synced_at'],
            ];
        }
        $taskSources[(string)$row['install_id'] . ':' . (int)$row['local_id']] = $canonicalSource;
    }

    $resultRows = [];
    $rawResultRows = geo_restore_rows($pdo, 'geo_sync_results', $cloudUserId, $resultCursor, $resultLimit, $resultCursorTime);
    $nextCursor = $resultCursor;
    $nextCursorTime = $resultCursorTime;
    foreach ($rawResultRows as $row) {
        $nextCursor = (int)($row['id'] ?? 0);
        $nextCursorTime = (string)($row['synced_at'] ?? $nextCursorTime);
        $payload = geo_restore_payload($row['payload'] ?? '');
        $installId = (string)$row['install_id'];
        $localTaskId = (int)($row['local_task_id'] ?? $payload['local_task_id'] ?? $payload['task_id'] ?? 0);
        $taskSource = $taskSources[$installId . ':' . $localTaskId] ?? ($installId . ':' . $localTaskId);
        $resultKey = geo_restore_result_fingerprint($taskSource, $payload);
        $parts = explode(':', $taskSource, 2);
        $payloadSourceInstall = trim((string)($payload['cloud_source_install_id'] ?? ''));
        $payloadSourceLocal = (int)($payload['cloud_source_local_id'] ?? 0);
        $resultRows[$resultKey] = [
            'install_id' => $installId,
            'local_id' => (int)$row['local_id'],
            'source_install_id' => $parts[0] ?? $installId,
            'source_task_local_id' => (int)($parts[1] ?? $localTaskId),
            'source_result_install_id' => $payloadSourceInstall !== '' ? $payloadSourceInstall : $installId,
            'source_local_id' => $payloadSourceInstall !== '' && $payloadSourceLocal > 0 ? $payloadSourceLocal : (int)$row['local_id'],
            'payload' => $payload,
            'synced_at' => $row['synced_at'],
        ];
    }

    $manuscriptRows = [];
    foreach ($includeMetadata ? geo_restore_rows($pdo, 'geo_sync_manuscripts', $cloudUserId) : [] as $row) {
        $payload = geo_restore_payload($row['payload'] ?? '');
        $installId = (string)$row['install_id'];
        $taskIds = [];
        if (!empty($payload['task_id'])) $taskIds[] = (int)$payload['task_id'];
        foreach (($payload['task_ids'] ?? []) as $taskId) $taskIds[] = (int)$taskId;
        $taskRefs = [];
        foreach (array_values(array_unique(array_filter($taskIds))) as $taskId) {
            $taskSource = $taskSources[$installId . ':' . $taskId] ?? ($installId . ':' . $taskId);
            $parts = explode(':', $taskSource, 2);
            $taskRefs[] = ['install_id' => $parts[0] ?? $installId, 'local_id' => (int)($parts[1] ?? $taskId)];
        }
        $key = geo_restore_manuscript_fingerprint($payload);
        $manuscriptRows[$key] = [
            'install_id' => $installId,
            'local_id' => (int)$row['local_id'],
            'source_install_id' => $installId,
            'source_local_id' => (int)$row['local_id'],
            'source_task_refs' => $taskRefs,
            'payload' => $payload,
            'synced_at' => $row['synced_at'],
        ];
    }

    $configRows = [];
    foreach ($includeMetadata ? geo_restore_rows($pdo, 'geo_sync_sentiment_configs', $cloudUserId) : [] as $row) {
        $payload = geo_restore_config_payload(geo_restore_payload($row['payload'] ?? ''));
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
        'paging' => [
            'cursor' => $resultCursor,
            'cursor_time' => $resultCursorTime,
            'next_cursor' => $nextCursor,
            'next_cursor_time' => $nextCursorTime,
            'limit' => $resultLimit,
            'has_more' => count($rawResultRows) >= $resultLimit,
            'included_metadata' => $includeMetadata,
        ],
    ]);
} catch (Throwable $e) {
    geo_json(['success' => false, 'message' => 'restore failed', 'error' => $e->getMessage()], 500);
}
