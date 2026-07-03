"""
DeepSeek https://chat.deepseek.com/
"""
import os
import re
import time
import random
import tempfile
from PIL import Image
from playwright.sync_api import Page, TimeoutError as PWTimeout
import config

URL = "https://chat.deepseek.com/"


def query(page: Page, question: str, brand_keywords: list = None, enable_screenshot: bool = True, output_dir: str = None) -> tuple[str, list]:
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
    for sel in ["textarea", "div[contenteditable='true']", "[class*='input']", "[role='textbox']"]:
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
        "[class*='send']",
        "[class*='submit']",
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
    """等待 DeepSeek 回答完成：文字停止增长（连续 4 次 × 2 秒无变化）"""
    print("    等待 DeepSeek 回答", end="", flush=True)
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
    """DeepSeek 引用：点击「已阅读 N 个网页」展开，逐步滚动抓取引用链接"""
    try:
        refs = []
        expected = 0

        # 找「已阅读 N 个网页」按钮
        try:
            all_els = page.evaluate("""() => {
                const results = [];
                // 增加更多可能的特征，比如包含图标的容器
                document.querySelectorAll('*').forEach(el => {
                    const t = (el.innerText || '').trim();
                    const r = el.getBoundingClientRect();
                    // 修改正则：支持 "36 个网页"、"已阅读 36 个网页"、"36 search results" 等
                    if (/(\d+)\s*(个网页|search results)/.test(t) && r.width > 0 && r.height > 0
                            && t.length < 50) {
                        results.push({x: r.x + r.width/2, y: r.y + r.height/2, text: t, el: el});
                    }
                });
                return results;
            }""")
            if all_els:
                last = all_els[-1]
                print(f"    找到引用按钮: '{last['text']}' at ({last['x']}, {last['y']})")
                # 提取数量
                import re
                m = re.search(r'(\d+)', last['text'])
                if m:
                    expected = int(m.group(1))
                
                # 点击展开：先移动再点击，更模拟真人
                page.mouse.move(last['x'], last['y'])
                time.sleep(0.5)
                page.mouse.click(last['x'], last['y'])
                time.sleep(3) # 等待面板弹出和加载
                print(f"    点击展开引用面板，预期 {expected} 篇")
        except Exception as e:
            print(f"    查找/点击引用按钮失败: {e}")
            pass

        # 找到引用面板的滚动容器
        scroll_container_info = page.evaluate("""() => {
            let bestContainer = null;
            let maxScrollHeight = 0;
            
            document.querySelectorAll('*').forEach(el => {
                const cs = window.getComputedStyle(el);
                const r = el.getBoundingClientRect();
                
                if ((cs.overflowY === 'auto' || cs.overflowY === 'scroll') &&
                    el.scrollHeight > el.clientHeight + 20 &&
                    r.width > 200 && r.height > 100 &&
                    r.left > 100) {
                    
                    const linkCount = el.querySelectorAll('a[href^="http"]').length;
                    if (linkCount > 0 && el.scrollHeight > maxScrollHeight) {
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
            refs = _extract_references_deepseek(page)
            if refs:
                print(f"    引用参考: {len(refs)}/{expected} 篇")
            else:
                print("    引用参考: 未找到")
            return refs

        # 逐步滚动引用面板
        scroll_height = scroll_container_info['scrollHeight']
        client_height = scroll_container_info['clientHeight']
        scroll_step = client_height // 2
        current_scroll = 0
        
        print(f"    开始逐步滚动引用面板 (总高度: {scroll_height}px, 步长: {scroll_step}px)", end="", flush=True)
        
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
            
            current_refs = _extract_references_deepseek(page)
            
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
        
        final_refs = _extract_references_deepseek(page)
        for ref in final_refs:
            if ref['url'] not in seen_refs:
                seen_refs.add(ref['url'])
                refs.append(ref)

        if refs:
            print(f"    引用参考: {len(refs)}/{expected} 篇")
        else:
            print("    引用参考: 未找到")

        return refs

    except Exception as e:
        print(f"    引用参考抓取失败: {e}")
        return []


def _extract_references_deepseek(page: Page) -> list:
    """从当前页面提取引用链接（DeepSeek专用）"""
    return page.evaluate("""() => {
        const results = [];
        const seen = new Set();
        
        // 优先从已标记的滚动容器抓取，如果没有则从全局抓取
        const container = document.querySelector('[data-ref-container="1"]');
        const root = container || document;
        
        root.querySelectorAll('a[href]').forEach(el => {
            const href = el.getAttribute('href') || '';
            let text = (el.innerText || el.textContent || '').trim();
            
            if (!href.startsWith('http') || seen.has(href)) return;
            // 排除 deepseek 自身的链接
            if (href.includes('deepseek.com') || href.includes('chat.deepseek')) return;
            
            // 如果文本太短或只有数字（可能是引用下标），尝试向上找更完整的标题
            if (!text || text.length < 3 || text.match(/^[-\\d\\s\\.]+$/)) {
                let cur = el.parentElement;
                // 向上查找最多5层，寻找包含较长文本的容器
                for (let i = 0; i < 5 && cur; i++) {
                    const t = (cur.innerText || '').trim();
                    if (t.length > 10 && !t.match(/^[-\\d\\s\\.]+$/)) {
                        // 取第一行作为标题，避免抓到太多内容
                        text = t.split('\\n')[0].slice(0, 200);
                        break;
                    }
                    cur = cur.parentElement;
                }
            }
            
            // 兜底：如果还是没标题，用 URL 截断
            if (!text || text.length < 3) {
                text = href;
            }
            
            text = text.slice(0, 200).trim();
            seen.add(href);
            results.push({title: text, url: href, content: ''});
        });
        
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
            // 如果没有检测到固定头部，使用默认值（DeepSeek通常有60-80px的头部）
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
            frames[0][1].save(shot_path)
            print(f"\n    截图: 1 帧，总高 {frames[0][1].height}px")
            return shot_path

        # 计算画布总高度：
        # 第一帧完整高度 + 后续每帧的新增高度（= 本帧 scrollTop - 上一帧 scrollTop）
        # new_px 即本次实际滚动量，也是每帧中真正新增的像素行数
        # overlap = img_h - new_px，即与上一帧底部重叠的行数，拼接时从顶部跳过
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

        canvas.save(shot_path)
        print(f"\n    截图: {len(frames)} 帧拼接，总高 {total_h}px")
        return shot_path

    except Exception as e:
        print(f"    截图失败: {e}")
        return ""
