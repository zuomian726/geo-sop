<?php
require '/www/wwwroot/geo.allgood.cn/api/common.php';

$pdo = geo_pdo();
geo_ensure_schema($pdo);
geo_bootstrap($pdo);
$user = geo_current_web_user($pdo);
if (!$user) {
    header('Location: /login/');
    exit;
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

$message = '';
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
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
    if ($payload['brand_keywords'] && $payload['questions'] && $payload['platforms']) {
        $now = date('Y-m-d H:i:s');
        $stmt = $pdo->prepare('INSERT INTO geo_remote_tasks (cloud_user_id,name,payload,status,created_at,updated_at) VALUES (?,?,?,?,?,?)');
        $stmt->execute([(int)$user['id'], $payload['name'], json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES), 'pending', $now, $now]);
        $message = '远程任务已创建。桌面端登录同一账号后会自动拉取并执行。';
    } else {
        $message = '请填写品牌关键词、采集问题，并至少选择一个平台。';
    }
}

$uid = (int)$user['id'];
$remoteStmt = $pdo->prepare('SELECT * FROM geo_remote_tasks WHERE cloud_user_id=? ORDER BY id DESC LIMIT 30');
$remoteStmt->execute([$uid]);
$remoteRows = $remoteStmt->fetchAll();

$taskStmt = $pdo->prepare('SELECT * FROM geo_sync_tasks WHERE cloud_user_id=? ORDER BY synced_at DESC LIMIT 80');
$taskStmt->execute([$uid]);
$syncedTasks = $taskStmt->fetchAll();

$resultStmt = $pdo->prepare('SELECT * FROM geo_sync_results WHERE cloud_user_id=? ORDER BY COALESCE(local_created_at, synced_at) ASC, id ASC LIMIT 5000');
$resultStmt->execute([$uid]);
$resultRows = $resultStmt->fetchAll();

$runStmt = $pdo->prepare('SELECT * FROM geo_sync_runs WHERE cloud_user_id=? ORDER BY synced_at DESC LIMIT 1');
$runStmt->execute([$uid]);
$lastRun = $runStmt->fetch() ?: null;

$totalResults = count($resultRows);
$exposedResults = 0;
$platformStats = [];
$dailyStats = [];
$referenceCounts = [];
$questionStats = [];
$screenshotCount = 0;
$referenceResultCount = 0;

foreach ($resultRows as $row) {
    $payload = geo_decode_payload($row['payload'] ?? '');
    $platform = (string)($row['platform'] ?? ($payload['platform'] ?? 'unknown'));
    $question = (string)($row['question'] ?? ($payload['question'] ?? ''));
    $hasExposure = (int)($row['has_brand_exposure'] ?? 0) === 1;
    if ($hasExposure) $exposedResults++;

    if (!isset($platformStats[$platform])) $platformStats[$platform] = ['platform' => $platform, 'answers' => 0, 'exposed' => 0];
    $platformStats[$platform]['answers']++;
    if ($hasExposure) $platformStats[$platform]['exposed']++;

    if ($question !== '') {
        if (!isset($questionStats[$question])) $questionStats[$question] = ['question' => $question, 'answers' => 0, 'exposed' => 0];
        $questionStats[$question]['answers']++;
        if ($hasExposure) $questionStats[$question]['exposed']++;
    }

    $dateRaw = $row['local_created_at'] ?: ($row['synced_at'] ?? '');
    $dateKey = $dateRaw ? substr((string)$dateRaw, 0, 10) : date('Y-m-d');
    if (!isset($dailyStats[$dateKey])) $dailyStats[$dateKey] = ['answers' => 0, 'exposed' => 0];
    $dailyStats[$dateKey]['answers']++;
    if ($hasExposure) $dailyStats[$dateKey]['exposed']++;

    if (!empty($payload['screenshot_path'])) $screenshotCount++;

    $refs = geo_payload_refs($payload);
    if ($refs) $referenceResultCount++;
    foreach ($refs as $ref) {
        if (!is_array($ref)) continue;
        $domain = geo_domain_from_url((string)($ref['url'] ?? $ref['link'] ?? $ref['domain'] ?? ''));
        if ($domain !== '') $referenceCounts[$domain] = ($referenceCounts[$domain] ?? 0) + 1;
    }
}

$completedTasks = 0;
$runningTasks = 0;
$failedTasks = 0;
foreach ($syncedTasks as $task) {
    $status = (string)($task['status'] ?? '');
    if ($status === 'completed') $completedTasks++;
    if (in_array($status, ['running', 'paused', 'pending'], true)) $runningTasks++;
    if ($status === 'failed') $failedTasks++;
}

uasort($platformStats, fn($a, $b) => $b['answers'] <=> $a['answers']);
arsort($referenceCounts);
uasort($questionStats, function ($a, $b) {
    $ar = $a['answers'] ? $a['exposed'] / $a['answers'] : 0;
    $br = $b['answers'] ? $b['exposed'] / $b['answers'] : 0;
    return $ar === $br ? $b['answers'] <=> $a['answers'] : $ar <=> $br;
});
ksort($dailyStats);

$activePlatforms = count($platformStats);
$referenceDomains = count($referenceCounts);
$exposureRate = geo_percent($exposedResults, $totalResults);
$screenshotRate = geo_percent($screenshotCount, $totalResults);
$referenceRate = geo_percent($referenceResultCount, $totalResults);
$dataQuality = $totalResults ? round($screenshotRate * 0.45 + $referenceRate * 0.35 + min($totalResults, 20) / 20 * 100 * 0.2, 1) : 0.0;
$coverageScore = round(min($activePlatforms / 4 * 100, 100), 1);
$sourceScore = round(min($referenceDomains / 8 * 100, 100), 1);
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
<title>AI 答案采集分析</title>
<style>
:root{--blue:#409eff;--blue2:#1769ff;--cyan:#00a6b2;--ink:#1f2937;--muted:#7b8aa0;--line:#dfe6f0;--soft:#f3f6fb;--card:#fff;--dark:#07111f;--good:#67c23a}
*{box-sizing:border-box}body{margin:0;background:var(--soft);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}a{text-decoration:none;color:inherit}.app-header{height:58px;background:#fff;border-bottom:1px solid #e8eef6;display:flex;align-items:center;justify-content:space-between;padding:0 18px;position:sticky;top:0;z-index:10}.title{display:flex;align-items:center;gap:12px;font-size:20px;font-weight:800}.logo{width:32px;height:32px;border-radius:7px}.tag{display:inline-flex;align-items:center;height:22px;padding:0 8px;border-radius:5px;background:#f0f2f5;color:#606266;font-size:12px;font-weight:700}.tag.green{background:#eaf8df;color:#529b2e}.header-actions{display:flex;gap:10px;align-items:center}.btn,button{display:inline-flex;align-items:center;justify-content:center;gap:6px;height:36px;padding:0 16px;border:1px solid #dcdfe6;border-radius:4px;background:#fff;color:#344054;font-weight:700;cursor:pointer}.btn.primary,button.primary{background:var(--blue);border-color:var(--blue);color:#fff}.btn.small{height:26px;padding:0 10px;font-size:12px}.wrap{width:min(1560px,calc(100% - 48px));max-width:none;margin:0 auto;padding:24px 0}.workspace-hero{display:grid;grid-template-columns:minmax(0,1.9fr) minmax(310px,.95fr);gap:18px}.hero-panel{min-height:242px;background:var(--dark);border-radius:6px;padding:34px 38px;color:#fff;box-shadow:0 18px 50px rgba(14,30,54,.08)}.kicker{font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:var(--cyan);font-weight:900}.hero-panel h1{font-size:34px;margin:14px 0 12px}.hero-panel p{color:#aab7c9;line-height:1.8;margin:0 0 22px}.hero-actions{display:flex;gap:14px;flex-wrap:wrap}.side-stack{display:grid;gap:14px}.side-card,.metric-card,.panel,.tabs{background:#fff;border:1px solid var(--line);border-radius:6px;box-shadow:0 10px 30px rgba(16,32,55,.06)}.panel{padding:28px 32px}.panel h2{margin:14px 0 16px}.panel>.muted{margin:0 0 24px}.panel form{display:grid;gap:18px}.panel form p{margin:0}.panel .table-wrap{margin-top:18px}.side-card{padding:22px}.side-card strong{display:block;font-size:19px;margin:10px 0 8px}.muted{color:var(--muted);line-height:1.7}.msg{margin:18px 0 0;padding:12px 14px;background:#ecfdf3;color:#027a48;border-radius:6px}.metric-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:18px 0}.metric-card{padding:20px}.metric-card span,.mini-label{display:block;color:#7b8aa0;font-size:13px;font-weight:700}.metric-card strong{display:block;font-size:30px;margin:8px 0 4px}.tabs{overflow:hidden}.tab-nav{height:38px;display:flex;align-items:center;border-bottom:1px solid var(--line);background:#fff}.tab-nav a{height:38px;padding:0 20px;display:flex;align-items:center;color:#7b8aa0;font-weight:800;font-size:14px;border-right:1px solid #eef2f7}.tab-nav a.active{color:var(--blue);background:#f8fbff}.tab-body{padding:20px}.analysis-summary{display:grid;grid-template-columns:220px 1fr;gap:16px}.score-hero,.action-hero{border:1px solid var(--line);border-radius:6px;background:#fff;padding:22px}.score-hero{text-align:center}.score-ring{width:126px;height:126px;margin:0 auto 18px;border-radius:999px;background:conic-gradient(var(--blue2) calc(var(--score)*1%),#e8edf5 0);display:grid;place-items:center}.score-ring strong{width:90px;height:90px;border-radius:999px;background:#fff;display:grid;place-items:center;font-size:34px}.action-hero{display:flex;flex-direction:column;justify-content:center}.action-hero strong{font-size:26px;margin:8px 0}.analysis-card-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:16px}.analysis-card{border:1px solid var(--line);border-radius:6px;background:#fff;padding:18px}.analysis-card strong{display:block;font-size:27px;margin:8px 0}.chart-grid{display:grid;grid-template-columns:1.3fr .9fr;gap:14px;margin-top:16px}.chart-panel{border:1px solid var(--line);border-radius:6px;background:#fff;padding:18px}.chart-panel h3{font-size:21px;margin:8px 0}.trend{display:flex;align-items:end;gap:8px;height:210px;padding-top:16px}.trend-col{flex:1;min-width:22px;display:flex;flex-direction:column;align-items:center;gap:8px}.trend-stack{width:100%;height:150px;display:flex;align-items:end;justify-content:center;border-bottom:1px solid #e4e7ec}.trend-bar{width:18px;border-radius:5px 5px 0 0;background:#cbd5e1;position:relative}.trend-dot{position:absolute;left:50%;width:9px;height:9px;margin-left:-4px;border-radius:999px;background:var(--blue2);box-shadow:0 0 0 4px #1769ff1a}.trend-label{font-size:12px;color:var(--muted)}.bar-list{display:grid;gap:12px;margin-top:16px}.bar-row{display:grid;grid-template-columns:92px 1fr 54px;gap:10px;align-items:center}.bar-track{height:11px;background:#edf2f7;border-radius:999px;overflow:hidden}.bar-fill{height:100%;background:linear-gradient(90deg,var(--cyan),var(--blue2));border-radius:999px}.source-row{display:grid;grid-template-columns:1fr 70px;gap:12px;align-items:center;padding:10px 0;border-bottom:1px solid #edf1f7}.question-row{padding:12px 0;border-bottom:1px solid #edf1f7}.question-row strong{display:block;line-height:1.5}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px 20px}input,textarea{width:100%;padding:13px 14px;border:1px solid #ccd6e4;border-radius:6px;font-size:14px;background:#fff}textarea{min-height:96px;resize:vertical;line-height:1.6}.checks{display:flex;flex-wrap:wrap;gap:12px;margin-top:2px}.checks label{display:inline-flex;align-items:center;gap:6px;background:#f8fafc;border:1px solid #e4e7ec;border-radius:999px;padding:8px 12px}.checks input{width:auto}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;font-size:14px;min-width:760px}th,td{text-align:left;padding:11px;border-bottom:1px solid #edf1f7}th{color:#7b8aa0;font-size:12px}.status{display:inline-flex;padding:3px 8px;border-radius:999px;background:#f2f4f7;color:#344054;font-size:12px;font-weight:800}.empty{padding:24px;text-align:center;color:var(--muted);background:#f8fafc;border:1px dashed #d0d5dd;border-radius:6px}.local-note{margin-top:10px;font-size:13px;color:#7b8aa0}.local-note strong{color:#344054}.hidden-section{display:none}@media(max-width:980px){.workspace-hero,.analysis-summary,.chart-grid,.form-grid,.metric-grid,.analysis-card-grid{grid-template-columns:1fr}.panel{padding:22px 18px}.app-header{height:auto;align-items:flex-start;gap:12px;padding:12px;flex-direction:column}.header-actions{flex-wrap:wrap}.wrap{width:calc(100% - 28px);padding:16px 0}.hero-panel h1{font-size:28px}.hero-panel{padding:26px}.tab-nav{overflow:auto}.tab-nav a{white-space:nowrap}}
select{width:100%;padding:12px 14px;border:1px solid #ccd6e4;border-radius:6px;background:#fff;font-size:14px}.query-grid{display:grid;grid-template-columns:1.4fr 1fr 1fr 1fr 1fr 1fr;gap:12px;align-items:end}.query-grid label{display:grid;gap:7px;color:#7b8aa0;font-size:12px;font-weight:800}.query-actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:14px}.pill{display:inline-flex;align-items:center;height:24px;padding:0 8px;border-radius:999px;background:#eef4ff;color:#175cd3;font-size:12px;font-weight:800}.pill.good{background:#ecfdf3;color:#027a48}.pill.bad{background:#fff1f3;color:#c01048}.answer-snippet{max-width:360px;color:#475467;line-height:1.55}.query-count{color:#7b8aa0;font-size:13px;font-weight:700}@media(max-width:1100px){.query-grid{grid-template-columns:1fr 1fr}}@media(max-width:720px){.query-grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<header class="app-header">
    <div class="title">
        <img class="logo" src="/public/assets/geo-sop-icon.png" onerror="this.src='/public/assets/allgood-logo-dark.png'" alt="Logo">
        <span>AI 答案采集分析</span>
        <span class="tag">v0.3.2-dev</span>
        <span class="tag green">账号同步</span>
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
                <strong>等待配置 API Key</strong>
                <p class="muted">配置 API URL、Key 和模型后，可自动生成观察、风险和下一步动作。</p>
                <button class="btn small primary" onclick="openLocalApp('ai-settings')">在本机配置 AI</button>
            </div>
        </div>
    </section>

    <?php if($message): ?><div class="msg"><?=geo_h($message)?></div><?php endif; ?>

    <section class="metric-grid">
        <div class="metric-card"><span>监测任务</span><strong><?=geo_h((string)count($syncedTasks))?></strong><small class="muted"><?=geo_h((string)$runningTasks)?> 个运行/暂停中</small></div>
        <div class="metric-card"><span>采集回答</span><strong><?=geo_h((string)$totalResults)?></strong><small class="muted">覆盖 <?=geo_h((string)$activePlatforms)?> 个 AI 平台</small></div>
        <div class="metric-card"><span>品牌曝光率</span><strong><?=geo_h((string)$exposureRate)?>%</strong><small class="muted">回答中命中品牌词的比例</small></div>
        <div class="metric-card"><span>引用域名</span><strong><?=geo_h((string)$referenceDomains)?></strong><small class="muted">截图留证 <?=geo_h((string)$screenshotCount)?> 条</small></div>
    </section>

    <section class="tabs" id="insights">
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

    <section class="panel" id="data-query" style="margin-top:16px">
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
            <button class="primary" type="button" onclick="queryCloudResults()">查询数据</button>
            <button type="button" onclick="resetCloudQuery()">重置</button>
            <span class="query-count" id="queryCount">等待查询</span>
        </div>
        <div class="table-wrap">
            <table>
                <thead><tr><th>时间</th><th>任务</th><th>平台</th><th>问题</th><th>曝光</th><th>引用</th><th>截图</th><th>回答摘要</th></tr></thead>
                <tbody id="queryRows"><tr><td colspan="8"><div class="empty">选择条件后点击查询，服务端会读取已同步的云端数据。</div></td></tr></tbody>
            </table>
        </div>
    </section>

    <section class="panel" id="create-task" style="margin-top:16px">
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
                <label><input type="checkbox" name="platforms[]" value="doubao" checked>豆包</label>
                <label><input type="checkbox" name="platforms[]" value="deepseek">DeepSeek</label>
                <label><input type="checkbox" name="platforms[]" value="kimi">Kimi</label>
                <label><input type="checkbox" name="platforms[]" value="qianwen">通义千问</label>
                <label><input type="checkbox" name="platforms[]" value="yuanbao">腾讯元宝</label>
            </p>
            <button class="primary">创建任务</button>
            <button type="button" onclick="openLocalApp('dashboard')">打开本机 App 执行</button>
        </form>
    </section>

    <section class="panel" style="margin-top:16px">
        <span class="kicker">Queue</span>
        <h2>任务管理</h2>
        <div class="table-wrap"><table><tr><th>ID</th><th>任务</th><th>状态</th><th>客户端</th><th>本地任务</th><th>创建时间</th></tr>
        <?php foreach($remoteRows as $r): ?><tr><td><?=geo_h($r['id'])?></td><td><?=geo_h($r['name'])?></td><td><span class="status"><?=geo_h($r['status'])?></span></td><td><?=geo_h($r['assigned_install_id'] ?: '-')?></td><td><?=geo_h($r['local_task_id'] ?: '-')?></td><td><?=geo_h($r['created_at'])?></td></tr><?php endforeach; ?>
        <?php if(!$remoteRows): ?><tr><td colspan="6"><div class="empty">暂无远程任务。</div></td></tr><?php endif; ?>
        </table></div>
    </section>

    <section class="panel" style="margin-top:16px">
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

async function loadCloudTasks(){
    try {
        var data = await geoApi({action: 'tasks'});
        var select = document.getElementById('queryTask');
        if (!select) return;
        data.tasks.forEach(function(task){
            var option = document.createElement('option');
            option.value = task.local_id;
            option.dataset.installId = task.install_id;
            option.textContent = '#' + task.local_id + ' ' + task.name;
            select.appendChild(option);
        });
    } catch (e) {
        console.warn(e);
    }
}

async function queryCloudResults(){
    var task = document.getElementById('queryTask');
    var selected = task.options[task.selectedIndex];
    var params = {
        action: 'results',
        limit: '80',
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
    try {
        var data = await geoApi(params);
        count.textContent = '共 ' + data.total + ' 条，当前显示 ' + data.results.length + ' 条';
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
        rows.innerHTML = '<tr><td colspan="8"><div class="empty">' + h(e.message) + '</div></td></tr>';
    }
}

function resetCloudQuery(){
    ['queryTask','queryPlatform','queryKeyword','queryStart','queryEnd','queryExposed'].forEach(function(id){
        var el = document.getElementById(id);
        if (el) el.value = '';
    });
    queryCloudResults();
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
document.addEventListener('DOMContentLoaded', function(){
    loadCloudTasks().then(queryCloudResults);
});
</script>
</body>
</html>
