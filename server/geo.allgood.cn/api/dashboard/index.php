<?php
declare(strict_types=1);

require dirname(__DIR__) . '/common.php';
require dirname(__DIR__) . '/platforms.php';

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
$user = geo_current_web_user($pdo) ?: geo_auth_user($pdo);
if (!$user) {
    geo_json(['success' => false, 'message' => 'unauthorized'], 401);
}

function geo_dashboard_payload(?string $value): array {
    $data = json_decode((string)$value, true);
    return is_array($data) ? $data : [];
}

function geo_dashboard_refs(array $payload): array {
    $refs = $payload['references'] ?? [];
    if (is_string($refs)) {
        $decoded = json_decode($refs, true);
        $refs = is_array($decoded) ? $decoded : [];
    }
    return is_array($refs) ? array_values($refs) : [];
}

function geo_dashboard_compact_refs(?string $value): array {
    $refs = json_decode((string)$value, true);
    return is_array($refs) ? array_values($refs) : [];
}

function geo_dashboard_domain(string $url): string {
    $url = trim($url);
    if ($url === '') return '';
    if (!preg_match('#^https?://#i', $url)) $url = 'https://' . $url;
    $host = parse_url($url, PHP_URL_HOST);
    if (!$host) return '';
    return strtolower((string)preg_replace('/^www\./', '', $host));
}

function geo_dashboard_url_key(string $url, bool $stripQuery = false): string {
    $url = trim(strtolower($url));
    if ($url === '') return '';
    $url = preg_replace('#^https?://#i', '', $url);
    $url = preg_replace('#^www\.#i', '', (string)$url);
    $url = preg_replace('/#.*$/', '', (string)$url);
    if ($stripQuery) $url = preg_replace('/\?.*$/', '', (string)$url);
    return trim((string)$url, " \t\n\r\0\x0B/");
}

function geo_dashboard_url_matches(string $targetUrl, string $referenceUrl): bool {
    $targetKeys = array_values(array_unique(array_filter([
        geo_dashboard_url_key($targetUrl, false),
        geo_dashboard_url_key($targetUrl, true),
    ])));
    $referenceKeys = array_values(array_unique(array_filter([
        geo_dashboard_url_key($referenceUrl, false),
        geo_dashboard_url_key($referenceUrl, true),
    ])));
    foreach ($targetKeys as $targetKey) {
        if (mb_strlen($targetKey, 'UTF-8') < 6) continue;
        foreach ($referenceKeys as $referenceKey) {
            if ($referenceKey === '') continue;
            if ($targetKey === $referenceKey || str_contains($referenceKey, $targetKey) || str_contains($targetKey, $referenceKey)) {
                return true;
            }
        }
    }
    return false;
}

function geo_dashboard_main_domain_from_url(string $url): string {
    $key = geo_dashboard_url_key($url, true);
    if ($key === '') return '';
    $host = explode('/', $key, 2)[0] ?? '';
    $parts = array_values(array_filter(explode('.', $host)));
    $count = count($parts);
    if ($count < 2) return $host;
    $lastTwo = implode('.', array_slice($parts, -2));
    if (in_array($lastTwo, ['com.cn', 'net.cn', 'org.cn', 'gov.cn', 'edu.cn'], true) && $count >= 3) {
        return implode('.', array_slice($parts, -3));
    }
    return $lastTwo;
}

function geo_dashboard_platform_name(string $platform): string {
    $catalog = geo_platform_catalog();
    return (string)($catalog[$platform]['name'] ?? $platform);
}

function geo_dashboard_percent(int $part, int $total): float {
    return $total > 0 ? round($part * 100 / $total, 1) : 0.0;
}

function geo_dashboard_release_version(): string {
    $path = dirname(__DIR__, 2) . '/update.json';
    if (!is_file($path)) return '';
    $manifest = json_decode((string)file_get_contents($path), true);
    return is_array($manifest) ? trim((string)($manifest['version'] ?? '')) : '';
}

function geo_dashboard_version_numbers(string $version): array {
    if (!preg_match('/(\d+)\.(\d+)\.(\d+)/', $version, $matches)) return [];
    return [(int)$matches[1], (int)$matches[2], (int)$matches[3]];
}

function geo_dashboard_version_is_older(string $version, string $latest): bool {
    $currentParts = geo_dashboard_version_numbers($version);
    $latestParts = geo_dashboard_version_numbers($latest);
    return $currentParts && $latestParts && version_compare(implode('.', $currentParts), implode('.', $latestParts), '<');
}

function geo_dashboard_remote_status_label(string $status): string {
    return [
        'pending' => '等待客户端',
        'claimed' => '客户端已认领',
        'imported' => '已导入本机',
        'queued' => '本机排队中',
        'running' => '正在采集',
        'completed' => '采集完成',
        'failed' => '采集失败',
        'stopped' => '已停止',
        'skipped' => '已跳过',
    ][$status] ?? ($status !== '' ? $status : '未知');
}

function geo_dashboard_limit(): int {
    $limit = (int)($_GET['limit'] ?? 100);
    return max(1, min(500, $limit));
}

function geo_dashboard_stream_rows(PDO $pdo): void {
    if (defined('PDO::MYSQL_ATTR_USE_BUFFERED_QUERY')) {
        $pdo->setAttribute(PDO::MYSQL_ATTR_USE_BUFFERED_QUERY, false);
    }
}

function geo_dashboard_reference_scan(PDO $pdo, int $cloudUserId, bool $deduplicate = false): array {
    $where = ['cloud_user_id=?'];
    $params = [$cloudUserId];
    $taskId = (int)($_GET['task_id'] ?? 0);
    $installId = trim((string)($_GET['install_id'] ?? ''));
    $platform = trim((string)($_GET['platform'] ?? ''));
    $dateStart = trim((string)($_GET['date_start'] ?? $_GET['start_date'] ?? ''));
    $dateEnd = trim((string)($_GET['date_end'] ?? $_GET['end_date'] ?? ''));
    if ($taskId > 0) {
        $where[] = 'local_task_id=?';
        $params[] = $taskId;
    }
    if ($installId !== '') {
        $where[] = 'install_id=?';
        $params[] = $installId;
    }
    if ($platform !== '') {
        $where[] = 'platform=?';
        $params[] = $platform;
    }
    if ($dateStart !== '') {
        $where[] = 'result_at>=?';
        $params[] = $dateStart . ' 00:00:00';
    }
    if ($dateEnd !== '') {
        $where[] = 'result_at<=?';
        $params[] = $dateEnd . ' 23:59:59';
    }

    $countStmt = $pdo->prepare('SELECT COUNT(*) FROM geo_sync_results WHERE ' . implode(' AND ', $where));
    $countStmt->execute($params);
    $totalResults = (int)$countStmt->fetchColumn();

    $referenceWhere = $where;
    $referenceWhere[] = 'reference_count>0';
    $sql = 'SELECT reference_items,result_at FROM geo_sync_results WHERE ' . implode(' AND ', $referenceWhere) . ' ORDER BY result_at ASC,id ASC LIMIT 20000';
    geo_dashboard_stream_rows($pdo);
    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    $fullCounts = [];
    $topCounts = [];
    $dailyFull = [];
    $dailyTop = [];
    $seenUrls = [];
    while ($row = $stmt->fetch(PDO::FETCH_ASSOC)) {
        $date = substr((string)($row['result_at'] ?? ''), 0, 10);
        foreach (geo_dashboard_compact_refs($row['reference_items'] ?? '') as $ref) {
            if (!is_array($ref)) continue;
            $url = trim((string)($ref['url'] ?? $ref['link'] ?? $ref['domain'] ?? ''));
            if ($url === '') continue;
            $urlKey = geo_dashboard_url_key($url, false);
            if ($deduplicate && $urlKey !== '') {
                if (isset($seenUrls[$urlKey])) continue;
                $seenUrls[$urlKey] = true;
            }
            $full = geo_dashboard_domain($url);
            $top = geo_dashboard_main_domain_from_url($url);
            if ($full !== '') {
                $fullCounts[$full] = ($fullCounts[$full] ?? 0) + 1;
                if ($date !== '') $dailyFull[$date][$full] = ($dailyFull[$date][$full] ?? 0) + 1;
            }
            if ($top !== '') {
                $topCounts[$top] = ($topCounts[$top] ?? 0) + 1;
                if ($date !== '') $dailyTop[$date][$top] = ($dailyTop[$date][$top] ?? 0) + 1;
            }
        }
    }
    arsort($fullCounts);
    arsort($topCounts);
    ksort($dailyFull);
    ksort($dailyTop);
    return [
        'total_results' => $totalResults,
        'full_counts' => $fullCounts,
        'top_counts' => $topCounts,
        'daily_full' => $dailyFull,
        'daily_top' => $dailyTop,
    ];
}

function geo_dashboard_reference_items(array $counts, int $limit = 0): array {
    $items = [];
    foreach (($limit > 0 ? array_slice($counts, 0, $limit, true) : $counts) as $name => $count) {
        $items[] = ['name' => (string)$name, 'domain' => (string)$name, 'count' => (int)$count];
    }
    return $items;
}

function geo_dashboard_task_map(PDO $pdo, int $cloudUserId): array {
    $stmt = $pdo->prepare('SELECT install_id,local_id,name,status FROM geo_sync_tasks WHERE cloud_user_id=? ORDER BY id DESC');
    $stmt->execute([$cloudUserId]);
    $map = [];
    foreach ($stmt->fetchAll() ?: [] as $row) {
        $map[(string)$row['install_id'] . ':' . (int)$row['local_id']] = $row;
    }
    return $map;
}

function geo_dashboard_asset_map(PDO $pdo, int $cloudUserId, array $pairs): array {
    if (!$pairs) return [];
    $uniquePairs = [];
    foreach ($pairs as $pair) {
        $key = (string)$pair['install_id'] . ':' . (int)$pair['local_result_id'];
        $uniquePairs[$key] = $pair;
    }
    $assets = [];
    foreach (array_chunk(array_values($uniquePairs), 200) as $chunk) {
        $clauses = [];
        $params = [$cloudUserId];
        foreach ($chunk as $pair) {
            $clauses[] = '(install_id=? AND local_result_id=?)';
            $params[] = (string)$pair['install_id'];
            $params[] = (int)$pair['local_result_id'];
        }
        $sql = 'SELECT install_id,local_result_id,storage_path,public_url,file_size,updated_at FROM geo_sync_assets WHERE cloud_user_id=? AND kind="screenshot" AND (' . implode(' OR ', $clauses) . ') ORDER BY updated_at DESC';
        $stmt = $pdo->prepare($sql);
        $stmt->execute($params);
        foreach ($stmt->fetchAll() ?: [] as $row) {
            $key = (string)$row['install_id'] . ':' . (int)$row['local_result_id'];
            if (!isset($assets[$key])) {
                $assets[$key] = [
                    'storage_path' => $row['storage_path'],
                    'url' => $row['public_url'],
                    'file_size' => (int)$row['file_size'],
                    'updated_at' => $row['updated_at'],
                ];
            }
        }
    }
    return $assets;
}

function geo_dashboard_result_item(array $row, array $taskMap, ?array $asset = null, int $answerLimit = 0, bool $summaryOnly = false): array {
    $payload = geo_dashboard_payload($row['payload'] ?? '');
    $taskKey = (string)$row['install_id'] . ':' . (int)$row['local_task_id'];
    $task = $taskMap[$taskKey] ?? null;
    $refs = geo_dashboard_refs($payload);
    $aiSentiment = $payload['ai_sentiment'] ?? $payload['ai_sentiment_result'] ?? null;
    if (is_string($aiSentiment)) {
        $decoded = json_decode($aiSentiment, true);
        $aiSentiment = is_array($decoded) ? $decoded : null;
    }
    $answer = (string)($payload['answer'] ?? '');
    if ($answerLimit > 0) {
        $answer = mb_substr($answer, 0, $answerLimit, 'UTF-8');
    }
    $item = [
        'id' => (int)$row['id'],
        'install_id' => (string)$row['install_id'],
        'local_id' => (int)$row['local_id'],
        'local_task_id' => (int)$row['local_task_id'],
        'task_name' => $task ? (string)$task['name'] : '',
        'platform' => (string)$row['platform'],
        'platform_name' => geo_dashboard_platform_name((string)$row['platform']),
        'question' => (string)$row['question'],
        'answer' => $answer,
        'has_brand_exposure' => ((int)$row['has_brand_exposure']) === 1,
        'exposed_keywords' => is_array($payload['exposed_keywords'] ?? null) ? array_values($payload['exposed_keywords']) : [],
        'references' => $refs,
        'reference_count' => isset($row['reference_count']) ? (int)$row['reference_count'] : count($refs),
        'screenshot_path' => (string)($payload['screenshot_path'] ?? ''),
        'screenshot_url' => $asset['url'] ?? null,
        'ai_sentiment' => is_array($aiSentiment) ? $aiSentiment : null,
        'created_at' => $row['local_created_at'] ?: $row['synced_at'],
        'synced_at' => $row['synced_at'],
    ];
    if ($summaryOnly) {
        unset($item['references'], $item['exposed_keywords'], $item['screenshot_path'], $item['ai_sentiment']);
    }
    return $item;
}

function geo_dashboard_filtered_rows(PDO $pdo, int $cloudUserId, int $limit = 5000): array {
    $where = ['cloud_user_id=?'];
    $params = [$cloudUserId];
    $taskId = trim((string)($_GET['task_id'] ?? ''));
    $installId = trim((string)($_GET['install_id'] ?? ''));
    if ($taskId !== '') {
        $where[] = 'local_task_id=?';
        $params[] = (int)$taskId;
    }
    if ($installId !== '') {
        $where[] = 'install_id=?';
        $params[] = $installId;
    }
    $platform = trim((string)($_GET['platform'] ?? ''));
    if ($platform !== '') {
        $where[] = 'platform=?';
        $params[] = $platform;
    }
    $keyword = trim((string)($_GET['keyword'] ?? ''));
    if ($keyword !== '') {
        $where[] = '(question LIKE ? OR payload LIKE ?)';
        $params[] = '%' . $keyword . '%';
        $params[] = '%' . $keyword . '%';
    }
    $exposed = trim((string)($_GET['exposed'] ?? ''));
    if ($exposed === '1' || $exposed === '0') {
        $where[] = 'has_brand_exposure=?';
        $params[] = (int)$exposed;
    }
    $start = trim((string)($_GET['start_date'] ?? ''));
    if ($start !== '') {
        $where[] = 'result_at >= ?';
        $params[] = $start . ' 00:00:00';
    }
    $end = trim((string)($_GET['end_date'] ?? ''));
    if ($end !== '') {
        $where[] = 'result_at <= ?';
        $params[] = $end . ' 23:59:59';
    }
    $sql = 'SELECT install_id,local_id,platform,question,local_created_at,synced_at FROM geo_sync_results WHERE ' . implode(' AND ', $where) . ' ORDER BY platform ASC, question ASC, result_at ASC, id ASC LIMIT ' . max(1, min(10000, $limit));
    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    return $stmt->fetchAll() ?: [];
}

function geo_dashboard_filtered_stmt(PDO $pdo, int $cloudUserId, int $limit = 5000, string $columns = '*'): PDOStatement {
    $where = ['cloud_user_id=?'];
    $params = [$cloudUserId];
    $taskId = trim((string)($_GET['task_id'] ?? ''));
    $installId = trim((string)($_GET['install_id'] ?? ''));
    if ($taskId !== '') {
        $where[] = 'local_task_id=?';
        $params[] = (int)$taskId;
    }
    if ($installId !== '') {
        $where[] = 'install_id=?';
        $params[] = $installId;
    }
    $platform = trim((string)($_GET['platform'] ?? ''));
    if ($platform !== '') {
        $where[] = 'platform=?';
        $params[] = $platform;
    }
    $keyword = trim((string)($_GET['keyword'] ?? ''));
    if ($keyword !== '') {
        $where[] = '(question LIKE ? OR payload LIKE ?)';
        $params[] = '%' . $keyword . '%';
        $params[] = '%' . $keyword . '%';
    }
    $exposed = trim((string)($_GET['exposed'] ?? ''));
    if ($exposed === '1' || $exposed === '0') {
        $where[] = 'has_brand_exposure=?';
        $params[] = (int)$exposed;
    }
    $start = trim((string)($_GET['start_date'] ?? ''));
    if ($start !== '') {
        $where[] = 'result_at >= ?';
        $params[] = $start . ' 00:00:00';
    }
    $end = trim((string)($_GET['end_date'] ?? ''));
    if ($end !== '') {
        $where[] = 'result_at <= ?';
        $params[] = $end . ' 23:59:59';
    }
    $safeColumns = preg_replace('/[^a-zA-Z0-9_.*, ()]/', '', $columns) ?: '*';
    $sql = 'SELECT ' . $safeColumns . ' FROM geo_sync_results WHERE ' . implode(' AND ', $where) . ' ORDER BY platform ASC, question ASC, result_at ASC, id ASC LIMIT ' . max(1, min(20000, $limit));
    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    return $stmt;
}

function geo_dashboard_task_name_map(PDO $pdo, int $cloudUserId): array {
    $stmt = $pdo->prepare('SELECT install_id,local_id,name FROM geo_sync_tasks WHERE cloud_user_id=?');
    $stmt->execute([$cloudUserId]);
    $map = [];
    foreach ($stmt->fetchAll() ?: [] as $row) {
        $map[(string)$row['install_id'] . ':' . (int)$row['local_id']] = (string)$row['name'];
    }
    return $map;
}

function geo_dashboard_task_ids_from_payload(array $payload): array {
    $ids = [];
    foreach (['task_ids', 'task_id'] as $key) {
        $value = $payload[$key] ?? null;
        if (is_string($value)) {
            $decoded = json_decode($value, true);
            $value = is_array($decoded) ? $decoded : preg_split('/[,，\s]+/', $value);
        }
        if (!is_array($value)) $value = $value === null ? [] : [$value];
        foreach ($value as $id) {
            $id = (int)$id;
            if ($id > 0) $ids[$id] = true;
        }
    }
    return array_keys($ids);
}

function geo_dashboard_xml(string $value): string {
    return htmlspecialchars($value, ENT_XML1 | ENT_COMPAT, 'UTF-8');
}

function geo_dashboard_xlsx_cell($value): string {
    if (is_int($value) || is_float($value)) {
        return '<c><v>' . $value . '</v></c>';
    }
    $text = geo_dashboard_xml((string)$value);
    return '<c t="inlineStr"><is><t xml:space="preserve">' . $text . '</t></is></c>';
}

function geo_dashboard_xlsx_sheet(array $rows): string {
    $xmlRows = [];
    foreach ($rows as $rIndex => $row) {
        $cells = array_map('geo_dashboard_xlsx_cell', $row);
        $xmlRows[] = '<row r="' . ($rIndex + 1) . '">' . implode('', $cells) . '</row>';
    }
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        . '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        . '<sheetData>' . implode('', $xmlRows) . '</sheetData></worksheet>';
}

function geo_dashboard_xlsx_write_row($handle, int $index, array $row): void {
    $cells = array_map('geo_dashboard_xlsx_cell', $row);
    fwrite($handle, '<row r="' . $index . '">' . implode('', $cells) . '</row>');
}

function geo_dashboard_xlsx_open_sheet(string $path) {
    $handle = fopen($path, 'wb');
    if (!$handle) {
        geo_json(['success' => false, 'message' => 'failed to create xlsx sheet'], 500);
    }
    fwrite($handle, '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        . '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>');
    return $handle;
}

function geo_dashboard_xlsx_close_sheet($handle): void {
    fwrite($handle, '</sheetData></worksheet>');
    fclose($handle);
}

function geo_dashboard_send_xlsx_files(string $filename, array $sheetFiles): void {
    if (!class_exists('ZipArchive')) {
        geo_json(['success' => false, 'message' => 'server ZipArchive is unavailable'], 500);
    }
    $tmp = tempnam(sys_get_temp_dir(), 'geo_xlsx_');
    $zip = new ZipArchive();
    if ($zip->open($tmp, ZipArchive::CREATE | ZipArchive::OVERWRITE) !== true) {
        geo_json(['success' => false, 'message' => 'failed to create xlsx'], 500);
    }
    $overrides = '';
    $workbookSheets = '';
    $rels = '';
    $sheetIndex = 1;
    foreach ($sheetFiles as $name => $path) {
        $zip->addFile($path, "xl/worksheets/sheet{$sheetIndex}.xml");
        $overrides .= '<Override PartName="/xl/worksheets/sheet' . $sheetIndex . '.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>';
        $workbookSheets .= '<sheet name="' . geo_dashboard_xml(substr((string)$name, 0, 31)) . '" sheetId="' . $sheetIndex . '" r:id="rId' . $sheetIndex . '"/>';
        $rels .= '<Relationship Id="rId' . $sheetIndex . '" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet' . $sheetIndex . '.xml"/>';
        $sheetIndex++;
    }
    $zip->addFromString('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' . $overrides . '</Types>');
    $zip->addFromString('_rels/.rels', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>');
    $zip->addFromString('xl/workbook.xml', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>' . $workbookSheets . '</sheets></workbook>');
    $zip->addFromString('xl/_rels/workbook.xml.rels', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' . $rels . '</Relationships>');
    $zip->close();
    foreach ($sheetFiles as $path) @unlink($path);
    header_remove('Content-Type');
    header('Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
    header('Content-Disposition: attachment; filename="' . rawurlencode($filename) . '"');
    header('Content-Length: ' . filesize($tmp));
    readfile($tmp);
    @unlink($tmp);
    exit;
}

function geo_dashboard_send_xlsx(string $filename, array $sheets): void {
    if (!class_exists('ZipArchive')) {
        geo_json(['success' => false, 'message' => 'server ZipArchive is unavailable'], 500);
    }
    $tmp = tempnam(sys_get_temp_dir(), 'geo_xlsx_');
    $zip = new ZipArchive();
    if ($zip->open($tmp, ZipArchive::CREATE | ZipArchive::OVERWRITE) !== true) {
        geo_json(['success' => false, 'message' => 'failed to create xlsx'], 500);
    }
    $overrides = '';
    $workbookSheets = '';
    $rels = '';
    $sheetIndex = 1;
    foreach ($sheets as $name => $rows) {
        $zip->addFromString("xl/worksheets/sheet{$sheetIndex}.xml", geo_dashboard_xlsx_sheet($rows));
        $overrides .= '<Override PartName="/xl/worksheets/sheet' . $sheetIndex . '.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>';
        $workbookSheets .= '<sheet name="' . geo_dashboard_xml(substr((string)$name, 0, 31)) . '" sheetId="' . $sheetIndex . '" r:id="rId' . $sheetIndex . '"/>';
        $rels .= '<Relationship Id="rId' . $sheetIndex . '" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet' . $sheetIndex . '.xml"/>';
        $sheetIndex++;
    }
    $zip->addFromString('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' . $overrides . '</Types>');
    $zip->addFromString('_rels/.rels', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>');
    $zip->addFromString('xl/workbook.xml', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>' . $workbookSheets . '</sheets></workbook>');
    $zip->addFromString('xl/_rels/workbook.xml.rels', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' . $rels . '</Relationships>');
    $zip->close();
    header_remove('Content-Type');
    header('Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
    header('Content-Disposition: attachment; filename="' . rawurlencode($filename) . '"');
    header('Content-Length: ' . filesize($tmp));
    readfile($tmp);
    @unlink($tmp);
    exit;
}

function geo_dashboard_safe_filename(string $value): string {
    $value = preg_replace('/[^\p{L}\p{N}._-]+/u', '-', $value);
    $value = trim((string)$value, '.-');
    return $value !== '' ? mb_substr($value, 0, 80, 'UTF-8') : 'file';
}

$cloudUserId = (int)$user['id'];
$isDemoUser = strtolower(trim((string)($user['username'] ?? ''))) === 'tuke';
$action = (string)($_GET['action'] ?? 'overview');

try {
    if ($action === 'remote_status') {
        $latestVersion = geo_dashboard_release_version();
        $offlineStmt = $pdo->prepare("UPDATE geo_desktop_clients
            SET status='offline', message='超过 90 秒未收到客户端心跳', updated_at=NOW()
            WHERE cloud_user_id=? AND status='online' AND last_seen_at < DATE_SUB(NOW(), INTERVAL 90 SECOND)");
        $offlineStmt->execute([$cloudUserId]);

        $clientStmt = $pdo->prepare('SELECT install_id,status,message,payload,last_seen_at,TIMESTAMPDIFF(SECOND,last_seen_at,NOW()) age_seconds FROM geo_desktop_clients WHERE cloud_user_id=? ORDER BY last_seen_at DESC LIMIT 20');
        $clientStmt->execute([$cloudUserId]);
        $clients = [];
        $clientLiveMap = [];
        $onlineClients = 0;
        $outdatedClients = 0;
        $onlineOutdatedClients = 0;
        $runningTasks = 0;
        $localPendingTasks = 0;
        $syncBacklog = 0;
        foreach ($clientStmt->fetchAll() ?: [] as $row) {
            $payload = geo_dashboard_payload($row['payload'] ?? '');
            $desktop = is_array($payload['desktop'] ?? null) ? $payload['desktop'] : [];
            $runtime = is_array($payload['runtime'] ?? null) ? $payload['runtime'] : [];
            $ageSeconds = max(0, (int)($row['age_seconds'] ?? 0));
            $live = (string)$row['status'] === 'online' && $ageSeconds <= 90;
            $version = trim((string)($desktop['app_version'] ?? ''));
            $outdated = $version !== '' && $latestVersion !== '' && geo_dashboard_version_is_older($version, $latestVersion);
            if ($live) $onlineClients++;
            if ($outdated) $outdatedClients++;
            if ($live && $outdated) $onlineOutdatedClients++;
            if ($live) {
                $runningTasks += max(0, (int)($runtime['running_tasks'] ?? 0));
                $localPendingTasks += max(0, (int)($runtime['pending_remote_tasks'] ?? 0));
                $syncBacklog += max(0, (int)($runtime['sync_backlog'] ?? 0));
            }
            $installId = (string)$row['install_id'];
            $clientLiveMap[$installId] = $live;
            $clients[] = [
                'install_id' => $installId,
                'status' => $live ? 'online' : 'offline',
                'live' => $live,
                'version' => $version,
                'version_known' => $version !== '',
                'outdated' => $outdated,
                'platform' => trim((string)($desktop['platform'] ?? '')),
                'worker_state' => trim((string)($runtime['worker_state'] ?? 'unknown')),
                'running_tasks' => max(0, (int)($runtime['running_tasks'] ?? 0)),
                'pending_remote_tasks' => max(0, (int)($runtime['pending_remote_tasks'] ?? 0)),
                'sync_backlog' => max(0, (int)($runtime['sync_backlog'] ?? 0)),
                'poll_seconds' => max(0, (int)($runtime['poll_seconds'] ?? 0)),
                'last_seen_at' => (string)$row['last_seen_at'],
                'age_seconds' => $ageSeconds,
                'message' => (string)($row['message'] ?? ''),
            ];
        }

        $taskStmt = $pdo->prepare('SELECT id,name,status,assigned_install_id,local_task_id,created_at,updated_at,started_at,finished_at,last_status_message FROM geo_remote_tasks WHERE cloud_user_id=? ORDER BY id DESC LIMIT 50');
        $taskStmt->execute([$cloudUserId]);
        $tasks = [];
        $pendingTasks = 0;
        foreach ($taskStmt->fetchAll() ?: [] as $row) {
            $status = (string)($row['status'] ?? '');
            $assignedInstallId = trim((string)($row['assigned_install_id'] ?? ''));
            $assignedLive = $assignedInstallId !== '' && !empty($clientLiveMap[$assignedInstallId]);
            if ($status === 'pending') {
                $pendingTasks++;
                $reason = $onlineClients > 0 ? '客户端在线，等待领取（通常 10 秒内）' : '没有在线客户端，请启动本机 App';
            } elseif ($status === 'claimed') {
                $reason = $assignedLive ? '客户端已领取，正在导入本机' : '领取任务的客户端已离线，超时后会自动重新排队';
            } elseif (in_array($status, ['imported', 'queued'], true)) {
                $reason = $assignedLive ? '任务已进入本机队列' : '执行客户端已离线，请重新启动 App';
            } elseif ($status === 'running') {
                $reason = $assignedLive ? '客户端正在采集并回传进度' : '执行客户端已离线，恢复后会继续补报';
            } else {
                $reason = trim((string)($row['last_status_message'] ?? '')) ?: geo_dashboard_remote_status_label($status);
            }
            $tasks[] = [
                'id' => (int)$row['id'],
                'name' => (string)$row['name'],
                'status' => $status,
                'status_label' => geo_dashboard_remote_status_label($status),
                'assigned_install_id' => $assignedInstallId,
                'assigned_client_live' => $assignedLive,
                'local_task_id' => $row['local_task_id'] !== null ? (int)$row['local_task_id'] : null,
                'created_at' => (string)$row['created_at'],
                'updated_at' => (string)$row['updated_at'],
                'reason' => $reason,
            ];
        }

        if ($isDemoUser) {
            $diagnosis = ['level' => 'demo', 'title' => '在线 Demo 只读模式', 'detail' => '这里展示样例任务和分析数据，不需要连接桌面客户端。'];
        } elseif ($onlineClients > 0 && $onlineOutdatedClients > 0) {
            $diagnosis = ['level' => 'warning', 'title' => '客户端在线，但版本过旧', 'detail' => '请升级到 ' . ($latestVersion ?: '最新版') . '，避免任务同步或状态回传异常。'];
        } elseif ($onlineClients > 0 && $syncBacklog > 0) {
            $diagnosis = ['level' => 'warning', 'title' => '客户端在线，正在补传结果', 'detail' => '还有 ' . $syncBacklog . ' 个任务等待结果或截图回传，请保持 App 运行和网络畅通。'];
        } elseif ($onlineClients > 0 && $runningTasks > 0) {
            $diagnosis = ['level' => 'healthy', 'title' => '客户端正在采集', 'detail' => '当前有 ' . $runningTasks . ' 个任务正在本机执行，完成后会自动同步到云端。'];
        } elseif ($onlineClients > 0 && $localPendingTasks > 0) {
            $diagnosis = ['level' => 'healthy', 'title' => '客户端已接收任务', 'detail' => '本机队列还有 ' . $localPendingTasks . ' 个任务，将按顺序自动执行。'];
        } elseif ($onlineClients > 0) {
            $diagnosis = ['level' => 'healthy', 'title' => '客户端连接正常', 'detail' => '云端任务会自动下发到在线客户端。'];
        } elseif ($clients && $outdatedClients > 0) {
            $diagnosis = ['level' => 'offline', 'title' => '客户端离线且版本过旧', 'detail' => '检测到旧版客户端。请先升级到 ' . ($latestVersion ?: '最新版') . '，再启动 GEO-SOP 并登录同一账号。'];
        } elseif ($clients) {
            $diagnosis = ['level' => 'offline', 'title' => '客户端当前离线', 'detail' => '请在电脑上启动 GEO-SOP 并登录同一账号，心跳恢复后任务会自动领取。'];
        } else {
            $diagnosis = ['level' => 'offline', 'title' => '尚未连接桌面客户端', 'detail' => '请先安装 GEO-SOP，在本机登录当前云端账号。'];
        }

        geo_json([
            'success' => true,
            'demo' => $isDemoUser,
            'latest_version' => $latestVersion,
            'checked_at' => geo_now(),
            'diagnosis' => $diagnosis,
            'summary' => [
                'online_clients' => $onlineClients,
                'outdated_clients' => $outdatedClients,
                'online_outdated_clients' => $onlineOutdatedClients,
                'pending_tasks' => $pendingTasks,
                'running_tasks' => $runningTasks,
                'local_pending_tasks' => $localPendingTasks,
                'sync_backlog' => $syncBacklog,
            ],
            'clients' => $clients,
            'tasks' => $tasks,
        ]);
    }

    if ($action === 'export_geo') {
        @set_time_limit(180);
        geo_dashboard_stream_rows($pdo);
        $taskNames = geo_dashboard_task_name_map($pdo, $cloudUserId);
        $dates = [];
        $groups = [];
        $detailPath = tempnam(sys_get_temp_dir(), 'geo_detail_');
        $detailHandle = geo_dashboard_xlsx_open_sheet($detailPath);
        $detailRow = 1;
        geo_dashboard_xlsx_write_row($detailHandle, $detailRow++, ['采集时间', '任务', 'AI平台', '问题', '品牌曝光', '曝光关键词', '引用数量', '截图路径', 'AI回答']);
        $stmt = geo_dashboard_filtered_stmt($pdo, $cloudUserId, 20000, 'install_id,local_id,local_task_id,platform,question,has_brand_exposure,payload,local_created_at,synced_at');
        $rowCount = 0;
        while ($row = $stmt->fetch(PDO::FETCH_ASSOC)) {
            $rowCount++;
            $payload = geo_dashboard_payload($row['payload'] ?? '');
            $refs = geo_dashboard_refs($payload);
            $createdAt = (string)($row['local_created_at'] ?: $row['synced_at']);
            $date = substr($createdAt, 0, 10);
            $dates[$date] = true;
            $platformName = geo_dashboard_platform_name((string)$row['platform']);
            $question = (string)$row['question'];
            $hasExposure = ((int)$row['has_brand_exposure']) === 1;
            $key = $platformName . '|' . $question;
            if (!isset($groups[$key])) {
                $groups[$key] = ['platform' => $platformName, 'question' => $question, 'dates' => [], 'exposed_dates' => []];
            }
            $groups[$key]['dates'][$date] = true;
            if ($hasExposure) $groups[$key]['exposed_dates'][$date] = true;
            $taskKey = (string)$row['install_id'] . ':' . (int)$row['local_task_id'];
            geo_dashboard_xlsx_write_row($detailHandle, $detailRow++, [
                $createdAt,
                $taskNames[$taskKey] ?? '',
                $platformName,
                $question,
                $hasExposure ? '是' : '否',
                implode('、', is_array($payload['exposed_keywords'] ?? null) ? array_values($payload['exposed_keywords']) : []),
                count($refs),
                (string)($payload['screenshot_path'] ?? ''),
                mb_substr((string)($payload['answer'] ?? ''), 0, 8000, 'UTF-8'),
            ]);
            unset($payload, $refs);
        }
        geo_dashboard_xlsx_close_sheet($detailHandle);
        if ($rowCount <= 0) {
            @unlink($detailPath);
            geo_json(['success' => false, 'message' => '当前筛选条件下暂无可导出的GEO效果数据'], 404);
        }
        $dates = array_keys($dates);
        sort($dates);
        $summaryPath = tempnam(sys_get_temp_dir(), 'geo_summary_');
        $summaryHandle = geo_dashboard_xlsx_open_sheet($summaryPath);
        $summaryRow = 1;
        geo_dashboard_xlsx_write_row($summaryHandle, $summaryRow++, array_merge(['序号', 'AI平台', '监控问题', '达标天数'], $dates));
        $i = 1;
        foreach ($groups as $group) {
            $line = [$i++, $group['platform'], $group['question'], count($group['exposed_dates'])];
            foreach ($dates as $date) $line[] = isset($group['exposed_dates'][$date]) ? '√' : '';
            geo_dashboard_xlsx_write_row($summaryHandle, $summaryRow++, $line);
        }
        geo_dashboard_xlsx_close_sheet($summaryHandle);
        geo_dashboard_send_xlsx_files('GEO效果_' . date('Ymd_His') . '.xlsx', ['GEO效果汇总' => $summaryPath, '采集明细' => $detailPath]);
    }

    if ($action === 'export_screenshots_zip') {
        if (!class_exists('ZipArchive')) {
            geo_json(['success' => false, 'message' => 'server ZipArchive is unavailable'], 500);
        }
        $rows = geo_dashboard_filtered_rows($pdo, $cloudUserId, 10000);
        if (!$rows) {
            geo_json(['success' => false, 'message' => '没有找到可导出的截图'], 404);
        }
        $pairs = array_map(fn($row) => ['install_id' => $row['install_id'], 'local_result_id' => (int)$row['local_id']], $rows);
        $assets = geo_dashboard_asset_map($pdo, $cloudUserId, $pairs);
        $tmp = tempnam(sys_get_temp_dir(), 'geo_zip_');
        $zip = new ZipArchive();
        if ($zip->open($tmp, ZipArchive::CREATE | ZipArchive::OVERWRITE) !== true) {
            geo_json(['success' => false, 'message' => 'failed to create zip'], 500);
        }
        $count = 0;
        foreach ($rows as $row) {
            $key = (string)$row['install_id'] . ':' . (int)$row['local_id'];
            $asset = $assets[$key] ?? null;
            $path = $asset['storage_path'] ?? '';
            if (!$path || !is_file($path)) continue;
            $date = substr((string)($row['local_created_at'] ?: $row['synced_at']), 0, 10);
            $name = geo_dashboard_safe_filename((string)$row['platform']) . '_' . geo_dashboard_safe_filename((string)$row['question']) . '_' . $date . '_' . (int)$row['local_id'] . '.' . pathinfo($path, PATHINFO_EXTENSION);
            $zip->addFile($path, $name);
            $count++;
        }
        $zip->close();
        if ($count <= 0) {
            $zip = new ZipArchive();
            if ($zip->open($tmp, ZipArchive::CREATE | ZipArchive::OVERWRITE) === true) {
                $zip->addFromString('README.txt', "没有找到已上传到云端的截图。\n请先在客户端点击“上传云端”，客户端会自动上传本地采集截图；之后再回到云端下载长截图 ZIP。\n");
                $zip->close();
            }
        }
        header_remove('Content-Type');
        header('Content-Type: application/zip');
        header('Content-Disposition: attachment; filename="' . rawurlencode('GEO长截图_' . date('Ymd_His') . '.zip') . '"');
        header('Content-Length: ' . filesize($tmp));
        readfile($tmp);
        @unlink($tmp);
        exit;
    }

    if ($action === 'geo_coverage') {
        $taskNames = geo_dashboard_task_name_map($pdo, $cloudUserId);
        $taskIdFilter = (int)($_GET['task_id'] ?? 0);
        $installIdFilter = trim((string)($_GET['install_id'] ?? ''));
        $platformFilter = trim((string)($_GET['platform'] ?? ''));
        $dateFilter = trim((string)($_GET['date'] ?? ''));
        $startDate = $dateFilter !== '' ? $dateFilter : trim((string)($_GET['start_date'] ?? ''));
        $endDate = $dateFilter !== '' ? $dateFilter : trim((string)($_GET['end_date'] ?? ''));

        $manuscriptWhere = ['cloud_user_id=?'];
        $manuscriptParams = [$cloudUserId];
        if ($installIdFilter !== '') {
            $manuscriptWhere[] = 'install_id=?';
            $manuscriptParams[] = $installIdFilter;
        }
        $stmt = $pdo->prepare('SELECT install_id,local_id,title,url,payload,local_created_at,synced_at FROM geo_sync_manuscripts WHERE ' . implode(' AND ', $manuscriptWhere) . ' ORDER BY title ASC, local_id ASC LIMIT 3000');
        $stmt->execute($manuscriptParams);
        $manuscripts = [];
        $manuscriptBuckets = [];
        foreach ($stmt->fetchAll(PDO::FETCH_ASSOC) ?: [] as $row) {
            $payload = geo_dashboard_payload($row['payload'] ?? '');
            $taskIds = geo_dashboard_task_ids_from_payload($payload);
            if ($taskIdFilter > 0 && $taskIds && !in_array($taskIdFilter, $taskIds, true)) continue;
            $taskLabels = [];
            foreach ($taskIds as $taskId) {
                $taskKey = (string)$row['install_id'] . ':' . $taskId;
                if (!empty($taskNames[$taskKey])) $taskLabels[] = $taskNames[$taskKey];
            }
            $manuscripts[] = [
                'id' => (int)$row['local_id'],
                'install_id' => (string)$row['install_id'],
                'title' => trim((string)$row['title']) ?: '未命名稿件',
                'url' => trim((string)$row['url']),
                'task_ids' => $taskIds,
                'task_name' => $taskLabels ? implode('、', array_values(array_unique($taskLabels))) : '未关联',
                'is_cited' => false,
                'cited_count' => 0,
                'details' => [],
                'created_at' => $row['local_created_at'] ?: $row['synced_at'],
            ];
            $index = count($manuscripts) - 1;
            $domain = geo_dashboard_main_domain_from_url((string)$row['url']);
            if ($domain !== '') $manuscriptBuckets[$domain][] = $index;
        }

        $resultWhere = ['cloud_user_id=?'];
        $resultParams = [$cloudUserId];
        if ($taskIdFilter > 0) {
            $resultWhere[] = 'local_task_id=?';
            $resultParams[] = $taskIdFilter;
        }
        if ($installIdFilter !== '') {
            $resultWhere[] = 'install_id=?';
            $resultParams[] = $installIdFilter;
        }
        if ($platformFilter !== '') {
            $resultWhere[] = 'platform=?';
            $resultParams[] = $platformFilter;
        }
        if ($startDate !== '') {
            $resultWhere[] = 'result_at >= ?';
            $resultParams[] = $startDate . ' 00:00:00';
        }
        if ($endDate !== '') {
            $resultWhere[] = 'result_at <= ?';
            $resultParams[] = $endDate . ' 23:59:59';
        }
        $sql = 'SELECT install_id,local_id,local_task_id,platform,question,reference_items,local_created_at,synced_at FROM geo_sync_results WHERE ' . implode(' AND ', $resultWhere) . ' ORDER BY result_at DESC, id DESC LIMIT 10000';
        geo_dashboard_stream_rows($pdo);
        $stmt = $pdo->prepare($sql);
        $stmt->execute($resultParams);
        while ($result = $stmt->fetch(PDO::FETCH_ASSOC)) {
            $refs = geo_dashboard_compact_refs($result['reference_items'] ?? '');
            if (!$refs) continue;
            foreach ($refs as $ref) {
                if (!is_array($ref)) continue;
                $refUrl = (string)($ref['url'] ?? $ref['link'] ?? $ref['domain'] ?? '');
                if ($refUrl === '') continue;
                $refDomain = geo_dashboard_main_domain_from_url($refUrl);
                $candidateIndexes = $refDomain !== '' && isset($manuscriptBuckets[$refDomain])
                    ? $manuscriptBuckets[$refDomain]
                    : array_keys($manuscripts);
                foreach ($candidateIndexes as $manuscriptIndex) {
                    $manuscript = $manuscripts[$manuscriptIndex];
                    if ($manuscript['install_id'] !== (string)$result['install_id']) continue;
                    if ($manuscript['task_ids'] && !in_array((int)$result['local_task_id'], $manuscript['task_ids'], true)) continue;
                    if (!geo_dashboard_url_matches((string)$manuscript['url'], $refUrl)) continue;
                    $manuscripts[$manuscriptIndex]['is_cited'] = true;
                    $manuscripts[$manuscriptIndex]['cited_count']++;
                    if (count($manuscripts[$manuscriptIndex]['details']) < 20) {
                        $manuscripts[$manuscriptIndex]['details'][] = [
                            'platform' => (string)$result['platform'],
                            'platform_name' => geo_dashboard_platform_name((string)$result['platform']),
                            'question' => (string)$result['question'],
                            'reference_title' => (string)($ref['title'] ?? ''),
                            'reference_url' => $refUrl,
                            'created_at' => $result['local_created_at'] ?: $result['synced_at'],
                            'result_id' => (int)$result['local_id'],
                        ];
                    }
                }
            }
        }

        $groups = [];
        foreach ($manuscripts as $manuscript) {
            $title = $manuscript['title'] ?: '未命名稿件';
            if (!isset($groups[$title])) {
                $groups[$title] = [
                    'title' => $title,
                    'task_name' => '',
                    'is_cited' => false,
                    'cited_count' => 0,
                    'url_count' => 0,
                    'children' => [],
                ];
            }
            $groups[$title]['children'][] = $manuscript;
            $groups[$title]['url_count']++;
            $groups[$title]['is_cited'] = $groups[$title]['is_cited'] || $manuscript['is_cited'];
            $groups[$title]['cited_count'] += (int)$manuscript['cited_count'];
        }
        foreach ($groups as &$group) {
            $taskLabels = [];
            foreach ($group['children'] as $child) {
                if (!empty($child['task_name']) && $child['task_name'] !== '未关联') $taskLabels[] = $child['task_name'];
            }
            $group['task_name'] = $taskLabels ? implode('、', array_values(array_unique($taskLabels))) : '未关联';
            usort($group['children'], fn($a, $b) => ((int)$b['cited_count'] <=> (int)$a['cited_count']) ?: strcmp((string)$a['url'], (string)$b['url']));
        }
        unset($group);
        $groupRows = array_values($groups);
        usort($groupRows, fn($a, $b) => ((int)$b['cited_count'] <=> (int)$a['cited_count']) ?: strcmp((string)$a['title'], (string)$b['title']));
        geo_json([
            'success' => true,
            'total_titles' => count($groupRows),
            'total_urls' => count($manuscripts),
            'cited_titles' => count(array_filter($groupRows, fn($row) => $row['is_cited'])),
            'cited_urls' => count(array_filter($manuscripts, fn($row) => $row['is_cited'])),
            'groups' => $groupRows,
        ]);
    }

    if ($action === 'tasks') {
        $stmt = $pdo->prepare('SELECT install_id,local_id,name,status,payload,local_created_at,local_updated_at,synced_at FROM geo_sync_tasks WHERE cloud_user_id=? ORDER BY COALESCE(local_updated_at, synced_at) DESC, id DESC LIMIT 500');
        $stmt->execute([$cloudUserId]);
        $tasks = [];
        foreach ($stmt->fetchAll() ?: [] as $row) {
            $payload = geo_dashboard_payload($row['payload'] ?? '');
            $tasks[] = [
                'install_id' => (string)$row['install_id'],
                'local_id' => (int)$row['local_id'],
                'name' => (string)$row['name'],
                'status' => (string)($row['status'] ?? ''),
                'platforms' => is_array($payload['platforms'] ?? null) ? array_values($payload['platforms']) : [],
                'questions' => is_array($payload['questions'] ?? null) ? array_values($payload['questions']) : [],
                'brand_keywords' => is_array($payload['brand_keywords'] ?? null) ? array_values($payload['brand_keywords']) : [],
                'created_at' => $row['local_created_at'],
                'updated_at' => $row['local_updated_at'],
                'synced_at' => $row['synced_at'],
            ];
        }
        geo_json(['success' => true, 'tasks' => $tasks]);
    }

    if ($action === 'results') {
        $where = ['cloud_user_id=?'];
        $params = [$cloudUserId];
        $taskId = trim((string)($_GET['task_id'] ?? ''));
        $installId = trim((string)($_GET['install_id'] ?? ''));
        if ($taskId !== '') {
            $where[] = 'local_task_id=?';
            $params[] = (int)$taskId;
        }
        if ($installId !== '') {
            $where[] = 'install_id=?';
            $params[] = $installId;
        }
        $platform = trim((string)($_GET['platform'] ?? ''));
        if ($platform !== '') {
            $where[] = 'platform=?';
            $params[] = $platform;
        }
        $keyword = trim((string)($_GET['keyword'] ?? ''));
        if ($keyword !== '') {
            $where[] = '(question LIKE ? OR payload LIKE ?)';
            $params[] = '%' . $keyword . '%';
            $params[] = '%' . $keyword . '%';
        }
        $exposed = trim((string)($_GET['exposed'] ?? ''));
        if ($exposed === '1' || $exposed === '0') {
            $where[] = 'has_brand_exposure=?';
            $params[] = (int)$exposed;
        }
        $start = trim((string)($_GET['start_date'] ?? ''));
        if ($start !== '') {
            $where[] = 'result_at >= ?';
            $params[] = $start . ' 00:00:00';
        }
        $end = trim((string)($_GET['end_date'] ?? ''));
        if ($end !== '') {
            $where[] = 'result_at <= ?';
            $params[] = $end . ' 23:59:59';
        }
        $limit = geo_dashboard_limit();
        $offset = max(0, (int)($_GET['offset'] ?? 0));

        $countStmt = $pdo->prepare('SELECT COUNT(*) c FROM geo_sync_results WHERE ' . implode(' AND ', $where));
        $countStmt->execute($params);
        $total = (int)($countStmt->fetch()['c'] ?? 0);

        $sql = 'SELECT * FROM geo_sync_results WHERE ' . implode(' AND ', $where) . ' ORDER BY result_at DESC, id DESC LIMIT ' . $limit . ' OFFSET ' . $offset;
        $stmt = $pdo->prepare($sql);
        $stmt->execute($params);
        $rows = $stmt->fetchAll() ?: [];
        $taskMap = geo_dashboard_task_map($pdo, $cloudUserId);
        $pairs = array_map(fn($row) => ['install_id' => $row['install_id'], 'local_result_id' => (int)$row['local_id']], $rows);
        $assets = geo_dashboard_asset_map($pdo, $cloudUserId, $pairs);
        $results = [];
        foreach ($rows as $row) {
            $key = (string)$row['install_id'] . ':' . (int)$row['local_id'];
            $results[] = geo_dashboard_result_item($row, $taskMap, $assets[$key] ?? null, 600, true);
        }
        geo_json(['success' => true, 'total' => $total, 'limit' => $limit, 'offset' => $offset, 'results' => $results]);
    }

    if ($action === 'result') {
        $localId = (int)($_GET['local_id'] ?? 0);
        $installId = trim((string)($_GET['install_id'] ?? ''));
        if ($localId <= 0 || $installId === '') {
            geo_json(['success' => false, 'message' => 'install_id and local_id are required'], 400);
        }
        $stmt = $pdo->prepare('SELECT * FROM geo_sync_results WHERE cloud_user_id=? AND install_id=? AND local_id=? LIMIT 1');
        $stmt->execute([$cloudUserId, $installId, $localId]);
        $row = $stmt->fetch();
        if (!$row) geo_json(['success' => false, 'message' => 'result not found'], 404);
        $taskMap = geo_dashboard_task_map($pdo, $cloudUserId);
        $assets = geo_dashboard_asset_map($pdo, $cloudUserId, [['install_id' => $installId, 'local_result_id' => $localId]]);
        $key = $installId . ':' . $localId;
        geo_json(['success' => true, 'result' => geo_dashboard_result_item($row, $taskMap, $assets[$key] ?? null)]);
    }

    if ($action === 'reference_analysis') {
        $deduplicate = strtolower((string)($_GET['deduplicate'] ?? 'true')) !== 'false';
        $scan = geo_dashboard_reference_scan($pdo, $cloudUserId, $deduplicate);
        geo_json([
            'success' => true,
            'full_data' => geo_dashboard_reference_items($scan['full_counts']),
            'top_data' => geo_dashboard_reference_items($scan['top_counts']),
            'total_results' => $scan['total_results'],
            'total_references' => array_sum($scan['full_counts']),
            'deduplicated' => $deduplicate,
        ]);
    }

    if ($action === 'reference_domains') {
        $level = (string)($_GET['level'] ?? 'top') === 'full' ? 'full' : 'top';
        $scan = geo_dashboard_reference_scan($pdo, $cloudUserId, false);
        $counts = $level === 'full' ? $scan['full_counts'] : $scan['top_counts'];
        geo_json([
            'success' => true,
            'level' => $level,
            'domains' => array_keys($counts),
            'counts' => $counts,
        ]);
    }

    if ($action === 'reference_trends') {
        $level = (string)($_GET['level'] ?? 'top') === 'full' ? 'full' : 'top';
        $topN = max(1, min(20, (int)($_GET['top_n'] ?? 10)));
        $selected = $_GET['domains'] ?? [];
        if (!is_array($selected)) $selected = array_filter(array_map('trim', explode(',', (string)$selected)));
        $selected = array_values(array_unique(array_filter(array_map('strval', $selected))));
        $scan = geo_dashboard_reference_scan($pdo, $cloudUserId, false);
        $counts = $level === 'full' ? $scan['full_counts'] : $scan['top_counts'];
        $daily = $level === 'full' ? $scan['daily_full'] : $scan['daily_top'];
        $domains = $selected ?: array_slice(array_keys($counts), 0, $topN);
        $dates = array_keys($daily);
        $series = [];
        foreach ($domains as $domain) {
            $values = [];
            foreach ($dates as $date) $values[] = (int)($daily[$date][$domain] ?? 0);
            $series[] = ['name' => $domain, 'type' => 'line', 'smooth' => true, 'data' => $values];
        }
        geo_json([
            'success' => true,
            'level' => $level,
            'dates' => $dates,
            'series' => $series,
            'top_domains' => $domains,
        ]);
    }

    if ($action === 'references') {
        $stmt = $pdo->prepare('SELECT reference_domains FROM geo_sync_results WHERE cloud_user_id=? AND reference_count>0 ORDER BY result_at DESC LIMIT 5000');
        $stmt->execute([$cloudUserId]);
        $domains = [];
        foreach ($stmt->fetchAll() ?: [] as $row) {
            $rowDomains = json_decode((string)($row['reference_domains'] ?? ''), true);
            if (!is_array($rowDomains)) continue;
            foreach ($rowDomains as $domain) {
                $domain = trim((string)$domain);
                if ($domain !== '') $domains[$domain] = ($domains[$domain] ?? 0) + 1;
            }
        }
        arsort($domains);
        $items = [];
        foreach (array_slice($domains, 0, geo_dashboard_limit(), true) as $domain => $count) {
            $items[] = ['domain' => $domain, 'count' => (int)$count];
        }
        geo_json(['success' => true, 'references' => $items]);
    }

    if ($action === 'overview') {
        $stmt = $pdo->prepare('SELECT COUNT(*) total,COALESCE(SUM(has_brand_exposure),0) exposed,COALESCE(SUM(has_screenshot),0) screenshots,SUM(reference_count>0) reference_results,COUNT(DISTINCT platform) platforms FROM geo_sync_results WHERE cloud_user_id=?');
        $stmt->execute([$cloudUserId]);
        $metrics = $stmt->fetch() ?: [];
        $total = (int)($metrics['total'] ?? 0);
        $exposed = (int)($metrics['exposed'] ?? 0);
        $screenshots = (int)($metrics['screenshots'] ?? 0);
        $referenceResults = (int)($metrics['reference_results'] ?? 0);
        $platforms = [];
        $platformStmt = $pdo->prepare('SELECT platform,COUNT(*) answers,COALESCE(SUM(has_brand_exposure),0) exposed FROM geo_sync_results WHERE cloud_user_id=? GROUP BY platform ORDER BY answers DESC');
        $platformStmt->execute([$cloudUserId]);
        foreach ($platformStmt->fetchAll() ?: [] as $row) {
            $platform = (string)$row['platform'];
            $platforms[] = [
                'platform' => $platform,
                'platform_name' => geo_dashboard_platform_name($platform),
                'answers' => (int)$row['answers'],
                'exposed' => (int)$row['exposed'],
                'exposure_rate' => geo_dashboard_percent((int)$row['exposed'], (int)$row['answers']),
            ];
        }
        $daily = [];
        $dailyStmt = $pdo->prepare('SELECT date_key,answers,exposed FROM (SELECT DATE(result_at) date_key,COUNT(*) answers,COALESCE(SUM(has_brand_exposure),0) exposed FROM geo_sync_results WHERE cloud_user_id=? GROUP BY date_key ORDER BY date_key DESC LIMIT 366) recent_days ORDER BY date_key ASC');
        $dailyStmt->execute([$cloudUserId]);
        foreach ($dailyStmt->fetchAll() ?: [] as $row) {
            $daily[] = [
                'date' => (string)$row['date_key'],
                'answers' => (int)$row['answers'],
                'exposed' => (int)$row['exposed'],
                'exposure_rate' => geo_dashboard_percent((int)$row['exposed'], (int)$row['answers']),
            ];
        }
        $taskCount = (int)$pdo->query('SELECT COUNT(*) c FROM geo_sync_tasks WHERE cloud_user_id=' . $cloudUserId)->fetch()['c'];
        geo_json([
            'success' => true,
            'metrics' => [
                'tasks' => $taskCount,
                'results' => $total,
                'brand_exposure_results' => $exposed,
                'brand_exposure_rate' => geo_dashboard_percent($exposed, $total),
                'screenshots' => $screenshots,
                'screenshot_rate' => geo_dashboard_percent($screenshots, $total),
                'reference_results' => $referenceResults,
                'reference_rate' => geo_dashboard_percent($referenceResults, $total),
                'platforms' => (int)($metrics['platforms'] ?? 0),
            ],
            'platforms' => $platforms,
            'daily' => $daily,
        ]);
    }

    geo_json(['success' => false, 'message' => 'unknown action'], 400);
} catch (Throwable $e) {
    geo_json(['success' => false, 'message' => 'dashboard query failed', 'error' => $e->getMessage()], 500);
}
