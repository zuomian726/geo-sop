<?php
require dirname(__DIR__) . '/api/common.php';
$pdo = geo_pdo(); geo_ensure_schema($pdo); geo_bootstrap($pdo); geo_start_session();

function wants_json(): bool {
    return stripos($_SERVER['HTTP_ACCEPT'] ?? '', 'application/json') !== false || strtolower($_SERVER['HTTP_X_REQUESTED_WITH'] ?? '') === 'fetch';
}

$error = '';
$account = '';
$demoRequested = !empty($_GET['demo']) || !empty($_POST['demo_login']);
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $demoLogin = (string)($_POST['demo_login'] ?? '') === '1';
    $account = $demoLogin ? geo_demo_username() : trim($_POST['username'] ?? '');
    $password = (string)($_POST['password'] ?? '');
    $stmt = $pdo->prepare($demoLogin
        ? 'SELECT * FROM geo_cloud_users WHERE LOWER(username) = ? LIMIT 1'
        : 'SELECT * FROM geo_cloud_users WHERE username = ? OR email = ? LIMIT 1');
    $stmt->execute($demoLogin ? [geo_demo_username()] : [$account, $account]);
    $user = $stmt->fetch();
    if ($user && ($demoLogin ? geo_is_demo_user($user) : password_verify($password, $user['password_hash']))) {
        $pdo->prepare('UPDATE geo_cloud_users SET last_login_at=? WHERE id=?')->execute([geo_now(), (int)$user['id']]);
        geo_login_user($user);
        if (wants_json()) geo_json(['success' => true, 'message' => '登录成功', 'redirect' => '/dashboard/']);
        header('Location: /dashboard/'); exit;
    }
    $error = $demoLogin ? '在线 Demo 暂时不可用，请稍后重试' : '账号或密码错误';
    if (wants_json()) geo_json(['success' => false, 'message' => $error], $demoLogin ? 503 : 401);
}
?><!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>登录 - GEO-SOP</title>
<style>
:root{--ink:#1b2332;--muted:#667085;--line:#dce5f2;--blue:#1769ff;--cyan:#0ea5b7;--soft:#f8fbff}*{box-sizing:border-box}body{margin:0;color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;background:radial-gradient(circle at 16% 18%,rgba(82,103,246,.18),transparent 34%),radial-gradient(circle at 82% 82%,rgba(23,105,255,.12),transparent 32%),linear-gradient(180deg,#f8fbff 0%,#eef3fb 100%)}a{text-decoration:none}.auth-shell{display:grid;grid-template-columns:minmax(0,1.08fr) minmax(420px,.92fr);min-height:100vh}.brand-panel{display:flex;flex-direction:column;justify-content:center;padding:72px 7vw}.brand-logo{width:148px;height:auto;margin-bottom:54px}.kicker{color:var(--cyan);font-size:12px;font-weight:900;letter-spacing:.18em;margin-bottom:16px}.brand-panel h1{font-size:48px;line-height:1.12;margin:0 0 18px;letter-spacing:0}.brand-panel p{max-width:660px;color:var(--muted);font-size:17px;line-height:1.8;margin:0 0 28px}.feature-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;max-width:720px}.feature{border:1px solid var(--line);border-radius:8px;background:rgba(255,255,255,.72);padding:16px}.feature strong{display:block;font-size:15px;margin-bottom:6px}.feature span{display:block;color:#7b8aa0;font-size:13px;line-height:1.6}.form-panel{display:flex;align-items:center;justify-content:center;padding:48px 6vw 48px 24px}.box{width:430px;background:#fff;border:1px solid var(--line);border-radius:8px;padding:34px;box-shadow:0 24px 70px rgba(16,32,55,.12)}.box-logo{width:126px;height:auto;margin-bottom:26px}.box h1{margin:0 0 8px;font-size:26px;font-weight:800}.muted{color:var(--muted);line-height:1.7;font-size:14px;margin:0 0 26px}.field{margin-top:14px}input{width:100%;padding:13px 14px;border:1px solid #ccd6e4;border-radius:8px;font-size:15px;background:#fff}input:focus{outline:none;border-color:#1769ff;box-shadow:0 0 0 3px rgba(23,105,255,.12)}button,.btn{display:flex;align-items:center;justify-content:center;width:100%;height:46px;margin-top:18px;border:0;border-radius:6px;background:var(--blue);color:#fff;font-weight:800;font-size:15px;cursor:pointer}.btn.ghost{background:#fff;color:#1769ff;border:1px solid #b8c8ff}.register-link{margin-top:18px;color:#667085;line-height:1.7;font-size:14px}.register-link a{color:#1769ff;font-weight:800}.note{margin-top:16px;padding:12px 14px;border-radius:8px;background:#f3f7ff;color:#5d6f8a;font-size:13px;line-height:1.7}.err{background:#fff0f0;color:#b42318;padding:10px;border-radius:8px;margin:14px 0}.ok{background:#ecfdf3;color:#027a48;padding:10px;border-radius:8px;margin:14px 0}@media(max-width:980px){.auth-shell{grid-template-columns:1fr}.brand-panel{padding:38px 22px 18px}.brand-logo{margin-bottom:28px}.brand-panel h1{font-size:34px}.feature-grid{grid-template-columns:1fr}.form-panel{padding:18px 22px 38px;align-items:flex-start}.box{width:100%}}
.demo-entry{margin:18px 0 24px;padding:16px;border:1px solid #b9d7ff;border-radius:8px;background:#f3f8ff}.demo-entry strong{display:block;font-size:15px}.demo-entry p{margin:6px 0 0;color:#5d6f8a;font-size:13px;line-height:1.6}.demo-entry button{margin-top:12px}.separator{display:flex;align-items:center;gap:10px;margin:22px 0 4px;color:#98a2b3;font-size:12px}.separator:before,.separator:after{content:"";height:1px;flex:1;background:#e4e7ec}
</style>
</head>
<body>
<main class="auth-shell">
<section class="brand-panel">
<img class="brand-logo" src="/public/assets/geosop-wordmark.png" alt="GEO-SOP">
<div class="kicker">GEO-SOP WORKSPACE</div>
<h1>监测 AI 平台如何回答你的品牌。</h1>
<p>GEO-SOP 将本机浏览器采集、截图留证、引用来源分析和云端任务同步放在同一套工作流里，帮助团队看清品牌在 AI 回答中的曝光、风险和下一步动作。</p>
<div class="feature-grid">
<div class="feature"><strong>本机采集</strong><span>浏览器登录态留在本机，采集过程可追踪。</span></div>
<div class="feature"><strong>证据留存</strong><span>保留回答、截图、来源和导出文件。</span></div>
<div class="feature"><strong>云端同步</strong><span>账号、任务和结果通过安全 API 打通。</span></div>
</div>
</section>
<section class="form-panel">
<div class="box">
<img class="box-logo" src="/public/assets/geosop-wordmark.png" alt="GEO-SOP">
<h1>登录 GEO-SOP</h1>
<p class="muted">使用 GEO-SOP 云端账号登录工作台，也可用于桌面端同步。</p>
<div id="notice" class="<?= $error ? 'err' : '' ?>"><?= $error ? geo_h($error) : '' ?></div>
<?php if ($demoRequested): ?>
<div class="demo-entry"><strong>在线 Demo · 只读安全模式</strong><p>无需输入账号密码即可浏览合成样例数据；创建、修改、采集和平台登录均被禁用。</p><form method="post" action="/login/?demo=1"><input type="hidden" name="demo_login" value="1"><button type="submit">一键进入 Demo 工作台</button></form></div>
<div class="separator">或登录自己的账号</div>
<?php endif; ?>
<form id="loginForm" method="post">
<div class="field"><input name="username" placeholder="用户名 / 邮箱" value="<?=geo_h($account)?>" required></div>
<div class="field"><input name="password" type="password" placeholder="密码" required></div>
<button id="submitBtn">登录并同步</button>
</form>
<div class="register-link">还没有账号？<a href="/register/">创建 GEO-SOP 账号</a></div>
<div class="note">登录后，云端任务、桌面端采集结果和分析数据会通过 HTTPS API 同步。</div>
</div>
</section>
</main>
<script>const form=document.getElementById('loginForm'),notice=document.getElementById('notice'),submitBtn=document.getElementById('submitBtn');function show(type,msg){notice.className=type;notice.textContent=msg||''}form.addEventListener('submit',async e=>{e.preventDefault();submitBtn.disabled=true;submitBtn.textContent='登录中...';try{const r=await fetch('/login/',{method:'POST',body:new FormData(form),headers:{Accept:'application/json','X-Requested-With':'fetch'}});const j=await r.json();if(j.success){show('ok',j.message||'登录成功');location.href=j.redirect||'/dashboard/';return}show('err',j.message||'登录失败')}catch(err){show('err','网络异常，请稍后重试')}finally{submitBtn.disabled=false;submitBtn.textContent='登录并同步'}});</script>
</body></html>
