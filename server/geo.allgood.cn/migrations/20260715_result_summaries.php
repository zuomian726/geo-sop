<?php
declare(strict_types=1);

require dirname(__DIR__) . '/api/common.php';

$pdo = geo_pdo();
$pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);

$columns = [
    'has_screenshot' => 'ALTER TABLE geo_sync_results ADD COLUMN has_screenshot TINYINT(1) NOT NULL DEFAULT 0 AFTER has_brand_exposure',
    'reference_count' => 'ALTER TABLE geo_sync_results ADD COLUMN reference_count INT UNSIGNED NOT NULL DEFAULT 0 AFTER has_screenshot',
    'reference_domains' => 'ALTER TABLE geo_sync_results ADD COLUMN reference_domains TEXT NULL AFTER reference_count',
    'reference_items' => 'ALTER TABLE geo_sync_results ADD COLUMN reference_items TEXT NULL AFTER reference_domains',
];
foreach ($columns as $name => $sql) {
    $stmt = $pdo->prepare('SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=? AND column_name=?');
    $stmt->execute(['geo_sync_results', $name]);
    if ((int)$stmt->fetchColumn() === 0) $pdo->exec($sql);
}

$select = $pdo->prepare('SELECT id,payload FROM geo_sync_results WHERE id>? ORDER BY id ASC LIMIT 250');
$update = $pdo->prepare('UPDATE geo_sync_results SET has_screenshot=?,reference_count=?,reference_domains=?,reference_items=? WHERE id=?');
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
        if (!is_array($refs)) $refs = [];
        $domains = [];
        $referenceItems = [];
        foreach ($refs as $ref) {
            if (!is_array($ref)) continue;
            $url = trim((string)($ref['url'] ?? $ref['link'] ?? $ref['domain'] ?? ''));
            if ($url === '') continue;
            $referenceItems[] = [
                'title' => trim((string)($ref['title'] ?? '')),
                'url' => $url,
            ];
            if (!preg_match('#^https?://#i', $url)) $url = 'https://' . $url;
            $host = strtolower((string)(parse_url($url, PHP_URL_HOST) ?: ''));
            $host = (string)preg_replace('/^www\./', '', $host);
            if ($host !== '') $domains[] = $host;
        }
        $hasScreenshot = (
            trim((string)($payload['screenshot_path'] ?? '')) !== ''
            || trim((string)($payload['screenshot_url'] ?? '')) !== ''
        ) ? 1 : 0;
        $update->execute([
            $hasScreenshot,
            count($refs),
            json_encode($domains, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
            json_encode($referenceItems, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
            $cursor,
        ]);
        $updated++;
    }
    $pdo->commit();
    echo "Backfilled {$updated} rows\n";
} while (count($rows) === 250);

echo "Result summary migration complete: {$updated} rows\n";
