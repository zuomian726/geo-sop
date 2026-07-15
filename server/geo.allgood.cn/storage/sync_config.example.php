<?php
declare(strict_types=1);

$requiredEnv = static function (string $name): string {
    $value = getenv($name);
    if ($value === false || trim($value) === '') {
        throw new RuntimeException("Required environment variable is missing: {$name}");
    }
    return trim($value);
};

return [
    'db_host' => $requiredEnv('GEO_DB_HOST'),
    'db_port' => (int)(getenv('GEO_DB_PORT') ?: 3306),
    'db_name' => $requiredEnv('GEO_DB_NAME'),
    'db_user' => $requiredEnv('GEO_DB_USER'),
    'db_pass' => $requiredEnv('GEO_DB_PASSWORD'),
    'token_sha256' => hash('sha256', $requiredEnv('GEO_LEGACY_SYNC_TOKEN')),
    'public_base_url' => rtrim((string)(getenv('GEO_PUBLIC_BASE_URL') ?: 'https://geo.allgood.cn'), '/'),

    'sms_enabled' => false,
    'aliyun_sms_key' => '',
    'aliyun_sms_secret' => '',
    'aliyun_sms_sign' => '',
    'aliyun_sms_templates' => [],
    'sms_webhook_url' => '',

    'wechat_enabled' => false,
    'wechat_appid' => '',
    'wechat_appsecret' => '',
    'wechat_redirect_uri' => '',
    'wechat_scan_qr_url' => '',
    'wechat_scan_status_url' => '',
];
