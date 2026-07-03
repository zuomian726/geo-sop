"""
文心一言 https://yiyan.baidu.com/
使用独立的浏览器配置
"""
import os
import re
import time
import random
import tempfile
from PIL import Image
from playwright.sync_api import Page, Browser, BrowserContext, sync_playwright, TimeoutError as PWTimeout
import config

URL = "https://yiyan.baidu.com/"

# 独立的浏览器配置目录
BROWSER_PROFILE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'browser_profile',
    'yiyan'
)


def launch_browser(profile_dir=None) -> tuple[Browser, BrowserContext, Page]:
    """
    启动文心一言专用的浏览器实例
    使用独立的用户数据目录，保持登录状态
    """
    from playwright.sync_api import sync_playwright
    
    # 确保配置目录存在
    browser_profile_dir = profile_dir or BROWSER_PROFILE_DIR
    os.makedirs(browser_profile_dir, exist_ok=True)
    print(f"  使用浏览器配置目录: {browser_profile_dir}")
    
    p = sync_playwright().start()
    
    try:
        # 先尝试使用持久化上下文（保持登录状态）
        try:
            context = p.chromium.launch_persistent_context(
                user_data_dir=browser_profile_dir,
                headless=False,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--start-maximized',
                    '--no-first-run',
                    '--no-default-browser-check',
                    '--disable-extensions',
                ],
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
                timeout=60000,
            )
        except Exception as e:
            print(f"  持久化上下文启动失败，使用临时浏览器: {e}")
            # 备用方案：使用普通浏览器
            browser = p.chromium.launch(
                headless=False,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--start-maximized',
                ],
                timeout=60000,
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
            )
        
        # 添加反检测脚本
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        # 获取或创建页面
        if context.pages:
            page = context.pages[0]
        else:
            page = context.new_page()
            
        return context.browser, context, page
        
    except Exception as e:
        p.stop()
        raise e


def query(page: Page, question: str, brand_keywords: list = None, enable_screenshot: bool = True, output_dir: str = None) -> tuple[str, list]:
    """
    与其他平台一致的接口：发送问题并获取回答
    返回: (answer, references)
    """
    # 设置窗口大小确保能显示右侧参考面板
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_selector(
            "textarea, div[contenteditable='true']",
            timeout=20000, state="visible"
        )
    except PWTimeout:
        pass
    _random_wait(1500, 2000)

    editor = _find_editor(page)
    if not editor:
        raise RuntimeError("未找到输入框")

    editor.click()
    _random_wait(400, 700)
    _human_type(page, question)
    _random_wait(500, 800)

    _verify_and_send(page, editor, question)

    _random_wait(2000, 3000)

    _wait_for_answer(page)

    answer = _get_last_answer(page)

    # 根据配置决定是否截图
    if enable_screenshot:
        screenshot_path = _take_screenshot(page, question, brand_keywords, output_dir)
        if screenshot_path:
            print(f"    截图 -> {screenshot_path}")
    else:
        print("    跳过截图（禁用）")

    references = _get_references(page)

    return answer, references


# ── 内部工具 ────────────────────────────────────────────

def _random_wait(min_ms, max_ms):
    time.sleep(random.randint(min_ms, max_ms) / 1000)


def _human_type(page: Page, text: str):
    for char in text:
        page.keyboard.type(char)
        time.sleep(random.randint(30, 100) / 1000)


def _find_editor(page: Page):
    selectors = ["textarea", "div[contenteditable='true']", "[class*='input']", "[role='textbox']"]
    for sel in selectors:
        loc = page.locator(sel).first
        try:
            if loc.is_visible(timeout=3000):
                print(f"    找到输入框: {sel}")
                return loc
        except PWTimeout:
            continue
    return None


def _verify_and_send(page: Page, editor, question: str):
    # 验证输入内容
    for attempt in range(3):
        try:
            content = editor.input_value(timeout=1000)
        except Exception:
            content = editor.inner_text(timeout=1000)

        if content.strip():
            break

        print(f"    输入框为空，重新输入(第{attempt+1}次)...")
        editor.click()
        _random_wait(300, 500)
        _human_type(page, question)
        _random_wait(400, 600)

    # 查找发送按钮
    sent = False
    send_selectors = [
        "button[aria-label*='发送']",
        "button[type='submit']",
        "[class*='send']",
        "[class*='submit']",
        "[role='button']",
        "button:has(svg)",
    ]
    
    for sel in send_selectors:
        btn = page.locator(sel).first
        try:
            if btn.is_visible(timeout=1500) and btn.is_enabled(timeout=1500):
                print(f"    找到发送按钮: {sel}")
                btn.click()
                sent = True
                break
        except PWTimeout:
            continue

    # 使用 Enter 键作为备选
    if not sent:
        print(f"    使用 Enter 键发送")
        editor.click()
        _random_wait(200, 300)
        page.keyboard.press("Enter")


def _wait_for_answer(page: Page):
    """等待文心回答完成：文字停止增长（连续 4 次 × 2 秒无变化）"""
    print("    等待文心回答", end="", flush=True)
    deadline = time.time() + config.ANSWER_TIMEOUT
    time.sleep(4)

    stable_count = 0
    last_len = -1

    while time.time() < deadline:
        current_text = _get_last_answer(page)
        current_len = len(current_text)

        if current_len > 50 and current_len == last_len:
            stable_count += 1
            print(".", end="", flush=True)
            if stable_count >= 4:
                print(" OK")
                break
        else:
            stable_count = 0
            if current_len > 0:
                print(f"({current_len})", end="", flush=True)

        last_len = current_len
        time.sleep(2)
    else:
        print(" 超时")

    time.sleep(2)


def _get_last_answer(page: Page) -> str:
    try:
        return page.evaluate("""() => {
            let best = null, bestLen = 0;
            for (const el of document.querySelectorAll('div, article, section')) {
                const r = el.getBoundingClientRect();
                if (r.left < 200 || r.width < 300) continue;
                if (el.children.length > 60) continue;
                const t = (el.innerText || '').trim();
                if (t.length > bestLen) { bestLen = t.length; best = el; }
            }
            return best ? best.innerText.trim() : '';
        }""") or ""
    except Exception:
        return ""


def _get_references(page: Page) -> list:
    """
    文心引用抓取：
    1. 查找AI答案顶部的「参考X个网页」按钮并点击
    2. 等待右侧引用面板展开
    3. 获取引用标题和URL
    """
    try:
        refs = []
        internal_domains = ['baidu.com', 'bdstatic.com', 'bcebos.com']

        # ── 1. 查找并点击AI答案顶部的「参考X个网页」按钮 ─────────────────
        print("    引用参考: 查找AI答案顶部的「参考X个网页」按钮...")
        
        # 使用 JavaScript 精确查找AI回答区域内的「参考X个网页」按钮
        result = page.evaluate("""() => {
            let found = null;
            
            // 首先找到AI回答的容器（通常是包含长文本的主要内容区域）
            const answerContainers = document.querySelectorAll('div, article, section');
            let answerContainer = null;
            
            for (const el of answerContainers) {
                const text = el.innerText || '';
                // 找到包含大量文本且宽度较大的容器（AI回答区域）
                if (text.length > 500 && el.offsetWidth > 500) {
                    answerContainer = el;
                    break;
                }
            }
            
            if (answerContainer) {
                // 在AI回答容器内查找「参考X个网页」按钮
                const pattern = /参考([0-9]+)[ \t]*(个)?[ \t]*(网页|来源|篇)/;
                
                // 先查找容器内的按钮和链接
                const clickables = answerContainer.querySelectorAll('button, a, [role="button"]');
                for (const el of clickables) {
                    const text = el.innerText || '';
                    if (pattern.test(text) && el.offsetHeight > 0 && el.offsetWidth > 0) {
                        found = {
                            text: text.trim(),
                            className: el.className,
                            tagName: el.tagName,
                            id: el.id,
                            type: 'clickable_in_answer'
                        };
                        try {
                            el.click();
                            found.clicked = true;
                        } catch (e) {
                            found.clicked = false;
                        }
                        break;
                    }
                }
                
                // 如果没找到，查找容器内的文本节点（可能是可点击的span/div）
                if (!found) {
                    const spans = answerContainer.querySelectorAll('span, div');
                    for (const el of spans) {
                        const text = el.innerText || '';
                        if (pattern.test(text) && el.offsetHeight > 0 && el.offsetWidth > 0) {
                            // 检查是否是独立的小元素（按钮样式），而不是大容器
                            if (el.offsetWidth < 200 && el.offsetHeight < 50) {
                                found = {
                                    text: text.trim(),
                                    className: el.className,
                                    tagName: el.tagName,
                                    id: el.id,
                                    type: 'text_button'
                                };
                                try {
                                    el.click();
                                    found.clicked = true;
                                } catch (e) {
                                    found.clicked = false;
                                }
                                break;
                            }
                        }
                    }
                }
            }
            
            // 如果还是没找到，尝试全局查找
            if (!found) {
                const allElements = document.querySelectorAll('*');
                const pattern = /参考([0-9]+)[ \t]*(个)?[ \t]*(网页|来源|篇)/;
                for (const el of allElements) {
                    const text = el.innerText || '';
                    if (pattern.test(text) && el.offsetHeight > 0 && el.offsetWidth > 0) {
                        if (el.offsetWidth < 300 && el.offsetHeight < 80) {
                            if (!text.includes('新对话') && !text.includes('创意写作')) {
                                found = {
                                    text: text.trim(),
                                    className: el.className,
                                    tagName: el.tagName,
                                    id: el.id,
                                    type: 'global_text_button'
                                };
                                try {
                                    el.click();
                                    found.clicked = true;
                                } catch (e) {
                                    found.clicked = false;
                                }
                                break;
                            }
                        }
                    }
                }
            }
            
            return found;
        }""")
        
        if result:
            print(f"    找到引用按钮: {result.get('text')}")
            print(f"    按钮信息: tag={result.get('tagName')}, class={result.get('className')}, type={result.get('type')}")
            if result.get('clicked'):
                print("    已点击该按钮")
            else:
                print("    点击该按钮失败")
        else:
            print("    引用参考: 未找到「参考X个网页」按钮")
            return []

        time.sleep(3)  # 等待右侧引用面板展开
        
        # ── 2. 查找右侧引用面板中的所有条目 ────────────────────────────
        print("    引用参考: 查找右侧引用面板条目...")
        
        # 使用JavaScript查找引用条目并返回它们的索引
        item_indices = page.evaluate("""() => {
            const indices = [];
            const datePattern = /\\d{4}-\\d{2}-\\d{2}/;
            
            // 查找右侧面板（offsetLeft > 窗口宽度的一半）
            const allElements = document.querySelectorAll('div, article, section');
            let itemIndex = 0;
            
            allElements.forEach((el, idx) => {
                const text = el.innerText || '';
                // 筛选包含日期且看起来像引用条目的元素
                if (datePattern.test(text) && text.trim().length > 30 && text.trim().length < 500) {
                    if (!text.includes('新对话') && !text.includes('创意写作') && !text.includes('请介绍')) {
                        indices.push(idx);  // 保存元素在allElements中的索引
                        itemIndex++;
                        if (itemIndex >= 10000) return false;  // 最多找10000条
                    }
                }
            });
            
            return indices;
        }""")
        
        if not item_indices or len(item_indices) == 0:
            print("    引用参考: 未找到引用条目")
            return []
        
        print(f"    引用参考: 发现 {len(item_indices)} 条引用")
        
        refs = []
        internal_domains = ['baidu.com', 'bdstatic.com', 'bcebos.com']
        
        # ── 3. 逐个点击引用条目，捕获新标签页URL ──────────────────────
        for i, element_idx in enumerate(item_indices):
            try:
                # 使用JavaScript点击指定索引的元素
                result = page.evaluate(f"""() => {{
                    const allElements = document.querySelectorAll('div, article, section');
                    const el = allElements[{element_idx}];
                    if (el) {{
                        try {{
                            el.click();
                            return el.innerText || '';
                        }} catch (e) {{
                            return null;
                        }}
                    }}
                    return null;
                }}""")
                
                if not result:
                    continue
                
                title = result.split('\n')[0].strip()[:120]
                print(f"    引用参考: 点击条目[{i+1}]: {title[:30]}")
                
                # 等待新标签页打开
                with page.context.expect_page(timeout=8000) as new_page_info:
                    # 已经通过JS点击了，这里只是等待
                    pass
                
                new_page = new_page_info.value
                try:
                    new_page.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    pass
                
                new_url = new_page.url
                new_page.close()
                page.bring_to_front()
                time.sleep(0.3)
                
                if (new_url and new_url.startswith('http') 
                        and not any(d in new_url for d in internal_domains)):
                    refs.append({"title": title, "url": new_url, "content": ""})
                    print(f"    OK [{len(refs)}] {title[:40]} -> {new_url[:70]}")
                
                # if len(refs) >= 10:  # 去掉条数限制
                #     break
            
            except Exception as e:
                # print(f"    引用参考: 处理条目失败: {e}")
                continue
        
        if not refs or len(refs) == 0:
            print("    引用参考: 未获取到有效URL")
            return []
        
        print(f"    引用参考: 共获取 {len(refs)} 条")
        for r in refs[:10]:
            print(f"      - {r['title'][:40]}: {r['url'][:50]}...")
        
        return refs

    except Exception as e:
        print(f"    引用参考抓取失败: {e}")
        import traceback
        traceback.print_exc()
        return []


def _take_screenshot(page: Page, question: str, brand_keywords: list = None, output_dir: str = None) -> str:
    """
    长截图：GoFullPage 同款算法
    """
    try:
        from utils import get_timestamp_dir, find_keyword_positions, draw_marks
        timestamp_dir = get_timestamp_dir()
        base_dir = output_dir if output_dir else config.OUTPUT_DIR
        shot_dir = os.path.join(base_dir, timestamp_dir, "screenshots")
        os.makedirs(shot_dir, exist_ok=True)
        safe_name = re.sub(r'[\\/:*?"<>|]', "_", question).strip(".")[:80]
        shot_path = os.path.join(shot_dir, f"{safe_name}.png")

        # 截图区域 - 左侧边界
        clip_x = page.evaluate("""() => {
            let leftBound = 200;
            Array.from(document.querySelectorAll('*')).forEach(el => {
                const r  = el.getBoundingClientRect();
                const cs = window.getComputedStyle(el);
                if (r.left < 10 && r.width > 80 && r.width < 400
                        && r.height > 400 && cs.display !== 'none') {
                    leftBound = Math.max(leftBound, Math.round(r.right) + 2);
                }
            });
            return leftBound;
        }""")
        vp     = page.viewport_size
        clip_w = vp["width"] - clip_x

        # 顶部边界：检测 fixed/sticky header，避免每帧都截到 header 导致拼接时重复出现
        clip_y = page.evaluate("""() => {
            let bottom = 0;
            document.querySelectorAll('*').forEach(el => {
                const cs = window.getComputedStyle(el);
                const r  = el.getBoundingClientRect();
                // 检测固定定位元素（登录栏、导航栏等）
                if ((cs.position === 'fixed' || cs.position === 'sticky')
                        && r.top <= 50 && r.width > 100 && r.height > 0
                        && r.height < 200 && cs.display !== 'none') {
                    bottom = Math.max(bottom, Math.round(r.bottom));
                }
            });
            // 确保最小顶部边距，避免内容被固定头部覆盖
            return Math.max(bottom, 100);
        }""")

        # 底部边界
        input_top = page.evaluate("""() => {
            const vh = window.innerHeight;
            let top = vh;
            document.querySelectorAll(
                'textarea, [class*="input"], [class*="composer"], [class*="suggest"], [class*="footer"]'
            ).forEach(el => {
                const r  = el.getBoundingClientRect();
                const cs = window.getComputedStyle(el);
                if (r.bottom > vh * 0.4 && r.width > 100 && cs.display !== 'none') {
                    top = Math.min(top, r.top);
                }
            });
            return Math.round(top);
        }""")
        clip_h = min(input_top - 4, vp["height"] - 150) - clip_y

        # 找滚动容器
        info = page.evaluate("""() => {
            let best = null, bestH = 0;
            document.querySelectorAll('*').forEach(el => {
                const cs = window.getComputedStyle(el);
                const r  = el.getBoundingClientRect();
                if ((cs.overflowY === 'auto' || cs.overflowY === 'scroll')
                        && el.scrollHeight > el.clientHeight + 50
                        && r.width > 300 && r.height > 200
                        && el.scrollHeight > bestH) {
                    bestH = el.scrollHeight;
                    best  = el;
                }
            });
            if (best) {
                best.setAttribute('data-gofullpage-target', '1');
                best.scrollTop = 0;
                return {
                    found: true,
                    scrollHeight: best.scrollHeight,
                    clientHeight: best.clientHeight,
                };
            }
            window.scrollTo(0, 0);
            return {
                found: false,
                scrollHeight: document.documentElement.scrollHeight,
                clientHeight: window.innerHeight,
            };
        }""")
        time.sleep(0.8)

        total_scroll = info["scrollHeight"]
        client_h     = info["clientHeight"]
        found        = info["found"]

        # 查找关键词位置
        keyword_marks = []
        if brand_keywords:
            keyword_marks = find_keyword_positions(page, brand_keywords)
            if keyword_marks:
                print(f"    发现 {len(keyword_marks)} 处品牌词曝光")

        step = clip_h

        def _scroll_to(pos: int):
            if found:
                page.evaluate(f"""() => {{
                    const el = document.querySelector('[data-gofullpage-target="1"]');
                    if (el) el.scrollTop = {pos};
                }}""")
            else:
                page.evaluate(f"window.scrollTo(0, {pos})")

        def _get_scroll() -> int:
            if found:
                return page.evaluate("""() => {
                    const el = document.querySelector('[data-gofullpage-target="1"]');
                    return el ? Math.round(el.scrollTop) : 0;
                }""")
            return page.evaluate("() => Math.round(window.scrollY)")

        def _snap() -> Image.Image:
            tmp = tempfile.mktemp(suffix=".png")
            page.screenshot(path=tmp, clip={
                "x": clip_x, "y": clip_y,
                "width": clip_w, "height": clip_h,
            })
            img = Image.open(tmp).copy()
            os.unlink(tmp)
            return img

        # 按坐标步进截图
        frames: list[tuple[int, Image.Image]] = []
        pos = 0

        while True:
            _scroll_to(pos)
            time.sleep(0.4)
            actual = _get_scroll()
            img    = _snap()
            frames.append((actual, img))
            print(f"(s={actual})", end="", flush=True)

            if actual + client_h >= total_scroll - 2:
                break
            if pos + step > total_scroll:
                break
            pos += step

        if not frames:
            print("    截图: 未获取到帧")
            return ""

        if len(frames) == 1:
            frames[0][1].save(shot_path, optimize=True, quality=95)
            print(f"\n    截图: 1 帧，总高 {frames[0][1].height}px")
            return shot_path

        # 计算画布总高度
        total_h = frames[0][1].height
        for i in range(1, len(frames)):
            new_px = frames[i][0] - frames[i-1][0]
            new_px = max(new_px, 1)
            new_px = min(new_px, frames[i][1].height)
            total_h += new_px

        canvas = Image.new("RGB", (frames[0][1].width, total_h), (255, 255, 255))

        canvas.paste(frames[0][1], (0, 0))
        y_offset = frames[0][1].height

        for i in range(1, len(frames)):
            new_px = frames[i][0] - frames[i-1][0]
            new_px = max(new_px, 1)
            new_px = min(new_px, frames[i][1].height)
            img_h   = frames[i][1].height
            overlap = img_h - new_px
            cropped = frames[i][1].crop((0, overlap, frames[i][1].width, img_h))
            canvas.paste(cropped, (0, y_offset))
            y_offset += cropped.height

        # 绘制品牌词红框
        if keyword_marks:
            canvas = draw_marks(canvas, keyword_marks, clip_x, clip_y)

        canvas.save(shot_path, optimize=True, quality=95)
        print(f"\n    截图: {len(frames)} 帧拼接，总高 {total_h}px")
        return shot_path

    except Exception as e:
        print(f"    截图失败: {e}")
        return ""
