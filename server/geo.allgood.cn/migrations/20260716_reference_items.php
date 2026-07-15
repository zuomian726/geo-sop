<?php
declare(strict_types=1);

require '/www/wwwroot/geo.allgood.cn/api/common.php';

$pdo = geo_pdo();
$pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);

$columnStmt = $pdo->prepare('SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=? AND column_name=?');
$columnStmt->execute(['geo_sync_results', 'reference_items']);
if ((int)$columnStmt->fetchColumn() === 0) {
    $pdo->exec('ALTER TABLE geo_sync_results ADD COLUMN reference_items TEXT NULL AFTER reference_domains');
}

$select = $pdo->prepare('SELECT id,payload FROM geo_sync_results WHERE id>? AND (reference_items IS NULL OR reference_items="") ORDER BY id ASC LIMIT 250');
$update = $pdo->prepare('UPDATE geo_sync_results SET reference_items=? WHERE id=?');
$cursor = 0;
$updated = 0;

do {
    $select->execute([$cursor]);
    $rows = $select->fetchAll() ?: [];
    if (!$rows) break;
    $pdo->beginTransaction();
    foreach ($rows as $row) {
        $cursor = (int)$row['id'];
        $payload = json_decode((string)$row['payload'], true);
        $payload = is_array($payload) ? $payload : [];
        $refs = $payload['references'] ?? [];
        if (is_string($refs)) {
            $decoded = json_decode($refs, true);
            $refs = is_array($decoded) ? $decoded : [];
        }
        $items = [];
        foreach (is_array($refs) ? $refs : [] as $ref) {
            if (!is_array($ref)) continue;
            $url = trim((string)($ref['url'] ?? $ref['link'] ?? $ref['domain'] ?? ''));
            if ($url === '') continue;
            $items[] = [
                'title' => trim((string)($ref['title'] ?? '')),
                'url' => $url,
            ];
        }
        $update->execute([json_encode($items, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES), $cursor]);
        $updated++;
    }
    $pdo->commit();
    echo "Backfilled {$updated} rows\n";
} while (count($rows) === 250);

echo "Reference item migration complete: {$updated} rows\n";
