<?php
declare(strict_types=1);

if (PHP_SAPI !== 'cli') {
    http_response_code(404);
    exit;
}

require dirname(__DIR__) . '/api/common.php';

const DEMO_INSTALL_ID = 'demo-static';
const DEMO_EXPECTED_TASKS = 6;
const DEMO_EXPECTED_RESULTS = 144;
const DEMO_EXPECTED_MANUSCRIPTS = 4;

function demo_json(array $value): string
{
    return json_encode($value, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR);
}

function demo_date(DateTimeImmutable $base, int $daysAgo, int $hour, int $minute): string
{
    return $base->modify("-{$daysAgo} days")->setTime($hour, $minute)->format('Y-m-d H:i:s');
}

$username = geo_demo_username();
foreach ($argv as $argument) {
    if (strpos($argument, '--username=') === 0) {
        $username = trim(substr($argument, strlen('--username=')));
    }
}
if ($username === '') {
    throw new RuntimeException('Demo username cannot be empty.');
}

$pdo = geo_pdo();
geo_ensure_schema($pdo);
geo_bootstrap($pdo);

$userStmt = $pdo->prepare('SELECT id,username,email FROM geo_cloud_users WHERE username=? LIMIT 1');
$userStmt->execute([$username]);
$user = $userStmt->fetch();
if (!$user) {
    throw new RuntimeException("Cloud user {$username} was not found.");
}

$cloudUserId = (int)$user['id'];
$userKey = trim((string)$user['email']) ?: $username . '@geo.allgood.cn';
$baseDate = new DateTimeImmutable('today', new DateTimeZone('Asia/Shanghai'));

$platforms = [
    'doubao' => '豆包',
    'deepseek' => 'DeepSeek',
    'yuanbao' => '腾讯元宝',
    'kimi' => 'Kimi',
    'qianwen' => '通义千问',
    'chatgpt' => 'ChatGPT',
];

$tasks = [
    ['品牌认知基线', ['星野智能是什么？', '有哪些值得关注的智能办公品牌？', '星野智能适合什么规模的企业？', '如何评价星野智能的市场定位？']],
    ['企业知识库选型', ['企业知识库工具应该怎么选？', '中小企业适合哪些知识库产品？', '知识库项目上线前要验证什么？', '星野智能和传统知识库有什么区别？']],
    ['智能客服体验', ['如何建设企业智能客服？', '智能客服如何降低人工成本？', '选择智能客服平台要看哪些指标？', '星野智能是否支持客服知识运营？']],
    ['团队协作效率', ['AI 如何提升跨部门协作效率？', '适合远程团队的智能协作工具有哪些？', '如何减少企业内部重复问答？', '星野智能能解决哪些协作问题？']],
    ['数据安全与治理', ['企业部署 AI 工具要注意哪些安全问题？', '知识库权限体系应该如何设计？', '如何评估 AI 办公产品的数据治理能力？', '星野智能的数据安全能力怎么样？']],
    ['行业解决方案', ['制造企业如何落地生成式 AI？', '专业服务公司适合哪些 AI 工具？', '零售企业如何使用知识库提升效率？', '星野智能有哪些行业应用场景？']],
];

$manuscripts = [
    ['企业智能办公实践指南', 'https://content.demo.example.com/guides/smart-office'],
    ['企业知识库建设清单', 'https://content.demo.example.com/guides/enterprise-kb'],
    ['智能客服评估框架', 'https://content.demo.example.com/research/service-framework'],
    ['企业 AI 数据安全白皮书', 'https://content.demo.example.com/research/ai-security'],
];

$externalReferences = [
    ['中小企业数字化选型观察', 'https://research.example.net/reports/sme-digital'],
    ['智能办公产品对比', 'https://insights.example.org/compare/office-tools'],
    ['企业 AI 工具实施手册', 'https://docs.example.com/playbooks/enterprise-ai'],
    ['知识管理成熟度研究', 'https://benchmark.example.org/knowledge/maturity'],
    ['行业智能化案例库', 'https://cases.example.net/ai/industry'],
];

$deleteTables = [
    'geo_sync_assets',
    'geo_sync_results',
    'geo_sync_manuscripts',
    'geo_sync_sentiment_configs',
    'geo_sync_stats_snapshots',
    'geo_sync_tasks',
    'geo_sync_runs',
    'geo_remote_tasks',
    'geo_desktop_clients',
];

$taskInsert = $pdo->prepare('INSERT INTO geo_sync_tasks
    (cloud_user_id,install_id,local_id,local_user_id,user_key,name,status,payload,local_created_at,local_updated_at,synced_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?)');
$resultInsert = $pdo->prepare('INSERT INTO geo_sync_results
    (cloud_user_id,install_id,local_id,local_task_id,local_user_id,user_key,platform,question,has_brand_exposure,has_screenshot,reference_count,reference_domains,reference_items,payload,local_created_at,synced_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)');
$manuscriptInsert = $pdo->prepare('INSERT INTO geo_sync_manuscripts
    (cloud_user_id,install_id,local_id,local_user_id,user_key,title,url,payload,local_created_at,synced_at)
    VALUES (?,?,?,?,?,?,?,?,?,?)');
$configInsert = $pdo->prepare('INSERT INTO geo_sync_sentiment_configs
    (cloud_user_id,install_id,local_id,local_user_id,user_key,name,is_default,payload,local_created_at,local_updated_at,synced_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?)');
$assetInsert = $pdo->prepare('INSERT INTO geo_sync_assets
    (cloud_user_id,install_id,user_key,local_result_id,local_task_id,kind,platform,question,original_name,storage_path,public_url,mime_type,file_size,sha256,payload,created_at,updated_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)');

$pdo->beginTransaction();
try {
    foreach ($deleteTables as $table) {
        $delete = $pdo->prepare("DELETE FROM {$table} WHERE cloud_user_id=?");
        $delete->execute([$cloudUserId]);
    }

    foreach ($manuscripts as $index => [$title, $url]) {
        $createdAt = demo_date($baseDate, 12 - $index * 2, 9 + $index, 10);
        $manuscriptInsert->execute([
            $cloudUserId, DEMO_INSTALL_ID, $index + 1, $cloudUserId, $userKey,
            $title, $url, demo_json(['title' => $title, 'url' => $url, 'task_id' => ($index % 6) + 1]),
            $createdAt, $createdAt,
        ]);
    }

    $resultId = 0;
    $exposedCount = 0;
    foreach ($tasks as $taskIndex => [$taskLabel, $questions]) {
        $taskId = $taskIndex + 1;
        $taskName = "星野智能 · {$taskLabel}";
        $taskCreatedAt = demo_date($baseDate, 12 - $taskIndex * 2, 9, 0);
        $taskPayload = [
            'local_id' => $taskId,
            'name' => $taskName,
            'brand_name' => '星野智能',
            'brand_keywords' => ['星野智能', '智能办公方案'],
            'competitor_brands' => ['云图协作', '简知企业版'],
            'questions' => $questions,
            'platforms' => array_keys($platforms),
            'status' => 'completed',
        ];
        $taskInsert->execute([
            $cloudUserId, DEMO_INSTALL_ID, $taskId, $cloudUserId, $userKey,
            $taskName, 'completed', demo_json($taskPayload), $taskCreatedAt, $taskCreatedAt, $taskCreatedAt,
        ]);

        foreach ($questions as $questionIndex => $question) {
            foreach (array_values($platforms) as $platformIndex => $platformName) {
                $platformId = array_keys($platforms)[$platformIndex];
                $resultId++;
                $exposed = (($taskId + $questionIndex + $platformIndex) % 3) !== 0;
                $negative = (($resultId % 17) === 0);
                $sentiment = $negative ? '负面' : ($exposed ? '正面' : '中性');
                $exposedCount += $exposed ? 1 : 0;
                $primaryReference = $manuscripts[($taskIndex + $questionIndex) % count($manuscripts)];
                $secondaryReference = $externalReferences[($platformIndex + $questionIndex) % count($externalReferences)];
                $references = [['title' => $primaryReference[0], 'url' => $primaryReference[1]]];
                if (($resultId % 2) === 0) {
                    $references[] = ['title' => $secondaryReference[0], 'url' => $secondaryReference[1]];
                }
                $answer = $exposed
                    ? "{$platformName} 的样例回答认为，星野智能可以作为{$taskLabel}场景的候选方案。评估时应结合数据安全、实施周期、团队使用习惯和持续运营成本，并通过真实问题进行验证。"
                    : "{$platformName} 的样例回答建议先明确{$taskLabel}场景的目标、预算和验收指标，再比较云图协作、简知企业版等候选产品，并安排小范围试用。";
                if ($negative) {
                    $answer .= ' 当前公开资料对部分能力说明仍不够完整，采购前需要进一步核验。';
                }
                $resultAt = demo_date($baseDate, 11 - (($taskIndex * 4 + $questionIndex) % 12), 10 + ($platformIndex % 6), ($resultId * 7) % 60);
                $domains = array_values(array_unique(array_map(
                    static fn(array $reference): string => (string)parse_url($reference['url'], PHP_URL_HOST),
                    $references
                )));
                $payload = [
                    'task_id' => $taskId,
                    'answer' => $answer,
                    'references' => $references,
                    'exposed_keywords' => $exposed ? ['星野智能'] : [],
                    'screenshot_path' => '',
                    'ai_sentiment' => [
                        'label' => $sentiment,
                        'score' => $negative ? 0.28 : ($exposed ? 0.78 : 0.5),
                        'reason' => $negative ? '样例回答提出资料完整性风险。' : ($exposed ? '样例回答自然提及目标品牌。' : '样例回答未提及目标品牌。'),
                    ],
                ];
                $hasScreenshot = in_array($resultId, [1, 25], true) ? 1 : 0;
                $resultInsert->execute([
                    $cloudUserId, DEMO_INSTALL_ID, $resultId, $taskId, $cloudUserId, $userKey,
                    $platformId, $question, $exposed ? 1 : 0, $hasScreenshot, count($references),
                    demo_json($domains), demo_json($references), demo_json($payload), $resultAt, $resultAt,
                ]);
            }
        }
    }

    if ($resultId !== DEMO_EXPECTED_RESULTS) {
        throw new RuntimeException("Generated {$resultId} results; expected " . DEMO_EXPECTED_RESULTS . '.');
    }

    $insightAt = demo_date($baseDate, 0, 9, 30);
    $exposureRate = round($exposedCount / DEMO_EXPECTED_RESULTS * 100, 1);
    $configPayload = [
        'local_id' => 1,
        'name' => 'Demo AI 分析',
        'enable_ai_sentiment' => true,
        'ai_platform' => 'openai',
        'ai_api_url' => 'https://api.example.com',
        'ai_api_key' => null,
        'ai_model_name' => 'demo-model',
        'is_default' => true,
        'latest_insight' => [
            'summary' => "星野智能在 144 条跨平台样例回答中的品牌曝光率为 {$exposureRate}%，已建立基础认知，但引用来源和平台稳定性仍有提升空间。",
            'observations' => [
                '6 个业务主题覆盖品牌认知、知识库、客服、协作、安全与行业方案。',
                '不同平台对品牌的提及稳定性存在差异，适合按主题持续复测。',
                '4 篇合成 GEO 稿件已产生引用，可继续扩展外部来源结构。',
            ],
            'actions' => [
                '优先补充未曝光问题对应的 FAQ、对比页和行业案例。',
                '围绕高频引用主题制作更完整、可验证的深度内容。',
                '下一周期沿用同一问题集复测，观察曝光率与引用来源变化。',
            ],
            'risks' => ['Demo 数据全部为合成样例，不代表任何真实企业或平台评价。'],
            'experiments' => ['按行业拆分问题集，比较不同内容主题对品牌曝光率的影响。'],
        ],
        'latest_insight_generated_at' => str_replace(' ', 'T', $insightAt) . '+08:00',
    ];
    $configInsert->execute([
        $cloudUserId, DEMO_INSTALL_ID, 1, $cloudUserId, $userKey, 'Demo AI 分析', 1,
        demo_json($configPayload), $insightAt, $insightAt, $insightAt,
    ]);

    $assetDefinitions = [
        [1, 1, 'doubao', $tasks[0][1][0], 'geo-answer-demo.svg'],
        [25, 2, 'doubao', $tasks[1][1][0], 'geo-dashboard-demo.svg'],
    ];
    foreach ($assetDefinitions as [$localResultId, $localTaskId, $platform, $question, $filename]) {
        $storagePath = __DIR__ . '/assets/' . $filename;
        if (!is_file($storagePath)) {
            throw new RuntimeException("Demo asset {$filename} is missing.");
        }
        $assetInsert->execute([
            $cloudUserId, DEMO_INSTALL_ID, $userKey, $localResultId, $localTaskId, 'screenshot',
            $platform, $question, $filename, $storagePath,
            'https://geo.allgood.cn/demo/assets/' . $filename, 'image/svg+xml', filesize($storagePath),
            hash_file('sha256', $storagePath), demo_json(['demo' => true]), $insightAt, $insightAt,
        ]);
    }

    $countChecks = [
        'geo_sync_tasks' => DEMO_EXPECTED_TASKS,
        'geo_sync_results' => DEMO_EXPECTED_RESULTS,
        'geo_sync_manuscripts' => DEMO_EXPECTED_MANUSCRIPTS,
    ];
    foreach ($countChecks as $table => $expected) {
        $countStmt = $pdo->prepare("SELECT COUNT(*) FROM {$table} WHERE cloud_user_id=?");
        $countStmt->execute([$cloudUserId]);
        $actual = (int)$countStmt->fetchColumn();
        if ($actual !== $expected) {
            throw new RuntimeException("{$table} contains {$actual} rows; expected {$expected}.");
        }
    }

    $pdo->commit();
    echo demo_json([
        'success' => true,
        'username' => $username,
        'tasks' => DEMO_EXPECTED_TASKS,
        'results' => DEMO_EXPECTED_RESULTS,
        'manuscripts' => DEMO_EXPECTED_MANUSCRIPTS,
        'exposed_results' => $exposedCount,
        'exposure_rate' => $exposureRate,
    ]), PHP_EOL;
} catch (Throwable $error) {
    if ($pdo->inTransaction()) {
        $pdo->rollBack();
    }
    fwrite(STDERR, $error->getMessage() . PHP_EOL);
    exit(1);
}
