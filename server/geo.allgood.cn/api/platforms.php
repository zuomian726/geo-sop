<?php
declare(strict_types=1);

function geo_platform_catalog(): array {
    return [
        'doubao' => ['name' => '豆包', 'url' => 'https://www.doubao.com/chat'],
        'deepseek' => ['name' => 'DeepSeek', 'url' => 'https://chat.deepseek.com'],
        'yuanbao' => ['name' => '腾讯元宝', 'url' => 'https://yuanbao.tencent.com/chat'],
        'kimi' => ['name' => 'Kimi', 'url' => 'https://www.kimi.com'],
        'qianwen' => ['name' => '通义千问', 'url' => 'https://www.qianwen.com'],
        'wenxin' => ['name' => '文心一言（wenxin）', 'url' => 'https://wenxin.baidu.com'],
        'yiyan' => ['name' => '文心一言（yiyan）', 'url' => 'https://yiyan.baidu.com'],
        'chatgpt' => ['name' => 'ChatGPT', 'url' => 'https://chatgpt.com'],
    ];
}

function geo_remote_string_list($value, int $limit = 500): array {
    if (!is_array($value)) return [];
    $items = [];
    foreach ($value as $item) {
        if (!is_scalar($item)) continue;
        $item = trim((string)$item);
        if ($item === '' || in_array($item, $items, true)) continue;
        $items[] = mb_substr($item, 0, 2000, 'UTF-8');
        if (count($items) >= $limit) break;
    }
    return $items;
}

function geo_validate_remote_task_payload(array $payload): array {
    $catalog = geo_platform_catalog();
    $brandKeywords = geo_remote_string_list($payload['brand_keywords'] ?? [], 100);
    $competitorBrands = geo_remote_string_list($payload['competitor_brands'] ?? [], 100);
    $questions = geo_remote_string_list($payload['questions'] ?? [], 500);
    $requestedPlatforms = geo_remote_string_list($payload['platforms'] ?? [], 20);
    $unsupported = array_values(array_diff($requestedPlatforms, array_keys($catalog)));

    if (!$brandKeywords || !$questions || !$requestedPlatforms) {
        return ['valid' => false, 'message' => '请填写品牌关键词、采集问题，并至少选择一个平台。'];
    }
    if ($unsupported) {
        return ['valid' => false, 'message' => '包含客户端不支持的平台：' . implode('、', $unsupported)];
    }

    $platforms = array_values(array_intersect($requestedPlatforms, array_keys($catalog)));
    $screenshotConfig = [];
    if (is_array($payload['screenshot_config'] ?? null)) {
        foreach ($platforms as $platformId) {
            if (array_key_exists($platformId, $payload['screenshot_config'])) {
                $screenshotConfig[$platformId] = (bool)$payload['screenshot_config'][$platformId];
            }
        }
    }
    $parallel = max(1, min(count($platforms), (int)($payload['max_parallel_platforms'] ?? 2)));

    $normalized = $payload;
    $normalized['name'] = mb_substr(trim((string)($payload['name'] ?? '远程采集任务')), 0, 160, 'UTF-8') ?: '远程采集任务';
    $normalized['brand_name'] = mb_substr(trim((string)($payload['brand_name'] ?? '')), 0, 160, 'UTF-8');
    $normalized['brand_keywords'] = $brandKeywords;
    $normalized['competitor_brands'] = $competitorBrands;
    $normalized['questions'] = $questions;
    $normalized['platforms'] = $platforms;
    $normalized['screenshot_config'] = $screenshotConfig;
    $normalized['collection_interval'] = max(5, min(3600, (int)($payload['collection_interval'] ?? 20)));
    $normalized['max_parallel_platforms'] = $parallel;
    $normalized['schedule_type'] = 'manual';
    $normalized['schedule_config'] = is_array($payload['schedule_config'] ?? null) ? $payload['schedule_config'] : [];

    return ['valid' => true, 'message' => '', 'payload' => $normalized];
}
