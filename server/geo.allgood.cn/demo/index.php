<?php
declare(strict_types=1);
?><!doctype html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>GEO-SOP 在线 Demo</title>
    <style>
        :root{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;color:#182235;background:#f4f7fb}
        *{box-sizing:border-box}body{margin:0}.shell{max-width:1120px;margin:0 auto;padding:28px 24px 56px}
        .nav{display:flex;align-items:center;justify-content:space-between;margin-bottom:72px}.brand{font-size:20px;font-weight:800;letter-spacing:.02em;color:#182235;text-decoration:none}.nav a{color:#5b6b82;text-decoration:none;font-size:14px}
        .hero{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(320px,.8fr);gap:56px;align-items:center}.kicker{color:#00a5b5;font-size:12px;font-weight:900;letter-spacing:.18em;text-transform:uppercase}.hero h1{font-size:clamp(38px,5vw,68px);line-height:1.08;letter-spacing:0;margin:14px 0 20px}.hero p{font-size:17px;line-height:1.8;color:#65758d;max-width:650px}.actions{display:flex;gap:12px;flex-wrap:wrap;margin-top:28px}.button{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:0 20px;border-radius:6px;text-decoration:none;font-weight:800;font-size:14px}.primary{background:#1769ff;color:#fff}.secondary{border:1px solid #cad5e5;background:#fff;color:#25344b}
        .demo-card{background:#0c1424;color:#fff;border-radius:10px;padding:28px;box-shadow:0 22px 60px rgba(24,42,70,.18)}.demo-card h2{margin:8px 0 10px;font-size:25px}.demo-card p{color:#aebbd0;font-size:14px;line-height:1.7}.credentials{margin:22px 0;padding:16px;border:1px solid #26364f;border-radius:7px;background:#121e33}.credentials div{display:flex;justify-content:space-between;gap:18px;padding:7px 0;color:#aebbd0;font-size:14px}.credentials strong{color:#fff;font-weight:700}.notice{font-size:12px!important;color:#93a6c2!important;margin-bottom:0}
        .product-preview{margin-top:88px}.section-heading{display:flex;justify-content:space-between;gap:30px;align-items:end;margin-bottom:22px}.section-heading h2{font-size:32px;line-height:1.2;margin:8px 0 0}.section-heading p{max-width:520px;margin:0;color:#718099;line-height:1.7}.preview-grid{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(300px,.75fr);gap:16px;align-items:start}.preview{margin:0;background:#fff;border:1px solid #e0e7f1;border-radius:8px;overflow:hidden;box-shadow:0 16px 42px rgba(29,49,78,.08)}.preview img{display:block;width:100%;height:auto}.preview figcaption{padding:16px 18px;color:#5f7089;font-size:13px;border-top:1px solid #e8edf4}.features{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:22px}.feature{background:#fff;border:1px solid #e0e7f1;border-radius:8px;padding:22px}.feature strong{display:block;font-size:16px;margin-bottom:8px}.feature span{color:#718099;font-size:13px;line-height:1.7}
        @media(max-width:800px){.nav{margin-bottom:42px}.hero,.preview-grid{grid-template-columns:1fr;gap:30px}.section-heading{display:block}.section-heading p{margin-top:12px}.features{grid-template-columns:1fr}.hero h1{font-size:42px}.product-preview{margin-top:56px}}
    </style>
</head>
<body>
<main class="shell">
    <nav class="nav"><a class="brand" href="/">GEO-SOP</a><a href="/tools/">下载桌面版</a></nav>
    <section class="hero">
        <div>
            <div class="kicker">Online Demo</div>
            <h1>先看见 AI 如何描述你的品牌。</h1>
            <p>进入只读安全环境，浏览 GEO-SOP 的数据看板、品牌曝光、引用来源、GEO 稿件分析和下一步动作建议。Demo 使用合成样例数据，不会修改线上业务数据。</p>
            <div class="actions"><a class="button primary" href="/login/?demo=1">进入在线 Demo</a><a class="button secondary" href="/tools/">了解桌面版</a></div>
        </div>
        <aside class="demo-card">
            <div class="kicker">Read-only Workspace</div>
            <h2>在线 Demo 账号</h2>
            <p>登录后可以浏览和导出样例数据。创建、删除、平台登录和采集操作均被禁用。</p>
            <div class="credentials"><div><span>用户名</span><strong>tuke</strong></div><div><span>密码</span><strong>123456</strong></div></div>
            <p class="notice">提示：Demo 数据为演示数据，不代表真实客户或线上业务结果。</p>
        </aside>
    </section>
    <section class="product-preview">
        <div class="section-heading"><div><div class="kicker">Product Preview</div><h2>从检测结果，到可执行动作。</h2></div><p>登录后进入与云端正式版相同的看板结构。示例账号只读，数据全部为合成内容。</p></div>
        <div class="preview-grid">
            <figure class="preview"><img src="/demo/assets/geo-dashboard-demo.svg" width="1200" height="700" alt="GEO-SOP 品牌曝光与引用来源数据看板"><figcaption>核心指标、平台对比、趋势和优先动作集中在一个工作台。</figcaption></figure>
            <figure class="preview"><img src="/demo/assets/geo-answer-demo.svg" width="1200" height="700" alt="GEO-SOP AI 回答与引用证据"><figcaption>保留回答、引用来源、品牌命中和截图证据。</figcaption></figure>
        </div>
    </section>
    <section class="features"><div class="feature"><strong>品牌曝光</strong><span>查看品牌在不同 AI 平台回答中的出现情况和变化。</span></div><div class="feature"><strong>引用来源</strong><span>按域名和文章查看 AI 回答引用了哪些公开来源。</span></div><div class="feature"><strong>下一步动作</strong><span>用清晰的指标和建议理解下一轮 GEO 优化方向。</span></div></section>
</main>
</body>
</html>
