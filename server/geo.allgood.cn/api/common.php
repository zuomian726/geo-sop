<?php
declare(strict_types=1);

function geo_root_dir(): string { return dirname(__DIR__); }
function geo_storage_path(string $relative = ''): string {
    $root = rtrim((string)(getenv('GEO_STORAGE_DIR') ?: geo_root_dir() . '/storage'), '/');
    return $relative === '' ? $root : $root . '/' . ltrim($relative, '/');
}
function geo_config(): array {
    static $config = null;
    if (is_array($config)) return $config;
    $path = (string)(getenv('GEO_SYNC_CONFIG') ?: geo_storage_path('sync_config.php'));
    if (!is_file($path)) throw new RuntimeException('GEO-SOP server configuration is missing');
    $loaded = require $path;
    if (!is_array($loaded)) throw new RuntimeException('GEO-SOP server configuration is invalid');
    foreach (['db_host', 'db_port', 'db_name', 'db_user', 'db_pass'] as $key) {
        if (!array_key_exists($key, $loaded)) throw new RuntimeException("GEO-SOP configuration key is missing: {$key}");
    }
    $config = $loaded;
    return $config;
}
function geo_json(array $data, int $status = 200): void { http_response_code($status); header('Content-Type: application/json; charset=utf-8'); echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES); exit; }
function geo_pdo(): PDO { $c = geo_config(); $dsn = sprintf('mysql:host=%s;port=%d;dbname=%s;charset=utf8mb4', $c['db_host'], $c['db_port'], $c['db_name']); return new PDO($dsn, $c['db_user'], $c['db_pass'], [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION, PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC, PDO::ATTR_EMULATE_PREPARES => false]); }
function geo_token(): string { $h = $_SERVER['HTTP_AUTHORIZATION'] ?? $_SERVER['REDIRECT_HTTP_AUTHORIZATION'] ?? ''; return stripos($h, 'Bearer ') === 0 ? trim(substr($h, 7)) : ''; }
function geo_h($s): string { return htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8'); }
function geo_now(): string { return date('Y-m-d H:i:s'); }
function geo_client_ip(): string { return substr((string)($_SERVER['REMOTE_ADDR'] ?? ''), 0, 80); }
function geo_random_token(int $bytes = 32): string { return bin2hex(random_bytes($bytes)); }
function geo_valid_mobile(string $mobile): bool { return (bool)preg_match('/^1\d{10}$/', $mobile); }
function geo_start_session(): void {
    if (session_status() === PHP_SESSION_ACTIVE) return;
    $forwardedProto = strtolower(trim(explode(',', (string)($_SERVER['HTTP_X_FORWARDED_PROTO'] ?? ''))[0]));
    $secure = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') || $forwardedProto === 'https';
    ini_set('session.use_strict_mode', '1');
    session_set_cookie_params(['lifetime' => 0, 'path' => '/', 'secure' => $secure, 'httponly' => true, 'samesite' => 'Lax']);
    session_start();
}
function geo_add_column(PDO $pdo, string $table, string $column, string $ddl): void { try { $pdo->exec("ALTER TABLE {$table} ADD COLUMN {$column} {$ddl}"); } catch (Throwable $e) {} }
function geo_add_index(PDO $pdo, string $table, string $name, string $ddl): void { try { $pdo->exec("ALTER TABLE {$table} ADD {$ddl}"); } catch (Throwable $e) {} }

function geo_ensure_schema(PDO $pdo): void {
    $pdo->exec("CREATE TABLE IF NOT EXISTS geo_cloud_users (id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY, username VARCHAR(120) NOT NULL UNIQUE, email VARCHAR(255) NOT NULL UNIQUE, password_hash VARCHAR(255) NOT NULL, api_token_hash CHAR(64) NOT NULL UNIQUE, api_token_last4 VARCHAR(8) NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
    geo_add_column($pdo, 'geo_cloud_users', 'mobile', "VARCHAR(20) NULL");
    geo_add_column($pdo, 'geo_cloud_users', 'mobile_verified', "TINYINT(1) NOT NULL DEFAULT 0");
    geo_add_column($pdo, 'geo_cloud_users', 'wechat_openid', "VARCHAR(128) NULL");
    geo_add_column($pdo, 'geo_cloud_users', 'wechat_unionid', "VARCHAR(128) NULL");
    geo_add_column($pdo, 'geo_cloud_users', 'nickname', "VARCHAR(120) NULL");
    geo_add_column($pdo, 'geo_cloud_users', 'avatar_url', "VARCHAR(500) NULL");
    geo_add_column($pdo, 'geo_cloud_users', 'last_login_at', "DATETIME NULL");
    geo_add_index($pdo, 'geo_cloud_users', 'uniq_geo_cloud_mobile', "UNIQUE KEY uniq_geo_cloud_mobile (mobile)");
    geo_add_index($pdo, 'geo_cloud_users', 'uniq_geo_cloud_wechat_openid', "UNIQUE KEY uniq_geo_cloud_wechat_openid (wechat_openid)");
    $pdo->exec("CREATE TABLE IF NOT EXISTS geo_cloud_tokens (id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY, cloud_user_id BIGINT UNSIGNED NOT NULL, token_hash CHAR(64) NOT NULL UNIQUE, token_last4 VARCHAR(8) NULL, device_name VARCHAR(120) NULL, created_at DATETIME NOT NULL, last_used_at DATETIME NULL, revoked_at DATETIME NULL, KEY idx_geo_cloud_tokens_user (cloud_user_id), KEY idx_geo_cloud_tokens_hash (token_hash)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
    $pdo->exec("CREATE TABLE IF NOT EXISTS geo_phone_codes (id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY, mobile VARCHAR(20) NOT NULL, scene VARCHAR(40) NOT NULL, code_hash CHAR(64) NOT NULL, ip VARCHAR(80) NULL, attempts INT NOT NULL DEFAULT 0, expires_at DATETIME NOT NULL, used_at DATETIME NULL, created_at DATETIME NOT NULL, KEY idx_geo_phone_mobile_scene (mobile, scene), KEY idx_geo_phone_ip_time (ip, created_at)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
    $pdo->exec("CREATE TABLE IF NOT EXISTS geo_wechat_states (id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY, state VARCHAR(80) NOT NULL UNIQUE, scene VARCHAR(40) NOT NULL, created_at DATETIME NOT NULL, expires_at DATETIME NOT NULL, used_at DATETIME NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
    $pdo->exec("CREATE TABLE IF NOT EXISTS geo_remote_tasks (id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY, cloud_user_id BIGINT UNSIGNED NOT NULL, name VARCHAR(255) NOT NULL, payload LONGTEXT NOT NULL, status VARCHAR(40) NOT NULL DEFAULT 'pending', assigned_install_id VARCHAR(64) NULL, assigned_user_key VARCHAR(255) NULL, local_task_id INT NULL, created_at DATETIME NOT NULL, pulled_at DATETIME NULL, updated_at DATETIME NOT NULL, KEY idx_remote_user_status (cloud_user_id, status), KEY idx_remote_assigned (assigned_install_id, assigned_user_key)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
}

function geo_auth_user(PDO $pdo): ?array { $token = geo_token(); if ($token === '') return null; $hash = hash('sha256', $token); $stmt = $pdo->prepare('SELECT * FROM geo_cloud_users WHERE api_token_hash = ? LIMIT 1'); $stmt->execute([$hash]); $u = $stmt->fetch(); if ($u) return $u; $stmt = $pdo->prepare('SELECT u.* FROM geo_cloud_tokens t JOIN geo_cloud_users u ON u.id=t.cloud_user_id WHERE t.token_hash=? AND t.revoked_at IS NULL LIMIT 1'); $stmt->execute([$hash]); $u = $stmt->fetch(); if ($u) { $pdo->prepare('UPDATE geo_cloud_tokens SET last_used_at=? WHERE token_hash=?')->execute([geo_now(), $hash]); return $u; } return null; }
function geo_bootstrap(PDO $pdo): void {
    // Kept as a compatibility hook; accounts are created only through registration.
}
function geo_current_web_user(PDO $pdo): ?array { geo_start_session(); if (empty($_SESSION['geo_cloud_user_id'])) return null; $stmt = $pdo->prepare('SELECT * FROM geo_cloud_users WHERE id = ? LIMIT 1'); $stmt->execute([(int)$_SESSION['geo_cloud_user_id']]); $u = $stmt->fetch(); return $u ?: null; }
function geo_login_user(array $user): void { geo_start_session(); session_regenerate_id(true); $_SESSION['geo_cloud_user_id'] = (int)$user['id']; }

function geo_sms_enabled(): bool { $c = geo_config(); return !empty($c['sms_enabled']); }

function geo_send_sms_provider(string $mobile, string $code, string $scene): array {
    $c = geo_config();
    if (empty($c['sms_enabled'])) return ['ok' => false, 'message' => '短信登录未启用'];
    if (!empty($c['aliyun_sms_key']) && !empty($c['aliyun_sms_secret']) && !empty($c['aliyun_sms_sign']) && !empty($c['aliyun_sms_templates'])) {
        $templates = is_array($c['aliyun_sms_templates']) ? $c['aliyun_sms_templates'] : [];
        $template = $templates[$scene] ?? $templates['register'] ?? '';
        if ($template === '') return ['ok' => false, 'message' => '短信模板未配置'];
        $params = [
            'AccessKeyId' => $c['aliyun_sms_key'],
            'Action' => 'SendSms',
            'Format' => 'JSON',
            'Version' => '2017-05-25',
            'SignatureVersion' => '1.0',
            'SignatureMethod' => 'HMAC-SHA1',
            'SignatureNonce' => bin2hex(random_bytes(16)),
            'Timestamp' => gmdate('Y-m-d\TH:i:s\Z'),
            'PhoneNumbers' => $mobile,
            'SignName' => $c['aliyun_sms_sign'],
            'TemplateCode' => $template,
            'TemplateParam' => json_encode(['code' => $code], JSON_UNESCAPED_UNICODE),
        ];
        ksort($params);
        $query = [];
        foreach ($params as $k => $v) {
            $query[] = rawurlencode((string)$k) . '=' . rawurlencode((string)$v);
        }
        $canonical = str_replace(['%7E'], ['~'], implode('&', $query));
        $stringToSign = 'GET&%2F&' . rawurlencode($canonical);
        $params['Signature'] = base64_encode(hash_hmac('sha1', $stringToSign, $c['aliyun_sms_secret'] . '&', true));
        $url = 'https://dysmsapi.aliyuncs.com/?' . http_build_query($params);
        $ch = curl_init($url);
        curl_setopt_array($ch, [CURLOPT_RETURNTRANSFER => true, CURLOPT_CONNECTTIMEOUT => 5, CURLOPT_TIMEOUT => 10]);
        $body = curl_exec($ch); $errno = curl_errno($ch); curl_close($ch);
        $json = json_decode((string)$body, true);
        if (!$errno && is_array($json) && ($json['Code'] ?? '') === 'OK') return ['ok' => true, 'message' => '验证码已发送'];
        $msg = is_array($json) && !empty($json['Message']) ? $json['Message'] : '短信发送失败';
        return ['ok' => false, 'message' => '短信发送失败：' . $msg];
    }
    if (!empty($c['sms_webhook_url'])) {
        $payload = json_encode(['mobile' => $mobile, 'code' => $code, 'scene' => $scene], JSON_UNESCAPED_UNICODE);
        $ch = curl_init($c['sms_webhook_url']);
        curl_setopt_array($ch, [CURLOPT_RETURNTRANSFER => true, CURLOPT_POST => true, CURLOPT_HTTPHEADER => ['Content-Type: application/json'], CURLOPT_POSTFIELDS => $payload, CURLOPT_TIMEOUT => 8]);
        $body = curl_exec($ch); $errno = curl_errno($ch); $status = (int)curl_getinfo($ch, CURLINFO_RESPONSE_CODE); curl_close($ch);
        if (!$errno && $status >= 200 && $status < 300) return ['ok' => true, 'message' => '验证码已发送'];
        return ['ok' => false, 'message' => '短信服务请求失败'];
    }
    $line = sprintf("[%s] mobile=%s scene=%s code=%s ip=%s\n", geo_now(), $mobile, $scene, $code, geo_client_ip());
    @file_put_contents(geo_storage_path('sms_codes.log'), $line, FILE_APPEND | LOCK_EX);
    return ['ok' => false, 'message' => '短信服务尚未配置，验证码已写入服务端日志用于联调'];
}

function geo_create_sms_code(PDO $pdo, string $mobile, string $scene): array {
    if (!geo_sms_enabled()) return ['ok' => false, 'message' => '短信登录未启用'];
    if (!geo_valid_mobile($mobile)) return ['ok' => false, 'message' => '手机号格式不正确'];
    $stmt = $pdo->prepare('SELECT id FROM geo_cloud_users WHERE mobile = ? LIMIT 1'); $stmt->execute([$mobile]);
    if ($scene === 'register' && $stmt->fetch()) return ['ok' => false, 'message' => '该手机号已注册'];
    $last = $pdo->prepare('SELECT created_at FROM geo_phone_codes WHERE mobile=? AND scene=? ORDER BY id DESC LIMIT 1'); $last->execute([$mobile, $scene]); $row = $last->fetch();
    if ($row && strtotime($row['created_at']) > time() - 60) return ['ok' => false, 'message' => '发送太频繁，请 60 秒后再试'];
    $ip = geo_client_ip(); $hour = date('Y-m-d H:i:s', time() - 3600);
    $cnt = $pdo->prepare('SELECT COUNT(*) c FROM geo_phone_codes WHERE ip=? AND created_at > ?'); $cnt->execute([$ip, $hour]);
    if ((int)$cnt->fetch()['c'] >= 5) return ['ok' => false, 'message' => '当前网络发送过于频繁，请稍后再试'];
    $code = (string)random_int(100000, 999999); $now = geo_now(); $expires = date('Y-m-d H:i:s', time() + 300);
    $stmt = $pdo->prepare('INSERT INTO geo_phone_codes (mobile,scene,code_hash,ip,expires_at,created_at) VALUES (?,?,?,?,?,?)');
    $stmt->execute([$mobile, $scene, hash('sha256', $mobile . '|' . $scene . '|' . $code), $ip, $expires, $now]);
    $sent = geo_send_sms_provider($mobile, $code, $scene);
    return ['ok' => $sent['ok'], 'message' => $sent['message']];
}

function geo_verify_sms_code(PDO $pdo, string $mobile, string $scene, string $code): bool {
    $stmt = $pdo->prepare('SELECT * FROM geo_phone_codes WHERE mobile=? AND scene=? AND used_at IS NULL ORDER BY id DESC LIMIT 1'); $stmt->execute([$mobile, $scene]); $row = $stmt->fetch();
    if (!$row || strtotime($row['expires_at']) < time() || (int)$row['attempts'] >= 10) return false;
    $ok = hash_equals($row['code_hash'], hash('sha256', $mobile . '|' . $scene . '|' . $code));
    if ($ok) { $u = $pdo->prepare('UPDATE geo_phone_codes SET used_at=? WHERE id=?'); $u->execute([geo_now(), (int)$row['id']]); return true; }
    $u = $pdo->prepare('UPDATE geo_phone_codes SET attempts=attempts+1 WHERE id=?'); $u->execute([(int)$row['id']]); return false;
}

function geo_wechat_enabled(): bool { $c = geo_config(); return !empty($c['wechat_enabled']) && !empty($c['wechat_appid']) && !empty($c['wechat_appsecret']); }
function geo_wechat_oauth_url(string $state): string { $c = geo_config(); $redirect = urlencode($c['wechat_redirect_uri'] ?? 'https://geo.allgood.cn/wechat/callback/'); return 'https://open.weixin.qq.com/connect/qrconnect?appid=' . urlencode($c['wechat_appid']) . '&redirect_uri=' . $redirect . '&response_type=code&scope=snsapi_login&state=' . urlencode($state) . '#wechat_redirect'; }
function geo_wechat_access_token(): array {
    $c = geo_config();
    if (!geo_wechat_enabled()) return ['ok' => false, 'message' => '微信配置缺失'];
    $cache = geo_storage_path('wechat_access_token.json');
    if (is_file($cache)) {
        $data = json_decode((string)file_get_contents($cache), true);
        if (is_array($data) && !empty($data['access_token']) && (int)($data['expires_at'] ?? 0) > time() + 120) {
            return ['ok' => true, 'access_token' => $data['access_token']];
        }
    }
    $url = 'https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid=' . urlencode($c['wechat_appid']) . '&secret=' . urlencode($c['wechat_appsecret']);
    $json = json_decode((string)@file_get_contents($url), true);
    if (!is_array($json) || empty($json['access_token'])) return ['ok' => false, 'message' => $json['errmsg'] ?? '获取微信 access_token 失败'];
    @file_put_contents($cache, json_encode(['access_token' => $json['access_token'], 'expires_at' => time() + (int)($json['expires_in'] ?? 7200)], JSON_UNESCAPED_SLASHES), LOCK_EX);
    return ['ok' => true, 'access_token' => $json['access_token']];
}
function geo_wechat_scan_qr(): array {
    $c = geo_config();
    if (!empty($c['wechat_scan_qr_url'])) {
        $json = json_decode((string)@file_get_contents($c['wechat_scan_qr_url']), true);
        $data = is_array($json) ? ($json['data'] ?? []) : [];
        if (is_array($data) && !empty($data['ticket']) && !empty($data['image'])) {
            $data['ok'] = true;
            return $data;
        }
        return ['ok' => false, 'message' => is_array($json) ? ($json['msg'] ?? '获取微信二维码失败') : '获取微信二维码失败'];
    }
    $token = geo_wechat_access_token();
    if (empty($token['ok'])) return $token;
    $url = 'https://api.weixin.qq.com/cgi-bin/qrcode/create?access_token=' . urlencode($token['access_token']);
    $payload = json_encode(['expire_seconds' => 120, 'action_name' => 'QR_STR_SCENE', 'action_info' => ['scene' => ['scene_str' => 'scan_login']]], JSON_UNESCAPED_UNICODE);
    $ch = curl_init($url);
    curl_setopt_array($ch, [CURLOPT_RETURNTRANSFER => true, CURLOPT_POST => true, CURLOPT_HTTPHEADER => ['Content-Type: application/json'], CURLOPT_POSTFIELDS => $payload, CURLOPT_TIMEOUT => 10]);
    $body = curl_exec($ch); $errno = curl_errno($ch); curl_close($ch);
    $json = json_decode((string)$body, true);
    if ($errno || !is_array($json) || empty($json['ticket'])) return ['ok' => false, 'message' => $json['errmsg'] ?? '创建微信二维码失败'];
    $json['ok'] = true;
    $json['image'] = 'https://mp.weixin.qq.com/cgi-bin/showqrcode?ticket=' . urlencode($json['ticket']);
    return $json;
}
function geo_wechat_poll_openid(string $ticket): array {
    $c = geo_config();
    $base = $c['wechat_scan_status_url'] ?? 'https://a.iqianfeng.com/weixin/login/oaScanLogin';
    $url = $base . (str_contains($base, '?') ? '&' : '?') . 'ticket=' . urlencode($ticket);
    $ch = curl_init($url);
    curl_setopt_array($ch, [CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 8]);
    $body = curl_exec($ch); $errno = curl_errno($ch); curl_close($ch);
    if ($errno) return ['ok' => false, 'message' => '扫码状态查询失败'];
    $json = json_decode((string)$body, true);
    $data = is_array($json) ? ($json['data'] ?? []) : [];
    $openid = is_array($data) ? ($data['openid'] ?? '') : '';
    if (!$openid) return ['ok' => false, 'message' => '等待扫码确认'];
    return ['ok' => true, 'openid' => $openid, 'ticket' => $ticket];
}
function geo_create_user(PDO $pdo, string $username, string $password, string $mobile = '', ?string $email = null): array {
    $now = geo_now(); $token = geo_random_token(32); $hash = hash('sha256', $token); $email = $email ?: $username . '@geo.allgood.cn';
    $stmt = $pdo->prepare('INSERT INTO geo_cloud_users (username,email,password_hash,api_token_hash,api_token_last4,mobile,mobile_verified,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)');
    $mobileValue = trim($mobile) !== '' ? trim($mobile) : null;
    $stmt->execute([$username, $email, password_hash($password, PASSWORD_DEFAULT), $hash, substr($hash, -4), $mobileValue, $mobileValue ? 1 : 0, $now, $now]);
    $id = (int)$pdo->lastInsertId();
    return ['id' => $id, 'token' => $token];
}
