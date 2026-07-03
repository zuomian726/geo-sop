# macOS 单机开发版

## 启动

```bash
cd /path/to/geo-sop
chmod +x run_macos_desktop.sh
./run_macos_desktop.sh
```

首次启动会创建 `.venv-desktop` 并安装依赖。

## 本地数据目录

单机版不会写入服务器数据库，数据保存在：

```text
~/Library/Application Support/GEO-SOP/
```

主要目录：

```text
instance/ai_monitor.db      本地 SQLite 数据库
browser_profile/            AI 平台 Cookie 和登录态
answers/                    采集结果和截图
```

## 登录体验

单机版会自动使用本地用户进入后台，不需要注册系统账号。点击平台的「去登录」后，会直接打开本机浏览器窗口完成扫码、验证码和登录。
