<?php
require dirname(__DIR__) . '/common.php';
if ($_SERVER['REQUEST_METHOD'] !== 'POST') geo_json(['success' => false, 'message' => 'Method not allowed'], 405);
if (!geo_sms_enabled()) geo_json(['success' => false, 'message' => '短信登录未启用'], 404);
$pdo = geo_pdo(); geo_ensure_schema($pdo); geo_bootstrap($pdo);
$mobile = trim($_POST['mobile'] ?? '');
$scene = trim($_POST['scene'] ?? 'register');
if (!in_array($scene, ['register', 'bind_wechat'], true)) $scene = 'register';
$result = geo_create_sms_code($pdo, $mobile, $scene);
geo_json(['success' => $result['ok'], 'message' => $result['message']], $result['ok'] ? 200 : 400);
