<?php
require dirname(__DIR__, 2) . '/api/common.php';
if (!geo_wechat_enabled()) { header('Location: /login/?wechat_disabled=1'); exit; }
$pdo = geo_pdo(); geo_ensure_schema($pdo); geo_bootstrap($pdo); geo_start_session();
$openid = $_SESSION['geo_pending_wechat_openid'] ?? '';
if (!$openid) { header('Location: /wechat/login/'); exit; }
function wants_json(): bool { return stripos($_SERVER['HTTP_ACCEPT'] ?? '', 'application/json') !== false || strtolower($_SERVER['HTTP_X_REQUESTED_WITH'] ?? '') === 'fetch'; }
$error = '';
$mobile = '';
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $mobile = trim($_POST['mobile'] ?? '');
    $code = trim($_POST['code'] ?? '');
    if (!geo_valid_mobile($mobile)) {
        $error = '手机号格式不正确';
        if (wants_json()) geo_json(['success' => false, 'message' => $error], 400);
    } elseif (!geo_verify_sms_code($pdo, $mobile, 'bind_wechat', $code)) {
        $error = '验证码不正确或已过期';
        if (wants_json()) geo_json(['success' => false, 'message' => $error], 400);
    } else {
        try {
            $stmt = $pdo->prepare('SELECT * FROM geo_cloud_users WHERE mobile=? LIMIT 1'); $stmt->execute([$mobile]); $user = $stmt->fetch();
            $unionid = $_SESSION['geo_pending_wechat_unionid'] ?? null; $now = geo_now();
            if ($user) {
                $pdo->prepare('UPDATE geo_cloud_users SET wechat_openid=?, wechat_unionid=?, mobile_verified=1, updated_at=? WHERE id=?')->execute([$openid, $unionid, $now, (int)$user['id']]);
            } else {
                $token = geo_random_token(32); $hash = hash('sha256', $token); $username = 'wx_' . substr(hash('sha256', $openid), 0, 10);
                $pdo->prepare('INSERT INTO geo_cloud_users (username,email,password_hash,api_token_hash,api_token_last4,mobile,mobile_verified,wechat_openid,wechat_unionid,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)')->execute([$username, $username . '@geo.allgood.cn', password_hash(geo_random_token(12), PASSWORD_DEFAULT), $hash, substr($hash, -4), $mobile, 1, $openid, $unionid, $now, $now]);
            }
            $stmt = $pdo->prepare('SELECT * FROM geo_cloud_users WHERE mobile=? LIMIT 1'); $stmt->execute([$mobile]); $user = $stmt->fetch();
            unset($_SESSION['geo_pending_wechat_openid'], $_SESSION['geo_pending_wechat_unionid']); geo_login_user($user);
            if (wants_json()) geo_json(['success' => true, 'message' => '绑定成功', 'redirect' => '/dashboard/']);
            header('Location: /dashboard/'); exit;
        } catch (Throwable $e) {
            $error = '微信绑定失败，请稍后重试';
            if (wants_json()) geo_json(['success' => false, 'message' => $error], 500);
        }
    }
}
?><!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>绑定手机号</title><style>body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f4f7fb;margin:0;color:#101828}.box{width:min(480px,calc(100% - 32px));margin:8vh auto;background:white;border:1px solid #dbe3ef;border-radius:16px;padding:30px;box-shadow:0 20px 60px #16203318}.brand{height:48px;object-fit:contain;margin-bottom:22px}.row{display:grid;grid-template-columns:1fr 128px;gap:10px}.field{margin-top:15px}input{width:100%;box-sizing:border-box;padding:13px 14px;border:1px solid #ccd6e4;border-radius:10px;font-size:15px}button{width:100%;margin-top:18px;padding:13px;border:0;border-radius:10px;background:#1769ff;color:white;font-weight:800}.send{margin:0;background:#101828}.err{background:#fff0f0;color:#b42318;padding:10px;border-radius:8px;margin-top:14px}.ok{background:#ecfdf3;color:#027a48;padding:10px;border-radius:8px;margin-top:14px}</style></head><body><main class="box"><img class="brand" src="/public/assets/allgood-logo.png" alt="ALLGOOD"><h1>绑定并验证手机号</h1><div id="notice" class="<?= $error ? 'err' : '' ?>"><?= $error ? geo_h($error) : '' ?></div><form id="bindForm" method="post"><div class="field row"><input id="mobile" name="mobile" placeholder="手机号" value="<?=geo_h($mobile)?>" required><button class="send" type="button" id="sendBtn">发送验证码</button></div><div class="field"><input name="code" placeholder="短信验证码" required></div><button id="submitBtn">完成绑定</button></form></main><script>const form=document.getElementById('bindForm'),sendBtn=document.getElementById('sendBtn'),submitBtn=document.getElementById('submitBtn'),notice=document.getElementById('notice');function show(type,msg){notice.className=type;notice.textContent=msg||''}sendBtn.onclick=async()=>{sendBtn.disabled=true;const fd=new FormData();fd.append('mobile',document.getElementById('mobile').value.trim());fd.append('scene','bind_wechat');try{const r=await fetch('/api/sms/',{method:'POST',body:fd,headers:{Accept:'application/json'}});const j=await r.json();show(j.success?'ok':'err',j.message||'发送失败')}catch(e){show('err','网络异常，请稍后重试')}setTimeout(()=>{sendBtn.disabled=false},60000)};form.addEventListener('submit',async e=>{e.preventDefault();submitBtn.disabled=true;submitBtn.textContent='绑定中...';try{const r=await fetch('/wechat/bind-phone/',{method:'POST',body:new FormData(form),headers:{Accept:'application/json','X-Requested-With':'fetch'}});const j=await r.json();if(j.success){show('ok',j.message||'绑定成功');location.href=j.redirect||'/dashboard/';return}show('err',j.message||'绑定失败')}catch(err){show('err','网络异常，请稍后重试')}finally{submitBtn.disabled=false;submitBtn.textContent='完成绑定'}});</script></body></html>
