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

function geo_dashboard_domain(string $url): string {
    $url = trim($url);
    if ($url === '') return '';
    if (!preg_match('#^https?://#i', $url)) $url = 'https://' . $url;
    $host = parse_url($url, PHP_URL_HOST);
    if (!$host) return '';
    return strtolower((string)preg_replace('/^www\./', '', $host));
}

function geo_dashboard_platform_name(string $platform): string {
    $map = [
        'doubao' => '豆包',
        'deepseek' => 'DeepSeek',
        'kimi' => 'Kimi',
        'qianwen' => '通义千问',
        'yuanbao' => '腾讯元宝',
        'chatgpt' => 'ChatGPT',
        'gemini' => 'Gemini',
        'wenxin' => '文心一言',
    ];
    return $map[$platform] ?? $platform;
}

function geo_dashboard_percent(int $part, int $total): float {
    return $total > 0 ? round($part * 100 / $total, 1) : 0.0;
}

function geo_dashboard_limit(): int {
    $limit = (int)($_GET['limit'] ?? 100);
    return max(1, min(500, $limit));
}

function geo_dashboard_task_map(PDO $pdo, int $cloudUserId): array {
    $stmt = $pdo->prepare('SELECT install_id,local_id,name,status,payload,local_created_at,local_updated_at,synced_at FROM geo_sync_tasks WHERE cloud_user_id=? ORDER BY COALESCE(local_updated_at, synced_at) DESC, id DESC');
    $stmt->execute([$cloudUserId]);
    $map = [];
    foreach ($stmt->fetchAll() ?: [] as $row) {
        $map[(string)$row['install_id'] . ':' . (int)$row['local_id']] = $row;
    }
    return $map;
}

function geo_dashboard_asset_map(PDO $pdo, int $cloudUserId, array $pairs): array {
    if (!$pairs) return [];
    $clauses = [];
    $params = [$cloudUserId];
    foreach ($pairs as $pair) {
        $clauses[] = '(install_id=? AND local_result_id=?)';
        $params[] = (string)$pair['install_id'];
        $params[] = (int)$pair['local_result_id'];
    }
    $sql = 'SELECT install_id,local_result_id,storage_path,public_url,file_size,updated_at FROM geo_sync_assets WHERE cloud_user_id=? AND kind="screenshot" AND (' . implode(' OR ', $clauses) . ') ORDER BY updated_at DESC';
    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    $assets = [];
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
    return $assets;
}

function geo_dashboard_result_item(array $row, array $taskMap, ?array $asset = null): array {
    $payload = geo_dashboard_payload($row['payload'] ?? '');
    $taskKey = (string)$row['install_id'] . ':' . (int)$row['local_task_id'];
    $task = $taskMap[$taskKey] ?? null;
    $refs = geo_dashboard_refs($payload);
    $aiSentiment = $payload['ai_sentiment'] ?? $payload['ai_sentiment_result'] ?? null;
    if (is_string($aiSentiment)) {
        $decoded = json_decode($aiSentiment, true);
        $aiSentiment = is_array($decoded) ? $decoded : null;
    }
    return [
        'id' => (int)$row['id'],
        'install_id' => (string)$row['install_id'],
        'local_id' => (int)$row['local_id'],
        'local_task_id' => (int)$row['local_task_id'],
        'task_name' => $task ? (string)$task['name'] : '',
        'platform' => (string)$row['platform'],
        'platform_name' => geo_dashboard_platform_name((string)$row['platform']),
        'question' => (string)$row['question'],
        'answer' => (string)($payload['answer'] ?? ''),
        'has_brand_exposure' => ((int)$row['has_brand_exposure']) === 1,
        'exposed_keywords' => is_array($payload['exposed_keywords'] ?? null) ? array_values($payload['exposed_keywords']) : [],
        'references' => $refs,
        'reference_count' => count($refs),
        'screenshot_path' => (string)($payload['screenshot_path'] ?? ''),
        'screenshot_url' => $asset['url'] ?? null,
        'ai_sentiment' => is_array($aiSentiment) ? $aiSentiment : null,
        'created_at' => $row['local_created_at'] ?: $row['synced_at'],
        'synced_at' => $row['synced_at'],
    ];
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
        $where[] = 'COALESCE(local_created_at, synced_at) >= ?';
        $params[] = $start . ' 00:00:00';
    }
    $end = trim((string)($_GET['end_date'] ?? ''));
    if ($end !== '') {
        $where[] = 'COALESCE(local_created_at, synced_at) <= ?';
        $params[] = $end . ' 23:59:59';
    }
    $sql = 'SELECT * FROM geo_sync_results WHERE ' . implode(' AND ', $where) . ' ORDER BY platform ASC, question ASC, COALESCE(local_created_at, synced_at) ASC, id ASC LIMIT ' . max(1, min(10000, $limit));
    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    return $stmt->fetchAll() ?: [];
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
$action = (string)($_GET['action'] ?? 'overview');

try {
    if ($action === 'export_geo') {
        $rows = geo_dashboard_filtered_rows($pdo, $cloudUserId, 10000);
        if (!$rows) {
            geo_json(['success' => false, 'message' => '当前筛选条件下暂无可导出的GEO效果数据'], 404);
        }
        $taskMap = geo_dashboard_task_map($pdo, $cloudUserId);
        $pairs = array_map(fn($row) => ['install_id' => $row['install_id'], 'local_result_id' => (int)$row['local_id']], $rows);
        $assets = geo_dashboard_asset_map($pdo, $cloudUserId, $pairs);
        $items = [];
        foreach ($rows as $row) {
            $key = (string)$row['install_id'] . ':' . (int)$row['local_id'];
            $items[] = geo_dashboard_result_item($row, $taskMap, $assets[$key] ?? null);
        }
        $dates = [];
        $groups = [];
        foreach ($items as $item) {
            $date = substr((string)$item['created_at'], 0, 10);
            $dates[$date] = true;
            $key = $item['platform_name'] . '|' . $item['question'];
            if (!isset($groups[$key])) {
                $groups[$key] = ['platform' => $item['platform_name'], 'question' => $item['question'], 'dates' => [], 'exposed_dates' => []];
            }
            $groups[$key]['dates'][$date] = true;
            if ($item['has_brand_exposure']) $groups[$key]['exposed_dates'][$date] = true;
        }
        $dates = array_keys($dates);
        sort($dates);
        $summary = [array_merge(['序号', 'AI平台', '监控问题', '达标天数'], $dates)];
        $i = 1;
        foreach ($groups as $group) {
            $line = [$i++, $group['platform'], $group['question'], count($group['exposed_dates'])];
            foreach ($dates as $date) $line[] = isset($group['exposed_dates'][$date]) ? '√' : '';
            $summary[] = $line;
        }
        $detail = [['采集时间', '任务', 'AI平台', '问题', '品牌曝光', '曝光关键词', '引用数量', '截图URL', 'AI回答']];
        foreach ($items as $item) {
            $detail[] = [
                $item['created_at'],
                $item['task_name'],
                $item['platform_name'],
                $item['question'],
                $item['has_brand_exposure'] ? '是' : '否',
                implode('、', $item['exposed_keywords']),
                $item['reference_count'],
                $item['screenshot_url'] ?: '',
                mb_substr($item['answer'], 0, 30000, 'UTF-8'),
            ];
        }
        geo_dashboard_send_xlsx('GEO效果_' . date('Ymd_His') . '.xlsx', ['GEO效果汇总' => $summary, '采集明细' => $detail]);
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
            $where[] = 'COALESCE(local_created_at, synced_at) >= ?';
            $params[] = $start . ' 00:00:00';
        }
        $end = trim((string)($_GET['end_date'] ?? ''));
        if ($end !== '') {
            $where[] = 'COALESCE(local_created_at, synced_at) <= ?';
            $params[] = $end . ' 23:59:59';
        }
        $limit = geo_dashboard_limit();
        $offset = max(0, (int)($_GET['offset'] ?? 0));

        $countStmt = $pdo->prepare('SELECT COUNT(*) c FROM geo_sync_results WHERE ' . implode(' AND ', $where));
        $countStmt->execute($params);
        $total = (int)($countStmt->fetch()['c'] ?? 0);

        $sql = 'SELECT * FROM geo_sync_results WHERE ' . implode(' AND ', $where) . ' ORDER BY COALESCE(local_created_at, synced_at) DESC, id DESC LIMIT ' . $limit . ' OFFSET ' . $offset;
        $stmt = $pdo->prepare($sql);
        $stmt->execute($params);
        $rows = $stmt->fetchAll() ?: [];
        $taskMap = geo_dashboard_task_map($pdo, $cloudUserId);
        $pairs = array_map(fn($row) => ['install_id' => $row['install_id'], 'local_result_id' => (int)$row['local_id']], $rows);
        $assets = geo_dashboard_asset_map($pdo, $cloudUserId, $pairs);
        $results = [];
        foreach ($rows as $row) {
            $key = (string)$row['install_id'] . ':' . (int)$row['local_id'];
            $results[] = geo_dashboard_result_item($row, $taskMap, $assets[$key] ?? null);
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

    if ($action === 'references') {
        $stmt = $pdo->prepare('SELECT payload FROM geo_sync_results WHERE cloud_user_id=? ORDER BY COALESCE(local_created_at, synced_at) DESC LIMIT 5000');
        $stmt->execute([$cloudUserId]);
        $domains = [];
        foreach ($stmt->fetchAll() ?: [] as $row) {
            foreach (geo_dashboard_refs(geo_dashboard_payload($row['payload'] ?? '')) as $ref) {
                if (!is_array($ref)) continue;
                $domain = geo_dashboard_domain((string)($ref['url'] ?? $ref['link'] ?? $ref['domain'] ?? ''));
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
        $stmt = $pdo->prepare('SELECT platform,has_brand_exposure,payload,local_created_at,synced_at FROM geo_sync_results WHERE cloud_user_id=? ORDER BY COALESCE(local_created_at, synced_at) ASC LIMIT 5000');
        $stmt->execute([$cloudUserId]);
        $rows = $stmt->fetchAll() ?: [];
        $total = count($rows);
        $exposed = 0;
        $screenshots = 0;
        $referenceResults = 0;
        $platforms = [];
        $daily = [];
        foreach ($rows as $row) {
            $payload = geo_dashboard_payload($row['payload'] ?? '');
            $hasExposure = ((int)$row['has_brand_exposure']) === 1;
            if ($hasExposure) $exposed++;
            if (!empty($payload['screenshot_path'])) $screenshots++;
            $refs = geo_dashboard_refs($payload);
            if ($refs) $referenceResults++;
            $platform = (string)$row['platform'];
            if (!isset($platforms[$platform])) $platforms[$platform] = ['platform' => $platform, 'platform_name' => geo_dashboard_platform_name($platform), 'answers' => 0, 'exposed' => 0];
            $platforms[$platform]['answers']++;
            if ($hasExposure) $platforms[$platform]['exposed']++;
            $date = substr((string)($row['local_created_at'] ?: $row['synced_at']), 0, 10);
            if (!isset($daily[$date])) $daily[$date] = ['date' => $date, 'answers' => 0, 'exposed' => 0];
            $daily[$date]['answers']++;
            if ($hasExposure) $daily[$date]['exposed']++;
        }
        foreach ($platforms as &$item) {
            $item['exposure_rate'] = geo_dashboard_percent((int)$item['exposed'], (int)$item['answers']);
        }
        unset($item);
        foreach ($daily as &$item) {
            $item['exposure_rate'] = geo_dashboard_percent((int)$item['exposed'], (int)$item['answers']);
        }
        unset($item);
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
                'platforms' => count($platforms),
            ],
            'platforms' => array_values($platforms),
            'daily' => array_values($daily),
        ]);
    }

    geo_json(['success' => false, 'message' => 'unknown action'], 400);
} catch (Throwable $e) {
    geo_json(['success' => false, 'message' => 'dashboard query failed', 'error' => $e->getMessage()], 500);
}
