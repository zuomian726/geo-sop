import os
import json

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "browser_config.json")

_DEFAULT_CANDIDATES = [
    # Linux
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/snap/bin/chromium",
    # macOS
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    # Windows
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\\Google\\Chrome\\Application\\chrome.exe"),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\\Microsoft\\Edge\\Application\\msedge.exe"),
]

def load_browser_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"加载浏览器配置失败: {e}")
    return {"browser_path": "", "candidates": _DEFAULT_CANDIDATES}

def save_browser_config(browser_path):
    config = load_browser_config()
    config["browser_path"] = browser_path
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    return True

def get_browser_candidates():
    config = load_browser_config()
    candidates = []
    if config.get("browser_path"):
        candidates.append(config["browser_path"])
    candidates.extend(config.get("candidates", []))
    candidates.extend(_DEFAULT_CANDIDATES)

    seen = set()
    unique_candidates = []
    for path in candidates:
        if path and path not in seen:
            seen.add(path)
            unique_candidates.append(path)
    return unique_candidates
