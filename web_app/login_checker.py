"""
AI平台登录状态检测模块
复用 main.py 中的登录检测逻辑，供 web_app 调用
"""
import sys
import os
import time
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('login_checker')

# 添加父目录到 Python 路径，以便导入 main.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.sync_api import sync_playwright, Page
from browser_utils import launch_browser
from profile_utils import get_profile_dir

PLATFORMS = {
    "doubao":   ("platforms.doubao",   "豆包",     "https://www.doubao.com/chat/"),
    "deepseek": ("platforms.deepseek", "DeepSeek", "https://chat.deepseek.com/"),
    "kimi":     ("platforms.kimi",     "Kimi",     "https://www.kimi.com/"),
    "yuanbao":  ("platforms.yuanbao",  "元宝",     "https://yuanbao.tencent.com/chat"),
    "wenxin":   ("platforms.wenxin",   "百度文心", "https://wenxin.baidu.com/"),
    "qianwen":  ("platforms.qianwen",  "千问",     "https://www.qianwen.com/"),
    "chatgpt":  ("platforms.chatgpt",  "ChatGPT",  "https://chatgpt.com/"),
    "yiyan":    ("platforms.yiyan",    "文心一言(yiyan)", "https://yiyan.baidu.com/"),
}


def _is_logged_in(page: Page, platform_key: str, url: str) -> bool:
    """
    检测当前页面是否已登录（从 main.py 复制）
    """
    current_url = page.url.lower()

    # URL 包含登录关键词，肯定未登录
    login_keywords = ["login", "signin", "sign-in", "passport", "auth", "register"]
    if any(kw in current_url for kw in login_keywords):
        return False

    try:
        if platform_key == "doubao":
            return page.locator("[class*='avatar'], [class*='history'], [class*='sidebar']").first.is_visible(timeout=3000)

        elif platform_key == "deepseek":
            for sel in [
                "textarea[placeholder*='DeepSeek']",
                "textarea[placeholder*='发送消息']",
                "[class*='_546d736']",
                "textarea",
            ]:
                try:
                    if page.locator(sel).first.is_visible(timeout=2000):
                        return True
                except Exception:
                    pass
            return False

        elif platform_key == "kimi":
            try:
                body_text = page.locator("body").inner_text(timeout=3000)
                if "发送验证码" in body_text or "手机号快捷登录" in body_text:
                    return False
            except Exception:
                pass
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
            for sel in ["text=登录", "text=注册", "button:has-text('登录')"]:
                try:
                    if page.locator(sel).first.is_visible(timeout=1000):
                        return False
                except Exception:
                    pass
            return page.locator("[class*='avatar'], [class*='history']").first.is_visible(timeout=2000)

        elif platform_key == "wenxin":
            for sel in ["text=登录", "button:has-text('登录')", "text=立即登录"]:
                try:
                    if page.locator(sel).first.is_visible(timeout=1000):
                        return False
                except Exception:
                    pass
            for sel in ["textarea", "div[contenteditable='true']", "[class*='input']"]:
                try:
                    if page.locator(sel).first.is_visible(timeout=2000):
                        return True
                except Exception:
                    pass
            return page.locator("[class*='avatar'], [class*='user'], [class*='profile']").first.is_visible(timeout=2000)

        elif platform_key == "yiyan":
            # 文心一言(yiyan) 和 wenxin 类似，都是百度产品
            for sel in ["text=登录", "button:has-text('登录')", "text=立即登录"]:
                try:
                    if page.locator(sel).first.is_visible(timeout=1000):
                        return False
                except Exception:
                    pass
            for sel in ["textarea", "div[contenteditable='true']", "[class*='input']"]:
                try:
                    if page.locator(sel).first.is_visible(timeout=2000):
                        return True
                except Exception:
                    pass
            return page.locator("[class*='avatar'], [class*='user'], [class*='profile']").first.is_visible(timeout=2000)

        elif platform_key == "qianwen":
            for sel in ["text=登录", "text=注册", "button:has-text('登录')"]:
                try:
                    if page.locator(sel).first.is_visible(timeout=1000):
                        return False
                except Exception:
                    pass
            for sel in ["[class*='avatar'], [class*='user'], [class*='history'], [class*='sidebar']"]:
                try:
                    if page.locator(sel).first.is_visible(timeout=2000):
                        return True
                except Exception:
                    pass
            return False

        elif platform_key == "chatgpt":
            # ChatGPT 登录检测优化：避免仅靠 URL 判定导致的误报 (False Positive)
            
            # 1. 检查是否存在未登录标识（显式的登录按钮）
            # 即使 URL 包含 /chat，如果看到这些按钮，也绝对是未登录
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
                        print(f"  [LoginCheck] ChatGPT 明确未登录: 发现登录按钮 {sel}")
                        return False
                except Exception:
                    pass

            # 2. 检查已登录特征（必须看到这些元素之一才算登录）
            logged_in_features = [
                "[data-testid='profile-button']",   # 用户头像按钮
                "#prompt-textarea",                # 真正的对话框
                "nav[aria-label='Chat history']",  # 侧边栏历史记录
                "button[aria-label*='User menu']",  # 用户菜单
                "div.markdown"                     # 已有的对话内容
            ]
            
            found_feature = False
            for sel in logged_in_features:
                try:
                    loc = page.locator(sel).first
                    if loc.is_visible(timeout=2000):
                        print(f"  [LoginCheck] ChatGPT 确认已登录: 发现特征 {sel}")
                        found_feature = True
                        break
                except Exception:
                    pass
            
            if found_feature:
                return True

            # 3. URL 辅助判定（仅作为参考，不能作为唯一依据）
            curr_url = page.url.lower()
            if "/chat" in curr_url and "auth" not in curr_url:
                # 如果 URL 匹配但没找到特征，可能是页面还没加载完或者被挡住了
                # 再次检查是否有文本框（可能是自定义的或者结构变了）
                try:
                    if page.locator("textarea").first.is_visible(timeout=1000):
                         print(f"  [LoginCheck] ChatGPT URL 匹配且发现 textarea，视为已登录")
                         return True
                except: pass
                
                print(f"  [LoginCheck] ChatGPT URL 匹配但未发现已登录特征，视为未登录: {curr_url}")
                return False
            
            return False

        else:
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


def check_platform_login(platform_key: str, user_id=None) -> dict:
    """
    检测指定平台的登录状态
    
    Args:
        platform_key: 平台标识 (doubao, deepseek, kimi, yuanbao, wenxin, qianwen)
    
    Returns:
        dict: {
            'platform': str,
            'name': str,
            'is_logged_in': bool,
            'error': str or None
        }
    """
    if platform_key not in PLATFORMS:
        return {
            'platform': platform_key,
            'name': platform_key,
            'is_logged_in': False,
            'error': f'未知平台: {platform_key}'
        }
    
    _, name, url = PLATFORMS[platform_key]
    user_data_dir = get_profile_dir(platform_key, user_id)
    
    try:
        with sync_playwright() as p:
            # 对于 ChatGPT，Headless 模式极易触发 Cloudflare 导致状态检测失败
            # 我们尝试先用 Headless 检测，如果疑似被拦截或未登录，则在 ChatGPT 情况下尝试一次有头模式（仅对 ChatGPT）
            is_chatgpt = (platform_key == "chatgpt")
            
            # 第一次尝试：默认 Headless
            context, browser = launch_browser(p, headless=True, user_data_dir=user_data_dir)
            page = context.pages[0] if context.pages else context.new_page()
            
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            
            # 等待页面加载关键元素
            try:
                page.wait_for_selector("textarea, div[contenteditable='true'], #prompt-textarea, [data-testid='profile-button'], body", timeout=15000)
            except: pass
            
            time.sleep(5)
            is_logged_in = _is_logged_in(page, platform_key, url)
            
            # 如果是 ChatGPT 且第一次检测失败，尝试有头模式检测一次
            if is_chatgpt and not is_logged_in:
                context.close()
                if browser: browser.close()
                
                context, browser = launch_browser(p, headless=False, user_data_dir=user_data_dir)
                page = context.pages[0] if context.pages else context.new_page()
                page.set_default_timeout(60000)
                
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                
                try:
                    is_turnstile = page.evaluate("() => !!document.querySelector('iframe[src*='turnstile']') || !!document.querySelector('#challenge-running')")
                    if is_turnstile:
                        time.sleep(10)
                except: pass
                
                try:
                    page.wait_for_selector("#prompt-textarea, [data-testid='profile-button'], nav[aria-label='Chat history']", timeout=25000)
                except: pass
                
                time.sleep(5)
                is_logged_in = _is_logged_in(page, platform_key, url)

            context.close()
            if browser:
                browser.close()
            else:
                context.close()
            
            logger.info(f"平台登录状态检测完成: {name} - {'已登录' if is_logged_in else '未登录'}")
            return {
                'platform': platform_key,
                'name': name,
                'is_logged_in': is_logged_in,
                'error': None
            }
    
    except Exception as e:
        error = str(e)
        if "ProcessSingleton" in error or "SingletonLock" in error or "profile directory" in error:
            error = f"{name} 登录浏览器仍在打开，请先关闭弹出的 {name} 浏览器窗口，再点击重新检测"
        logger.error(f"平台登录状态检测失败: {name} - {error}")
        return {
            'platform': platform_key,
            'name': name,
            'is_logged_in': False,
            'error': error
        }


def check_all_platforms(user_id=None) -> list:
    """
    检测所有平台的登录状态
    
    Returns:
        list: 包含所有平台登录状态的列表
    """
    results = []
    for platform_key in PLATFORMS.keys():
        result = check_platform_login(platform_key, user_id)
        results.append(result)
    return results


if __name__ == "__main__":
    # 测试代码
    import sys
    
    if len(sys.argv) > 1:
        platform = sys.argv[1]
        result = check_platform_login(platform)
        print(f"\n平台: {result['name']}")
        print(f"登录状态: {'已登录' if result['is_logged_in'] else '未登录'}")
        if result['error']:
            print(f"错误: {result['error']}")
    else:
        results = check_all_platforms()
        print("\n=== 登录状态检测结果 ===")
        for r in results:
            status = "✓ 已登录" if r['is_logged_in'] else "✗ 未登录"
            print(f"{r['name']:10s} {status}")
            if r['error']:
                print(f"           错误: {r['error']}")
