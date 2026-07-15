<?php
require dirname(__DIR__) . '/api/common.php';
$pdo = geo_pdo(); geo_ensure_schema($pdo); geo_bootstrap($pdo); geo_start_session();

function wants_json(): bool {
    return stripos($_SERVER['HTTP_ACCEPT'] ?? '', 'application/json') !== false || strtolower($_SERVER['HTTP_X_REQUESTED_WITH'] ?? '') === 'fetch';
}
function register_error(string $message, int $status = 400): void {
    if (wants_json()) geo_json(['success' => false, 'message' => $message], $status);
    $GLOBALS['error'] = $message;
}

$error = '';
$username = '';
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $username = trim($_POST['username'] ?? '');
    $password = (string)($_POST['password'] ?? '');
    $derivedEmail = $username . '@geo.allgood.cn';

    if (!preg_match('/^[A-Za-z0-9_\x{4e00}-\x{9fa5}]{3,40}$/u', $username)) register_error('用户名需 3-40 位，可使用中文、英文、数字和下划线');
    elseif (strlen($password) < 8) register_error('密码至少 8 位');
    else {
        $stmt = $pdo->prepare('SELECT username,email FROM geo_cloud_users WHERE username=? OR email=? LIMIT 1');
        $stmt->execute([$username, $derivedEmail]);
        $exists = $stmt->fetch();
        if ($exists) {
            if ($exists['username'] === $username) register_error('用户名已被注册');
            else register_error('邮箱已被注册');
        } else {
            try {
                $created = geo_create_user($pdo, $username, $password);
                $stmt = $pdo->prepare('SELECT * FROM geo_cloud_users WHERE id=? LIMIT 1');
                $stmt->execute([$created['id']]);
                $user = $stmt->fetch();
                geo_login_user($user);
                if (wants_json()) geo_json(['success' => true, 'message' => '注册成功', 'redirect' => '/dashboard/']);
                header('Location: /dashboard/'); exit;
            } catch (Throwable $e) {
                register_error('用户名或邮箱已被注册');
            }
        }
    }
}
?><!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>注册 - GEO-SOP</title>
<style>
:root{--ink:#1b2332;--muted:#667085;--line:#dce5f2;--blue:#1769ff;--cyan:#0ea5b7;--soft:#f8fbff}*{box-sizing:border-box}body{margin:0;color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;background:radial-gradient(circle at 16% 18%,rgba(82,103,246,.18),transparent 34%),radial-gradient(circle at 82% 82%,rgba(23,105,255,.12),transparent 32%),linear-gradient(180deg,#f8fbff 0%,#eef3fb 100%)}a{text-decoration:none}.auth-shell{display:grid;grid-template-columns:minmax(0,1.08fr) minmax(420px,.92fr);min-height:100vh}.brand-panel{display:flex;flex-direction:column;justify-content:center;padding:72px 7vw}.brand-logo{width:148px;height:auto;margin-bottom:54px}.kicker{color:var(--cyan);font-size:12px;font-weight:900;letter-spacing:.18em;margin-bottom:16px}.brand-panel h1{font-size:48px;line-height:1.12;margin:0 0 18px;letter-spacing:0}.brand-panel p{max-width:660px;color:var(--muted);font-size:17px;line-height:1.8;margin:0 0 28px}.feature-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;max-width:720px}.feature{border:1px solid var(--line);border-radius:8px;background:rgba(255,255,255,.72);padding:16px}.feature strong{display:block;font-size:15px;margin-bottom:6px}.feature span{display:block;color:#7b8aa0;font-size:13px;line-height:1.6}.form-panel{display:flex;align-items:center;justify-content:center;padding:48px 6vw 48px 24px}.box{width:430px;background:#fff;border:1px solid var(--line);border-radius:8px;padding:34px;box-shadow:0 24px 70px rgba(16,32,55,.12)}.box-logo{width:126px;height:auto;margin-bottom:26px}.box h1{margin:0 0 8px;font-size:26px;font-weight:800}.muted{color:var(--muted);line-height:1.7;font-size:14px;margin:0 0 26px}.field{margin-top:14px}input{width:100%;padding:13px 14px;border:1px solid #ccd6e4;border-radius:8px;font-size:15px;background:#fff}input:focus{outline:none;border-color:#1769ff;box-shadow:0 0 0 3px rgba(23,105,255,.12)}button,.btn{display:flex;align-items:center;justify-content:center;width:100%;height:46px;margin-top:18px;border:0;border-radius:6px;background:var(--blue);color:#fff;font-weight:800;font-size:15px;cursor:pointer}.btn.ghost{background:#fff;color:#1769ff;border:1px solid #b8c8ff}.register-link{margin-top:18px;color:#667085;line-height:1.7;font-size:14px}.register-link a{color:#1769ff;font-weight:800}.note{margin-top:16px;padding:12px 14px;border-radius:8px;background:#f3f7ff;color:#5d6f8a;font-size:13px;line-height:1.7}.err{background:#fff0f0;color:#b42318;padding:10px;border-radius:8px;margin:14px 0}.ok{background:#ecfdf3;color:#027a48;padding:10px;border-radius:8px;margin:14px 0}@media(max-width:980px){.auth-shell{grid-template-columns:1fr}.brand-panel{padding:38px 22px 18px}.brand-logo{margin-bottom:28px}.brand-panel h1{font-size:34px}.feature-grid{grid-template-columns:1fr}.form-panel{padding:18px 22px 38px;align-items:flex-start}.box{width:100%}}
</style>
</head>
<body>
<main class="auth-shell">
<section class="brand-panel">
<img class="brand-logo" src="/public/assets/geosop-wordmark.png" alt="GEO-SOP">
<div class="kicker">START WITH GEO-SOP</div>
<h1>创建账号，连接云端和本机采集。</h1>
<p>注册后可以在云端创建任务，在桌面端完成平台登录、回答采集、截图留证和分析同步。账号只用于 GEO-SOP 工作流，不需要绑定手机号。</p>
<div class="feature-grid">
<div class="feature"><strong>一个账号</strong><span>云端工作台和本机 App 使用同一套账号。</span></div>
<div class="feature"><strong>本机执行</strong><span>平台登录和浏览器采集仍在本机完成。</span></div>
<div class="feature"><strong>结果同步</strong><span>任务、回答、引用和看板数据自动归档。</span></div>
</div>
</section>
<section class="form-panel">
<div class="box">
<img class="box-logo" src="/public/assets/geosop-wordmark.png" alt="GEO-SOP">
<h1>注册 GEO-SOP</h1>
<p class="muted">使用用户名和密码即可创建云端账号。</p>
<div id="notice" class="<?= $error ? 'err' : '' ?>"><?= $error ? geo_h($error) : '' ?></div>
<form id="registerForm" method="post">
<div class="field"><input name="username" placeholder="用户名" value="<?=geo_h($username)?>" required></div>
<div class="field"><input name="password" type="password" placeholder="密码，至少 8 位" required></div>
<button id="submitBtn">注册并进入工作台</button>
</form>
<a class="btn ghost" href="/login/">已有账号，去登录</a>
<div class="note">注册成功后会自动登录云端工作台，桌面端可使用同一账号同步数据。</div>
</div>
</section>
</main>
<script>const form=document.getElementById('registerForm'),submitBtn=document.getElementById('submitBtn'),notice=document.getElementById('notice');function show(type,msg){notice.className=type;notice.textContent=msg||''}form.addEventListener('submit',async e=>{e.preventDefault();submitBtn.disabled=true;submitBtn.textContent='注册中...';try{const r=await fetch('/register/',{method:'POST',body:new FormData(form),headers:{Accept:'application/json','X-Requested-With':'fetch'}});const j=await r.json();if(j.success){show('ok',j.message||'注册成功');location.href=j.redirect||'/dashboard/';return}show('err',j.message||'注册失败')}catch(err){show('err','网络异常，请稍后重试')}finally{submitBtn.disabled=false;submitBtn.textContent='注册并进入工作台'}});</script>
</body></html>
