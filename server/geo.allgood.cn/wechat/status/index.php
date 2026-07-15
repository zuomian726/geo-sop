<?php
require dirname(__DIR__, 2) . '/api/common.php';
if (!geo_wechat_enabled()) geo_json(['success' => false, 'message' => '微信登录未启用'], 404);
$pdo = geo_pdo(); geo_ensure_schema($pdo); geo_bootstrap($pdo); geo_start_session();
$ticket = trim($_GET['ticket'] ?? '');
if ($ticket === '') geo_json(['success' => false, 'message' => 'ticket 缺失'], 400);
$result = geo_wechat_poll_openid($ticket);
if (empty($result['ok'])) geo_json(['success' => false, 'message' => $result['message'] ?? '等待扫码确认']);
$openid = $result['openid'];
$stmt = $pdo->prepare('SELECT * FROM geo_cloud_users WHERE wechat_openid=? LIMIT 1');
$stmt->execute([$openid]);
$user = $stmt->fetch();
if ($user && (int)$user['mobile_verified'] === 1) {
    $pdo->prepare('UPDATE geo_cloud_users SET last_login_at=? WHERE id=?')->execute([geo_now(), (int)$user['id']]);
    geo_login_user($user);
    geo_json(['success' => true, 'message' => '扫码成功，正在进入工作台', 'redirect' => '/dashboard/']);
}
$_SESSION['geo_pending_wechat_openid'] = $openid;
$_SESSION['geo_pending_wechat_unionid'] = null;
geo_json(['success' => true, 'message' => '扫码成功，请绑定手机号', 'redirect' => '/wechat/bind-phone/']);
