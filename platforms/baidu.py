"""
百度AI助手 https://chat.baidu.com/
"""
import os
import re
import time
import random
import tempfile
from PIL import Image
from playwright.sync_api import Page, TimeoutError as PWTimeout
import config

URL = "https://chat.baidu.com/"


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

    # 智能等待参考信息区域加载（参考doubao.py）
    print("    等待参考信息区域加载...")
    ref_loaded = False
    for i in range(20):  # 最多等待10秒
        time.sleep(0.5)
        ref_check = page.evaluate("""() => {
            const els = document.querySelectorAll('*');
            for (const el of els) {
                const t = el.innerText || '';
                if (/共参考\\s*\\d+\\s*篇资料/.test(t) && t.length < 200) {
                    const r = el.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) {
                        return {found: true, text: t};
                    }
                }
            }
            // 检查是否有外部链接
            const links = document.querySelectorAll('a[href^="http"]');
            let refLinks = 0;
            for (const l of links) {
                const href = l.getAttribute('href') || '';
                if (!href.includes('baidu.com') && !href.includes('bdstatic.com') && href.length > 20) {
                    refLinks++;
                }
            }
            return {found: false, refLinks: refLinks};
        }""")
        
        if ref_check.get('found') or ref_check.get('refLinks', 0) > 0:
            print(f"    参考信息区域已加载（检测轮次 {i+1}）")
            ref_loaded = True
            break
        elif i % 4 == 3:
            print(f"    等待中...（{i+1}/20 轮）")
    
    if not ref_loaded:
        print("    警告: 参考信息区域未完全加载，继续尝试提取...")

    # 先抓取引用（在截图之前，避免截图操作影响引用面板状态）
    print("    开始提取参考信息...")
    references = _get_references(page)
    print(f"    参考信息提取完成，共 {len(references)} 条")

    # 根据配置决定是否截图
    if enable_screenshot:
        screenshot_path = _take_screenshot(page, question, brand_keywords, output_dir)
        if screenshot_path:
            print(f"    截图 -> {screenshot_path}")
    else:
        print("    跳过截图（禁用）")

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
    """等待百度回答完成：文字停止增长（连续 4 次 × 2 秒无变化）"""
    print("    等待百度回答", end="", flush=True)
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
    百度AI助手引用抓取（参考wenxin.py方法）：
    1. 滚动到页面顶部，点击「共参考X篇资料」展开
    2. 点击「搜索全球X篇资料」展开引用列表
    3. 逐条点击引用条目，捕获新标签页 URL
    """
    try:
        refs = []
        internal_domains = ['baidu.com', 'bdstatic.com', 'bcebos.com']

        # ── 0. 滚动到页面顶部（按钮在AI答案上方）───────────────
        print("    滚动到页面顶部...")
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(0.5)

        # ── 1. 点击「共参考X篇资料」按钮（使用JS查找，不受视口限制）─────
        print("    步骤1 - 查找「共参考X篇资料」按钮...")
        step1_result = page.evaluate("""() => {
            const allEls = document.querySelectorAll('*');
            for (const el of allEls) {
                const t = (el.innerText || '').trim();
                const r = el.getBoundingClientRect();
                if (/共参考\\s*\\d+\\s*篇资料/.test(t) && r.width > 50 && r.height > 20
                        && t.length < 200 && r.top > -100) {
                    el.scrollIntoView({ behavior: 'instant', block: 'center' });
                    return { found: true, text: t, top: r.top, left: r.left, width: r.width, height: r.height };
                }
            }
            return { found: false };
        }""")

        if step1_result.get('found'):
            print(f"    找到按钮: \"{step1_result['text']}\"")
            time.sleep(0.5)
            
            # 使用JS点击
            page.evaluate("""() => {
                const allEls = document.querySelectorAll('*');
                for (const el of allEls) {
                    const t = (el.innerText || '').trim();
                    if (/共参考\\s*\\d+\\s*篇资料/.test(t)) {
                        el.click();
                        break;
                    }
                }
            }""")
            print("    ✓ 点击「共参考X篇资料」成功")
            time.sleep(2)
        else:
            print("    未找到「共参考X篇资料」按钮，尝试备用...")
            refs = _extract_baidu_references(page, internal_domains)
            if refs:
                return refs

        # ── 2. 点击「搜索全球X篇资料」按钮（使用JS查找）───────────────
        print("    步骤2 - 查找「搜索全球X篇资料」按钮...")
        step2_result = page.evaluate("""() => {
            const allEls = document.querySelectorAll('*');
            for (const el of allEls) {
                const t = (el.innerText || '').trim();
                const r = el.getBoundingClientRect();
                if (/搜索全球\\s*\\d+\\s*篇资料/.test(t) && r.width > 50 && r.height > 20
                        && t.length < 200 && r.top > -100) {
                    el.scrollIntoView({ behavior: 'instant', block: 'center' });
                    return { found: true, text: t };
                }
            }
            return { found: false };
        }""")

        if step2_result.get('found'):
            print(f"    找到按钮: \"{step2_result['text']}\"")
            time.sleep(0.5)
            
            # 使用JS点击
            page.evaluate("""() => {
                const allEls = document.querySelectorAll('*');
                for (const el of allEls) {
                    const t = (el.innerText || '').trim();
                    if (/搜索全球\\s*\\d+\\s*篇资料/.test(t)) {
                        el.click();
                        break;
                    }
                }
            }""")
            print("    ✓ 点击「搜索全球X篇资料」成功")
            time.sleep(3)
        else:
            print("    未找到「搜索全球X篇资料」按钮")

        # ── 3. 查找引用条目并点击（参考wenxin.py方法）───────────
        print("    步骤3 - 查找引用条目...")
        
        reference_items = page.locator("[class*='reference']").all()
        if not reference_items:
            reference_items = page.locator("li[data-long-press-ext-info]").all()
        if not reference_items:
            reference_items = page.locator("li[data-long-press-menu-buttons]").all()

        if not reference_items:
            print("    未找到引用条目，尝试备用提取...")
            refs = _extract_baidu_references(page, internal_domains)
            if refs:
                return refs
            print("    引用参考: 未找到引用条目")
            return []

        print(f"    发现 {len(reference_items)} 条引用条目，开始抓取...")
        
        # 查找蓝色文字链接（用户要求点击蓝色的字）
        refs = _extract_baidu_references_by_click(page, internal_domains)

        # ── 5. 去重 ────────────────────────────────────────
        seen, unique = set(), []
        for r in refs:
            if r["url"] not in seen:
                seen.add(r["url"])
                unique.append(r)

        print(f"    引用参考: 共 {len(unique)} 篇")
        return unique

    except Exception as e:
        print(f"    引用参考抓取失败: {e}")
        return []


def _extract_references_from_answer(page: Page, internal_domains: list) -> list:
    """从答案文本中提取引用链接（最后备用方案）"""
    refs = []
    try:
        answer_text = _get_last_answer(page)
        if not answer_text:
            return refs

        lines = answer_text.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue

            url_pattern = r'https?://[^\s]+'
            urls = re.findall(url_pattern, line)
            for url in urls:
                url = url.rstrip(',.')
                if any(d in url for d in internal_domains):
                    continue
                if len(url) > 20:
                    title = re.sub(url_pattern, '', line).strip()[:120]
                    if not title:
                        title = url[:60]
                    refs.append({"title": title, "url": url, "content": ""})
                    print(f"    OK [{len(refs)}] {title[:40]} -> {url[:70]}")

    except Exception as e:
        print(f"    _extract_references_from_answer 失败: {e}")

    return refs


def _extract_baidu_references(page: Page, internal_domains: list) -> list:
    """从展开的引用面板中提取引用链接（从li元素的data-long-press-ext-info属性中提取）"""
    refs = []
    try:
        # 先诊断：打印第一个li元素的data-long-press-ext-info属性值
        diagnostic_info = page.evaluate("""() => {
            const liEls = document.querySelectorAll('li[data-long-press-ext-info]');
            if (liEls.length > 0) {
                const first = liEls[0];
                return {
                    count: liEls.length,
                    firstAttr: first.getAttribute('data-long-press-ext-info'),
                    firstClass: first.className,
                    firstText: first.innerText.substring(0, 100)
                };
            }
            return { count: 0, firstAttr: null, firstClass: null, firstText: null };
        }""")
        
        print(f"    诊断: li[data-long-press-ext-info] 数量={diagnostic_info.get('count', 0)}")
        if diagnostic_info.get('firstAttr'):
            print(f"    第一个元素属性: {diagnostic_info['firstAttr'][:150]}")
            print(f"    第一个元素class: {diagnostic_info.get('firstClass', '')}")
            print(f"    第一个元素文本: {diagnostic_info.get('firstText', '')[:50]}")
        
        refs_data = page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('li[data-long-press-ext-info]').forEach(el => {
                const extInfo = el.getAttribute('data-long-press-ext-info');
                if (extInfo) {
                    try {
                        const data = JSON.parse(extInfo);
                        if (Array.isArray(data) && data.length > 0) {
                            const item = data[0];
                            if (item && item.link && item.linkTitle) {
                                results.push({
                                    url: item.link,
                                    title: item.linkTitle
                                });
                            } else if (item && item.url && item.linkTitle) {
                                results.push({
                                    url: item.url,
                                    title: item.linkTitle
                                });
                            } else if (item && item.link) {
                                results.push({
                                    url: item.link,
                                    title: item.title || item.text || ''
                                });
                            } else if (item && item.url) {
                                results.push({
                                    url: item.url,
                                    title: item.title || item.text || ''
                                });
                            }
                        } else if (data && data.link && data.linkTitle) {
                            results.push({
                                url: data.link,
                                title: data.linkTitle
                            });
                        } else if (data && data.url && data.linkTitle) {
                            results.push({
                                url: data.url,
                                title: data.linkTitle
                            });
                        } else if (data && data.link) {
                            results.push({
                                url: data.link,
                                title: data.title || data.text || ''
                            });
                        } else if (data && data.url) {
                            results.push({
                                url: data.url,
                                title: data.title || data.text || ''
                            });
                        }
                    } catch (e) {}
                }
            });
            return results;
        }""")
        
        for ref in refs_data[:50]:
            url = ref['url']
            title = ref['title']
            
            if not url or not title:
                continue
            if any(d in url for d in internal_domains):
                continue
            
            refs.append({"title": title[:120], "url": url, "content": ""})
            print(f"    OK [{len(refs)}] {title[:40]} -> {url[:70]}")
            
            if len(refs) >= 30:
                break
                
    except Exception as e:
        print(f"    _extract_baidu_references 失败: {e}")
    
    return refs


def _extract_baidu_references_fallback(page: Page, internal_domains: list) -> list:
    """备用：直接查找页面上所有可见的外部链接"""
    refs = []
    try:
        # 查找包含"来源"、"参考"、"引用"等关键词的容器内的链接
        refs_data = page.evaluate("""() => {
            const results = [];
            const containers = document.querySelectorAll('*');
            
            for (const container of containers) {
                const t = container.innerText || '';
                if (t.includes('来源') || t.includes('参考') || t.includes('引用') || t.includes('资料')) {
                    const links = container.querySelectorAll('a[href^="http"]');
                    for (const link of links) {
                        const href = link.getAttribute('href') || '';
                        const text = link.innerText || link.getAttribute('title') || '';
                        if (href.length > 20) {
                            results.push({
                                href: href,
                                text: text.substring(0, 200)
                            });
                        }
                    }
                }
            }
            return results;
        }""")
        
        for ref in refs_data[:50]:
            url = ref['href']
            title = ref['text']
            
            if any(d in url for d in internal_domains):
                continue
            
            refs.append({"title": title[:120], "url": url, "content": ""})
            print(f"    OK [{len(refs)}] {title[:40]} -> {url[:70]}")
            
            if len(refs) >= 30:
                break
                
    except Exception as e:
        print(f"    _extract_baidu_references_fallback 失败: {e}")
    
    return refs


def _extract_baidu_references_by_click(page: Page, internal_domains: list) -> list:
    """通过点击蓝色文字获取引用（用户要求）"""
    refs = []
    try:
        # 查找蓝色文字元素
        blue_links = page.evaluate("""() => {
            const results = [];
            const allEls = document.querySelectorAll('*');
            
            for (const el of allEls) {
                if (el.tagName === 'SCRIPT' || el.tagName === 'STYLE') continue;
                
                const text = (el.innerText || '').trim();
                if (!text || text.length < 3) continue;
                
                const r = el.getBoundingClientRect();
                if (r.width < 10 || r.height < 10) continue;
                
                const cs = window.getComputedStyle(el);
                const color = cs.color || '';
                const textDecoration = cs.textDecoration || '';
                
                if (textDecoration.includes('underline') || color.includes('0, 0, 255') || 
                    color.includes('0, 102, 204') || color.includes('0, 51, 204') ||
                    color.includes('0, 85, 170') || color.includes('26, 115, 232') ||
                    color.includes('66, 133, 244') || color.includes('#0000ff') ||
                    color.includes('#0066cc') || color.includes('#0055aa')) {
                    results.push({
                        text: text.substring(0, 100),
                        x: r.left + r.width / 2,
                        y: r.top + r.height / 2,
                        tag: el.tagName
                    });
                }
            }
            
            return results.slice(0, 30);
        }""")
        
        print(f"    找到 {len(blue_links)} 个蓝色文字元素")
        
        for i, link in enumerate(blue_links):
            try:
                title = link.get('text', '')[:120]
                x = link.get('x', 0)
                y = link.get('y', 0)
                
                if not title or len(title) < 3:
                    continue
                
                print(f"    [{i+1}] 点击蓝色文字 ({x:.0f}, {y:.0f}) - {title[:30]}")
                
                with page.context.expect_page(timeout=6000) as new_page_info:
                    page.mouse.click(x, y)
                
                new_page = new_page_info.value
                try:
                    new_page.wait_for_load_state("domcontentloaded", timeout=8000)
                except Exception:
                    pass
                
                new_url = new_page.url
                new_title = new_page.title()
                new_page.close()
                page.bring_to_front()
                time.sleep(0.3)
                
                if (new_url and new_url.startswith('http')
                        and not any(d in new_url for d in internal_domains)):
                    refs.append({"title": new_title[:120] if new_title else title[:120], "url": new_url, "content": ""})
                    print(f"    OK [{len(refs)}] {title[:40]} -> {new_url[:70]}")
                    if len(refs) >= 30:
                        break
            
            except Exception as e:
                print(f"    跳过: {str(e)[:60]}")
                continue
        
        if not refs:
            print("    蓝色文字点击方式失败，尝试属性提取...")
            refs = _extract_baidu_references(page, internal_domains)
    
    except Exception as e:
        print(f"    _extract_baidu_references_by_click 失败: {e}")
    
    return refs


def _take_screenshot(page: Page, question: str, brand_keywords: list = None, output_dir: str = None) -> str:
    """
    长截图：GoFullPage 同款算法。
    用 JS 给滚动容器打标记，按固定步长精确设置 scrollTop，
    每步截图后按坐标直接拼接，零图像匹配，零重复。
    """
    try:
        from utils import get_timestamp_dir, find_keyword_positions, draw_marks
        timestamp_dir = get_timestamp_dir()
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

        # 顶部边界：检测 fixed/sticky header 和置顶导航，避免每帧都截到 header 导致拼接时重复出现
        clip_y = page.evaluate("""() => {
            let bottom = 0;
            document.querySelectorAll('*').forEach(el => {
                const cs = window.getComputedStyle(el);
                const r  = el.getBoundingClientRect();
                
                if (cs.display === 'none') return;
                
                const isFixed = cs.position === 'fixed' || cs.position === 'sticky';
                const zIndex = parseInt(cs.zIndex) || 0;
                
                if ((isFixed || zIndex > 100) && r.top < 50 && r.width > 200 && r.height > 0 && r.height < 150) {
                    bottom = Math.max(bottom, Math.round(r.bottom));
                }
                
                if (r.top < 80 && r.bottom > 30 && r.width > 500 && r.height > 20 && r.height < 80) {
                    const text = el.innerText || '';
                    if (text.includes('百度首页') || text.includes('通知') || text.includes('网页') || 
                        text.includes('图片') || text.includes('更多')) {
                        bottom = Math.max(bottom, Math.round(r.bottom));
                    }
                }
            });
            return bottom;
        }""")

        # 底部边界：排除输入框、追问建议框和底部工具栏（任务、AI生图等）
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
            
            document.querySelectorAll('*').forEach(el => {
                const r  = el.getBoundingClientRect();
                const cs = window.getComputedStyle(el);
                if (cs.display === 'none') return;
                
                const text = el.innerText || '';
                if (r.bottom > vh * 0.5 && r.top > vh * 0.3 && r.width > 300 && r.height > 15 && r.height < 80) {
                    if (text.includes('任务') || text.includes('AI生图') || text.includes('AI志愿报告') || 
                        text.includes('AI写作') || text.includes('AI PPT') || text.includes('AI编程') || 
                        text.includes('更多') || text.includes('深度思考')) {
                        top = Math.min(top, r.top);
                    }
                }
            });
            
            return Math.round(top);
        }""")
        clip_h = min(input_top - 4, vp["height"] - 150) - clip_y
        clip_h = max(clip_h, 200)

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
