"""
AI 多平台问答浏览器采集工具
用法:
  python main.py                          # 采集全部平台
  python main.py --platforms deepseek kimi
  python main.py --login doubao           # 手动登录并保存登录状态
  python main.py --debug                  # 显示浏览器窗口（调试）
"""
import argparse
import sys
import time
import importlib
from playwright.sync_api import sync_playwright, Page
from utils import load_questions, save_answer, print_result
from browser_utils import launch_browser, launch_debug_browser
import config

# 配置项
PROFILE_DIR = "browser_profile"

PLATFORMS = {
    "doubao":   ("platforms.doubao",   "豆包",     "https://www.doubao.com/chat/"),
    "deepseek": ("platforms.deepseek", "DeepSeek", "https://chat.deepseek.com/"),
    "kimi":     ("platforms.kimi",     "Kimi",     "https://www.kimi.com/"),
    "yuanbao":  ("platforms.yuanbao",  "元宝",     "https://yuanbao.tencent.com/chat"),
    "wenxin":   ("platforms.wenxin",   "百度文心", "https://wenxin.baidu.com/"),
    "baidu":    ("platforms.baidu",    "百度AI助手", "https://chat.baidu.com/"),
    "qianwen":  ("platforms.qianwen",  "千问",     "https://www.qianwen.com/"),
    "chatgpt":  ("platforms.chatgpt",  "ChatGPT",  "https://chatgpt.com/"),
}

# 各平台判断"已登录"的特征：页面上存在该文字或元素则视为已登录
_LOGIN_CHECKS = {
    "doubao":   {"url_not": "login", "text": None},
    "deepseek": {"url_not": "login", "text": None},
    "kimi":     {"url_not": "login", "text": None},
    "yuanbao":  {"url_not": "login", "text": None},
    "wenxin":   {"url_not": "login", "text": None},
    "baidu":    {"url_not": "login", "text": None},
    "qianwen":  {"url_not": "login", "text": None},
    "chatgpt":  {"url_not": "login", "text": None},
}


def _is_logged_in(page: Page, platform_key: str, url: str) -> bool:
    """
    检测当前页面是否已登录，每个平台有专属检测逻辑。
    """
    current_url = page.url.lower()

    # URL 包含登录关键词，肯定未登录
    login_keywords = ["login", "signin", "sign-in", "passport", "auth", "register"]
    if any(kw in current_url for kw in login_keywords):
        return False

    try:
        if platform_key == "doubao":
            # 豆包：已登录时左侧有用户头像或历史对话列表
            return page.locator("[class*='avatar'], [class*='history'], [class*='sidebar']").first.is_visible(timeout=3000)

        elif platform_key == "deepseek":
            # DeepSeek：已登录时有输入框（placeholder 含"DeepSeek"）或历史对话列表
            for sel in [
                "textarea[placeholder*='DeepSeek']",
                "textarea[placeholder*='发送消息']",
                "[class*='_546d736']",   # 历史对话链接
                "textarea",              # 兜底：有输入框即视为已登录
            ]:
                try:
                    if page.locator(sel).first.is_visible(timeout=2000):
                        return True
                except Exception:
                    pass
            return False

        elif platform_key == "kimi":
            # Kimi：检测是否在对话页面（不是登录弹窗）
            # 登录弹窗特征：页面上有"发送验证码"或"手机号"文字
            try:
                body_text = page.locator("body").inner_text(timeout=3000)
                if "发送验证码" in body_text or "手机号快捷登录" in body_text:
                    return False
            except Exception:
                pass
            # 已登录特征：URL 包含 chat 或页面有对话历史
            if "/chat" in page.url:
                return True
            for sel in ["[class*='history']", "[class*='session-list']",
                        "[class*='chat-list']", "[class*='sidebar']"]:
                try:
                    if page.locator(sel).first.is_visible(timeout=1500):
                        return True
                except Exception:
                    pass
            return False

        elif platform_key == "yuanbao":
            # 元宝：已登录时有用户头像或对话历史
            for sel in ["text=登录", "text=注册", "button:has-text('登录')"]:
                try:
                    if page.locator(sel).first.is_visible(timeout=1000):
                        return False
                except Exception:
                    pass
            return page.locator("[class*='avatar'], [class*='history']").first.is_visible(timeout=2000)

        elif platform_key == "wenxin":
            # 文心：已登录时有用户信息或输入框
            # 先检查是否有未登录标识
            for sel in ["text=登录", "button:has-text('登录')", "text=立即登录"]:
                try:
                    if page.locator(sel).first.is_visible(timeout=1000):
                        return False
                except Exception:
                    pass
            # 检查是否有输入框（登录后可以直接看到输入框）
            for sel in ["textarea", "div[contenteditable='true']", "[class*='input']"]:
                try:
                    if page.locator(sel).first.is_visible(timeout=2000):
                        return True
                except Exception:
                    pass
            # 检查用户信息
            return page.locator("[class*='avatar'], [class*='user'], [class*='profile']").first.is_visible(timeout=2000)

        elif platform_key == "qianwen":
            # 千问：已登录时有用户信息或对话历史
            for sel in ["text=登录", "text=注册", "button:has-text('登录')"]:
                try:
                    if page.locator(sel).first.is_visible(timeout=1000):
                        return False
                except Exception:
                    pass
            # 检查用户信息或历史对话
            for sel in ["[class*='avatar'], [class*='user'], [class*='history'], [class*='sidebar']"]:
                try:
                    if page.locator(sel).first.is_visible(timeout=2000):
                        return True
                except Exception:
                    pass
            return False

        elif platform_key == "baidu":
            # 百度AI助手：已登录时有输入框或用户信息
            for sel in ["text=登录", "button:has-text('登录')", "text=立即登录"]:
                try:
                    if page.locator(sel).first.is_visible(timeout=1000):
                        return False
                except Exception:
                    pass
            # 检查是否有输入框（登录后可以直接看到输入框）
            for sel in ["textarea", "div[contenteditable='true']", "[class*='input']"]:
                try:
                    if page.locator(sel).first.is_visible(timeout=2000):
                        return True
                except Exception:
                    pass
            # 检查用户信息
            return page.locator("[class*='avatar'], [class*='user'], [class*='profile']").first.is_visible(timeout=2000)

        elif platform_key == "chatgpt":
            # ChatGPT 登录检测优化：避免仅靠 URL 判定导致的误报 (False Positive)
            # 1. 检查是否存在未登录标识（显式的登录按钮）
            login_buttons = [
                "button[data-testid='login-button']",
                "a[href*='/auth/login']",
                "button:has-text('Log in')", 
                "a:has-text('Log in')", 
                "button:has-text('登录')", 
                "a:has-text('登录')"
            ]
            for sel in login_buttons:
                try:
                    loc = page.locator(sel).first
                    if loc.is_visible(timeout=1500):
                        return False
                except Exception:
                    pass

            # 2. 检查已登录特征（必须是登录后才有的元素，排除游客模式也存在的输入框）
            logged_in_features = [
                "[data-testid='profile-button']",   # 用户头像按钮
                "nav[aria-label='Chat history']",  # 侧边栏历史记录
                "button[aria-label*='User menu']",  # 用户菜单
                "div.markdown",                    # 已有的对话内容
                "a[href='/gpts']",                 # GPTs 商店入口（登录后可见）
            ]
            
            for sel in logged_in_features:
                try:
                    if page.locator(sel).first.is_visible(timeout=2000):
                        return True
                except Exception:
                    pass
            
            # 3. URL 辅助判定（仅作为参考，不再仅靠 textarea 判定）
            curr_url = page.url.lower()
            if "/chat" in curr_url and "auth" not in curr_url:
                # 即使 URL 匹配，也需要至少一个登录特征（由上面的循环处理）
                # 这里返回 False 是为了防止在没有特征的情况下误判
                return False
            
            return False

        else:
            # 通用逻辑：没有登录按钮 + 有输入框
            for text in ["登录", "立即登录", "注册", "sign in", "log in"]:
                try:
                    if page.locator(f"button:has-text('{text}'), a:has-text('{text}')").first.is_visible(timeout=800):
                        return False
                except Exception:
                    pass
            for sel in ["textarea", "div[contenteditable='true']"]:
                try:
                    if page.locator(sel).first.is_visible(timeout=2000):
                        return True
                except Exception:
                    pass
            return False

    except Exception:
        return False


def _wait_for_login(page: Page, platform_key: str, name: str, url: str,
                    timeout: int = 180) -> bool:
    """
    等待用户完成登录，最长等待 timeout 秒。
    每 3 秒检测一次登录状态，登录成功后立即返回。
    """
    print(f"  ! {name} 未登录，请在浏览器中完成登录...")
    if platform_key == "chatgpt":
        print("  （请在弹出的真实浏览器窗口中操作，登录成功后程序会自动识别）")
    else:
        print(f"  （最长等待 {timeout} 秒，登录成功后自动继续）")

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(3)
        try:
            if _is_logged_in(page, platform_key, url):
                print(f"  OK {name} 登录成功，继续采集         ") # 加空格覆盖剩余秒数
                time.sleep(2)  # 等页面稳定
                return True
        except Exception as e:
            # 捕获浏览器关闭错误
            err_msg = str(e).lower()
            if "closed" in err_msg or "target" in err_msg:
                print(f"\n  ! 浏览器已关闭，等待终止")
                return False
            pass
        remaining = int(deadline - time.time())
        print(f"  等待登录... 剩余 {remaining}s   ", end="\r", flush=True)

    print(f"\n  X {name} 登录超时，跳过该平台")
    return False


def do_login(platform_key: str):
    """打开浏览器让用户手动登录，登录状态自动保存"""
    _, name, url = PLATFORMS[platform_key]
    user_data_dir = f"{PROFILE_DIR}/{platform_key}"
    print(f"正在打开浏览器访问 {name}，请完成登录...")
    
    with sync_playwright() as p:
        # ChatGPT 专门处理：使用调试端口模式以绕过谷歌登录拦截
        if platform_key == "chatgpt":
            print("  [提示] ChatGPT 建议使用调试模式以绕过 Google 登录拦截...")
            if launch_debug_browser(platform_key, user_data_dir):
                time.sleep(2) # 等待浏览器启动
        
        context, browser = launch_browser(p, headless=False, user_data_dir=user_data_dir)
        page = context.pages[0] if context.pages else context.new_page()
        
        # 增加超时时间到 60 秒，并捕获可能的超时错误
        print(f"  正在访问 {url}...")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"  ! 页面加载较慢或超时: {e}")
            print("  尝试继续检测登录状态...")

        # 自动检测登录状态，登录成功后提示
        print("  正在检测登录状态，登录完成后会自动提示...")
        logged_in = _wait_for_login(page, platform_key, name, url, timeout=300)
        if logged_in:
            print(f"OK {name} 登录状态已保存")
        else:
            try:
                input("  未检测到登录，如已登录请按 Enter 手动确认保存...")
            except EOFError:
                pass

        try:
            # 如果是连接的现有浏览器，browser 为 None
            if browser:
                browser.close()
            else:
                # 调试模式下我们只关闭 context
                context.close()
        except Exception:
            pass


def run_platform(platform_key: str, questions: list, headless: bool, brand_keywords: list = None):
    module_path, name, url = PLATFORMS[platform_key]
    mod = importlib.import_module(module_path)
    user_data_dir = f"{PROFILE_DIR}/{platform_key}"

    print(f"\n{'─'*50}")
    print(f"平台: {name}  共 {len(questions)} 个问题")
    if brand_keywords:
        print(f"品牌关键词: {brand_keywords}")

    with sync_playwright() as p:
        context, browser = launch_browser(p, headless=headless, user_data_dir=user_data_dir)
        page = context.pages[0] if context.pages else context.new_page()

        # ── 登录状态检测 ──────────────────────────────────
        print(f"  正在打开 {name}...")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)  # 60秒超时
        try:
            page.wait_for_selector(
                "textarea, div[contenteditable='true']",
                timeout=15000, state="visible"
            )
        except Exception:
            pass
        time.sleep(2)

        if not _is_logged_in(page, platform_key, url):
            # 未登录：等待用户登录（最长 5 分钟）
            logged_in = _wait_for_login(page, platform_key, name, url, timeout=300)
            if not logged_in:
                try:
                    if browser:
                        browser.close()
                    else:
                        context.close()
                except Exception:
                    pass
                return
        else:
            print(f"  OK {name} 已登录")

        # ── 逐题采集 ──────────────────────────────────────
        for i, question in enumerate(questions, 1):
            print(f"\n  [{i}/{len(questions)}] {question}")
            try:
                # CLI 模式默认开启截图，或者可以根据需要扩展参数
                answer, references = mod.query(
                    page, 
                    question, 
                    brand_keywords=brand_keywords,
                    enable_screenshot=True 
                )
                if not answer:
                    print("  ! 未获取到答案")
                    continue
                filepath = save_answer(question, platform_key, answer, references, config.OUTPUT_DIR)
                print(f"  OK 已保存 -> {filepath}")
                print_result(name, question, answer, references)
            except Exception as e:
                print(f"  X 失败: {e}")
            
            # 问题之间间隔 20 秒（最后一个问题不需要等待）
            if i < len(questions):
                print(f"  等待 20 秒后继续下一个问题...", end="", flush=True)
                for remaining in range(20, 0, -1):
                    time.sleep(1)
                    print(f"\r  等待 {remaining} 秒后继续下一个问题...", end="", flush=True)
                print()  # 换行

        if browser:
            browser.close()
        else:
            context.close()


def main():
    valid_platforms = list(PLATFORMS.keys())

    def platform_type(value: str) -> str:
        """将平台名转小写，并验证是否合法（大小写不敏感）"""
        lower = value.lower()
        if lower not in valid_platforms:
            raise argparse.ArgumentTypeError(
                f"无效平台 '{value}'，可选: {', '.join(valid_platforms)}"
            )
        return lower

    parser = argparse.ArgumentParser(description="AI 多平台问答浏览器采集工具")
    parser.add_argument("--platforms", nargs="+", type=platform_type,
                        default=valid_platforms, help="指定平台（默认全部，大小写不敏感）")
    parser.add_argument("--questions", default="question.txt", help="问题文件")
    parser.add_argument("--keywords", nargs="+", help="品牌关键词（用于在截图中标记）")
    parser.add_argument("--login", metavar="PLATFORM", type=platform_type,
                        help="手动登录指定平台并保存登录状态")
    parser.add_argument("--debug", action="store_true", help="显示浏览器窗口")
    args = parser.parse_args()

    if args.login:
        do_login(args.login)
        return

    questions = load_questions(args.questions)
    if not questions:
        print("question.txt 中没有找到问题。")
        sys.exit(1)
# 运行
    headless = config.HEADLESS and not args.debug

    for platform_key in args.platforms:
        run_platform(platform_key, questions, headless, brand_keywords=args.keywords)

    print(f"\n全部完成！答案保存在 '{config.OUTPUT_DIR}/' 目录下。")


if __name__ == "__main__":
    main()
