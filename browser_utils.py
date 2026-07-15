"""
自动检测并启动用户系统上已安装的浏览器（Chrome / Edge）
优先级: Chrome > Edge
包含反检测处理：抹除 webdriver 标志，绕过自动化检测
"""
import os
import subprocess
import sys
import time
from pathlib import Path
from browser_config import get_browser_candidates

def launch_debug_browser(platform_key: str, user_data_dir: str):
    """
    专门针对 ChatGPT 等高难度平台：
    1. 尝试杀掉现有的 Chrome 进程
    2. 以 --remote-debugging-port=9222 模式启动 Chrome
    """
    _, exe = find_browser()
    if "chrome" not in exe.lower():
        print("  ! 警告: 只有 Chrome 支持此调试模式启动")
        return False

    print(f"  正在尝试以调试模式启动 Chrome...")
    
    # 尝试杀掉现有进程（Windows）
    try:
        subprocess.run(["taskkill", "/F", "/IM", "chrome.exe", "/T"], capture_output=True)
        time.sleep(1)
    except: pass

    # 启动浏览器
    cmd = [
        exe,
        "--remote-debugging-port=9222",
        f"--user-data-dir={os.path.abspath(user_data_dir)}",
        "--no-first-run",
        "--no-default-browser-check"
    ]
    
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("  OK 已启动调试模式 Chrome，请在弹出的窗口中操作。")
        return True
    except Exception as e:
        print(f"  X 启动失败: {e}")
        return False

# 注入到每个页面，抹除自动化特征（纯 JS，不依赖 Chrome flag）
_STEALTH_SCRIPT = """
// 1. 核心工具：模拟原生函数
const patchProperty = (obj, prop, value) => {
    if (!obj) return;
    try {
        const getter = () => value;
        Object.defineProperty(getter, 'name', { value: `get ${prop}`, configurable: true });
        Object.defineProperty(getter, 'toString', { 
            value: () => `function get ${prop}() { [native code] }`, 
            configurable: true 
        });
        Object.defineProperty(obj, prop, {
            get: getter,
            set: () => {},
            configurable: true,
            enumerable: true
        });
    } catch (e) {}
};

// 2. 抹除 webdriver (Prototype 级别和实例级别)
try {
    delete Navigator.prototype.webdriver;
    delete navigator.webdriver;
} catch (e) {}
patchProperty(Navigator.prototype, 'webdriver', false);
patchProperty(window, 'webdriver', undefined); // 掩盖某些旧式全局变量检测

// 3. 伪造插件列表和 MimeTypes (深度模拟原生结构)
const mockPluginsAndMimeTypes = () => {
    const pluginData = [
        { name: 'PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format', mimetypes: [{ type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format' }] },
        { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer', description: 'Google Chrome PDF Viewer', mimetypes: [{ type: 'application/pdf', suffixes: 'pdf', description: 'Google Chrome PDF Viewer' }] },
        { name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer', description: 'Chromium PDF Viewer', mimetypes: [{ type: 'application/pdf', suffixes: 'pdf', description: 'Chromium PDF Viewer' }] }
    ];

    const pluginList = [];
    const mimeTypeList = [];

    pluginData.forEach(data => {
        const plugin = Object.create(Plugin.prototype);
        const mimes = data.mimetypes.map(m => {
            const mime = Object.create(MimeType.prototype);
            patchProperty(mime, 'type', m.type);
            patchProperty(mime, 'suffixes', m.suffixes);
            patchProperty(mime, 'description', m.description);
            patchProperty(mime, 'enabledPlugin', plugin);
            return mime;
        });

        patchProperty(plugin, 'name', data.name);
        patchProperty(plugin, 'filename', data.filename);
        patchProperty(plugin, 'description', data.description);
        patchProperty(plugin, 'length', mimes.length);
        plugin.item = (i) => mimes[i];
        plugin.namedItem = (name) => mimes.find(m => m.type === name);

        pluginList.push(plugin);
        mimeTypeList.push(...mimes);
    });

    const pluginArray = Object.create(PluginArray.prototype);
    patchProperty(pluginArray, 'length', pluginList.length);
    pluginArray.item = (i) => pluginList[i];
    pluginArray.namedItem = (name) => pluginList.find(p => p.name === name);
    pluginArray.refresh = () => {};

    const mimeTypeArray = Object.create(MimeTypeArray.prototype);
    patchProperty(mimeTypeArray, 'length', mimeTypeList.length);
    mimeTypeArray.item = (i) => mimeTypeList[i];
    mimeTypeArray.namedItem = (name) => mimeTypeList.find(m => m.type === name);

    patchProperty(Navigator.prototype, 'plugins', pluginArray);
    patchProperty(Navigator.prototype, 'mimeTypes', mimeTypeArray);
};
mockPluginsAndMimeTypes();

// 4. 抹除 cdc_ 相关的特征 (Chromium 内部生成的变量名)
const cleanCDC = () => {
    const targets = [
        window, document, navigator, 
        Element.prototype, Document.prototype, 
        Node.prototype, Object.prototype
    ];
    targets.forEach(t => {
        if (!t) return;
        try {
            for (let prop in t) {
                if (prop && (prop.startsWith('cdc_') || prop.startsWith('__$cdc_'))) {
                    delete t[prop];
                }
            }
        } catch (e) {}
    });
};
cleanCDC();
setInterval(cleanCDC, 50); // 极高频率清理

// 5. 深度伪造 chrome 对象
window.chrome = {
    app: {
        isInstalled: false,
        InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
        RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' },
        getDetails: function() {},
        getIsInstalled: function() {},
        install: function() {}
    },
    runtime: {
        OnInstalledReason: { CHROME_UPDATE: 'chrome_update', INSTALL: 'install', SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update' },
        OnRestartRequiredReason: { APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' },
        PlatformArch: { ARM: 'arm', ARM64: 'arm64', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
        PlatformNaclArch: { ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
        PlatformOs: { ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win' },
        RequestUpdateCheckStatus: { NO_UPDATE: 'no_update', THROTTLED: 'throttled', UPDATE_AVAILABLE: 'update_available' },
        id: "abcdefghijklmnoabcdefghijklmno",
        sendMessage: function() {},
        connect: function() {}
    },
    csi: function() {},
    loadTimes: function() {}
};

// 6. 修复 permissions.query
if (window.navigator.permissions) {
    const origQuery = window.navigator.permissions.query.bind(navigator.permissions);
    window.navigator.permissions.query = (params) =>
        params.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : origQuery(params);
}

// 7. 伪造 UserAgentData
if (Navigator.prototype.userAgentData) {
    const brands = [
        { brand: 'Not(A:Brand', version: '99' },
        { brand: 'Google Chrome', version: '131' },
        { brand: 'Chromium', version: '131' }
    ];
    patchProperty(Navigator.prototype.userAgentData, 'brands', brands);
    patchProperty(Navigator.prototype.userAgentData, 'mobile', false);
    patchProperty(Navigator.prototype.userAgentData, 'platform', 'Windows');
}

// 8. 伪造其他基础属性
patchProperty(Navigator.prototype, 'vendor', 'Google Inc.');
patchProperty(Navigator.prototype, 'productSub', '20030107');
patchProperty(Navigator.prototype, 'hardwareConcurrency', 8);
patchProperty(Navigator.prototype, 'deviceMemory', 8);
patchProperty(Navigator.prototype, 'languages', ['zh-CN', 'zh', 'en-US', 'en']);
patchProperty(Navigator.prototype, 'platform', 'Win32');
patchProperty(Navigator.prototype, 'maxTouchPoints', 0);

// 7. 修复权限和通知
if (window.Notification) {
    patchProperty(Notification, 'permission', 'default');
}

// 8. 修复 window 尺寸和 Connection
if (navigator.connection) {
    patchProperty(navigator.connection, 'rtt', 50);
    patchProperty(navigator.connection, 'downlink', 10);
    patchProperty(navigator.connection, 'effectiveType', '4g');
    patchProperty(navigator.connection, 'saveData', false);
}

// 10. 伪造 Media Codecs (绕过部分音视频环境检测)
try {
    const video = document.createElement('video');
    const origCanPlayType = video.canPlayType.bind(video);
    patchProperty(HTMLVideoElement.prototype, 'canPlayType', (type) => {
        if (type === 'video/mp4; codecs="avc1.42E01E"') return 'probably';
        if (type === 'video/webm; codecs="vp8, vorbis"') return 'probably';
        return origCanPlayType(type);
    });
} catch (e) {}

// 11. 修复 window.name 和检测痕迹
if (window.name && (window.name.includes('playwright') || window.name.includes('pw_'))) {
    window.name = '';
}

// 12. 修复 window.outerWidth/outerHeight
const fixWindowDimensions = () => {
    if (window.outerWidth === 0 || window.outerWidth === window.innerWidth) {
        patchProperty(window, 'outerWidth', window.innerWidth);
    }
    if (window.outerHeight === 0 || window.outerHeight === window.innerHeight) {
        patchProperty(window, 'outerHeight', window.innerHeight + 85);
    }
};
fixWindowDimensions();
window.addEventListener('resize', fixWindowDimensions);

// 13. 模拟 WebGL 信息
try {
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        if (parameter === 37445) return 'Google Inc. (Intel)';
        if (parameter === 37446) return 'ANGLE (Intel, Intel(R) UHD Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)';
        // 伪造更多参数
        if (parameter === 3379) return 16384; // MAX_TEXTURE_SIZE
        if (parameter === 36349) return 1024; // MAX_VERTEX_UNIFORM_VECTORS
        return getParameter.call(this, parameter);
    };
} catch (e) {}

console.log('[Stealth] Ultra Prototype Stealth loaded');
"""

_LAUNCH_ARGS = [
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-infobars",
    "--window-size=1280,900",
    #"--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process",
    "--start-maximized",
    "--disable-dev-shm-usage",
    "--use-gl=angle",
]

if os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() == 0:
    _LAUNCH_ARGS.append("--no-sandbox")

# 模拟真实的 User-Agent
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"

# 排除 Playwright 默认加的会触发警告的参数
_IGNORE_DEFAULT_ARGS = [
    "--enable-automation",
]


def _bundled_browser_candidates() -> list[str]:
    roots = []
    configured_root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if configured_root:
        roots.append(Path(configured_root))
    if getattr(sys, "frozen", False):
        roots.append(Path(sys.executable).resolve().parent / "ms-playwright")

    patterns = (
        "chromium-*/chrome-win*/chrome.exe",
        "chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium",
        "chromium-*/chrome-mac*/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
        "chromium-*/chrome-linux*/chrome",
    )
    candidates = []
    seen = set()
    for root in roots:
        if not root.is_dir():
            continue
        for pattern in patterns:
            for path in sorted(root.glob(pattern), reverse=True):
                value = str(path)
                if path.is_file() and value not in seen:
                    seen.add(value)
                    candidates.append(value)
    return candidates


def find_browser() -> tuple[str, str]:
    """返回 (browser_type, executable_path)，browser_type: 'chrome' | 'msedge'"""
    for path in [*get_browser_candidates(), *_bundled_browser_candidates()]:
        if os.path.exists(path):
            btype = "msedge" if "edge" in path.lower() else "chrome"
            return btype, path
    raise RuntimeError(
        "未找到可用浏览器。请安装 Chrome/Edge，或重新安装包含 Chromium 的 GEO-SOP 完整版"
    )


def launch_browser(playwright, headless=False, user_data_dir=None, max_retries=2):
    """
    优先尝试连接已经手动打开的远程调试浏览器 (port 9222)。
    如果连接失败，再按照原有逻辑启动新浏览器。
    
    Args:
        playwright: Playwright实例
        headless: 是否无头模式
        user_data_dir: 用户数据目录路径
        max_retries: 最大重试次数
    
    Returns:
        (context, browser) 元组
    """
    btype, exe = find_browser()
    
    # 尝试连接现有浏览器 (Remote Debugging)
    try:
        print("  尝试连接已打开的远程调试浏览器 (port 9222)...")
        browser = playwright.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        print("  OK 已成功连接到现有浏览器实例")
        return context, browser
    except Exception:
        print("  未检测到已打开的远程调试浏览器，将尝试启动新实例")

    # --- 以下为原有的启动逻辑 ---
    print(f"  使用浏览器: {btype}  路径: {exe}")
    
    for attempt in range(max_retries + 1):
        try:
            if user_data_dir:
                os.makedirs(user_data_dir, exist_ok=True)
                context = playwright.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    executable_path=exe,
                    headless=headless,
                    args=_LAUNCH_ARGS,
                    user_agent=_USER_AGENT, # 显式指定 User-Agent
                    viewport={"width": 1280, "height": 900},
                    locale="zh-CN",
                    timezone_id="Asia/Shanghai",
                    ignore_default_args=_IGNORE_DEFAULT_ARGS,
                    timeout=60000,  # 增加超时时间
                )
                # 在所有页面加载前注入脚本
                context.add_init_script(_STEALTH_SCRIPT)
                return context, None
            else:
                browser = playwright.chromium.launch(
                    executable_path=exe,
                    headless=headless,
                    args=_LAUNCH_ARGS,
                    ignore_default_args=_IGNORE_DEFAULT_ARGS,
                    timeout=60000,  # 增加超时时间
                )
                context = browser.new_context(
                    user_agent=_USER_AGENT, # 显式指定 User-Agent
                    viewport={"width": 1280, "height": 900},
                    locale="zh-CN",
                    timezone_id="Asia/Shanghai",
                )
                # 在所有页面加载前注入脚本
                context.add_init_script(_STEALTH_SCRIPT)
                return context, browser
                
        except Exception as e:
            if attempt < max_retries:
                print(f"  浏览器启动失败 (尝试 {attempt + 1}/{max_retries + 1}): {e}")
                print("  等待2秒后重试...")
                time.sleep(2)
            else:
                print(f"  浏览器启动失败 (已达最大重试次数 {max_retries + 1}): {e}")
                raise
