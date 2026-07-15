<?php
require '/www/wwwroot/geo.allgood.cn/api/common.php';
require '/www/wwwroot/geo.allgood.cn/api/platforms.php';

$pdo = geo_pdo();
geo_ensure_schema($pdo);
geo_bootstrap($pdo);
$user = geo_current_web_user($pdo);
if (!$user) {
    header('Location: /login/');
    exit;
}
$isDemoUser = strtolower(trim((string)($user['username'] ?? ''))) === 'tuke';
$appVersion = '0.3.13-dev';
$releaseManifest = '/www/wwwroot/geo.allgood.cn/update.json';
if (is_file($releaseManifest)) {
    $releaseData = json_decode((string)file_get_contents($releaseManifest), true);
    if (is_array($releaseData) && !empty($releaseData['version'])) {
        $appVersion = (string)$releaseData['version'];
    }
}

function geo_decode_payload($value): array {
    $data = json_decode((string)$value, true);
    return is_array($data) ? $data : [];
}

function geo_percent(int $part, int $total): float {
    return $total > 0 ? round($part * 100 / $total, 1) : 0.0;
}

function geo_score_label(float $score): string {
    if ($score >= 80) return '健康';
    if ($score >= 60) return '可优化';
    return '需要关注';
}

function geo_domain_from_url(string $url): string {
    $url = trim($url);
    if ($url === '') return '';
    if (!preg_match('#^https?://#i', $url)) $url = 'https://' . $url;
    $host = parse_url($url, PHP_URL_HOST);
    if (!$host) return '';
    $host = strtolower(preg_replace('/^www\./', '', $host));
    return $host ?: '';
}

function geo_payload_refs(array $payload): array {
    $refs = $payload['references'] ?? [];
    if (is_string($refs)) {
        $decoded = json_decode($refs, true);
        $refs = is_array($decoded) ? $decoded : [];
    }
    return is_array($refs) ? $refs : [];
}

function geo_platform_name(string $platform): string {
    $catalog = geo_platform_catalog();
    return (string)($catalog[$platform]['name'] ?? $platform);
}

$message = '';
$supportedPlatforms = geo_platform_catalog();
function geo_remote_status_label(string $status): string {
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
        'pulled' => '已导入本机',
    ][$status] ?? ($status !== '' ? $status : '未知');
}
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    if ($isDemoUser) {
        $message = '在线 Demo 为只读安全模式，不能创建或修改任务。';
    } else {
    $payload = [
        'name' => trim($_POST['name'] ?? '服务端采集任务'),
        'brand_name' => trim($_POST['brand_name'] ?? ''),
        'brand_keywords' => array_values(array_filter(array_map('trim', explode("\n", (string)($_POST['brand_keywords'] ?? ''))))),
        'competitor_brands' => array_values(array_filter(array_map('trim', explode("\n", (string)($_POST['competitor_brands'] ?? ''))))),
        'questions' => array_values(array_filter(array_map('trim', explode("\n", (string)($_POST['questions'] ?? ''))))),
        'platforms' => array_values(array_filter($_POST['platforms'] ?? [])),
        'screenshot_config' => [],
        'collection_interval' => 20,
        'max_parallel_platforms' => 2,
        'schedule_type' => 'manual',
        'schedule_config' => ['source' => 'cloud_dashboard'],
    ];
    $validation = geo_validate_remote_task_payload($payload);
    if ($validation['valid']) {
        $payload = $validation['payload'];
        $now = date('Y-m-d H:i:s');
        $stmt = $pdo->prepare('INSERT INTO geo_remote_tasks (cloud_user_id,name,payload,status,created_at,updated_at) VALUES (?,?,?,?,?,?)');
        $stmt->execute([(int)$user['id'], $payload['name'], json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES), 'pending', $now, $now]);
        $message = '远程任务已创建。桌面端登录同一账号后会自动拉取并执行。';
    } else {
        $message = $validation['message'];
    }
    }
}

$uid = (int)$user['id'];
$remoteStmt = $pdo->prepare('SELECT * FROM geo_remote_tasks WHERE cloud_user_id=? ORDER BY id DESC LIMIT 30');
$remoteStmt->execute([$uid]);
$remoteRows = $remoteStmt->fetchAll();

$offlineStmt = $pdo->prepare("UPDATE geo_desktop_clients
    SET status='offline', message='超过 90 秒未收到客户端心跳', updated_at=NOW()
    WHERE cloud_user_id=? AND status='online' AND last_seen_at < DATE_SUB(NOW(), INTERVAL 90 SECOND)");
$offlineStmt->execute([$uid]);

$clientStmt = $pdo->prepare('SELECT install_id,user_key,status,message,payload,last_seen_at FROM geo_desktop_clients WHERE cloud_user_id=? ORDER BY last_seen_at DESC LIMIT 20');
$clientStmt->execute([$uid]);
$clientRows = $clientStmt->fetchAll();

foreach ($clientRows as &$clientRow) {
    $clientPayload = json_decode((string)($clientRow['payload'] ?? ''), true);
    $clientRow['platform'] = is_array($clientPayload) ? (string)($clientPayload['desktop']['platform'] ?? '') : '';
    $clientRow['version'] = is_array($clientPayload) ? (string)($clientPayload['desktop']['app_version'] ?? '') : '';
    $lastSeen = strtotime((string)($clientRow['last_seen_at'] ?? '')) ?: 0;
    $clientRow['live'] = $lastSeen > 0 && (time() - $lastSeen) <= 90 && (string)$clientRow['status'] === 'online';
}
unset($clientRow);

$configStmt = $pdo->prepare('SELECT name,is_default,payload,local_updated_at,synced_at FROM geo_sync_sentiment_configs WHERE cloud_user_id=? ORDER BY COALESCE(local_updated_at, synced_at) DESC, id DESC LIMIT 10');
$configStmt->execute([$uid]);
$configRows = $configStmt->fetchAll();
$latestInsight = null;
$latestInsightGeneratedAt = '';
foreach ($configRows as &$configRow) {
    $configPayload = geo_decode_payload($configRow['payload'] ?? '');
    $configRow['platform'] = (string)($configPayload['ai_platform'] ?? '');
    $configRow['model'] = (string)($configPayload['ai_model_name'] ?? '');
    $configRow['api_host'] = (string)(parse_url((string)($configPayload['ai_api_url'] ?? ''), PHP_URL_HOST) ?: '');
    $configRow['metadata_ready'] = !empty($configPayload['enable_ai_sentiment'])
        && trim((string)($configPayload['ai_api_url'] ?? '')) !== ''
        && trim((string)($configPayload['ai_model_name'] ?? '')) !== '';
    if ($latestInsight === null && is_array($configPayload['latest_insight'] ?? null)) {
        $latestInsight = $configPayload['latest_insight'];
        $latestInsightGeneratedAt = (string)($configPayload['latest_insight_generated_at'] ?? '');
    }
}
unset($configRow);

$taskStmt = $pdo->prepare('SELECT * FROM geo_sync_tasks WHERE cloud_user_id=? ORDER BY synced_at DESC LIMIT 80');
$taskStmt->execute([$uid]);
$syncedTasks = $taskStmt->fetchAll();

$taskMetricStmt = $pdo->prepare("SELECT COUNT(*) total, COALESCE(SUM(status IN ('running','paused')),0) running FROM geo_sync_tasks WHERE cloud_user_id=?");
$taskMetricStmt->execute([$uid]);
$taskMetricRow = $taskMetricStmt->fetch() ?: [];
$totalTaskCount = (int)($taskMetricRow['total'] ?? 0);
$runningTasks = (int)($taskMetricRow['running'] ?? 0);

$runStmt = $pdo->prepare('SELECT * FROM geo_sync_runs WHERE cloud_user_id=? ORDER BY synced_at DESC LIMIT 1');
$runStmt->execute([$uid]);
$lastRun = $runStmt->fetch() ?: null;

$metricStmt = $pdo->prepare('SELECT COUNT(*) total, COALESCE(SUM(has_brand_exposure),0) exposed, COUNT(DISTINCT platform) platforms FROM geo_sync_results WHERE cloud_user_id=?');
$metricStmt->execute([$uid]);
$metricRow = $metricStmt->fetch() ?: [];
$totalResults = (int)($metricRow['total'] ?? 0);
$exposedResults = (int)($metricRow['exposed'] ?? 0);
$activePlatforms = (int)($metricRow['platforms'] ?? 0);

$screenshotCount = 0;
try {
    $screenshotStmt = $pdo->prepare("SELECT COUNT(DISTINCT CONCAT(install_id, ':', local_result_id)) c FROM geo_sync_assets WHERE cloud_user_id=? AND kind='screenshot'");
    $screenshotStmt->execute([$uid]);
    $screenshotCount = (int)($screenshotStmt->fetch()['c'] ?? 0);
} catch (Throwable $e) {
    $screenshotStmt = $pdo->prepare('SELECT COALESCE(SUM(has_screenshot),0) c FROM geo_sync_results WHERE cloud_user_id=?');
    $screenshotStmt->execute([$uid]);
    $screenshotCount = (int)($screenshotStmt->fetch()['c'] ?? 0);
}

$manuscriptStmt = $pdo->prepare('SELECT COUNT(*) c FROM geo_sync_manuscripts WHERE cloud_user_id=?');
$manuscriptStmt->execute([$uid]);
$manuscriptCount = (int)($manuscriptStmt->fetch()['c'] ?? 0);

$referenceStmt = $pdo->prepare('SELECT COUNT(*) c FROM geo_sync_results WHERE cloud_user_id=? AND reference_count>0');
$referenceStmt->execute([$uid]);
$referenceResultCount = (int)($referenceStmt->fetch()['c'] ?? 0);

$platformStats = [];
$platformStmt = $pdo->prepare('SELECT platform, COUNT(*) answers, COALESCE(SUM(has_brand_exposure),0) exposed FROM geo_sync_results WHERE cloud_user_id=? GROUP BY platform ORDER BY answers DESC LIMIT 8');
$platformStmt->execute([$uid]);
foreach ($platformStmt->fetchAll() ?: [] as $row) {
    $platform = (string)($row['platform'] ?? 'unknown');
    $platformStats[$platform] = ['platform' => $platform, 'answers' => (int)$row['answers'], 'exposed' => (int)$row['exposed']];
}

$dailyStats = [];
$dailyStmt = $pdo->prepare('SELECT DATE(result_at) date_key, COUNT(*) answers, COALESCE(SUM(has_brand_exposure),0) exposed FROM geo_sync_results WHERE cloud_user_id=? GROUP BY date_key ORDER BY date_key DESC LIMIT 14');
$dailyStmt->execute([$uid]);
foreach ($dailyStmt->fetchAll() ?: [] as $row) {
    $dateKey = (string)($row['date_key'] ?: date('Y-m-d'));
    $dailyStats[$dateKey] = ['answers' => (int)$row['answers'], 'exposed' => (int)$row['exposed']];
}

$referenceCounts = [];
$questionStats = [];

$questionStmt = $pdo->prepare('SELECT question,COUNT(*) answers,COALESCE(SUM(has_brand_exposure),0) exposed FROM geo_sync_results WHERE cloud_user_id=? AND question<>\'\' GROUP BY question ORDER BY (COALESCE(SUM(has_brand_exposure),0)/COUNT(*)) ASC, answers DESC LIMIT 5');
$questionStmt->execute([$uid]);
foreach ($questionStmt->fetchAll() ?: [] as $row) {
    $questionStats[(string)$row['question']] = ['question' => (string)$row['question'], 'answers' => (int)$row['answers'], 'exposed' => (int)$row['exposed']];
}

$referenceCursor = 0;
$referencePreviewStmt = $pdo->prepare('SELECT id,reference_domains FROM geo_sync_results WHERE cloud_user_id=? AND reference_count>0 AND id>? ORDER BY id ASC LIMIT 1000');
do {
    $referencePreviewStmt->execute([$uid, $referenceCursor]);
    $referenceBatch = $referencePreviewStmt->fetchAll() ?: [];
    foreach ($referenceBatch as $row) {
        $referenceCursor = max($referenceCursor, (int)$row['id']);
        $domains = json_decode((string)($row['reference_domains'] ?? ''), true);
        if (!is_array($domains)) continue;
        foreach ($domains as $domain) {
            $domain = trim((string)$domain);
            if ($domain !== '') $referenceCounts[$domain] = ($referenceCounts[$domain] ?? 0) + 1;
        }
    }
} while (count($referenceBatch) === 1000);

uasort($platformStats, fn($a, $b) => $b['answers'] <=> $a['answers']);
arsort($referenceCounts);
uasort($questionStats, function ($a, $b) {
    $ar = $a['answers'] ? $a['exposed'] / $a['answers'] : 0;
    $br = $b['answers'] ? $b['exposed'] / $b['answers'] : 0;
    return $ar === $br ? $b['answers'] <=> $a['answers'] : $ar <=> $br;
});
ksort($dailyStats);

$referenceDomains = count($referenceCounts);
$exposureRate = geo_percent($exposedResults, $totalResults);
$screenshotRate = geo_percent($screenshotCount, $totalResults);
$referenceRate = geo_percent($referenceResultCount, $totalResults);
$dataQuality = $totalResults ? round($screenshotRate * 0.45 + $referenceRate * 0.35 + min($totalResults, 20) / 20 * 100 * 0.2, 1) : 0.0;
$coverageScore = round(min($activePlatforms / 4 * 100, 100), 1);
$domainSourceScore = min($referenceDomains / 8 * 100, 100);
$manuscriptSourceScore = min($manuscriptCount / 5 * 100, 100);
$sourceScore = round($domainSourceScore * 0.65 + $manuscriptSourceScore * 0.35, 1);
$geoScore = round($exposureRate * 0.38 + $coverageScore * 0.22 + $sourceScore * 0.2 + $dataQuality * 0.2, 1);

if (!$syncedTasks) {
    $nextAction = ['title' => '先连接桌面端同步数据', 'detail' => '用桌面软件登录同一个账号，完成一次采集并同步后，云端看板会自动出现检测结果。'];
} elseif (!$totalResults) {
    $nextAction = ['title' => '先完成一轮采集', 'detail' => '当前已有任务记录，但还没有回答结果。先在桌面端运行采集，建立第一版基线。'];
} elseif ($exposureRate < 30) {
    $nextAction = ['title' => '优先解决品牌不出现的问题', 'detail' => '从下方曝光最低的问题开始，补充 FAQ、对比页和案例页，让 AI 有内容可以引用。'];
} elseif ($activePlatforms < 3) {
    $nextAction = ['title' => '扩大 AI 平台覆盖', 'detail' => '至少覆盖 3 个平台，避免单个平台偏好影响判断。'];
} elseif ($referenceDomains < 3) {
    $nextAction = ['title' => '补充可被引用的内容源', 'detail' => '让官网知识页、媒体稿和说明页成为 AI 回答里更稳定的引用来源。'];
} else {
    $nextAction = ['title' => '保持固定监测节奏', 'detail' => '每周固定采集，观察品牌出现率、引用来源和竞品压力是否持续变化。'];
}

$trendRows = array_slice($dailyStats, -14, 14, true);
$platformRows = array_slice(array_values($platformStats), 0, 8);
$sourceRows = array_slice($referenceCounts, 0, 6, true);
$weakQuestions = array_slice(array_values($questionStats), 0, 5);
$maxDailyAnswers = 1;
foreach ($trendRows as $item) $maxDailyAnswers = max($maxDailyAnswers, (int)$item['answers']);
$maxSourceCount = $sourceRows ? max($sourceRows) : 1;

?><!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GEO-SOP | AI 品牌可见度工作台</title>
<style>
:root{--blue:#409eff;--blue2:#1769ff;--cyan:#00a6b2;--ink:#1f2937;--muted:#7b8aa0;--line:#dfe6f0;--soft:#f3f6fb;--card:#fff;--dark:#07111f;--good:#67c23a}
	*{box-sizing:border-box}body{margin:0;background:var(--soft);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}a{text-decoration:none;color:inherit}.app-header{height:58px;background:#fff;border-bottom:1px solid #e8eef6;display:flex;align-items:center;justify-content:space-between;padding:0 18px;position:sticky;top:0;z-index:10}.title{display:flex;align-items:center;gap:12px;font-size:20px;font-weight:800}.logo{width:32px;height:32px;border-radius:7px}.tag{display:inline-flex;align-items:center;height:22px;padding:0 8px;border-radius:5px;background:#f0f2f5;color:#606266;font-size:12px;font-weight:700}.tag.green{background:#eaf8df;color:#529b2e}.header-actions{display:flex;gap:10px;align-items:center}.btn,button{display:inline-flex;align-items:center;justify-content:center;gap:6px;height:36px;padding:0 16px;border:1px solid #dcdfe6;border-radius:4px;background:#fff;color:#344054;font-weight:700;cursor:pointer}.btn.primary,button.primary{background:var(--blue);border-color:var(--blue);color:#fff}.btn.small{height:26px;padding:0 10px;font-size:12px}.wrap{width:min(1560px,calc(100% - 48px));max-width:none;margin:0 auto;padding:24px 0}.workspace-hero{display:grid;grid-template-columns:minmax(0,1.9fr) minmax(310px,.95fr);gap:18px}.hero-panel{min-height:242px;background:var(--dark);border-radius:6px;padding:34px 38px;color:#fff;box-shadow:0 18px 50px rgba(14,30,54,.08)}.kicker{font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:var(--cyan);font-weight:900}.hero-panel h1{font-size:34px;margin:14px 0 12px}.hero-panel p{color:#aab7c9;line-height:1.8;margin:0 0 22px}.hero-actions{display:flex;gap:14px;flex-wrap:wrap}.side-stack{display:grid;gap:14px}.side-card,.metric-card,.panel,.tabs{background:#fff;border:1px solid var(--line);border-radius:6px;box-shadow:0 10px 30px rgba(16,32,55,.06)}.panel,.tabs{position:relative}.panel{padding:28px 32px}.panel h2{margin:14px 0 16px;padding-right:120px}.panel>.muted{margin:0 0 24px}.panel form{display:grid;gap:18px}.panel form p{margin:0}.panel .table-wrap{margin-top:18px}.collapse-toggle{position:absolute;top:18px;right:20px;height:30px;padding:0 11px;border-radius:4px;font-size:12px;background:#f8fafc}.panel.is-collapsed{padding-bottom:22px}.panel.is-collapsed>:not(.kicker):not(h2):not(.collapse-toggle){display:none}.tabs.is-collapsed .tab-body{display:none}.tabs.is-collapsed .tab-nav{border-bottom:0}.side-card{padding:22px}.side-card strong{display:block;font-size:19px;margin:10px 0 8px}.muted{color:var(--muted);line-height:1.7}.msg{margin:18px 0 0;padding:12px 14px;background:#ecfdf3;color:#027a48;border-radius:6px}.metric-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:18px 0}.metric-card{padding:20px}.metric-card span,.mini-label{display:block;color:#7b8aa0;font-size:13px;font-weight:700}.metric-card strong{display:block;font-size:30px;margin:8px 0 4px}.tabs{overflow:hidden}.tab-nav{height:38px;display:flex;align-items:center;border-bottom:1px solid var(--line);background:#fff;padding-right:110px}.tab-nav a{height:38px;padding:0 20px;display:flex;align-items:center;color:#7b8aa0;font-weight:800;font-size:14px;border-right:1px solid #eef2f7}.tab-nav a.active{color:var(--blue);background:#f8fbff}.tab-body{padding:20px}.analysis-summary{display:grid;grid-template-columns:220px 1fr;gap:16px}.score-hero,.action-hero{border:1px solid var(--line);border-radius:6px;background:#fff;padding:22px}.score-hero{text-align:center}.score-ring{width:126px;height:126px;margin:0 auto 18px;border-radius:999px;background:conic-gradient(var(--blue2) calc(var(--score)*1%),#e8edf5 0);display:grid;place-items:center}.score-ring strong{width:90px;height:90px;border-radius:999px;background:#fff;display:grid;place-items:center;font-size:34px}.action-hero{display:flex;flex-direction:column;justify-content:center}.action-hero strong{font-size:26px;margin:8px 0}.analysis-card-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:16px}.analysis-card{border:1px solid var(--line);border-radius:6px;background:#fff;padding:18px}.analysis-card strong{display:block;font-size:27px;margin:8px 0}.chart-grid{display:grid;grid-template-columns:1.3fr .9fr;gap:14px;margin-top:16px}.chart-panel{border:1px solid var(--line);border-radius:6px;background:#fff;padding:18px}.chart-panel h3{font-size:21px;margin:8px 0}.trend{display:flex;align-items:end;gap:8px;height:210px;padding-top:16px}.trend-col{flex:1;min-width:22px;display:flex;flex-direction:column;align-items:center;gap:8px}.trend-stack{width:100%;height:150px;display:flex;align-items:end;justify-content:center;border-bottom:1px solid #e4e7ec}.trend-bar{width:18px;border-radius:5px 5px 0 0;background:#cbd5e1;position:relative}.trend-dot{position:absolute;left:50%;width:9px;height:9px;margin-left:-4px;border-radius:999px;background:var(--blue2);box-shadow:0 0 0 4px #1769ff1a}.trend-label{font-size:12px;color:var(--muted)}.bar-list{display:grid;gap:12px;margin-top:16px}.bar-row{display:grid;grid-template-columns:92px 1fr 54px;gap:10px;align-items:center}.bar-track{height:11px;background:#edf2f7;border-radius:999px;overflow:hidden}.bar-fill{height:100%;background:linear-gradient(90deg,var(--cyan),var(--blue2));border-radius:999px}.source-row{display:grid;grid-template-columns:1fr 70px;gap:12px;align-items:center;padding:10px 0;border-bottom:1px solid #edf1f7}.question-row{padding:12px 0;border-bottom:1px solid #edf1f7}.question-row strong{display:block;line-height:1.5}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px 20px}input,textarea{width:100%;padding:13px 14px;border:1px solid #ccd6e4;border-radius:6px;font-size:14px;background:#fff}textarea{min-height:96px;resize:vertical;line-height:1.6}.checks{display:flex;flex-wrap:wrap;gap:12px;margin-top:2px}.checks label{display:inline-flex;align-items:center;gap:6px;background:#f8fafc;border:1px solid #e4e7ec;border-radius:999px;padding:8px 12px}.checks input{width:auto}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;font-size:14px;min-width:760px}th,td{text-align:left;padding:11px;border-bottom:1px solid #edf1f7}th{color:#7b8aa0;font-size:12px}.status{display:inline-flex;padding:3px 8px;border-radius:999px;background:#f2f4f7;color:#344054;font-size:12px;font-weight:800}.empty{padding:24px;text-align:center;color:var(--muted);background:#f8fafc;border:1px dashed #d0d5dd;border-radius:6px}.local-note{margin-top:10px;font-size:13px;color:#7b8aa0}.local-note strong{color:#344054}.connection-diagnosis{display:flex;align-items:center;justify-content:space-between;gap:20px;margin:16px 0;padding:16px 18px;border:1px solid #d0d5dd;border-left:4px solid #98a2b3;border-radius:6px;background:#f8fafc}.connection-diagnosis.healthy,.connection-diagnosis.demo{border-left-color:#12b76a;background:#f0fdf4}.connection-diagnosis.warning{border-left-color:#f79009;background:#fffaeb}.connection-diagnosis.offline{border-left-color:#f04438;background:#fff5f5}.connection-diagnosis strong{display:block;font-size:17px;margin-bottom:5px}.diagnosis-actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.diagnosis-stats{display:flex;gap:8px;flex-wrap:wrap}.hidden-section{display:none}@media(max-width:980px){.workspace-hero,.analysis-summary,.chart-grid,.form-grid,.metric-grid,.analysis-card-grid{grid-template-columns:1fr}.panel{padding:22px 18px}.panel h2{padding-right:96px}.collapse-toggle{top:16px;right:14px}.app-header{height:auto;align-items:flex-start;gap:12px;padding:12px;flex-direction:column}.header-actions{flex-wrap:wrap}.wrap{width:calc(100% - 28px);padding:16px 0}.hero-panel h1{font-size:28px}.hero-panel{padding:26px}.tab-nav{overflow:auto}.tab-nav a{white-space:nowrap}.connection-diagnosis{align-items:flex-start;flex-direction:column}}
	select{width:100%;padding:12px 14px;border:1px solid #ccd6e4;border-radius:6px;background:#fff;font-size:14px}.query-grid{display:grid;grid-template-columns:1.4fr 1fr 1fr 1fr 1fr 1fr;gap:12px;align-items:end}.query-grid label{display:grid;gap:7px;color:#7b8aa0;font-size:12px;font-weight:800}.query-actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:14px}.query-pagination{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-top:14px;padding:12px 0;border-top:1px solid #edf1f7}.query-page-controls{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.query-page-controls select{width:auto;height:34px;padding:0 28px 0 10px}.query-page-controls button:disabled{opacity:.45;cursor:not-allowed}.pill{display:inline-flex;align-items:center;height:24px;padding:0 8px;border-radius:999px;background:#eef4ff;color:#175cd3;font-size:12px;font-weight:800}.pill.good{background:#ecfdf3;color:#027a48}.pill.bad{background:#fff1f3;color:#c01048}.answer-snippet{max-width:360px;color:#475467;line-height:1.55}.query-count{color:#7b8aa0;font-size:13px;font-weight:700}.geo-summary{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:16px 0}.geo-summary-item{border:1px solid var(--line);border-radius:6px;background:#fff;padding:14px}.geo-summary-item span{display:block;color:var(--muted);font-size:12px;font-weight:800}.geo-summary-item strong{display:block;font-size:24px;margin-top:6px}.geo-title-row{cursor:pointer}.geo-title-main{display:flex;align-items:center;gap:10px;font-weight:800}.geo-caret{width:22px;height:22px;border:1px solid #d0d5dd;border-radius:999px;display:inline-flex;align-items:center;justify-content:center;color:#667085;font-size:12px}.geo-child-row{background:#fbfdff}.geo-url-list{padding:8px 0}.geo-url-card{display:grid;grid-template-columns:minmax(260px,1fr) 150px 150px 170px;gap:14px;align-items:start;padding:12px 14px;border-bottom:1px solid #edf1f7}.geo-url-card:last-child{border-bottom:0}.geo-url{color:#175cd3;word-break:break-all;line-height:1.5}.geo-detail-list{margin-top:8px;display:grid;gap:7px}.geo-detail-item{padding:8px 10px;background:#f8fafc;border:1px solid #e4e7ec;border-radius:6px;color:#475467;line-height:1.5}.geo-muted{color:#7b8aa0;font-size:12px}@media(max-width:1100px){.query-grid{grid-template-columns:1fr 1fr}.geo-summary{grid-template-columns:1fr 1fr}.geo-url-card{grid-template-columns:1fr}}@media(max-width:720px){.query-grid{grid-template-columns:1fr}.geo-summary{grid-template-columns:1fr}}
</style>
</head>
<body>
<header class="app-header">
    <div class="title">
        <img class="logo" src="/public/assets/geo-sop-icon.png" onerror="this.src='/public/assets/allgood-logo-dark.png'" alt="Logo">
        <span>GEO-SOP</span>
        <span class="tag">v<?=geo_h($appVersion)?></span>
        <span class="tag green">账号同步</span>
        <span class="tag">当前账号: <?=geo_h((string)($user['username'] ?? $user['email'] ?? $user['id']))?></span>
    </div>
    <div class="header-actions">
        <a class="btn" href="#create-task">采集设置: 50条 30~120秒</a>
        <button class="btn" onclick="openLocalApp('login')">检测平台登录</button>
        <a class="btn" href="#ai-settings">智慧舆情设置</a>
        <a class="btn primary" href="#create-task">创建任务</a>
        <a class="btn" href="/logout/">退出登录</a>
    </div>
</header>

<main class="wrap">
    <?php if ($isDemoUser): ?><div class="msg" style="background:#fff8e6;color:#8a5a00;border:1px solid #f5d48a;margin-bottom:18px">当前为在线 Demo 只读模式：可以查看、筛选和导出样例数据；创建任务、平台登录、采集和修改操作已关闭。</div><?php endif; ?>
    <section class="workspace-hero">
        <div class="hero-panel">
            <div class="kicker">GEO-SOP WORKSPACE</div>
            <h1>AI 平台品牌可见度工作台</h1>
            <p>从账号登录、问题采集、引用来源到 AI 分析建议，集中管理品牌在 AI 回答里的曝光、风险和下一步动作。</p>
            <div class="hero-actions">
                <a class="btn primary" href="#insights">查看数据看板</a>
                <button class="btn" onclick="openLocalApp('login')">检测平台登录</button>
                <a class="btn" href="#create-task">新建监测任务</a>
            </div>
        </div>
        <div class="side-stack">
            <div class="side-card">
                <span class="kicker">Next step</span>
                <strong><?=geo_h($nextAction['title'])?></strong>
                <p class="muted"><?=geo_h($nextAction['detail'])?></p>
                <p class="local-note"><strong>平台登录、浏览器采集和账号绑定需要在本机 App 完成。</strong>点击按钮会尝试唤起本机 App。</p>
                <button class="btn small primary" onclick="openLocalApp('login')">打开本机 App</button>
            </div>
            <div class="side-card" id="ai-settings">
                <span class="kicker">AI Analysis</span>
                <strong>在本机 App 配置智慧舆情</strong>
                <p class="muted">API URL、Key 和模型保存在本机客户端。配置完成后，可生成观察、风险和下一步动作，并随采集结果同步到云端看板。</p>
                <?php if($configRows): ?>
                <?php foreach(array_slice($configRows, 0, 2) as $config): ?>
                <p class="local-note"><strong><?=geo_h((string)$config['name'])?></strong> · <?=geo_h($config['platform'] ?: 'OpenAI 兼容')?> / <?=geo_h($config['model'] ?: '未设置模型')?> · <?= $config['metadata_ready'] ? '配置已同步' : '等待完整配置' ?><br>API Key 仅保存在本机</p>
                <?php endforeach; ?>
                <?php else: ?><p class="local-note">当前账号还没有同步的舆情配置。</p><?php endif; ?>
                <button class="btn small primary" onclick="openLocalApp('ai-settings')">在本机配置 AI</button>
            </div>
        </div>
    </section>

    <?php if($message): ?><div class="msg"><?=geo_h($message)?></div><?php endif; ?>

    <section class="metric-grid">
        <div class="metric-card"><span>监测任务</span><strong><?=geo_h((string)$totalTaskCount)?></strong><small class="muted"><?=geo_h((string)$runningTasks)?> 个运行/暂停中</small></div>
        <div class="metric-card"><span>采集回答</span><strong><?=geo_h((string)$totalResults)?></strong><small class="muted">覆盖 <?=geo_h((string)$activePlatforms)?> 个 AI 平台</small></div>
        <div class="metric-card"><span>品牌曝光率</span><strong><?=geo_h((string)$exposureRate)?>%</strong><small class="muted">回答中命中品牌词的比例</small></div>
        <div class="metric-card"><span>引用域名</span><strong><?=geo_h((string)$referenceDomains)?></strong><small class="muted">截图留证 <?=geo_h((string)$screenshotCount)?> 条</small></div>
    </section>

    <section class="tabs" id="insights" data-collapsible="insights" data-collapse-default="open">
        <nav class="tab-nav">
            <a class="active" href="#insights">数据看板</a>
            <a href="#create-task">任务管理</a>
            <a href="#sources">引用参考源分析</a>
            <a href="#trend">引用参考源走势图</a>
            <a href="#geo">GEO稿件被引用分析</a>
            <a href="#ai-settings">智慧舆情设置</a>
        </nav>
        <div class="tab-body">
            <div class="analysis-summary">
                <div class="score-hero">
                    <span class="mini-label">GEO 健康分</span>
                    <div class="score-ring" style="--score:<?=geo_h((string)$geoScore)?>"><strong><?=geo_h((string)round($geoScore))?></strong></div>
                    <p class="muted"><?=geo_h(geo_score_label($geoScore))?>。这个分数综合品牌出现率、平台覆盖、引用来源和数据完整度。</p>
                </div>
                <div class="action-hero">
                    <span class="mini-label">现在最该做的一件事</span>
                    <strong><?=geo_h($nextAction['title'])?></strong>
                    <p class="muted"><?=geo_h($nextAction['detail'])?></p>
                </div>
            </div>

            <?php if(is_array($latestInsight) && trim((string)($latestInsight['summary'] ?? '')) !== ''): ?>
            <div class="chart-panel" style="margin-top:16px">
                <span class="mini-label">AI 分析<?= $latestInsightGeneratedAt !== '' ? ' · ' . geo_h($latestInsightGeneratedAt) : '' ?></span>
                <h3><?=geo_h((string)$latestInsight['summary'])?></h3>
                <div class="chart-grid" style="margin-top:8px">
                    <div>
                        <strong>关键观察</strong>
                        <?php foreach(array_slice(is_array($latestInsight['observations'] ?? null) ? $latestInsight['observations'] : [], 0, 5) as $item): ?>
                        <p class="muted">• <?=geo_h((string)$item)?></p>
                        <?php endforeach; ?>
                    </div>
                    <div>
                        <strong>下一步动作</strong>
                        <?php foreach(array_slice(is_array($latestInsight['actions'] ?? null) ? $latestInsight['actions'] : [], 0, 5) as $item): ?>
                        <p class="muted">• <?=geo_h((string)$item)?></p>
                        <?php endforeach; ?>
                    </div>
                </div>
            </div>
            <?php endif; ?>

            <div class="analysis-card-grid">
                <div class="analysis-card"><span class="mini-label">品牌出现率 · <?=geo_h(geo_score_label($exposureRate))?></span><strong><?=geo_h((string)$exposureRate)?>%</strong><p class="muted">AI 回答里提到你的比例</p></div>
                <div class="analysis-card"><span class="mini-label">平台覆盖 · <?=geo_h($activePlatforms >= 3 ? '健康' : '需要关注')?></span><strong><?=geo_h((string)$activePlatforms)?>个平台</strong><p class="muted">建议至少覆盖 3 个平台</p></div>
                <div class="analysis-card"><span class="mini-label">引用来源 · <?=geo_h($referenceDomains >= 3 ? '可优化' : '需要关注')?></span><strong><?=geo_h((string)$referenceDomains)?>个域名</strong><p class="muted">AI 引用了哪些来源</p></div>
                <div class="analysis-card"><span class="mini-label">数据质量 · <?=geo_h(geo_score_label($dataQuality))?></span><strong><?=geo_h((string)$dataQuality)?>分</strong><p class="muted">截图、引用和样本是否完整</p></div>
            </div>

            <div class="chart-grid" id="trend">
                <div class="chart-panel">
                    <span class="mini-label">趋势</span>
                    <h3>品牌出现率有没有变好？</h3>
                    <p class="muted">蓝点是品牌出现率，灰柱是每天采集到的回答数。小白只要看蓝点有没有向上。</p>
                    <?php if($trendRows): ?>
                    <div class="trend">
                        <?php foreach($trendRows as $date => $item): $rate = geo_percent((int)$item['exposed'], (int)$item['answers']); $bar = max(8, round((int)$item['answers'] / $maxDailyAnswers * 150)); $dot = max(4, min(150, round($rate / 100 * 150))); ?>
                        <div class="trend-col"><div class="trend-stack"><div class="trend-bar" style="height:<?=$bar?>px"><i class="trend-dot" style="bottom:<?=$dot?>px"></i></div></div><div class="trend-label"><?=geo_h(substr($date, 5))?></div></div>
                        <?php endforeach; ?>
                    </div>
                    <?php else: ?><div class="empty">暂无趋势数据。桌面端同步采集结果后会自动生成。</div><?php endif; ?>
                </div>
                <div class="chart-panel">
                    <span class="mini-label">平台对比</span>
                    <h3>哪个 AI 平台更愿意提到你？</h3>
                    <p class="muted">对比不同平台的品牌出现率，优先补最弱的平台。</p>
                    <div class="bar-list">
                        <?php foreach($platformRows as $item): $rate = geo_percent((int)$item['exposed'], (int)$item['answers']); ?>
                        <div class="bar-row"><span><?=geo_h(geo_platform_name($item['platform']))?></span><div class="bar-track"><div class="bar-fill" style="width:<?=$rate?>%"></div></div><strong><?=$rate?>%</strong></div>
                        <?php endforeach; ?>
                        <?php if(!$platformRows): ?><div class="empty">暂无平台数据。</div><?php endif; ?>
                    </div>
                </div>
            </div>

            <div class="chart-grid" id="sources">
                <div class="chart-panel">
                    <span class="mini-label">引用来源</span>
                    <h3>AI 主要引用谁？</h3>
                    <?php foreach($sourceRows as $domain => $count): $width = $maxSourceCount ? round($count / $maxSourceCount * 100) : 0; ?>
                    <div class="source-row"><span><?=geo_h($domain)?><div class="bar-track" style="margin-top:8px"><div class="bar-fill" style="width:<?=$width?>%"></div></div></span><strong><?=geo_h((string)$count)?> 次</strong></div>
                    <?php endforeach; ?>
                    <?php if(!$sourceRows): ?><div class="empty">暂无引用来源。可以增加容易触发引用的问题类型。</div><?php endif; ?>
                </div>
                <div class="chart-panel">
                    <span class="mini-label">弱项问题</span>
                    <h3>优先优化哪些问题？</h3>
                    <?php foreach($weakQuestions as $item): $rate = geo_percent((int)$item['exposed'], (int)$item['answers']); ?>
                    <div class="question-row"><strong><?=geo_h($item['question'])?></strong><p class="muted">品牌出现率 <?=$rate?>% · 样本 <?=geo_h((string)$item['answers'])?> 条</p></div>
                    <?php endforeach; ?>
                    <?php if(!$weakQuestions): ?><div class="empty">暂无问题数据。</div><?php endif; ?>
                </div>
            </div>
        </div>
    </section>

    <section class="panel" id="geo" style="margin-top:16px" data-collapsible="geo" data-collapse-default="closed">
        <span class="kicker">GEO</span>
        <h2>GEO稿件被引用分析</h2>
        <p class="muted">按稿件/文章标题聚合同一篇内容，展开后查看每个 URL 是否被 AI 回答引用，以及对应的平台、问题和引用来源。</p>
        <div class="query-grid">
            <label>关联任务<select id="geoTask"><option value="">全部任务</option></select></label>
            <label>AI 平台<select id="geoPlatform"><option value="">全部平台</option><option value="doubao">豆包</option><option value="deepseek">DeepSeek</option><option value="kimi">Kimi</option><option value="qianwen">通义千问</option><option value="yuanbao">腾讯元宝</option><option value="chatgpt">ChatGPT</option><option value="gemini">Gemini</option><option value="wenxin">文心一言</option></select></label>
            <label>日期<input id="geoDate" type="date"></label>
            <label>开始日期<input id="geoStart" type="date"></label>
            <label>结束日期<input id="geoEnd" type="date"></label>
            <label>排序<select id="geoSort"><option value="cited_desc">引用次数高到低</option><option value="title_asc">标题 A-Z</option><option value="uncited_first">未引用优先</option></select></label>
        </div>
        <div class="query-actions">
            <button class="primary" type="button" onclick="loadGeoCoverage()">刷新分析</button>
            <button type="button" id="geoMoreBtn" onclick="loadMoreGeoCoverage()" style="display:none">继续加载</button>
            <button type="button" onclick="resetGeoCoverage()">重置</button>
            <span class="query-count" id="geoCount">等待分析</span>
        </div>
        <div class="geo-summary">
            <div class="geo-summary-item"><span>稿件标题</span><strong id="geoTitleTotal">0</strong></div>
            <div class="geo-summary-item"><span>URL 数量</span><strong id="geoUrlTotal">0</strong></div>
            <div class="geo-summary-item"><span>被引用标题</span><strong id="geoCitedTitleTotal">0</strong></div>
            <div class="geo-summary-item"><span>被引用 URL</span><strong id="geoCitedUrlTotal">0</strong></div>
        </div>
        <div class="table-wrap">
            <table>
                <thead><tr><th>稿件标题</th><th>关联任务</th><th>引用状态</th><th>引用次数</th><th>URL 数量</th></tr></thead>
                <tbody id="geoRows"><tr><td colspan="5"><div class="empty">正在加载前 20 个稿件标题...</div></td></tr></tbody>
            </table>
        </div>
    </section>

    <section class="panel" id="data-query" style="margin-top:16px" data-collapsible="data-query" data-collapse-default="closed">
        <span class="kicker">Query</span>
        <h2>云端数据查询</h2>
        <p class="muted">服务端会读取同一账号同步上来的任务、回答、引用来源和截图。平台登录和真实采集仍在本机 App 内完成。</p>
        <div class="query-grid">
            <label>监测任务<select id="queryTask"><option value="">全部任务</option></select></label>
            <label>AI 平台<select id="queryPlatform"><option value="">全部平台</option><option value="doubao">豆包</option><option value="deepseek">DeepSeek</option><option value="kimi">Kimi</option><option value="qianwen">通义千问</option><option value="yuanbao">腾讯元宝</option><option value="chatgpt">ChatGPT</option><option value="gemini">Gemini</option><option value="wenxin">文心一言</option></select></label>
            <label>关键词<input id="queryKeyword" placeholder="问题或回答关键词"></label>
            <label>开始日期<input id="queryStart" type="date"></label>
            <label>结束日期<input id="queryEnd" type="date"></label>
            <label>品牌曝光<select id="queryExposed"><option value="">全部</option><option value="1">已曝光</option><option value="0">未曝光</option></select></label>
        </div>
        <div class="query-actions">
            <button class="primary" type="button" onclick="queryCloudResults(1)">查询数据</button>
            <button type="button" onclick="resetCloudQuery()">重置</button>
            <button type="button" onclick="exportCloudGeo()">导出GEO效果</button>
            <button class="primary" type="button" onclick="exportCloudScreenshots()">GEO长截图下载</button>
            <span class="query-count" id="queryCount">等待查询</span>
        </div>
        <div class="query-pagination">
            <span class="query-count" id="queryPageInfo">第 1 页</span>
            <div class="query-page-controls">
                <span class="query-count">每页</span>
                <select id="queryPageSize" onchange="queryCloudResults(1)">
                    <option value="20" selected>20 条</option>
                    <option value="30">30 条</option>
                    <option value="50">50 条</option>
                    <option value="100">100 条</option>
                </select>
                <button type="button" id="queryPrevBtn" onclick="queryCloudResults(queryState.page - 1)">上一页</button>
                <button type="button" id="queryNextBtn" onclick="queryCloudResults(queryState.page + 1)">下一页</button>
            </div>
        </div>
        <div class="table-wrap">
            <table>
                <thead><tr><th>时间</th><th>任务</th><th>平台</th><th>问题</th><th>曝光</th><th>引用</th><th>截图</th><th>回答摘要</th></tr></thead>
                <tbody id="queryRows"><tr><td colspan="8"><div class="empty">正在加载最近 20 条云端数据...</div></td></tr></tbody>
            </table>
        </div>
    </section>

    <section class="panel" id="create-task" style="margin-top:16px" data-collapsible="create-task" data-collapse-default="closed">
        <span class="kicker">Task</span>
        <h2>创建监测任务</h2>
        <p class="muted">云端可创建任务；真正的平台登录、浏览器采集、截图留证会由同账号本机 App 完成。</p>
        <form method="post">
            <div class="form-grid">
                <p><input name="name" placeholder="任务名称" value="云端下发任务"></p>
                <p><input name="brand_name" placeholder="品牌名称"></p>
                <p><textarea name="brand_keywords" placeholder="品牌关键词，每行一个" required></textarea></p>
                <p><textarea name="competitor_brands" placeholder="竞品品牌，每行一个，可选"></textarea></p>
            </div>
            <p><textarea name="questions" placeholder="采集问题，每行一个" required></textarea></p>
            <p class="checks">
                <?php foreach($supportedPlatforms as $platformId => $platformMeta): ?>
                <label><input type="checkbox" name="platforms[]" value="<?=geo_h($platformId)?>" <?= $platformId === 'doubao' ? 'checked' : '' ?>><?=geo_h($platformMeta['name'])?></label>
                <?php endforeach; ?>
            </p>
            <button class="primary" <?= $isDemoUser ? 'disabled title="Demo 为只读模式"' : '' ?>>创建任务</button>
            <button type="button" onclick="openLocalApp('dashboard')" <?= $isDemoUser ? 'disabled title="Demo 为只读模式"' : '' ?>>打开本机 App 执行</button>
        </form>
    </section>

    <section class="panel" style="margin-top:16px" data-collapsible="remote-tasks" data-collapse-default="closed">
        <span class="kicker">Queue</span>
        <h2>任务管理</h2>
        <p class="muted">云端下发任务是从网页创建、等待客户端执行的队列；本地同步任务是桌面端已经采集并同步回来的历史任务。</p>
        <div class="connection-diagnosis" id="connectionDiagnosis">
            <div><strong id="diagnosisTitle">正在检查客户端连接...</strong><span class="muted" id="diagnosisDetail">正在读取最近心跳、客户端版本和任务队列。</span></div>
            <div class="diagnosis-actions">
                <div class="diagnosis-stats"><span class="pill" id="onlineClientCount">在线 0</span><span class="pill" id="pendingTaskCount">等待 0</span></div>
                <button type="button" onclick="openLocalApp('dashboard')" <?= $isDemoUser ? 'disabled title="Demo 为只读模式"' : '' ?>>打开本机 App</button>
                <a class="btn" href="/#download">下载最新版</a>
            </div>
        </div>
        <h3 style="margin:18px 0 8px">云端下发任务</h3>
        <div class="table-wrap"><table><thead><tr><th>ID</th><th>任务</th><th>状态</th><th>进度说明</th><th>客户端</th><th>本地任务</th><th>更新时间</th></tr></thead><tbody id="remoteTaskRows">
        <?php foreach($remoteRows as $r): ?><tr><td><?=geo_h($r['id'])?></td><td><?=geo_h($r['name'])?></td><td><span class="status" title="<?=geo_h($r['last_status_message'] ?: '')?>"><?=geo_h(geo_remote_status_label((string)$r['status']))?></span></td><td><?=geo_h($r['last_status_message'] ?: '等待状态刷新')?></td><td><?=geo_h($r['assigned_install_id'] ?: '-')?></td><td><?=geo_h($r['local_task_id'] ?: '-')?></td><td><?=geo_h($r['updated_at'])?></td></tr><?php endforeach; ?>
        <?php if(!$remoteRows): ?><tr><td colspan="7"><div class="empty">暂无远程任务。</div></td></tr><?php endif; ?>
        </tbody></table></div>
        <h3 style="margin:22px 0 8px">客户端连接状态</h3>
        <p class="muted">只有同一账号下的桌面客户端保持在线，云端任务才会被自动拉取。超过 90 秒未收到心跳会显示为离线，本区域每 15 秒自动刷新。</p>
        <div class="table-wrap"><table><thead><tr><th>状态</th><th>客户端</th><th>版本</th><th>平台</th><th>最近心跳</th><th>提示</th></tr></thead><tbody id="desktopClientRows">
        <?php foreach($clientRows as $client): ?><tr><td><span class="status" style="color:<?= $client['live'] ? '#16803c' : '#8a5a00' ?>"><?= $client['live'] ? '在线' : '离线' ?></span></td><td><?=geo_h($client['install_id'])?></td><td><?=geo_h($client['version'] ?: '-')?></td><td><?=geo_h($client['platform'] ?: '-')?></td><td><?=geo_h($client['last_seen_at'])?></td><td><?=geo_h($client['message'] ?: '-')?></td></tr><?php endforeach; ?>
        <?php if(!$clientRows): ?><tr><td colspan="6"><div class="empty">暂无客户端心跳。请在桌面端登录同一账号并保持 App 运行。</div></td></tr><?php endif; ?>
        </tbody></table></div>
        <h3 style="margin:22px 0 8px">本地同步任务</h3>
        <div class="table-wrap"><table><tr><th>本地ID</th><th>任务</th><th>状态</th><th>客户端</th><th>同步时间</th></tr>
        <?php foreach(array_slice($syncedTasks, 0, 30) as $r): ?><tr><td><?=geo_h($r['local_id'])?></td><td><?=geo_h($r['name'])?></td><td><span class="status"><?=geo_h($r['status'] ?: '-')?></span></td><td><?=geo_h($r['install_id'])?></td><td><?=geo_h($r['synced_at'])?></td></tr><?php endforeach; ?>
        <?php if(!$syncedTasks): ?><tr><td colspan="5"><div class="empty">暂无本地同步任务。请先在桌面软件里登录同一账号并同步。</div></td></tr><?php endif; ?>
        </table></div>
    </section>

    <section class="panel" style="margin-top:16px" data-collapsible="sync-records" data-collapse-default="closed">
        <span class="kicker">Sync</span>
        <h2>桌面端同步记录</h2>
        <div class="table-wrap"><table><tr><th>本地ID</th><th>任务</th><th>状态</th><th>用户</th><th>同步时间</th></tr>
        <?php foreach(array_slice($syncedTasks, 0, 30) as $r): ?><tr><td><?=geo_h($r['local_id'])?></td><td><?=geo_h($r['name'])?></td><td><span class="status"><?=geo_h($r['status'] ?: '-')?></span></td><td><?=geo_h($r['user_key'])?></td><td><?=geo_h($r['synced_at'])?></td></tr><?php endforeach; ?>
        <?php if(!$syncedTasks): ?><tr><td colspan="5"><div class="empty">暂无桌面端同步任务。请先在桌面软件里登录同一账号并同步。</div></td></tr><?php endif; ?>
        </table></div>
    </section>
</main>

<script>
function h(text){
    return String(text == null ? '' : text).replace(/[&<>"']/g, function(c){
        return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
}

async function geoApi(params){
    var url = '/api/dashboard/?' + new URLSearchParams(params).toString();
    var res = await fetch(url, {credentials: 'same-origin'});
    var data = await res.json();
    if (!res.ok || !data.success) throw new Error(data.message || '查询失败');
    return data;
}

var remoteStatusLoading = false;

function remoteStatusPill(status){
    if (status === 'completed') return 'pill good';
    if (status === 'failed' || status === 'stopped' || status === 'skipped') return 'pill bad';
    return 'pill';
}

function heartbeatAge(seconds){
    seconds = Math.max(0, Number(seconds || 0));
    if (seconds < 60) return Math.round(seconds) + ' 秒前';
    if (seconds < 3600) return Math.floor(seconds / 60) + ' 分钟前';
    if (seconds < 86400) return Math.floor(seconds / 3600) + ' 小时前';
    return Math.floor(seconds / 86400) + ' 天前';
}

function renderRemoteStatus(data){
    var diagnosis = data.diagnosis || {};
    var diagnosisBox = document.getElementById('connectionDiagnosis');
    if (diagnosisBox) {
        diagnosisBox.classList.remove('healthy', 'warning', 'offline', 'demo');
        diagnosisBox.classList.add(diagnosis.level || 'offline');
    }
    document.getElementById('diagnosisTitle').textContent = diagnosis.title || '客户端状态未知';
    document.getElementById('diagnosisDetail').textContent = diagnosis.detail || '请稍后重新检查。';
    document.getElementById('onlineClientCount').textContent = '在线 ' + Number(data.summary?.online_clients || 0);
    document.getElementById('pendingTaskCount').textContent = '等待 ' + Number(data.summary?.pending_tasks || 0);

    var taskRows = document.getElementById('remoteTaskRows');
    var tasks = Array.isArray(data.tasks) ? data.tasks : [];
    if (taskRows) {
        taskRows.innerHTML = tasks.length ? tasks.map(function(task){
            return '<tr>' +
                '<td>' + h(task.id) + '</td>' +
                '<td>' + h(task.name || '-') + '</td>' +
                '<td><span class="' + remoteStatusPill(task.status) + '">' + h(task.status_label || task.status) + '</span></td>' +
                '<td>' + h(task.reason || '-') + '</td>' +
                '<td>' + h(task.assigned_install_id || '-') + '</td>' +
                '<td>' + h(task.local_task_id || '-') + '</td>' +
                '<td>' + h(task.updated_at || '-') + '</td>' +
            '</tr>';
        }).join('') : '<tr><td colspan="7"><div class="empty">暂无远程任务。</div></td></tr>';
    }

    var clientRows = document.getElementById('desktopClientRows');
    var clients = Array.isArray(data.clients) ? data.clients : [];
    if (clientRows) {
        clientRows.innerHTML = clients.length ? clients.map(function(client){
            var state = client.live ? '<span class="pill good">在线</span>' : '<span class="pill bad">离线</span>';
            var version = h(client.version || '未知版本');
            if (client.outdated) version += ' <span class="pill bad">请升级至 ' + h(data.latest_version || '最新版') + '</span>';
            var heartbeat = h(client.last_seen_at || '-') + '<br><span class="muted">' + h(heartbeatAge(client.age_seconds)) + '</span>';
            return '<tr>' +
                '<td>' + state + '</td>' +
                '<td>' + h(client.install_id || '-') + '</td>' +
                '<td>' + version + '</td>' +
                '<td>' + h(client.platform || '-') + '</td>' +
                '<td>' + heartbeat + '</td>' +
                '<td>' + h(client.message || '-') + '</td>' +
            '</tr>';
        }).join('') : '<tr><td colspan="6"><div class="empty">暂无客户端心跳。请在桌面端登录同一账号并保持 App 运行。</div></td></tr>';
    }
}

async function loadRemoteStatus(){
    if (remoteStatusLoading || document.hidden) return;
    remoteStatusLoading = true;
    try {
        renderRemoteStatus(await geoApi({action: 'remote_status'}));
    } catch (error) {
        var diagnosisBox = document.getElementById('connectionDiagnosis');
        if (diagnosisBox) {
            diagnosisBox.classList.remove('healthy', 'warning', 'demo');
            diagnosisBox.classList.add('offline');
        }
        document.getElementById('diagnosisTitle').textContent = '连接状态暂时无法读取';
        document.getElementById('diagnosisDetail').textContent = error.message || '请稍后重试。';
    } finally {
        remoteStatusLoading = false;
    }
}

async function loadCloudTasks(){
    try {
        var data = await geoApi({action: 'tasks'});
        var selects = [document.getElementById('queryTask'), document.getElementById('geoTask')].filter(Boolean);
        data.tasks.forEach(function(task){
            selects.forEach(function(select){
                var option = document.createElement('option');
                option.value = task.local_id;
                option.dataset.installId = task.install_id;
                option.textContent = '#' + task.local_id + ' ' + task.name;
                select.appendChild(option);
            });
        });
    } catch (e) {
        console.warn(e);
    }
}

var queryState = { page: 1, pageSize: 20, total: 0 };
var geoState = { groups: [], expanded: {}, visible: 20, step: 20 };

function updateQueryPagination(){
    var totalPages = Math.max(1, Math.ceil(queryState.total / queryState.pageSize));
    if (queryState.page > totalPages) queryState.page = totalPages;
    var info = document.getElementById('queryPageInfo');
    var prev = document.getElementById('queryPrevBtn');
    var next = document.getElementById('queryNextBtn');
    if (info) info.textContent = '第 ' + queryState.page + ' / ' + totalPages + ' 页';
    if (prev) prev.disabled = queryState.page <= 1;
    if (next) next.disabled = queryState.page >= totalPages || queryState.total === 0;
}

async function queryCloudResults(page){
    var task = document.getElementById('queryTask');
    var selected = task.options[task.selectedIndex];
    queryState.pageSize = parseInt(document.getElementById('queryPageSize').value || '30', 10);
    queryState.page = Math.max(1, parseInt(page || queryState.page || 1, 10));
    var params = {
        action: 'results',
        limit: String(queryState.pageSize),
        offset: String((queryState.page - 1) * queryState.pageSize),
        task_id: task.value || '',
        install_id: selected ? (selected.dataset.installId || '') : '',
        platform: document.getElementById('queryPlatform').value,
        keyword: document.getElementById('queryKeyword').value.trim(),
        start_date: document.getElementById('queryStart').value,
        end_date: document.getElementById('queryEnd').value,
        exposed: document.getElementById('queryExposed').value
    };
    var rows = document.getElementById('queryRows');
    var count = document.getElementById('queryCount');
    rows.innerHTML = '<tr><td colspan="8"><div class="empty">正在查询云端数据...</div></td></tr>';
    count.textContent = '查询中';
    updateQueryPagination();
    try {
        var data = await geoApi(params);
        queryState.total = data.total || 0;
        updateQueryPagination();
        var start = queryState.total ? ((queryState.page - 1) * queryState.pageSize + 1) : 0;
        var end = Math.min(queryState.total, (queryState.page - 1) * queryState.pageSize + data.results.length);
        count.textContent = '共 ' + queryState.total + ' 条，当前显示 ' + start + '-' + end + ' 条';
        if (!data.results.length) {
            rows.innerHTML = '<tr><td colspan="8"><div class="empty">没有匹配的数据。</div></td></tr>';
            return;
        }
        rows.innerHTML = data.results.map(function(item){
            var refs = item.reference_count ? '<span class="pill">' + item.reference_count + ' 个</span>' : '-';
            var shot = item.screenshot_url ? '<a class="pill good" target="_blank" href="' + h(item.screenshot_url) + '">查看截图</a>' : '-';
            var exposed = item.has_brand_exposure ? '<span class="pill good">已曝光</span>' : '<span class="pill bad">未曝光</span>';
            var answer = item.answer ? item.answer.replace(/\s+/g, ' ').slice(0, 120) : '';
            return '<tr>' +
                '<td>' + h(item.created_at || '-') + '</td>' +
                '<td>' + h(item.task_name || ('#' + item.local_task_id)) + '</td>' +
                '<td>' + h(item.platform_name || item.platform) + '</td>' +
                '<td>' + h(item.question) + '</td>' +
                '<td>' + exposed + '</td>' +
                '<td>' + refs + '</td>' +
                '<td>' + shot + '</td>' +
                '<td><div class="answer-snippet">' + h(answer || '-') + '</div></td>' +
            '</tr>';
        }).join('');
    } catch (e) {
        count.textContent = '查询失败';
        queryState.total = 0;
        updateQueryPagination();
        rows.innerHTML = '<tr><td colspan="8"><div class="empty">' + h(e.message) + '</div></td></tr>';
    }
}

function resetCloudQuery(){
    ['queryTask','queryPlatform','queryKeyword','queryStart','queryEnd','queryExposed'].forEach(function(id){
        var el = document.getElementById(id);
        if (el) el.value = '';
    });
    queryCloudResults(1);
}

function buildCloudQueryParams(action){
    var task = document.getElementById('queryTask');
    var selected = task.options[task.selectedIndex];
    return new URLSearchParams({
        action: action,
        task_id: task.value || '',
        install_id: selected ? (selected.dataset.installId || '') : '',
        platform: document.getElementById('queryPlatform').value,
        keyword: document.getElementById('queryKeyword').value.trim(),
        start_date: document.getElementById('queryStart').value,
        end_date: document.getElementById('queryEnd').value,
        exposed: document.getElementById('queryExposed').value
    });
}

function exportCloudGeo(){
    window.location.href = '/api/dashboard/?' + buildCloudQueryParams('export_geo').toString();
}

function exportCloudScreenshots(){
    window.location.href = '/api/dashboard/?' + buildCloudQueryParams('export_screenshots_zip').toString();
}

function buildGeoParams(){
    var task = document.getElementById('geoTask');
    var selected = task.options[task.selectedIndex];
    return {
        action: 'geo_coverage',
        task_id: task.value || '',
        install_id: selected ? (selected.dataset.installId || '') : '',
        platform: document.getElementById('geoPlatform').value,
        date: document.getElementById('geoDate').value,
        start_date: document.getElementById('geoStart').value,
        end_date: document.getElementById('geoEnd').value
    };
}

function sortGeoGroups(groups){
    var sort = document.getElementById('geoSort').value;
    var rows = groups.slice();
    if (sort === 'title_asc') {
        rows.sort(function(a, b){ return String(a.title).localeCompare(String(b.title), 'zh-Hans-CN'); });
    } else if (sort === 'uncited_first') {
        rows.sort(function(a, b){ return Number(a.is_cited) - Number(b.is_cited) || (b.cited_count || 0) - (a.cited_count || 0); });
    } else {
        rows.sort(function(a, b){ return (b.cited_count || 0) - (a.cited_count || 0) || String(a.title).localeCompare(String(b.title), 'zh-Hans-CN'); });
    }
    return rows;
}

function renderGeoCoverage(){
    var rows = document.getElementById('geoRows');
    var count = document.getElementById('geoCount');
    var groups = sortGeoGroups(geoState.groups);
    var visibleGroups = groups.slice(0, geoState.visible);
    var moreBtn = document.getElementById('geoMoreBtn');
    if (!groups.length) {
        rows.innerHTML = '<tr><td colspan="5"><div class="empty">暂无 GEO 稿件数据。请先在桌面端添加稿件并同步到云端。</div></td></tr>';
        count.textContent = '暂无数据';
        if (moreBtn) moreBtn.style.display = 'none';
        return;
    }
    count.textContent = '共 ' + groups.length + ' 个标题，当前显示 ' + visibleGroups.length + ' 个';
    if (moreBtn) moreBtn.style.display = visibleGroups.length < groups.length ? 'inline-flex' : 'none';
    rows.innerHTML = visibleGroups.map(function(group, index){
        var key = encodeURIComponent(group.title || ('row-' + index));
        var expanded = !!geoState.expanded[key];
        var status = group.is_cited ? '<span class="pill good">已引用</span>' : '<span class="pill bad">未引用</span>';
        var childRows = '';
        if (expanded) {
            childRows = '<tr class="geo-child-row"><td colspan="5"><div class="geo-url-list">' +
                (group.children || []).map(function(child){
                    var url = child.url || '';
                    var href = /^https?:\/\//i.test(url) ? url : 'https://' + url;
                    var details = (child.details || []).slice(0, 8).map(function(detail){
                        return '<div class="geo-detail-item"><strong>' + h(detail.platform_name || detail.platform || '-') + '</strong> · ' +
                            h(detail.question || '-') + '<br><span class="geo-muted">' + h(detail.created_at || '') + ' · ' +
                            h(detail.reference_title || '引用来源') + '</span></div>';
                    }).join('');
                    return '<div class="geo-url-card">' +
                        '<div><a class="geo-url" href="' + h(href) + '" target="_blank">' + h(url || '-') + '</a>' + (details ? '<div class="geo-detail-list">' + details + '</div>' : '') + '</div>' +
                        '<div>' + h(child.task_name || '-') + '</div>' +
                        '<div>' + (child.is_cited ? '<span class="pill good">已引用</span>' : '<span class="pill bad">未引用</span>') + '</div>' +
                        '<div><strong>' + h(child.cited_count || 0) + '</strong> 次</div>' +
                    '</div>';
                }).join('') +
            '</div></td></tr>';
        }
        return '<tr class="geo-title-row" data-geo-key="' + h(key) + '" onclick="toggleGeoGroup(this.dataset.geoKey)">' +
            '<td><div class="geo-title-main"><span class="geo-caret">' + (expanded ? '−' : '+') + '</span><span>' + h(group.title || '未命名稿件') + '</span></div></td>' +
            '<td>' + h(group.task_name || '-') + '</td>' +
            '<td>' + status + '</td>' +
            '<td><strong>' + h(group.cited_count || 0) + '</strong></td>' +
            '<td>' + h(group.url_count || ((group.children || []).length)) + '</td>' +
        '</tr>' + childRows;
    }).join('');
}

async function loadGeoCoverage(){
    var rows = document.getElementById('geoRows');
    var count = document.getElementById('geoCount');
    rows.innerHTML = '<tr><td colspan="5"><div class="empty">正在分析稿件引用情况...</div></td></tr>';
    count.textContent = '分析中';
    try {
        var data = await geoApi(buildGeoParams());
        geoState.groups = data.groups || [];
        geoState.visible = geoState.step;
        document.getElementById('geoTitleTotal').textContent = data.total_titles || 0;
        document.getElementById('geoUrlTotal').textContent = data.total_urls || 0;
        document.getElementById('geoCitedTitleTotal').textContent = data.cited_titles || 0;
        document.getElementById('geoCitedUrlTotal').textContent = data.cited_urls || 0;
        renderGeoCoverage();
    } catch (e) {
        count.textContent = '分析失败';
        rows.innerHTML = '<tr><td colspan="5"><div class="empty">' + h(e.message) + '</div></td></tr>';
    }
}

function toggleGeoGroup(key){
    geoState.expanded[key] = !geoState.expanded[key];
    renderGeoCoverage();
}

function resetGeoCoverage(){
    ['geoTask','geoPlatform','geoDate','geoStart','geoEnd'].forEach(function(id){
        var el = document.getElementById(id);
        if (el) el.value = '';
    });
    document.getElementById('geoSort').value = 'cited_desc';
    geoState.expanded = {};
    geoState.visible = geoState.step;
    loadGeoCoverage();
}

function loadMoreGeoCoverage(){
    geoState.visible += geoState.step;
    renderGeoCoverage();
}

function openLocalApp(target){
    var fallback = 'https://geo.allgood.cn/';
    var url = 'geo-sop://open?target=' + encodeURIComponent(target || 'dashboard');
    var started = Date.now();
    window.location.href = url;
    setTimeout(function(){
        if (Date.now() - started < 1800) {
            alert('如果本机 App 没有自动打开，请先安装并启动 GEO-SOP 桌面端，然后在 App 内登录同一个账号。');
        }
    }, 900);
}

function initCollapsibleSections(){
    document.querySelectorAll('[data-collapsible]').forEach(function(section){
        var key = section.dataset.collapsible;
        var storageKey = 'geoDashboardSection:' + key;
        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'collapse-toggle';
        section.appendChild(button);
        function setCollapsed(collapsed, persist){
            section.classList.toggle('is-collapsed', collapsed);
            button.textContent = collapsed ? '展开' : '收起';
            button.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
            if (persist) localStorage.setItem(storageKey, collapsed ? 'closed' : 'open');
        }
        var saved = localStorage.getItem(storageKey);
        var collapsed = saved ? saved === 'closed' : section.dataset.collapseDefault === 'closed';
        setCollapsed(collapsed, false);
        button.addEventListener('click', function(event){
            event.preventDefault();
            setCollapsed(!section.classList.contains('is-collapsed'), true);
        });
    });
    document.querySelectorAll('a[href^="#"]').forEach(function(link){
        link.addEventListener('click', function(){
            var id = decodeURIComponent(link.getAttribute('href').slice(1));
            if (!id) return;
            var target = document.getElementById(id);
            if (target && target.matches('[data-collapsible]') && target.classList.contains('is-collapsed')) {
                var btn = target.querySelector('.collapse-toggle');
                if (btn) btn.click();
            }
        });
    });
}

document.addEventListener('DOMContentLoaded', function(){
    initCollapsibleSections();
    updateQueryPagination();
    loadRemoteStatus();
    window.setInterval(loadRemoteStatus, 15000);
    document.addEventListener('visibilitychange', function(){
        if (!document.hidden) loadRemoteStatus();
    });
    loadCloudTasks().then(function(){
        queryCloudResults(1);
        loadGeoCoverage();
    });
    var geoSort = document.getElementById('geoSort');
    if (geoSort) geoSort.addEventListener('change', renderGeoCoverage);
});
</script>
</body>
</html>
