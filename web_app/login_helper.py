"""
AI平台登录辅助模块
提供打开浏览器窗口让用户手动登录的功能
"""
import sys
import os
import time

# 添加父目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.sync_api import sync_playwright
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


def open_login_browser(platform_key: str, wait_time: int = 60, user_id=None) -> dict:
    """
    打开浏览器窗口让用户手动登录
    类似 python main.py --login doubao --debug
    
    Args:
        platform_key: 平台标识 (doubao, deepseek, kimi, yuanbao, wenxin, qianwen)
        wait_time: 等待用户登录的时间（秒），默认60秒
    
    Returns:
        dict: {
            'success': bool,
            'platform': str,
            'name': str,
            'message': str
        }
    """
    if platform_key not in PLATFORMS:
        return {
            'success': False,
            'platform': platform_key,
            'name': platform_key,
            'message': f'未知平台: {platform_key}'
        }
    
    _, name, url = PLATFORMS[platform_key]
    user_data_dir = get_profile_dir(platform_key, user_id)
    
    try:
        print(f"\n{'='*60}")
        print(f"正在打开 {name} 登录页面...")
        print(f"平台: {name}")
        print(f"URL: {url}")
        print(f"配置目录: {user_data_dir}")
        print(f"{'='*60}\n")
        
        with sync_playwright() as p:
            # 启动浏览器（非无头模式，让用户可以看到并操作）
            context, browser = launch_browser(p, headless=False, user_data_dir=user_data_dir)
            page = context.pages[0] if context.pages else context.new_page()
            
            # 访问平台页面
            print(f"正在访问 {url}...")
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            
            # 等待页面加载
            try:
                page.wait_for_selector(
                    "textarea, div[contenteditable='true'], body",
                    timeout=10000, state="visible"
                )
            except Exception:
                pass
            
            print(f"\n{'='*60}")
            print(f"浏览器已打开，请在浏览器窗口中完成登录")
            print(f"")
            print(f"提示：")
            print(f"  1. 如果已经登录，可以直接关闭浏览器")
            print(f"  2. 如果未登录，请在浏览器中完成登录操作")
            print(f"  3. 登录完成后，关闭浏览器窗口")
            print(f"  4. 浏览器将在 {wait_time} 秒后自动关闭")
            print(f"{'='*60}\n")
            
            # 等待用户操作
            # 注意：这里不能使用 input()，因为在Web应用中无法交互
            # 所以我们让浏览器保持打开状态，用户可以手动关闭
            # 或者等待超时自动关闭
            
            # 检测浏览器是否被用户关闭
            start_time = time.time()
            while time.time() - start_time < wait_time:
                try:
                    # 检查页面是否还存在
                    page.title()
                    time.sleep(1)
                except Exception:
                    # 页面已关闭，用户手动关闭了浏览器
                    print("检测到浏览器已关闭")
                    break
            
            # 关闭浏览器
            try:
                if browser:
                    browser.close()
                else:
                    context.close()
            except Exception:
                pass
            
            print(f"\n{'='*60}")
            print(f"{name} 登录流程完成")
            print(f"登录状态已保存到: {user_data_dir}")
            print(f"{'='*60}\n")
            
            return {
                'success': True,
                'platform': platform_key,
                'name': name,
                'message': f'{name} 登录流程完成，请重新检测登录状态'
            }
    
    except Exception as e:
        error_msg = f"打开登录浏览器失败: {str(e)}"
        print(f"\n错误: {error_msg}\n")
        return {
            'success': False,
            'platform': platform_key,
            'name': name,
            'message': error_msg
        }


if __name__ == "__main__":
    # 测试代码
    import sys
    
    if len(sys.argv) > 1:
        platform = sys.argv[1]
        wait_time = int(sys.argv[2]) if len(sys.argv) > 2 else 60
        result = open_login_browser(platform, wait_time)
        print(f"\n结果: {result}")
    else:
        print("用法: python login_helper.py <platform> [wait_time]")
        print("示例: python login_helper.py doubao 60")
