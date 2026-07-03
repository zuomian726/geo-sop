"""
豆包 https://www.doubao.com/chat
"""
import os
import re
import time
import random
import tempfile
from PIL import Image
from playwright.sync_api import Page, TimeoutError as PWTimeout
import config

URL = "https://www.doubao.com/chat/"


def query(page: Page, question: str, brand_keywords: list = None, enable_screenshot: bool = True, output_dir: str = None) -> tuple[str, list]:
    # 随机等待，模拟人类打开页面的延迟
    _random_wait(1000, 2000)
    
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    
    # 模拟人类行为：随机移动鼠标
    try:
        page.mouse.move(random.randint(100, 500), random.randint(100, 400))
        _random_wait(300, 600)
    except:
        pass
    
    try:
        page.wait_for_selector(
            "textarea, div[contenteditable='true']",
            timeout=20000, state="visible"
        )
    except PWTimeout:
        pass
    _random_wait(1500, 2500)

    editor = _find_editor(page)
    if not editor:
        raise RuntimeError("未找到输入框")

    # 模拟人类：先移动鼠标到输入框附近
    try:
        box = editor.bounding_box()
        if box:
            page.mouse.move(
                box['x'] + box['width'] / 2 + random.randint(-20, 20),
                box['y'] + box['height'] / 2 + random.randint(-10, 10)
            )
            _random_wait(200, 400)
    except:
        pass
    
    editor.click()
    _random_wait(500, 900)
    
    # 模拟人类输入：有停顿、有快慢
    _human_type(page, question)
    _random_wait(600, 1000)

    _verify_and_send(page, editor, question)
    _random_wait(2000, 3500)
    _wait_for_answer(page)

    answer = _get_last_answer(page)

    # 智能等待参考信息区域加载
    print("    等待参考信息区域加载...")
    ref_loaded = False
    for i in range(20):  # 最多等待10秒（20 * 0.5）
        time.sleep(0.5)
        # 检查是否有参考相关的元素出现
        ref_check = page.evaluate("""() => {
            const els = document.querySelectorAll('*');
            for (const el of els) {
                const t = el.innerText || '';
                if (/参考\\s*\\d+/.test(t) && t.length < 200) {
                    const r = el.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) {
                        return {found: true, text: t};
                    }
                }
            }
            // 也检查是否有外部链接出现
            const links = document.querySelectorAll('a[href^="http"]');
            let refLinks = 0;
            for (const l of links) {
                const href = l.getAttribute('href') || '';
                if (!href.includes('doubao.com') && !href.includes('volces.com') && href.length > 20) {
                    refLinks++;
                }
            }
            return {found: false, refLinks: refLinks};
        }""")
        
        if ref_check.get('found') or ref_check.get('refLinks', 0) > 0:
            print(f"    参考信息区域已加载（检测轮次 {i+1}）")
            ref_loaded = True
            break
        elif i % 4 == 3:  # 每2秒打印一次进度
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
    """模拟人类输入：有快有慢，偶尔停顿"""
    for i, char in enumerate(text):
        page.keyboard.type(char)
        
        # 基础延迟：30-120ms
        base_delay = random.randint(30, 120)
        
        # 标点符号后停顿更久
        if char in '，。！？、；：':
            base_delay += random.randint(100, 300)
        
        # 每隔几个字符，随机长停顿（模拟思考）
        if i > 0 and i % random.randint(5, 10) == 0:
            base_delay += random.randint(200, 500)
        
        time.sleep(base_delay / 1000)


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
    """验证输入并发送消息"""
    # 确保输入框有内容
    content = ""
    for attempt in range(3):
        try:
            # 先尝试获取input_value（适用于textarea/input）
            content = editor.input_value(timeout=1000)
        except Exception:
            try:
                # 再尝试inner_text（适用于contenteditable）
                content = editor.inner_text(timeout=1000)
            except Exception as e:
                content = ""
        
        print(f"    输入验证(第{attempt+1}次): 内容长度={len(content.strip())}")
        
        if content.strip():
            break

        print(f"    输入框为空，重新输入(第{attempt+1}次)...")
        editor.click()
        _random_wait(300, 500)
        # 使用page.keyboard.type代替_human_type，确保输入更可靠
        page.keyboard.type(question)
        _random_wait(400, 600)

    # 如果仍然为空，尝试使用JavaScript直接设置内容
    if not content.strip():
        print("    警告: 常规输入失败，尝试使用JavaScript注入...")
        # 使用JSON编码安全传递数据
        import json
        question_json = json.dumps(question)
        page.evaluate(f"""
            (text) => {{
                const selector = 'textarea, div[contenteditable="true"], [role="textbox"], input[type="text"]';
                const el = document.querySelector(selector);
                if (el) {{
                    const tagName = el.tagName.toLowerCase();
                    if (tagName === 'textarea' || tagName === 'input') {{
                        el.value = text;
                    }} else if (el.isContentEditable || el.getAttribute('contenteditable') === 'true') {{
                        el.innerText = text;
                    }} else {{
                        el.textContent = text;
                    }}
                    // 触发必要的事件
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('keyup', {{ bubbles: true }}));
                    return true;
                }}
                return false;
            }}
        """, question_json)
        _random_wait(500, 800)

    # 尝试发送
    sent = False
    
    # 方法1：点击发送按钮
    send_selectors = [
        "button[aria-label*='发送']",
        "button[type='submit']",
        "[class*='send']",
        "[class*='submit']",
        "button:has(svg)",
        "[data-testid*='send']",
        ".send-btn",
    ]
    
    for sel in send_selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=1500) and btn.is_enabled(timeout=1500):
                print(f"    找到发送按钮: {sel}")
                btn.click()
                sent = True
                break
        except PWTimeout:
            continue

    # 方法2：按Enter键发送
    if not sent:
        print("    未找到发送按钮，尝试按Enter键...")
        editor.click()
        _random_wait(200, 300)
        # 有些页面需要Ctrl+Enter发送
        try:
            page.keyboard.press("Enter")
            sent = True
        except Exception as e:
            print(f"    Enter键发送失败: {e}")
            try:
                page.keyboard.press("Control+Enter")
                sent = True
            except Exception as e2:
                print(f"    Ctrl+Enter发送失败: {e2}")

    if sent:
        print("    ✓ 消息已发送")
    else:
        print("    ✗ 发送失败")


def _wait_for_answer(page: Page):
    """等待豆包回答完成：文字停止增长（连续 4 次 × 2 秒无变化）"""
    print("    等待豆包回答", end="", flush=True)
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
    豆包引用：点击「搜索 N 个关键词，参考 N 篇资料」按钮展开，抓取引用链接
    新版豆包UI：参考信息源在AI回答答案的顶部，点击展开所有参考信息源
    """
    try:
        refs = []
        expected = 0
        button_found = False

        # ===== 方法1：查找并点击展开按钮 =====
        try:
            # 获取页面所有可能的参考按钮
            all_els = page.evaluate("""() => {
                const results = [];
                document.querySelectorAll('*').forEach(el => {
                    const t = (el.innerText || '').trim();
                    const r = el.getBoundingClientRect();
                    // 匹配：数字 + (篇资料|个网页|篇文献|条结果)
                    if (/\\d+\\s*(篇资料|个网页|篇文献|条结果)/.test(t) && r.width > 0 && r.height > 0
                            && t.length < 200 && r.left > 50) {
                        results.push({
                            x: r.x + r.width/2, 
                            y: r.y + r.height/2, 
                            text: t, 
                            top: r.top, 
                            width: r.width, 
                            left: r.left,
                            bottom: r.bottom
                        });
                    }
                });
                // 优先选择宽度 >= 120 的元素（主内容区按钮），再按位置排序
                results.sort((a, b) => {
                    const aIsMain = a.width >= 120 ? 0 : 1;
                    const bIsMain = b.width >= 120 ? 0 : 1;
                    if (aIsMain !== bIsMain) return aIsMain - bIsMain;
                    return a.top - b.top;
                });
                return results;
            }""")
            
            if all_els:
                print(f"    阶段1 - 找到 {len(all_els)} 个候选按钮")
                for i, el in enumerate(all_els):
                    print(f"      [{i}] text=\"{el['text']}\", top={el['top']}, width={el['width']}, left={el.get('left', 0)}")
                
                # 选择包含"参考"字样的按钮，或者最宽的按钮
                target = None
                for el in all_els:
                    if "参考" in el['text']:
                        target = el
                        break
                if not target:
                    target = all_els[0]

                m = re.search(r'参考\s*(\d+)', target['text'])
                if not m:
                    m = re.search(r'(\d+)\s*(篇资料|个网页|篇文献)', target['text'])
                if not m:
                    m = re.search(r'(\d+)', target['text'])
                
                if m:
                    expected = int(m.group(1))
                
                # 点击展开：先移动鼠标，再点击
                print(f"    选中目标按钮: \"{target['text']}\"，预期 {expected} 篇参考资料")
                
                # 先滚动到按钮位置，确保在视口内
                print(f"    滚动到按钮位置...")
                
                # 使用 JavaScript 滚动到元素位置，确保它在视口内
                page.evaluate("""() => {
                    // 查找包含"参考"字样的元素
                    const allEls = document.querySelectorAll('*');
                    for (const el of allEls) {
                        const t = el.innerText || '';
                        const r = el.getBoundingClientRect();
                        // 匹配参考相关文本
                        if ((/参考\\s*\\d+/.test(t) || /\\d+\\s*篇/.test(t))
                            && r.width > 0 && r.height > 0 && t.length < 300) {
                            // 滚动元素到视口中央
                            el.scrollIntoView({ behavior: 'instant', block: 'center' });
                            return { found: true, top: r.top, y: window.scrollY };
                        }
                    }
                    return { found: false };
                }""")
                time.sleep(1)  # 等待滚动完成
                
                # 再次获取元素位置（滚动后位置可能改变）
                new_target_info = page.evaluate("""() => {
                    const allEls = document.querySelectorAll('*');
                    for (const el of allEls) {
                        const t = el.innerText || '';
                        const r = el.getBoundingClientRect();
                        if ((/参考\\s*\\d+/.test(t) || /\\d+\\s*篇/.test(t))
                            && r.width > 0 && r.height > 0 && t.length < 300 && r.top > -100 && r.top < window.innerHeight) {
                            return {
                                found: true,
                                x: r.x + r.width / 2,
                                y: r.y + r.height / 2,
                                top: r.top,
                                text: t.substring(0, 50)
                            };
                        }
                    }
                    return { found: false };
                }""")
                
                if new_target_info.get('found'):
                    target_x = new_target_info['x']
                    target_y = new_target_info['y']
                    print(f"    元素当前位置: ({target_x:.0f}, {target_y:.0f})")
                else:
                    # 备用方案：使用之前的坐标
                    target_x = target['x']
                    target_y = target['y']
                    print(f"    使用备用坐标: ({target_x:.0f}, {target_y:.0f})")
                
                # 使用 locator.click() 替代低级鼠标点击，提高可靠性
                print(f"    点击展开按钮...")
                try:
                    # 方法1：使用文本选择器定位按钮
                    button_text = target.get('text', '').strip()[:50]
                    button_locator = page.locator('button', has_text=re.compile(re.escape(button_text)[:30]))
                    if button_locator.is_visible(timeout=2000):
                        button_locator.click(timeout=5000)
                        print(f"    ✓ 使用文本选择器点击成功")
                    else:
                        # 方法2：使用坐标附近的元素
                        print(f"    尝试使用坐标附近的元素点击...")
                        page.click(f'[data-testid]', position={'x': target_x, 'y': target_y})
                except Exception as e:
                    print(f"    locator.click() 失败，回退到 mouse.click(): {e}")
                    page.mouse.click(target_x, target_y)
                
                # 等待展开动画完成（豆包UI通常需要1-2秒）
                print(f"    等待展开动画完成...")
                time.sleep(2)
                
                # 等待网络请求完成（最多等待8秒）
                print(f"    等待参考链接网络请求完成...")
                wait_done = False
                for _ in range(16):  # 16 * 0.5 = 8秒
                    time.sleep(0.5)
                    # 检查是否有新的网络请求完成
                    new_request_count = page.evaluate("""() => {
                        const links = document.querySelectorAll('a[href^="http"]');
                        let refCount = 0;
                        links.forEach(l => {
                            const href = l.getAttribute('href') || '';
                            if (!href.includes('doubao.com') && !href.includes('volces.com') && href.length > 20) {
                                refCount++;
                            }
                        });
                        return refCount;
                    }""")
                    
                    # 如果找到外部链接，认为加载完成
                    if new_request_count > 0:
                        print(f"    检测到 {new_request_count} 个外部链接，网络请求可能已完成")
                        wait_done = True
                        break
                    
                    # 检查是否展开（查找展开后的容器）
                    is_expanded = page.evaluate("""() => {
                        const els = document.querySelectorAll('*');
                        for (const el of els) {
                            const t = el.innerText || '';
                            // 查找展开后的参考资料列表
                            if (t.includes('参考资料') || t.includes('来源') || t.includes('引用')) {
                                const links = el.querySelectorAll('a[href^="http"]');
                                if (links.length > 0) {
                                    return true;
                                }
                            }
                        }
                        return false;
                    }""")
                    
                    if is_expanded:
                        print(f"    检测到展开的参考资料容器")
                        wait_done = True
                        break
                
                # 如果没有检测到网络请求完成，继续等待一段时间
                if not wait_done:
                    print(f"    未检测到网络请求完成，继续等待...")
                    time.sleep(3)  # 额外等待
                
                # 额外等待并滚动页面，确保所有内容都可见
                print(f"    等待并滚动页面...")
                time.sleep(1)
                page.evaluate("""() => {
                    window.scrollTo(0, 0);
                }""")
                time.sleep(0.5)
                page.evaluate("""() => {
                    window.scrollBy(0, 200);
                }""")
                time.sleep(0.5)
                
                button_found = True
                print(f"    已点击展开按钮，等待完成")
        except Exception as e:
            print(f"    阶段1 - 查找/点击引用按钮失败: {e}")

        # 等待展开完成
        time.sleep(2)
        
        # 检查是否已展开，如果没有，尝试再次点击
        is_expanded = page.evaluate("""() => {
            const els = document.querySelectorAll('*');
            for (const el of els) {
                const t = el.innerText || '';
                if (t.includes('参考资料') || t.includes('来源') || t.includes('引用')) {
                    const links = el.querySelectorAll('a[href^="http"]');
                    if (links.length > 0) {
                        return true;
                    }
                }
            }
            return false;
        }""")
        
        if not is_expanded and target:
            print(f"    初次点击后未展开，尝试再次点击...")
            time.sleep(1)
            try:
                # 使用 locator.click() 进行再次点击
                button_text = target.get('text', '').strip()[:50]
                button_locator = page.locator('button', has_text=re.compile(re.escape(button_text)[:30]))
                if button_locator.is_visible(timeout=2000):
                    button_locator.click(timeout=5000)
                    print(f"    ✓ 再次点击成功")
                else:
                    page.mouse.click(target['x'], target['y'])
            except Exception as e:
                print(f"    再次点击失败: {e}")
                page.mouse.click(target['x'], target['y'])
            time.sleep(3)  # 等待更长时间
        
        # ===== 方法2：提取引用（主方法）=====
        if button_found:
            print("    阶段2 - 尝试从展开区域提取引用...")
            refs = _extract_references(page)
        
        # ===== 方法3：备用提取方式 =====
        if not refs:
            print("    阶段3 - 尝试备用提取方式（直接查找链接）...")
            refs = _extract_references_fallback(page)
        
        # ===== 方法4：提取所有可见外部链接 =====
        if not refs:
            print("    阶段4 - 尝试提取所有可见外部链接...")
            refs = _extract_all_external_links(page)
        
        # ===== 方法5：基于位置的链接提取（针对新版布局）=====
        if not refs and button_found:
            print("    阶段5 - 尝试基于位置的链接提取...")
            refs = _extract_references_by_position(page)
        
        # ===== 方法6：无限制链接提取（最后尝试）=====
        if not refs:
            print("    阶段6 - 尝试无限制链接提取...")
            refs = _extract_all_links_unrestricted(page)
        
        # ===== 方法7：逐个点击参考条目提取（用户建议方案）=====
        if not refs and button_found:
            print("    阶段7 - 尝试逐个点击参考条目提取...")
            refs = _extract_references_by_clicking(page)
        
        # ===== 结果处理 =====
        if refs:
            print(f"    引用参考: 成功提取到 {len(refs)} 篇 (预期 {expected} 篇)")
            # 如果数量不匹配，提供可能原因
            if expected > 0 and len(refs) < expected:
                print(f"    注意: 提取数量({len(refs)})少于预期({expected})，可能原因:")
                print(f"      - 部分链接重复被去重")
                print(f"      - 部分链接为豆包内部链接被过滤")
                print(f"      - 部分链接未完全加载")
            
            # 统计信息
            urls = [ref.get('url', '') for ref in refs]
            unique_urls = len(set(urls))
            print(f"    统计: 共 {len(refs)} 条，去重后 {unique_urls} 条")
            
            for i, ref in enumerate(refs[:5]):
                print(f"      [{i}] {ref.get('title', '')[:60]} -> {ref.get('url', '')[:60]}")
        else:
            print("    引用参考: 所有方法均未找到展开的链接")
            # 详细调试信息
            debug_info = page.evaluate("""() => {
                const info = {
                    links: [],
                    refSections: [],
                    pageHeight: window.innerHeight,
                    docHeight: document.documentElement.scrollHeight
                };
                document.querySelectorAll('a[href^="http"]').forEach(el => {
                    const r = el.getBoundingClientRect();
                    info.links.push({
                        text: (el.innerText || '').slice(0, 50),
                        href: el.getAttribute('href'),
                        top: r.top,
                        left: r.left,
                        width: r.width
                    });
                });
                document.querySelectorAll('div, section').forEach(el => {
                    const t = el.innerText || '';
                    if (t.includes('参考') || t.includes('来源')) {
                        const r = el.getBoundingClientRect();
                        info.refSections.push({
                            text: t.slice(0, 100),
                            top: r.top,
                            links: el.querySelectorAll('a[href^="http"]').length
                        });
                    }
                });
                return info;
            }""")
            print(f"    调试信息: 页面高度={debug_info.get('pageHeight', 0)}, 文档高度={debug_info.get('docHeight', 0)}")
            print(f"    页面共有 {len(debug_info.get('links', []))} 个外部链接")
            for i, link in enumerate(debug_info.get('links', [])[:5]):
                print(f"      [{i}] text=\"{link['text']}\", top={link['top']}, left={link['left']}")
            print(f"    找到 {len(debug_info.get('refSections', []))} 个参考区域")
            for i, sec in enumerate(debug_info.get('refSections', [])):
                print(f"      [{i}] text=\"{sec['text'][:50]}\", top={sec['top']}, links={sec['links']}")

        return refs

    except Exception as e:
        print(f"    引用参考抓取失败: {e}")
        import traceback
        print(f"    详细错误: {traceback.format_exc()}")
        return []


def _extract_references_by_position(page: Page) -> list:
    """
    基于位置的链接提取：针对新版豆包展开后的布局
    参考信息源在AI回答答案的顶部，展开后显示为列表形式
    """
    return page.evaluate("""() => {
        const results = [];
        const seen = new Set();
        
        // 查找所有包含"参考"或"来源"文本的元素的下方区域
        const refButtons = document.querySelectorAll('*');
        let refAreaTop = -1;
        let refAreaBottom = -1;
        
        for (const el of refButtons) {
            const t = el.innerText || '';
            if (/参考.*\\d+/.test(t) && t.length < 150) {
                const r = el.getBoundingClientRect();
                refAreaTop = r.bottom;  // 参考按钮下方开始
                refAreaBottom = refAreaTop + 1500;  // 向下1500px范围
                break;
            }
        }
        
        // 如果找到了参考区域，在该区域内查找链接
        if (refAreaTop > 0) {
            document.querySelectorAll('a[href^="http"]').forEach(link => {
                const href = link.getAttribute('href') || '';
                if (!href || seen.has(href)) return;
                if (href.includes('doubao.com') || href.includes('volces.com')) return;
                
                const r = link.getBoundingClientRect();
                if (r.top < refAreaTop || r.top > refAreaBottom) return;
                
                let title = (link.innerText || link.textContent || '').trim();
                if (!title || title.length < 3) {
                    const parent = link.parentElement;
                    if (parent) {
                        const parentText = parent.innerText || '';
                        const lines = parentText.split('\\n').map(s => s.trim()).filter(s => s.length > 3);
                        if (lines.length > 0) {
                            title = lines[0].substring(0, 100);
                        }
                    }
                }
                if (!title) title = href;
                
                seen.add(href);
                results.push({title: title, url: href, content: ''});
            });
        }
        
        return results;
    }""") or []


def _extract_all_external_links(page: Page) -> list:
    """
    通用外部链接提取：提取页面上所有可见的外部链接
    """
    return page.evaluate("""() => {
        const results = [];
        const seen = new Set();
        
        document.querySelectorAll('a[href^="http"]').forEach(link => {
            try {
                const href = link.getAttribute('href') || '';
                if (!href || seen.has(href)) return;
                if (href.includes('doubao.com') || href.includes('volces.com')) return;
                
                const r = link.getBoundingClientRect();
                if (r.width === 0 || r.height === 0) return;
                if (r.top < -100 || r.top > window.innerHeight + 100) return;
                
                let title = (link.innerText || link.textContent || '').trim();
                if (!title || title.length < 3) {
                    const parent = link.parentElement;
                    if (parent) {
                        const parentText = parent.innerText || '';
                        const lines = parentText.split('\\n').map(s => s.trim()).filter(s => s.length > 3);
                        if (lines.length > 0) {
                            title = lines[0].substring(0, 100);
                        }
                    }
                }
                if (!title) title = href;
                
                seen.add(href);
                results.push({title: title, url: href, content: ''});
            } catch(e) {}
        });
        
        return results;
    }""") or []


def _extract_all_links_unrestricted(page: Page) -> list:
    """
    无限制链接提取：提取页面上所有外部链接，不限制位置
    用于处理参考信息可能不在视口内的情况
    """
    return page.evaluate("""() => {
        const results = [];
        const seen = new Set();
        
        document.querySelectorAll('a[href^="http"]').forEach(link => {
            try {
                const href = link.getAttribute('href') || '';
                if (!href || seen.has(href)) return;
                if (href.includes('doubao.com') || href.includes('volces.com')) return;
                
                let title = (link.innerText || link.textContent || '').trim();
                if (!title || title.length < 2) {
                    const parent = link.parentElement;
                    if (parent) {
                        const parentText = parent.innerText || '';
                        const lines = parentText.split('\\n').map(s => s.trim()).filter(s => s.length > 3);
                        if (lines.length > 0) {
                            title = lines[0].substring(0, 150);
                        }
                    }
                }
                if (!title) title = href;
                
                seen.add(href);
                results.push({title: title, url: href, content: ''});
            } catch(e) {}
        });
        
        return results;
    }""") or []


def _extract_references_by_clicking(page: Page) -> list:
    """
    用户建议方案：逐个点击参考条目提取URL和标题
    新版豆包UI中，参考信息源在AI回答顶部，点击展开后显示为列表
    逐个点击每个条目来获取完整的URL和标题信息
    """
    refs = []
    try:
        # 首先获取所有参考条目
        items = page.evaluate("""() => {
            const items = [];
            // 查找包含参考信息的区域
            const containers = document.querySelectorAll('div, section');
            for (const container of containers) {
                const text = container.innerText || '';
                // 查找包含"参考"或"来源"的区域，且包含链接
                if ((text.includes('参考') || text.includes('来源')) && container.querySelectorAll('a[href^="http"]').length > 0) {
                    const links = container.querySelectorAll('a[href^="http"]');
                    for (let i = 0; i < links.length; i++) {
                        const link = links[i];
                        const r = link.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0) {
                            items.push({
                                x: r.x + r.width / 2,
                                y: r.y + r.height / 2,
                                text: (link.innerText || '').trim(),
                                href: link.getAttribute('href'),
                                index: i,
                                containerTop: container.getBoundingClientRect().top
                            });
                        }
                    }
                }
            }
            // 按位置排序（从上到下）
            items.sort((a, b) => a.containerTop - b.containerTop || a.index - b.index);
            return items;
        }""")
        
        if not items:
            print("      未找到参考条目")
            return []
        
        print(f"      找到 {len(items)} 个参考条目")
        
        # 逐个点击每个条目
        seen = set()
        for i, item in enumerate(items):
            try:
                # 使用 locator.click() 替代低级鼠标点击
                print(f"      [{i+1}] 尝试点击条目: {item.get('text', '')[:30]}")
                item_text = item.get('text', '').strip()
                
                try:
                    # 方法1：使用文本选择器定位
                    if item_text:
                        item_locator = page.locator('a', has_text=re.compile(re.escape(item_text)[:20]))
                        if item_locator.is_visible(timeout=1000):
                            item_locator.click(timeout=3000)
                            print(f"        ✓ 使用 locator.click() 成功")
                        else:
                            # 方法2：使用 href 选择器
                            if item.get('href'):
                                item_locator = page.locator(f'a[href="{item["href"]}"]')
                                item_locator.click(timeout=3000)
                                print(f"        ✓ 使用 href 选择器成功")
                            else:
                                raise Exception("无法定位元素")
                    else:
                        raise Exception("无文本内容")
                except Exception as e:
                    print(f"        locator.click() 失败({e})，回退到 mouse.click()")
                    page.mouse.move(item['x'], item['y'])
                    time.sleep(0.2)
                    page.mouse.click(item['x'], item['y'])
                
                time.sleep(0.5)
                
                # 再次获取该条目的信息（点击后可能会有变化）
                result = page.evaluate("""(index) => {
                    const containers = document.querySelectorAll('div, section');
                    for (const container of containers) {
                        const text = container.innerText || '';
                        if ((text.includes('参考') || text.includes('来源'))) {
                            const links = container.querySelectorAll('a[href^="http"]');
                            if (index < links.length) {
                                const link = links[index];
                                return {
                                    title: (link.innerText || link.textContent || '').trim(),
                                    url: link.getAttribute('href') || ''
                                };
                            }
                        }
                    }
                    return null;
                }""", i)
                
                if result and result.get('url') and result['url'] not in seen:
                    seen.add(result['url'])
                    refs.append({
                        'title': result.get('title', '') or f'参考来源 {i+1}',
                        'url': result['url'],
                        'content': ''
                    })
                    print(f"      [{i+1}] 成功提取: {result.get('title', '')[:40]} -> {result['url'][:60]}")
                
            except Exception as e:
                print(f"      [{i+1}] 点击失败: {e}")
                continue
        
        # 如果点击方式没有获取到，尝试直接提取所有可见链接
        if not refs:
            print("      点击方式未成功，尝试直接提取")
            refs = page.evaluate("""() => {
                const results = [];
                const seen = new Set();
                document.querySelectorAll('div, section').forEach(container => {
                    const text = container.innerText || '';
                    if ((text.includes('参考') || text.includes('来源'))) {
                        container.querySelectorAll('a[href^="http"]').forEach(link => {
                            const href = link.getAttribute('href');
                            if (href && !seen.has(href) && !href.includes('doubao.com') && !href.includes('volces.com')) {
                                seen.add(href);
                                results.push({
                                    title: (link.innerText || link.textContent || '').trim() || href,
                                    url: href,
                                    content: ''
                                });
                            }
                        });
                    }
                });
                return results;
            }""") or []
    
    except Exception as e:
        print(f"      _extract_references_by_clicking 失败: {e}")
    
    return refs


def _extract_references_fallback(page: Page) -> list:
    """
    备用引用提取方法：针对新版豆包展开后的结构
    参考信息源在AI回答答案的顶部，展开后显示为列表形式
    """
    return page.evaluate("""() => {
        const results = [];
        const seen = new Set();
        
        // 查找包含"参考资料"或"来源"的区域
        const refSections = document.querySelectorAll('section, div, article');
        for (const section of refSections) {
            const text = section.innerText || '';
            if (text.includes('参考资料') || text.includes('来源') || text.includes('引用')) {
                // 查找这个区域内的所有链接
                const links = section.querySelectorAll('a[href^="http"]');
                if (links.length > 0) {
                    for (const link of links) {
                        const href = link.getAttribute('href') || '';
                        if (!href || seen.has(href)) continue;
                        if (href.includes('doubao.com') || href.includes('volces.com')) continue;
                        
                        let title = (link.innerText || link.textContent || '').trim();
                        if (!title || title.length < 3) {
                            // 尝试获取父元素的文本
                            const parentText = link.parentElement?.innerText || '';
                            const lines = parentText.split('\\n').map(s => s.trim()).filter(s => s.length > 3);
                            if (lines.length > 0) {
                                title = lines[0].substring(0, 100);
                            }
                        }
                        if (!title) title = href;
                        
                        seen.add(href);
                        results.push({title: title, url: href, content: ''});
                    }
                }
            }
        }
        
        // 如果上面没找到，尝试通用方法：查找所有外部链接
        if (results.length === 0) {
            document.querySelectorAll('a[href^="http"]').forEach(link => {
                const href = link.getAttribute('href') || '';
                if (!href || seen.has(href)) return;
                if (href.includes('doubao.com') || href.includes('volces.com')) return;
                
                // 检查链接是否在主要内容区域（排除侧边栏）
                const r = link.getBoundingClientRect();
                if (r.left < 100 || r.width < 50) return;
                
                let title = (link.innerText || link.textContent || '').trim();
                if (!title || title.length < 3) {
                    const parentText = link.parentElement?.innerText || '';
                    const lines = parentText.split('\\n').map(s => s.trim()).filter(s => s.length > 3);
                    if (lines.length > 0) {
                        title = lines[0].substring(0, 100);
                    }
                }
                if (!title) title = href;
                
                seen.add(href);
                results.push({title: title, url: href, content: ''});
            });
        }
        
        return results;
    }""") or []


def _extract_references(page: Page) -> list:
    """
    从当前页面提取引用链接（辅助函数）
    优化：放宽过滤条件，增强标题抓取能力，专门针对展开后的列表区域
    """
    return page.evaluate("""() => {
        const results = [];
        const seen = new Set();
        
        // 1. 尝试定位展开后的参考资料容器
        // 豆包展开后通常会有一个包含多个条目的列表
        let container = null;
        const possibleContainers = document.querySelectorAll('div, section, article');
        for (const el of possibleContainers) {
            const t = el.innerText || '';
            if (t.includes('参考资料') || t.includes('来源') || t.includes('引用')) {
                const links = el.querySelectorAll('a[href^="http"]');
                if (links.length >= 2) {
                    container = el;
                    // 如果找到了包含多个链接的容器，优先从这里抓取
                    break;
                }
            }
        }

        const root = container || document;
        root.querySelectorAll('a[href]').forEach(el => {
            const href = el.getAttribute('href') || '';
            const r = el.getBoundingClientRect();
            
            // 基础过滤
            if (!href.startsWith('http') || seen.has(href)) return;
            if (r.width === 0 && r.height === 0) return;
            if (href.includes('doubao.com') || href.includes('volces.com')) return;
            
            // 标题抓取逻辑优化
            let title = '';
            
            // 优先看链接自身的文本
            let linkText = (el.innerText || el.textContent || '').trim();
            // 排除只包含数字、连字符、空格和点的文本
            const isJustSymbols = /^[-\\d\\s.]+$/.test(linkText);
            if (linkText && linkText.length > 5 && !isJustSymbols) {
                title = linkText;
            } else {
                // 如果链接文本太短或者是数字索引（如 [1]），查找附近的标题元素
                // 向上查找最近的包含较长文本的父级或兄弟级元素
                let cur = el.parentElement;
                for (let i = 0; i < 4 && cur; i++) {
                    const t = (cur.innerText || '').trim();
                    // 排除掉只包含数字和标点的文本
                    if (t.length > 8) {
                        // 取第一行非空文本作为标题
                        const lines = t.split('\\n').map(s => s.trim()).filter(s => s.length > 5);
                        if (lines.length > 0) {
                            title = lines[0].substring(0, 150);
                            break;
                        }
                    }
                    cur = cur.parentElement;
                }
            }

            if (!title) title = href; // 兜底使用 URL
            
            seen.add(href);
            results.push({title: title, url: href, content: ''});
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
        safe_name = re.sub(r'[\/:*?"<>|]', "_", question).strip(".")[:80]
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
            // 如果没有检测到固定头部，使用默认值（豆包通常有60-80px的头部）
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
            let best = null, bestH = 0, isReverse = false;
            document.querySelectorAll('*').forEach(el => {
                const cs = window.getComputedStyle(el);
                const r  = el.getBoundingClientRect();
                if ((cs.overflowY === 'auto' || cs.overflowY === 'scroll')
                        && el.scrollHeight > el.clientHeight + 50
                        && r.width > 300 && r.height > 200
                        && el.scrollHeight > bestH) {
                    bestH = el.scrollHeight;
                    best  = el;
                    // 检测是否是反向滚动容器
                    isReverse = cs.flexDirection === 'column-reverse' || 
                                cs.display === 'flex' && el.className.includes('reverse');
                }
            });
            if (best) {
                best.setAttribute('data-gofullpage-target', '1');
                // 反向容器：scrollTop=0是底部，需要滚动到负值看顶部
                // 正常容器：scrollTop=0是顶部
                if (isReverse) {
                    // 反向容器：滚动到最小值（最负）= 顶部
                    best.scrollTop = best.scrollTop - 999999;  // 强制滚到最顶
                } else {
                    best.scrollTop = 0;
                }
                return {
                    found: true,
                    scrollHeight: best.scrollHeight,
                    clientHeight: best.clientHeight,
                    isReverse: isReverse,
                };
            }
            window.scrollTo(0, 0);
            return {
                found: false,
                scrollHeight: document.documentElement.scrollHeight,
                clientHeight: window.innerHeight,
                isReverse: false,
            };
        }""")
        time.sleep(0.8)

        total_scroll = info["scrollHeight"]
        client_h     = info["clientHeight"]
        found        = info["found"]
        is_reverse   = info.get("isReverse", False)

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
                if is_reverse:
                    # 反向容器：从最负值开始，逐渐增加（向下滚动）
                    # pos=0 对应最顶部（最负的scrollTop）
                    # pos=total_scroll 对应最底部（scrollTop=0）
                    actual_scroll = -(total_scroll - client_h) + pos
                    page.evaluate(f"""() => {{
                        const el = document.querySelector('[data-gofullpage-target="1"]');
                        if (el) el.scrollTop = {actual_scroll};
                    }}""")
                else:
                    page.evaluate(f"""() => {{
                        const el = document.querySelector('[data-gofullpage-target="1"]');
                        if (el) el.scrollTop = {pos};
                    }}""")
            else:
                page.evaluate(f"window.scrollTo(0, {pos})")

        def _get_scroll() -> int:
            if found:
                actual = page.evaluate("""() => {
                    const el = document.querySelector('[data-gofullpage-target="1"]');
                    return el ? Math.round(el.scrollTop) : 0;
                }""")
                if is_reverse:
                    # 反向容器：将实际scrollTop转换为虚拟位置
                    # scrollTop最负 -> pos=0（顶部）
                    # scrollTop=0 -> pos=total_scroll（底部）
                    max_scroll = total_scroll - client_h
                    return max_scroll + actual
                return actual
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
            new_px = min(new_px, min(frames[i][1].height, clip_h))
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
        import traceback
        print(f"    截图失败: {e}")
        print(f"    详细错误: {traceback.format_exc()}")
        return ""
