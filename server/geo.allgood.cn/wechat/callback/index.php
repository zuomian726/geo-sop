<?php
require dirname(__DIR__, 2) . '/api/common.php';
if (!geo_wechat_enabled()) { header('Location: /wechat/login/'); exit; }
$pdo = geo_pdo(); geo_ensure_schema($pdo); geo_bootstrap($pdo); geo_start_session();
$code = trim($_GET['code'] ?? ''); $state = trim($_GET['state'] ?? '');
$stmt = $pdo->prepare('SELECT * FROM geo_wechat_states WHERE state=? AND used_at IS NULL LIMIT 1'); $stmt->execute([$state]); $row = $stmt->fetch();
if (!$code || !$row || strtotime($row['expires_at']) < time()) die('微信登录状态已过期，请重新扫码');
$pdo->prepare('UPDATE geo_wechat_states SET used_at=? WHERE id=?')->execute([geo_now(), (int)$row['id']]);
$c = geo_config();
$url = 'https://api.weixin.qq.com/sns/oauth2/access_token?appid=' . urlencode($c['wechat_appid']) . '&secret=' . urlencode($c['wechat_appsecret']) . '&code=' . urlencode($code) . '&grant_type=authorization_code';
$json = json_decode((string)@file_get_contents($url), true);
$openid = $json['openid'] ?? ''; $unionid = $json['unionid'] ?? null;
if (!$openid) die('微信授权失败，请重新扫码');
$stmt = $pdo->prepare('SELECT * FROM geo_cloud_users WHERE wechat_openid=? OR (wechat_unionid IS NOT NULL AND wechat_unionid=?) LIMIT 1'); $stmt->execute([$openid, $unionid]); $user = $stmt->fetch();
if ($user && (int)$user['mobile_verified'] === 1) { geo_login_user($user); header('Location: /dashboard/'); exit; }
$_SESSION['geo_pending_wechat_openid'] = $openid; $_SESSION['geo_pending_wechat_unionid'] = $unionid; header('Location: /wechat/bind-phone/'); exit;
