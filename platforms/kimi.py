"""
Kimi https://kimi.moonshot.cn/
"""
import os
import re
import time
import random
import tempfile
from PIL import Image
from playwright.sync_api import Page, TimeoutError as PWTimeout
import config

URL = "https://www.kimi.com/"


def query(page: Page, question: str, brand_keywords: list = None, enable_screenshot: bool = True, output_dir: str = None) -> tuple[str, list]:
    page.goto(URL, wait_until="domcontentloaded")
    try:
        page.wait_for_selector(
            "div[contenteditable='true'], textarea",
            timeout=15000, state="visible"
        )
    except PWTimeout:
        pass
    _random_wait(1000, 1500)

    editor = _find_editor(page)
    if not editor:
        raise RuntimeError("未找到输入框")

    editor.click()
    _random_wait(400, 700)
    _human_type(page, question)
    _random_wait(500, 800)

    _verify_and_send(page, editor, question)

    # 等待 URL 变化（确认进入对话）
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
    for sel in ["div[contenteditable='true']", "textarea"]:
        loc = page.locator(sel).first
        try:
            if loc.is_visible(timeout=3000):
                return loc
        except PWTimeout:
            continue
    return None


def _verify_and_send(page: Page, editor, question: str):
    for attempt in range(3):
        # contenteditable div 用 inner_text，textarea 用 input_value
        try:
            tag = editor.evaluate("el => el.tagName").lower()
            content = editor.input_value(timeout=1000) if tag == "textarea" \
                      else editor.inner_text(timeout=1000)
        except Exception:
            content = ""

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
        "[class*='send']",
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
    """等待 Kimi 回答完成：文字停止增长（连续 4 次 × 2 秒无变化）"""
    print("    等待 Kimi 回答", end="", flush=True)
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

    # 额外等待确保回答完全
    time.sleep(2)


def _get_last_answer(page: Page) -> str:
    try:
        return page.evaluate("""() => {
            let best = null, bestLen = 0;
            for (const el of document.querySelectorAll('div, article, section')) {
                const r = el.getBoundingClientRect();
                if (r.left < 250 || r.width < 300) continue;
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
    Kimi 引用来源：通常显示为「引用来源 N」或「N 个来源」按钮，点击展开后逐步滚动抓取链接。
    """
    try:
        expected = 0
        clicked = False

        # 尝试找并点击来源按钮
        for sel in [
            "button:has-text('引用')",
            "text=/引用/",
            "text=/引用来源\\s*\\d+/",
            "text=/查看来源\\s*\\d+/",
            "text=/\\d+\\s*个来源/",
            "text=/来源\\s*\\d+/",
            "text=/来源/",
            "[class*='source']",
            "[class*='reference']",
            "[class*='cite']",
        ]:
            try:
                btn = page.locator(sel).last
                if btn.count() and btn.is_visible(timeout=2000):
                    txt = btn.inner_text(timeout=1000)
                    print(f"    找到按钮: {txt[:50]}")
                    m = re.search(r'(\d+)', txt)
                    if m:
                        expected = int(m.group(1))
                    btn.click()
                    clicked = True
                    print(f"    点击成功，等待展开...")
                    time.sleep(2)
                    break
            except Exception:
                continue

        if not clicked:
            print("    未找到可点击的来源按钮")
            return []

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
            refs = _extract_references_kimi(page)
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
            
            current_refs = _extract_references_kimi(page)
            
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
        
        final_refs = _extract_references_kimi(page)
        for ref in final_refs:
            if ref['url'] not in seen_refs:
                seen_refs.add(ref['url'])
                refs.append(ref)

        if refs:
            if expected > 0 and len(refs) < expected:
                print(f"    引用参考: 抓取到 {len(refs)} 篇 (预期 {expected} 篇，部分 URL 重复已去重)")
            else:
                print(f"    引用参考: 抓取到 {len(refs)} 篇")
        else:
            print("    引用参考: 未找到")
        
        return refs
    except Exception as e:
        print(f"    引用参考抓取失败: {e}")
        return []


def _extract_references_kimi(page: Page) -> list:
    """从当前页面提取引用链接（Kimi专用）"""
    return page.evaluate("""() => {
        const seen = new Set();
        const results = [];
        
        const elements = document.querySelectorAll('a[href^="http"], [data-url], [data-link]');
        elements.forEach(el => {
            let url = el.href || el.dataset.url || el.dataset.link;
            if (!url || !url.startsWith('http')) return;
            const r = el.getBoundingClientRect();
            if (r.width <= 0 || r.height <= 0) return;
            if (r.left < 150) return;
            if (seen.has(url)) return;
            if (url.includes('kimi.moonshot.cn')) return;
            seen.add(url);
            
            let title = (el.innerText || '').trim();
            if (!title || title.length < 2 || title.match(/^[-\\d\\s\\.\\/:]+$/)) {
                let cur = el.parentElement;
                for (let i = 0; i < 5 && cur; i++) {
                    const t = (cur.innerText || '').trim();
                    if (t.length > 5 && !t.match(/^[-\\d\\s\\.\\/:]+$/)) {
                        title = t.split('\\n')[0].slice(0, 100);
                        break;
                    }
                    cur = cur.parentElement;
                }
            }
            results.push({ title: title || url, url, content: '' });
        });
        return results;
    }""") or []


def _take_screenshot(page: Page, question: str, brand_keywords: list = None, output_dir: str = None) -> str:
    """
    长截图：GoFullPage 同款算法（与 DeepSeek 完全一致）
    用 JS 精确控制 scrollTop，按坐标直接拼接，零图像匹配，零重复。
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
            let leftBound = 165;
            Array.from(document.querySelectorAll('*')).forEach(el => {
                const r  = el.getBoundingClientRect();
                const cs = window.getComputedStyle(el);
                if (r.left < 10 && r.width > 100 && r.width < 300
                        && r.height > 400 && cs.display !== 'none') {
                    leftBound = Math.max(leftBound, Math.round(r.right) + 2);
                }
            });
            return leftBound;
        }""")
        vp     = page.viewport_size
        clip_w = vp["width"] - clip_x

        # 顶部边界：检测 fixed/sticky header 和追问建议框
        clip_y = page.evaluate("""() => {
            let bottom = 0;
            document.querySelectorAll('*').forEach(el => {
                const cs = window.getComputedStyle(el);
                const r  = el.getBoundingClientRect();
                
                // 1. 检测 fixed/sticky 元素
                if ((cs.position === 'fixed' || cs.position === 'sticky')
                        && r.top < 20 && r.width > 200 && r.height > 0
                        && r.height < 120 && cs.display !== 'none') {
                    bottom = Math.max(bottom, Math.round(r.bottom));
                }
                
                // 2. 检测追问建议框（Kimi 特有）
                // 特征：在顶部附近、有边框、包含刷新按钮等
                const text = (el.innerText || '').trim();
                if (r.top < 150 && r.top > 0 
                        && r.width > 300 && r.height > 30 && r.height < 100
                        && cs.display !== 'none'
                        && (text.includes('?') || text.includes('？') 
                            || text.includes('事件') || text.includes('新闻')
                            || el.querySelector('[class*="refresh"], [class*="reload"]'))) {
                    // 可能是追问建议框
                    bottom = Math.max(bottom, Math.round(r.bottom) + 10);
                }
            });
            return bottom;
        }""")

        # 底部边界：排除输入框和追问建议
        input_top = page.evaluate("""() => {
            const vh = window.innerHeight;
            let top = vh;
            document.querySelectorAll(
                'textarea, div[contenteditable="true"], [class*="input"], [class*="composer"], [class*="suggest"], [class*="footer"], [class*="follow"]'
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
            const candidates = [];
            
            document.querySelectorAll('*').forEach(el => {
                const cs = window.getComputedStyle(el);
                const r  = el.getBoundingClientRect();
                
                // 必须是可滚动的
                if (cs.overflowY !== 'auto' && cs.overflowY !== 'scroll') return;
                
                // 必须有足够的滚动空间
                if (el.scrollHeight <= el.clientHeight + 50) return;
                
                // 必须有合理的尺寸
                if (r.width < 300 || r.height < 200) return;
                
                candidates.push({
                    tag: el.tagName,
                    className: el.className?.slice(0, 30),
                    scrollHeight: el.scrollHeight,
                    clientHeight: el.clientHeight,
                    width: Math.round(r.width),
                    height: Math.round(r.height),
                });
                
                if (el.scrollHeight > bestH) {
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
                    candidates: candidates,
                };
            }
            
            window.scrollTo(0, 0);
            return {
                found: false,
                scrollHeight: document.documentElement.scrollHeight,
                clientHeight: window.innerHeight,
                candidates: candidates,
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

        # 调试信息
        print(f"    [调试] 滚动容器: {'找到' if found else '未找到'}")
        print(f"    [调试] 总高度: {total_scroll}px, 视口: {client_h}px")
        if "candidates" in info and info["candidates"]:
            print(f"    [调试] 候选容器: {len(info['candidates'])} 个")
            for c in info["candidates"][:3]:
                print(f"      - {c['tag']}.{c['className']}: scroll={c['scrollHeight']}, client={c['clientHeight']}")

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

        print(f"    开始截图拼接（GoFullPage 算法）", end="", flush=True)
        print(f"\n    [调试] clip_x={clip_x}, clip_y={clip_y}, clip_w={clip_w}, clip_h={clip_h}")
        print(f"    [调试] step={clip_h}, total={total_scroll}")

        while True:
            _scroll_to(pos)
            time.sleep(0.4)
            actual = _get_scroll()
            img    = _snap()
            frames.append((actual, img))
            
            # 详细的调试信息
            if len(frames) <= 3 or len(frames) % 5 == 0:
                print(f"\n    [调试] 帧{len(frames)}: 目标={pos}, 实际={actual}, 差值={actual-pos if len(frames)>1 else 0}", end="")
            else:
                print(".", end="", flush=True)

            # 到底判断：实际 scrollTop + clientHeight >= scrollHeight
            if actual + client_h >= total_scroll - 2:
                print(f"\n    [调试] 到达底部: {actual} + {client_h} >= {total_scroll}")
                break
            if pos + step > total_scroll:
                print(f"\n    [调试] 超出范围: {pos} + {step} > {total_scroll}")
                break
            pos += step

        print()  # 换行

        # ── 4. 按坐标直接拼接（无图像匹配）─────────────
        if not frames:
            print("    截图: 未获取到帧")
            return ""

        if len(frames) == 1:
            frames[0][1].save(shot_path, optimize=True, quality=95)
            print(f"    截图完成: 1 帧，总高 {frames[0][1].height}px")
            return shot_path

        # 计算画布总高度：
        # 第一帧完整高度 + 后续每帧的新增高度（= 本帧 scrollTop - 上一帧 scrollTop）
        print(f"    [调试] 开始拼接 {len(frames)} 帧")
        total_h = frames[0][1].height
        for i in range(1, len(frames)):
            new_px = frames[i][0] - frames[i-1][0]  # 本次实际滚动了多少 px
            new_px = max(new_px, 1)
            new_px = min(new_px, frames[i][1].height)
            if i <= 3:
                print(f"    [调试] 帧{i}: scroll={frames[i][0]}, prev={frames[i-1][0]}, new_px={new_px}")
            total_h += new_px

        # 内存检查
        max_height = 65000  # PIL 限制
        if total_h > max_height:
            print(f"    警告: 总高度 {total_h}px 超过限制，将裁剪到 {max_height}px")
            total_h = max_height

        canvas = Image.new("RGB", (frames[0][1].width, total_h), (255, 255, 255))

        # 第一帧完整粘贴
        canvas.paste(frames[0][1], (0, 0))
        y_offset = frames[0][1].height
        print(f"    [调试] 帧0: 完整粘贴, y_offset={y_offset}")

        for i in range(1, len(frames)):
            if y_offset >= total_h:
                break
            new_px = frames[i][0] - frames[i-1][0]
            new_px = max(new_px, 1)
            new_px = min(new_px, frames[i][1].height)
            # 从当前帧顶部跳过与上一帧重叠的部分，取剩余新内容
            img_h   = frames[i][1].height
            overlap = img_h - new_px  # 与上一帧重叠的像素数
            cropped = frames[i][1].crop((0, overlap, frames[i][1].width, img_h))
            
            if i <= 3:
                print(f"    [调试] 帧{i}: img_h={img_h}, overlap={overlap}, cropped_h={cropped.height}, y_offset={y_offset}")
            
            # 检查是否超出画布
            if y_offset + cropped.height > total_h:
                cropped = cropped.crop((0, 0, cropped.width, total_h - y_offset))
            
            canvas.paste(cropped, (0, y_offset))
            y_offset += cropped.height

        # ── 5. 绘制品牌词红框 ───────────────────────────
        if keyword_marks:
            canvas = draw_marks(canvas, keyword_marks, clip_x, clip_y)

        canvas.save(shot_path, optimize=True, quality=95)
        print(f"    截图完成: {len(frames)} 帧，总高 {canvas.height}px")
        return shot_path

    except Exception as e:
        import traceback
        print(f"    截图失败: {e}")
        print(f"    详细错误: {traceback.format_exc()}")
        return ""
