import os
from local_paths import answers_dir, browser_profile_dir

# 浏览器自动化配置

# 是否显示浏览器窗口（False=无头模式，True=可见窗口，调试时建议True）
HEADLESS = False

# 每个平台等待AI回答完成的最长时间（秒）
ANSWER_TIMEOUT = 120

# 输出目录
OUTPUT_DIR = os.environ.get("GEO_ANSWERS_DIR") or (answers_dir() if os.environ.get("GEO_DESKTOP_MODE") == "1" else "answers")

# 浏览器用户数据目录（持久化登录状态，无需反复登录）
# 每个平台独立一个 profile，路径: browser_profile/<platform>/
PROFILE_DIR = os.environ.get("GEO_PROFILE_DIR") or (browser_profile_dir() if os.environ.get("GEO_DESKTOP_MODE") == "1" else "browser_profile")
