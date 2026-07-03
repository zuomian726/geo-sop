"""
ChatGPT https://chatgpt.com/
"""
import os
import re
import time
import random
import tempfile
from PIL import Image
from playwright.sync_api import Page, TimeoutError as PWTimeout
import config

URL = "https://chatgpt.com/"


def query(page: Page, question: str, brand_keywords: list = None, enable_screenshot: bool = True, output_dir: str = None) -> tuple[str, list]:
    print(f"    正在访问 {URL}...")
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    
    # 等待页面加载完成的特征
    print("    等待输入框出现...")
    try:
        page.wait_for_selector(
            "#prompt-textarea, textarea, [contenteditable='true']",
            timeout=30000, state="visible"
        )
        print("    输入框已就绪")
    except PWTimeout:
        print("    等待输入框超时，尝试继续...")
    
    _random_wait(2000, 3000)

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
    print(f"    正在输入问题: {text}")
    for char in text:
        page.keyboard.type(char)
        time.sleep(random.randint(20, 50) / 1000)
    print("    输入完成")


def _find_editor(page: Page):
    selectors = ["#prompt-textarea", "textarea", "div[contenteditable='true']", "[role='textbox']"]
    for sel in selectors:
        loc = page.locator(sel).first
        try:
            if loc.is_visible(timeout=5000):
                print(f"    找到输入框: {sel}")
                return loc
        except PWTimeout:
            continue
    
    # 如果没找到，打印一下当前页面的关键信息帮助调试
    print("    未能找到输入框，当前页面标题:", page.title())
    return None


def _verify_and_send(page: Page, editor, question: str):
    # 先验证内容是否输入成功
    print("    验证输入内容...")
    for attempt in range(3):
        try:
            content = editor.input_value(timeout=2000)
        except Exception:
            try:
                content = editor.inner_text(timeout=2000)
            except Exception:
                content = ""

        if content.strip():
            print(f"    内容验证通过: {content[:20]}...")
            break

        print(f"    输入框为空，重新输入(第{attempt+1}次)...")
        editor.click()
        _random_wait(300, 500)
        _human_type(page, question)
        _random_wait(400, 600)

    print("    正在寻找发送按钮...")
    sent = False
    for sel in [
        "[data-testid='send-button']",
        "button[aria-label*='Send']",
        "button[aria-label*='发送']",
        "button.bg-black", 
    ]:
        btn = page.locator(sel).first
        try:
            if btn.is_visible(timeout=1500) and btn.is_enabled(timeout=1500):
                btn.click()
                sent = True
                break
        except PWTimeout:
            continue

    if not sent:
        editor.click()
        _random_wait(200, 300)
        page.keyboard.press("Enter")


def _wait_for_answer(page: Page):
    """等待 ChatGPT 回答完成：停止按钮消失或发送按钮重新出现"""
    print("    等待 ChatGPT 回答", end="", flush=True)
    deadline = time.time() + config.ANSWER_TIMEOUT
    time.sleep(4)

    last_content = ""
    stable_count = 0

    while time.time() < deadline:
        # 如果看到 "Stop generating" 按钮，说明还在生成
        is_generating = page.locator("[data-testid='stop-button'], [aria-label*='Stop']").first.is_visible(timeout=1000)
        
        if not is_generating:
            # 再检查一下发送按钮是否可用（ChatGPT 结束时发送按钮会恢复可用状态）
            send_btn = page.locator("[data-testid='send-button']").first
            try:
                if send_btn.is_visible(timeout=1000) and send_btn.is_enabled(timeout=1000):
                    print(" OK (发送按钮就绪)")
                    break
            except Exception:
                pass
        
        # 兜底方案：检测内容是否停止变化
        curr_content = _get_last_answer(page)
        if curr_content and curr_content == last_content:
            stable_count += 1
            if stable_count >= 3: # 连续 6 秒没变化
                print(" OK (内容已稳定)")
                break
        else:
            last_content = curr_content
            stable_count = 0

        print(".", end="", flush=True)
        time.sleep(2)
    else:
        print(" 超时")

    time.sleep(2)


def _get_last_answer(page: Page) -> str:
    try:
        return page.evaluate("""() => {
            const turns = document.querySelectorAll("[data-testid^='conversation-turn-']");
            if (turns.length === 0) return '';
            // 找到最后一个回答（通常是偶数索引，或者是最后一个包含 .markdown 的 turn）
            for (let i = turns.length - 1; i >= 0; i--) {
                const markdown = turns[i].querySelector('.markdown');
                if (markdown) {
                    return markdown.innerText.trim();
                }
            }
            return '';
        }""") or ""
    except Exception:
        return ""


def _get_references(page: Page) -> list:
    """ChatGPT 引用：通常在回答中以链接形式存在"""
    try:
        return page.evaluate("""() => {
            const results = [];
            const seen = new Set();
            const turns = document.querySelectorAll("[data-testid^='conversation-turn-']");
            if (turns.length === 0) return [];
            
            let lastMarkdown = null;
            for (let i = turns.length - 1; i >= 0; i--) {
                const markdown = turns[i].querySelector('.markdown');
                if (markdown) {
                    lastMarkdown = markdown;
                    break;
                }
            }
            
            if (!lastMarkdown) return [];
            
            // 查找所有链接，排除 chatgpt/openai 自身的
            lastMarkdown.querySelectorAll('a[href]').forEach(el => {
                const href = el.getAttribute('href') || '';
                if (!href.startsWith('http') || href.includes('openai.com') || href.includes('chatgpt.com')) return;
                if (seen.has(href)) return;
                
                let title = (el.innerText || el.textContent || '').trim();
                // 如果标题是数字（引用下标），尝试找更完整的描述
                if (!title || title.length < 2 || /^\\d+$/.test(title)) {
                    title = el.getAttribute('aria-label') || el.getAttribute('title') || title;
                }
                
                if (!title || title.length < 2) {
                    title = href;
                }
                
                seen.add(href);
                results.push({title: title.slice(0, 200), url: href, content: ''});
            });
            return results;
        }""") or []
    except Exception:
        return []


def _take_screenshot(page: Page, question: str, brand_keywords: list = None, output_dir: str = None) -> str:
    """长截图逻辑，复用 GoFullPage 算法"""
    try:
        from utils import get_timestamp_dir, find_keyword_positions, draw_marks
        timestamp_dir = get_timestamp_dir()
        # 使用传入的 output_dir，如果没有则使用默认配置
        base_dir = output_dir if output_dir else config.OUTPUT_DIR
        shot_dir = os.path.join(base_dir, timestamp_dir, "screenshots")
        os.makedirs(shot_dir, exist_ok=True)
        safe_name = re.sub(r'[\\/:*?"<>|]', "_", question).strip(".")[:80]
        shot_path = os.path.join(shot_dir, f"{safe_name}.png")

        # ── 1. 截图区域（适配 ChatGPT） ────────────────────
        clip_x = page.evaluate("""() => {
            let leftBound = 200;
            // 尝试定位主内容区
            const main = document.querySelector('main');
            if (main) {
                const r = main.getBoundingClientRect();
                leftBound = Math.max(leftBound, Math.round(r.left));
            }
            return leftBound;
        }""")
        vp     = page.viewport_size
        clip_w = vp["width"] - clip_x

        # 顶部边界：检测 header
        clip_y = page.evaluate("""() => {
            let bottom = 0;
            document.querySelectorAll('header, [class*="header"], [class*="sticky"]').forEach(el => {
                const cs = window.getComputedStyle(el);
                const r  = el.getBoundingClientRect();
                if ((cs.position === 'fixed' || cs.position === 'sticky')
                        && r.top <= 20 && r.height > 0 && r.height < 150) {
                    bottom = Math.max(bottom, Math.round(r.bottom));
                }
            });
            return bottom || 60;
        }""")

        # 底部边界：排除输入框
        input_top = page.evaluate("""() => {
            const vh = window.innerHeight;
            let top = vh;
            document.querySelectorAll('form, [class*="input"], [class*="bottom"]').forEach(el => {
                const r  = el.getBoundingClientRect();
                const cs = window.getComputedStyle(el);
                // 排除固定在顶部的元素，且确保元素在页面中下部
                if (r.bottom > vh * 0.7 && r.width > 200 && cs.position !== 'fixed' && r.top > 100) {
                    top = Math.min(top, r.top);
                }
            });
            return Math.round(top);
        }""")
        clip_h = min(input_top - 4, vp["height"] - 100) - clip_y
        
        # 安全检查与调试
        if clip_h <= 0:
            print(f"    警告: clip_h({clip_h}) <= 0, 重置为默认值")
            clip_h = vp["height"] - clip_y - 100
        
        print(f"    截图参数: x={clip_x}, y={clip_y}, w={clip_w}, h={clip_h}")

        # ── 2. 找滚动容器 ───────────────────────────────
        info = page.evaluate("""() => {
            let best = null, bestH = 0;
            // ChatGPT 的滚动容器通常是 main 的父级或 main 自身
            document.querySelectorAll('*').forEach(el => {
                const cs = window.getComputedStyle(el);
                if ((cs.overflowY === 'auto' || cs.overflowY === 'scroll')
                        && el.scrollHeight > el.clientHeight + 50
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

        # ── 3. 关键词位置 ───────────────────────────────
        keyword_marks = []
        if brand_keywords:
            keyword_marks = find_keyword_positions(page, brand_keywords)

        # ── 4. 步进截图 ─────────────────────────────────
        frames = []
        pos = 0
        step = clip_h

        def _scroll_to(p: int):
            if found:
                page.evaluate(f"document.querySelector('[data-gofullpage-target=\"1\"]').scrollTop = {p}")
            else:
                page.evaluate(f"window.scrollTo(0, {p})")

        def _get_scroll() -> int:
            if found:
                return page.evaluate("Math.round(document.querySelector('[data-gofullpage-target=\"1\"]').scrollTop)")
            return page.evaluate("Math.round(window.scrollY)")

        while True:
            _scroll_to(pos)
            time.sleep(0.4)
            actual = _get_scroll()
            
            tmp = tempfile.mktemp(suffix=".png")
            try:
                page.screenshot(path=tmp, clip={
                    "x": clip_x, "y": clip_y,
                    "width": clip_w, "height": clip_h,
                }, timeout=60000, animations="disabled")
                img = Image.open(tmp).copy()
                os.unlink(tmp)
                frames.append((actual, img))
            except Exception as e:
                print(f"    单帧截图失败(pos={pos}): {e}")
                if os.path.exists(tmp): os.unlink(tmp)
            
            if actual + client_h >= total_scroll - 5: break
            if pos + step > total_scroll: break
            pos += step

        # ── 5. 拼接 ────────────────────────────────────
        if not frames: return ""
        
        total_h = frames[0][1].height
        for i in range(1, len(frames)):
            total_h += (frames[i][0] - frames[i-1][0])

        canvas = Image.new("RGB", (frames[0][1].width, total_h), (255, 255, 255))
        canvas.paste(frames[0][1], (0, 0))
        y_offset = frames[0][1].height

        for i in range(1, len(frames)):
            new_px = frames[i][0] - frames[i-1][0]
            if new_px <= 0: continue
            img_h = frames[i][1].height
            overlap = img_h - new_px
            cropped = frames[i][1].crop((0, max(0, overlap), frames[i][1].width, img_h))
            canvas.paste(cropped, (0, y_offset))
            y_offset += cropped.height

        if keyword_marks:
            canvas = draw_marks(canvas, keyword_marks, clip_x, clip_y)

        canvas.save(shot_path)
        return shot_path

    except Exception as e:
        print(f"    截图失败: {e}")
        return ""
