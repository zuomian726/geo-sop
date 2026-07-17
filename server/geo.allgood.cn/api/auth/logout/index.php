<?php
declare(strict_types=1);

require dirname(__DIR__, 2) . '/common.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    geo_json(['success' => false, 'message' => 'Method not allowed'], 405);
}

$pdo = geo_pdo();
geo_ensure_schema($pdo);
geo_bootstrap($pdo);
$token = geo_token();
if ($token === '') {
    geo_json(['success' => false, 'message' => 'unauthorized'], 401);
}

$hash = hash('sha256', $token);
$stmt = $pdo->prepare('UPDATE geo_cloud_tokens SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL');
$stmt->execute([geo_now(), $hash]);

geo_json([
    'success' => true,
    'revoked' => $stmt->rowCount() > 0,
]);
