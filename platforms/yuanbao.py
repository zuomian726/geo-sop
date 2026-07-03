"""
元宝 (腾讯) https://yuanbao.tencent.com/chat/
"""
import os
import re
import time
import random
import tempfile
from PIL import Image
from playwright.sync_api import Page, TimeoutError as PWTimeout
import config

URL = "https://yuanbao.tencent.com/chat/"


def query(page: Page, question: str, brand_keywords: list = None, enable_screenshot: bool = True, output_dir: str = None) -> tuple[str, list]:
    page.goto(URL, wait_until="domcontentloaded")
    try:
        page.wait_for_selector(
            "textarea, div[contenteditable='true'], [class*='input'], [role='textbox']",
            timeout=15000, state="visible"
        )
    except PWTimeout:
        pass
    _random_wait(2000, 3500)

    editor = _find_editor(page)
    if not editor:
        raise RuntimeError("未找到输入框")

    editor.click()
    _random_wait(400, 700)
    _human_type(page, question)
    _random_wait(500, 800)

    _verify_and_send(page, editor, question)

    # 等待 URL 变化（元宝发送后跳转到 /chat/<id>）
    try:
        page.wait_for_url("**/chat/**", timeout=10000)
    except PWTimeout:
        pass
    _random_wait(1500, 2000)

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
    # 方式1: CSS 选择器
    for sel in ["textarea", "div[contenteditable='true']", "[class*='input']", "[role='textbox']"]:
        loc = page.locator(sel).first
        try:
            if loc.is_visible(timeout=3000):
                return loc
        except PWTimeout:
            continue

    # 方式2: JavaScript 探测（兼容隐式输入框）
    result = page.evaluate("""() => {
        const selector = 'textarea, div[contenteditable="true"], [role="textbox"], input[type="text"]';
        const els = document.querySelectorAll(selector);
        for (const el of els) {
            const r = el.getBoundingClientRect();
            if (r.width > 0 && r.height > 0 && r.top >= 0) {
                return el.tagName;
            }
        }
        return null;
    }""")

    if result:
        tag = result
        for sel in ["textarea", "div[contenteditable='true']", "[role='textbox']"]:
            loc = page.locator(sel).first
            try:
                if loc.is_visible(timeout=3000):
                    return loc
            except PWTimeout:
                continue

    return None


def _verify_and_send(page: Page, editor, question: str):
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

    sent = False
    for sel in [
        "button[aria-label*='发送']",
        "button[type='submit']",
        "[class*='send-btn']",
        "[class*='sendBtn']",
        "[class*='send_btn']",
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
    """等待元宝回答完成：文字停止增长（连续 4 次 × 2 秒无变化）"""
    print("    等待元宝回答", end="", flush=True)
    deadline = time.time() + config.ANSWER_TIMEOUT
    time.sleep(4)

    stable_count = 0
    last_len = -1

    while time.time() < deadline:
        current_text = _get_last_answer(page)
        current_len  = len(current_text)

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
    元宝引用入口是回复底部的「源」按钮。
    逐步滚动抓取展开后的引用列表（包括插件引用和网页链接）
    
    注意：元宝的引用URL存储在元素的 data-url 属性中，而不是 <a> 标签的 href 属性。
    """
    try:
        expected = 0

        # 找「源」按钮，悬停读取 tooltip 数量，再点击展开
        src_btn = page.locator("text=源").last
        if src_btn.count() and src_btn.is_visible(timeout=3000):
            try:
                src_btn.hover()
                time.sleep(0.8)
                for sel in ["[class*='tooltip']", "[class*='tip']", "[role='tooltip']",
                            "[class*='popover']"]:
                    tip = page.locator(sel).last
                    if tip.count() and tip.is_visible(timeout=500):
                        m = re.search(r'(\d+)', tip.inner_text(timeout=500))
                        if m:
                            expected = int(m.group(1))
                        break
            except Exception:
                pass

            src_btn.click()
            time.sleep(2.0)

        # 找到引用面板的滚动容器
        scroll_container_info = page.evaluate("""() => {
            let bestContainer = null;
            let maxScrollHeight = 0;
            
            document.querySelectorAll('*').forEach(el => {
                const cs = window.getComputedStyle(el);
                const r = el.getBoundingClientRect();
                
                if ((cs.overflowY === 'auto' || cs.overflowY === 'scroll') &&
                    el.scrollHeight > el.clientHeight + 20 &&
                    r.width > 200 && r.height > 100) {
                    
                    // 检查是否包含 data-url 元素
                    const urlCount = el.querySelectorAll('[data-url]').length;
                    if (urlCount > 0 && el.scrollHeight > maxScrollHeight) {
                        maxScrollHeight = el.scrollHeight;
                        bestContainer = el;
                    }
                }
            });
            
            if (bestContainer) {
                bestContainer.setAttribute('data-ref-container', '1');
                return {
                    found: true,
                    scrollHeight: bestContainer.scrollHeight,
                    clientHeight: bestContainer.clientHeight
                };
            }
            return { found: false };
        }""")

        if not scroll_container_info['found']:
            print("    未找到引用滚动容器，尝试直接抓取")
            refs = _extract_references_yuanbao(page)
            if refs:
                print(f"    引用参考: 抓取到 {len(refs)} 篇 (预期 {expected} 篇，可能存在重复或未展开)")
                return refs
            if expected > 0:
                print(f"    引用参考: 链接不可访问，共 {expected} 篇")
                return [{"title": "插件信息暂不支持访问", "url": "", "content": ""}] * expected
            else:
                print("    引用参考: 未找到")
                return []

        # 逐步滚动引用面板
        scroll_height = scroll_container_info['scrollHeight']
        client_height = scroll_container_info['clientHeight']
        scroll_step = client_height // 2
        current_scroll = 0
        
        print(f"    开始逐步滚动引用面板 (总高度: {scroll_height}px, 步长: {scroll_step}px)", end="", flush=True)
        
        refs = []
        seen_refs = set()
        scroll_attempts = 0
        max_attempts = 50
        
        while current_scroll < scroll_height and scroll_attempts < max_attempts:
            page.evaluate(f"""() => {{
                const container = document.querySelector('[data-ref-container="1"]');
                if (container) {{
                    container.scrollTop = {current_scroll};
                }}
            }}""")
            
            time.sleep(0.5)
            
            current_refs = _extract_references_yuanbao(page)
            
            new_count = 0
            for ref in current_refs:
                if ref['url'] not in seen_refs:
                    seen_refs.add(ref['url'])
                    refs.append(ref)
                    new_count += 1
            
            if new_count > 0:
                print(f".", end="", flush=True)
            
            current_scroll += scroll_step
            scroll_attempts += 1
            
            if len(refs) >= expected and new_count == 0:
                break
        
        print(f" 完成")
        
        # 最后滚动到底部
        page.evaluate("""() => {
            const container = document.querySelector('[data-ref-container="1"]');
            if (container) {
                container.scrollTop = container.scrollHeight;
            }
        }""")
        time.sleep(0.8)
        
        final_refs = _extract_references_yuanbao(page)
        for ref in final_refs:
            if ref['url'] not in seen_refs:
                seen_refs.add(ref['url'])
                refs.append(ref)

        if refs:
            print(f"    引用参考: {len(refs)}/{expected} 篇")
            return refs

        if expected > 0:
            print(f"    引用参考: 链接不可访问，共 {expected} 篇")
            return [{"title": "插件信息暂不支持访问", "url": "", "content": ""}] * expected
        else:
            print("    引用参考: 未找到")
            return [{"title": "插件信息暂不支持访问", "url": "", "content": ""}]

    except Exception as e:
        print(f"    引用参考抓取失败: {e}")
        return [{"title": "插件信息暂不支持访问", "url": "", "content": ""}]


def _extract_references_yuanbao(page: Page) -> list:
    """从当前页面提取引用链接（元宝专用）"""
    return page.evaluate("""() => {
        const results = [];
        const seen = new Set();
        
        // 查找所有带有 data-url 属性的元素
        const allElements = Array.from(document.querySelectorAll('[data-url]'));
        
        for (const el of allElements) {
            const dataUrl = el.getAttribute('data-url') || '';
            const r = el.getBoundingClientRect();
            
            if (r.width === 0 && r.height === 0) continue;
            if (!dataUrl || dataUrl === '#') continue;
            if (dataUrl.includes('yuanbao.tencent.com') && 
                !dataUrl.includes('markdown') && 
                !dataUrl.includes('ref')) continue;
            if (seen.has(dataUrl)) continue;
            
            let title = (el.innerText || '').trim();
            
            if (title.length > 150) {
                const lines = title.split('\\n').filter(l => l.trim().length > 5);
                if (lines.length > 0) {
                    for (const line of lines) {
                        const trimmed = line.trim();
                        if (trimmed.length > 10 && 
                            trimmed.length < 150 &&
                            !trimmed.match(/^\\d+$/) &&
                            !trimmed.match(/^\\d{4}年\\d{1,2}月\\d{1,2}日$/)) {
                            title = trimmed;
                            break;
                        }
                    }
                    if (title.length > 150) {
                        title = lines[0];
                    }
                }
                title = title.slice(0, 150);
            }
            
            if (!title || title.length < 5) {
                const textElements = el.querySelectorAll('*');
                for (const child of textElements) {
                    const text = (child.innerText || '').trim();
                    if (text.length > 10 && text.length < 200) {
                        title = text.split('\\n')[0];
                        break;
                    }
                }
            }
            
            if (!title || title.length < 5) {
                title = dataUrl;
            }
            
            seen.add(dataUrl);
            results.push({
                title: title,
                url: dataUrl,
                content: ''
            });
        }
        
        // 如果没有找到 data-url，尝试查找普通的 <a> 链接作为备选
        if (results.length === 0) {
            const allLinks = Array.from(document.querySelectorAll('a[href]'));
            for (const a of allLinks) {
                const href = a.getAttribute('href') || '';
                const r = a.getBoundingClientRect();
                
                if (r.width === 0 && r.height === 0) continue;
                if (!href.startsWith('http')) continue;
                if (href.includes('yuanbao.tencent.com')) continue;
                if (seen.has(href)) continue;
                
                let title = (a.innerText || '').trim();
                if (!title || title.length < 5) {
                    let cur = a.parentElement;
                    for (let i = 0; i < 3 && cur; i++) {
                        const text = (cur.innerText || '').trim();
                        if (text.length > 10 && text.length < 200) {
                            title = text.split('\\n')[0];
                            break;
                        }
                        cur = cur.parentElement;
                    }
                }
                
                if (!title || title.length < 5) {
                    title = href;
                }
                
                title = title.slice(0, 150);
                seen.add(href);
                results.push({
                    title: title,
                    url: href,
                    content: ''
                });
            }
        }
        
        return results;
    }""") or []


def _take_screenshot(page: Page, question: str, brand_keywords: list = None, output_dir: str = None) -> str:
    """
    长截图：GoFullPage 同款算法。
    用 JS 给滚动容器打标记，按固定步长精确设置 scrollTop，
    每步截图后按坐标直接拼接，零图像匹配，零重复。
    """
    try:
        from utils import get_timestamp_dir, find_keyword_positions, draw_marks
        timestamp_dir = get_timestamp_dir()
        # 使用传入的 output_dir，如果没有则使用默认配置
        base_dir = output_dir if output_dir else config.OUTPUT_DIR
        shot_dir = os.path.join(base_dir, timestamp_dir, "screenshots")
        os.makedirs(shot_dir, exist_ok=True)
        safe_name = re.sub(r'[\\/:*?"<>|]', "_", question).strip(".")[:80]
        shot_path = os.path.join(shot_dir, f"{safe_name}.png")

        # ── 1. 截图区域 ───────────────────────────────────
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
                // 检测固定定位的顶部元素（导航栏、标题栏等）
                if ((cs.position === 'fixed' || cs.position === 'sticky')
                        && r.top <= 20 && r.width > 200 && r.height > 0
                        && r.height < 150 && cs.display !== 'none'
                        && r.left < window.innerWidth * 0.8) {  // 排除右侧固定元素
                    bottom = Math.max(bottom, Math.round(r.bottom));
                }
            });
            // 如果没有检测到固定头部，使用默认值（元宝通常有60-80px的头部）
            if (bottom === 0) {
                bottom = 70;
            }
            return bottom;
        }""")

        # 底部边界：排除输入框和追问建议框
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

        # ── 2. 找滚动容器，打标记，获取总高度 ────────────
        info = page.evaluate("""() => {
            // 找 scrollHeight 最大的可滚动容器
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

        # ── 3. 查找关键词位置 ───────────────────────────
        keyword_marks = []
        if brand_keywords:
            keyword_marks = find_keyword_positions(page, brand_keywords)
            if keyword_marks:
                print(f"    发现 {len(keyword_marks)} 处品牌词曝光")

        # 步长 = clip_h（每次滚动一个视口高度）
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

        # ── 3. 按坐标步进截图（GoFullPage 同款）─────────
        # 每帧记录截图时的实际 scrollTop
        frames: list[tuple[int, Image.Image]] = []  # (actual_scroll, img)
        pos = 0

        while True:
            _scroll_to(pos)
            time.sleep(0.4)
            actual = _get_scroll()
            img    = _snap()
            frames.append((actual, img))
            print(f"(s={actual})", end="", flush=True)

            # 到底判断：实际 scrollTop + clientHeight >= scrollHeight
            if actual + client_h >= total_scroll - 2:
                break
            if pos + step > total_scroll:
                break
            pos += step

        # ── 4. 按坐标直接拼接（无图像匹配）─────────────
        if not frames:
            print("    截图: 未获取到帧")
            return ""

        if len(frames) == 1:
            frames[0][1].save(shot_path, optimize=True, quality=95)
            print(f"\n    截图: 1 帧，总高 {frames[0][1].height}px")
            return shot_path

        # 计算画布总高度：
        # 第一帧完整高度 + 后续每帧的新增高度（= 本帧 scrollTop - 上一帧 scrollTop）
        total_h = frames[0][1].height
        for i in range(1, len(frames)):
            new_px = frames[i][0] - frames[i-1][0]  # 本次实际滚动了多少 px
            new_px = max(new_px, 1)
            new_px = min(new_px, frames[i][1].height)
            total_h += new_px

        canvas = Image.new("RGB", (frames[0][1].width, total_h), (255, 255, 255))

        # 第一帧完整粘贴
        canvas.paste(frames[0][1], (0, 0))
        y_offset = frames[0][1].height

        for i in range(1, len(frames)):
            new_px = frames[i][0] - frames[i-1][0]
            new_px = max(new_px, 1)
            new_px = min(new_px, frames[i][1].height)
            # 从当前帧顶部跳过与上一帧重叠的部分，取剩余新内容
            img_h   = frames[i][1].height
            overlap = img_h - new_px  # 与上一帧重叠的像素数
            cropped = frames[i][1].crop((0, overlap, frames[i][1].width, img_h))
            canvas.paste(cropped, (0, y_offset))
            y_offset += cropped.height

        # ── 5. 绘制品牌词红框 ───────────────────────────
        if keyword_marks:
            canvas = draw_marks(canvas, keyword_marks, clip_x, clip_y)

        canvas.save(shot_path, optimize=True, quality=95)
        print(f"\n    截图: {len(frames)} 帧拼接，总高 {total_h}px")
        return shot_path

    except Exception as e:
        print(f"    截图失败: {e}")
        return ""
