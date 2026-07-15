<?php
require dirname(__DIR__, 2) . '/common.php';
$pdo = geo_pdo(); geo_ensure_schema($pdo); geo_bootstrap($pdo);
if ($_SERVER['REQUEST_METHOD'] !== 'POST') geo_json(['success' => false, 'message' => 'Method not allowed'], 405);
$raw = file_get_contents('php://input');
$data = json_decode($raw ?: '', true);
if (!is_array($data)) $data = $_POST;
$account = trim($data['account'] ?? $data['username'] ?? '');
$password = (string)($data['password'] ?? '');
if ($account === '' || $password === '') geo_json(['success' => false, 'message' => '请输入账号和密码'], 400);
$stmt = $pdo->prepare('SELECT * FROM geo_cloud_users WHERE username = ? OR email = ? OR mobile = ? LIMIT 1');
$stmt->execute([$account, $account, $account]);
$user = $stmt->fetch();
if (!$user || !password_verify($password, $user['password_hash'])) geo_json(['success' => false, 'message' => '账号或密码错误'], 401);
$token = geo_random_token(32);
$hash = hash('sha256', $token);
$now = geo_now();
$device = trim($data['device_name'] ?? 'GEO-SOP Desktop');
$pdo->prepare('INSERT INTO geo_cloud_tokens (cloud_user_id, token_hash, token_last4, device_name, created_at, last_used_at) VALUES (?,?,?,?,?,?)')->execute([(int)$user['id'], $hash, substr($hash, -4), $device, $now, $now]);
$pdo->prepare('UPDATE geo_cloud_users SET last_login_at=?, updated_at=? WHERE id=?')->execute([$now, $now, (int)$user['id']]);
geo_json([
    'success' => true,
    'message' => '登录成功',
    'cloud_sync_url' => 'https://geo.allgood.cn/api',
    'token' => $token,
    'user' => [
        'id' => (int)$user['id'],
        'username' => $user['username'],
        'email' => $user['email'],
        'mobile' => $user['mobile'],
        'mobile_verified' => (int)$user['mobile_verified'] === 1,
    ],
]);
