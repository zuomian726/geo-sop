"""
文心一言 https://yiyan.baidu.com/
"""
import os
import re
import time
import random
import tempfile
from PIL import Image
from playwright.sync_api import Page, TimeoutError as PWTimeout
import config

URL = "https://yiyan.baidu.com/"


def query(page: Page, question: str, brand_keywords: list = None, enable_screenshot: bool = True, output_dir: str = None) -> tuple[str, list]:
    # ===== 页面加载 =====
    # 注意：不要在已有的页面上设置 viewport，这可能导致页面重新加载或布局问题
    # viewport 应该在创建 context 时设置，而不是在页面加载后
    
    # 页面加载重试机制
    max_retries = 3
    page_timeout = 60000  # 60秒超时
    
    for attempt in range(max_retries):
        try:
            print(f"    正在加载页面 (尝试 {attempt + 1}/{max_retries})...")
            
            # 使用 wait_until="domcontentloaded" 而不是 "networkidle"
            # networkidle 会等待所有网络请求完成，但文心一言页面可能有持续的网络请求
            # 导致永远不会满足条件，页面"一直在加载中"
            page.goto(URL, wait_until="domcontentloaded", timeout=page_timeout)
            
            # 等待页面初始化完成（给页面一些时间加载资源）
            print("    等待页面初始化...")
            time.sleep(3)
            
            # 检查页面是否真的加载成功
            title = page.title()
            print(f"    页面标题: '{title}'")
            
            # 检查登录状态
            login_status = _check_login_status(page)
            print(f"    登录状态: {login_status}")
            
            # 如果未登录，等待用户登录
            if "未登录" in login_status:
                print("    ⚠️ 检测到未登录状态，请在浏览器中登录文心一言")
                print("    ⚠️ 登录完成后按 Enter 键继续...")
                # 等待用户登录，每5秒检查一次
                login_timeout = 300  # 5分钟超时
                login_check_interval = 5  # 每5秒检查一次
                start_time = time.time()
                
                while time.time() - start_time < login_timeout:
                    time.sleep(login_check_interval)
                    login_status = _check_login_status(page)
                    print(f"    登录状态检查: {login_status}")
                    
                    if "已登录" in login_status:
                        print("    ✓ 用户已登录")
                        break
                
                # 再次检查登录状态
                login_status = _check_login_status(page)
                if "未登录" in login_status:
                    raise RuntimeError(f"登录超时 ({login_timeout}秒)，请手动登录后重试")
            
            # 页面标题应该包含"文心一言"
            if "文心一言" in title:
                print(f"    ✓ 页面加载成功")
                break
            
            # 如果标题不对，继续重试
            raise RuntimeError(f"页面标题不正确: '{title}'")
                
        except Exception as e:
            print(f"    页面加载失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                print(f"    等待3秒后重试...")
                time.sleep(3)
            else:
                raise RuntimeError(f"页面加载失败，已达最大重试次数 {max_retries}: {e}")
    
    # 检查是否有环境异常提示
    if _check_environment_warning(page):
        print("    检测到环境异常提示，尝试刷新页面...")
        page.reload(wait_until="domcontentloaded")
        _random_wait(3000, 4000)
    
    # 等待编辑器出现
    editor_found = False
    for attempt in range(5):
        try:
            page.wait_for_selector(
                "textarea, div[contenteditable='true']",
                timeout=10000, state="visible"
            )
            editor_found = True
            break
        except PWTimeout:
            print(f"    等待编辑器出现 (尝试 {attempt + 1}/5)...")
            _random_wait(2000, 3000)
    
    if not editor_found:
        print("    警告: 未找到编辑器，但继续尝试")
    
    _random_wait(1500, 2000)

    editor = _find_editor(page)
    if not editor:
        raise RuntimeError("未找到输入框")

    # 直接调用验证和发送函数（包含输入逻辑）
    _verify_and_send(page, editor, question)

    _random_wait(2000, 3000)

    _wait_for_answer(page)

    answer = _get_last_answer(page)

    # 根据配置决定是否截图
    if enable_screenshot:
        print(f"    开始截图... output_dir={output_dir}")
        screenshot_path = _take_screenshot(page, question, brand_keywords, output_dir)
        if screenshot_path:
            print(f"    截图 -> {screenshot_path}")
        else:
            print("    ✗ 截图失败")
    else:
        print("    跳过截图（禁用）")

    references = _get_references(page)

    return answer, references


# ── 内部工具 ────────────────────────────────────────────

def _check_login_status(page: Page) -> str:
    """检查文心一言的登录状态"""
    try:
        # 方法1：检查页面URL（未登录可能跳转到登录页）
        current_url = page.url
        if "login" in current_url.lower() or "passport" in current_url.lower():
            return "未登录（跳转到登录页）"
        
        # 方法2：检查登录按钮
        login_selectors = [
            "text=登录",
            "text=请登录",
            "button[class*='login']",
            "a[href*='login']",
        ]
        
        for selector in login_selectors:
            try:
                if page.locator(selector).count() > 0:
                    return "未登录（检测到登录按钮）"
            except Exception:
                continue
        
        # 方法3：检查用户信息元素
        user_selectors = [
            "[class*='avatar']",
            "[class*='user']",
            "[class*='profile']",
        ]
        
        for selector in user_selectors:
            try:
                if page.locator(selector).count() > 0:
                    return "已登录"
            except Exception:
                continue
        
        # 方法4：检查页面内容
        page_content = page.content()
        if "登录" in page_content and "请登录" in page_content:
            return "未登录（页面包含登录提示）"
        
        # 方法5：使用JavaScript检查
        try:
            result = page.evaluate("""() => {
                // 检查localStorage中的登录信息
                if (localStorage.getItem('passport_csrf_token') || 
                    localStorage.getItem('passport_stoken') ||
                    localStorage.getItem('BAIDUID')) {
                    return '已登录（localStorage检测）';
                }
                
                // 检查是否有用户头像或用户名元素
                const userElements = document.querySelectorAll('[class*="avatar"], [class*="user"], [class*="profile"]');
                if (userElements.length > 0) {
                    return '已登录（DOM检测）';
                }
                
                // 检查是否有登录按钮
                const loginElements = document.querySelectorAll('text="登录", text="请登录", [class*="login"]');
                if (loginElements.length > 0) {
                    return '未登录（DOM检测）';
                }
                
                return '未知';
            }""")
            if result != "未知":
                return result
        except Exception:
            pass
        
        return "未知（无法确定）"
        
    except Exception as e:
        return f"检测失败: {e}"


def _check_environment_warning(page: Page) -> bool:
    """检查页面是否显示环境异常提示"""
    try:
        warning_texts = [
            "当前访问环境存在异常",
            "请更换浏览器再尝试提问",
            "检测到异常访问",
            "安全验证"
        ]
        
        # 注意：text= 选择器需要用引号包裹文本内容
        for text in warning_texts:
            if page.locator(f"text='{text}'").count() > 0:
                print(f"    检测到环境警告: {text}")
                return True
        
        # 检查是否有红色警告条
        warning_selectors = [
            "[class*='warning']",
            "[class*='alert']",
            "[class*='error']",
            "div[style*='red']"
        ]
        
        for selector in warning_selectors:
            try:
                loc = page.locator(selector)
                if loc.is_visible(timeout=1000):
                    inner_text = loc.inner_text(timeout=1000)
                    if any(w in inner_text for w in warning_texts):
                        print(f"    检测到环境警告 (通过选择器 {selector})")
                        return True
            except Exception:
                continue
        
        return False
    except Exception as e:
        print(f"    _check_environment_warning 异常: {e}")
        return False


def _random_wait(min_ms, max_ms):
    time.sleep(random.randint(min_ms, max_ms) / 1000)


def _human_type(page: Page, text: str):
    for char in text:
        page.keyboard.type(char)
        time.sleep(random.randint(30, 100) / 1000)


def _find_editor(page: Page):
    """查找输入框，增加更多选择器和调试信息"""
    selectors = [
        "div[contenteditable='true']",
        "textarea",
        "[role='textbox']",
        "[class*='editor']",
        "[class*='input']",
        "[class*='chat-input']",
        "[class*='message-input']",
        "div[data-placeholder]",
        "div[class*='composer']",
    ]
    
    for sel in selectors:
        loc = page.locator(sel)
        count = loc.count()
        print(f"    查找编辑器: {sel} -> 找到 {count} 个元素")
        
        try:
            if count > 0:
                # 尝试找到可见的输入框
                for i in range(count):
                    el = loc.nth(i)
                    if el.is_visible(timeout=2000):
                        print(f"    ✓ 找到可见的编辑器: {sel}[{i}]")
                        return el
        except PWTimeout:
            continue
    
    # 备用：使用 JavaScript 查找
    try:
        result = page.evaluate("""() => {
            const selectors = [
                "div[contenteditable='true']",
                "textarea",
                "[role='textbox']"
            ];
            for (const sel of selectors) {
                const els = document.querySelectorAll(sel);
                for (const el of els) {
                    const r = el.getBoundingClientRect();
                    if (r.width > 200 && r.height > 20 && r.top > 0) {
                        return true;
                    }
                }
            }
            return false;
        }""")
        print(f"    JS检查: 找到可编辑元素 = {result}")
    except Exception as e:
        print(f"    JS检查失败: {e}")
    
    return None


def _verify_and_send(page: Page, editor, question: str):
    """验证输入并发送消息"""
    print("    验证并发送消息...")
    
    # 确保编辑器获得焦点
    editor.click()
    _random_wait(300, 500)
    
    # 清除可能存在的内容
    try:
        page.keyboard.press("Ctrl+A")
        _random_wait(200, 300)
        page.keyboard.press("Backspace")
        _random_wait(200, 300)
        print("    已清除输入框内容")
    except Exception as e:
        print(f"    清除内容失败（可能为空）: {e}")
    
    # 重新输入问题
    _human_type(page, question)
    _random_wait(500, 800)
    
    # 验证输入
    content = ""
    for attempt in range(3):
        try:
            content = editor.input_value(timeout=1000)
        except Exception:
            try:
                content = editor.inner_text(timeout=1000)
            except Exception:
                pass
        
        if content.strip():
            print(f"    输入内容验证成功: {content[:30]}...")
            break
        
        print(f"    输入框为空，重新输入(第{attempt+1}次)...")
        editor.click()
        _random_wait(300, 500)
        _human_type(page, question)
        _random_wait(400, 600)

    # 发送消息
    sent = False
    
    # 方法1：查找发送按钮
    send_selectors = [
        "button[aria-label*='发送']",
        "button[type='submit']",
        "[class*='send']",
        "[class*='submit']",
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
    
    # 方法2：按 Enter 键发送
    if not sent:
        print("    未找到发送按钮，尝试按 Enter 键发送")
        editor.click()
        _random_wait(200, 300)
        page.keyboard.press("Enter")
        sent = True
    
    if sent:
        print("    ✓ 消息已发送")
    else:
        print("    ✗ 发送失败")


def _wait_for_answer(page: Page):
    """等待文心一言回答完成：文字停止增长（连续 4 次 × 2 秒无变化）"""
    print("    等待文心一言回答", end="", flush=True)
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
    """获取文心一言的AI回答内容"""
    try:
        return page.evaluate("""() => {
            let best = null, bestLen = 0;
            
            // 调试：打印页面结构信息
            console.log('[DEBUG] Page title:', document.title);
            
            // 优先查找AI回答区域（文心一言特有结构）
            const aiAnswerSelectors = [
                '.response-container',           // 常见回答容器
                '.assistant-message',           // 助手消息
                '.message-content',             // 消息内容
                '[class*="msg-content"]',       // 消息内容变体
                '[class*="answer-content"]',    // 回答内容
                '[class*="bot-response"]',      // 机器人响应
                '.chat-content',                // 聊天内容
                '.answer-box',                  // 回答框
                '[role="article"]',             // 文章角色
            ];
            
            console.log('[DEBUG] Testing selectors...');
            
            for (const selector of aiAnswerSelectors) {
                const elements = document.querySelectorAll(selector);
                console.log(`[DEBUG] Selector "${selector}" found ${elements.length} elements`);
                
                elements.forEach(el => {
                    const r = el.getBoundingClientRect();
                    const t = (el.innerText || '').trim();
                    console.log(`[DEBUG] Element text length: ${t.length}, position: ${r.left},${r.top}`);
                    
                    if (r.left >= 0 && r.width >= 100 && r.height >= 20) {
                        if (t.length > 50 && t.length > bestLen) {
                            bestLen = t.length;
                            best = el;
                            console.log(`[DEBUG] Found candidate: ${t.slice(0, 30)}...`);
                        }
                    }
                });
            }
            
            // 如果没找到，使用通用方式
            if (!best) {
                console.log('[DEBUG] Falling back to universal search...');
                document.querySelectorAll('div').forEach(el => {
                    const r = el.getBoundingClientRect();
                    if (r.left < 200 || r.width < 300) return;
                    if (el.children.length > 60) return;
                    const t = (el.innerText || '').trim();
                    // 过滤掉明显不是回答的内容
                    if (t.includes('请输入问题') || t.includes('文心一言') || 
                        t.includes('思考') || t.includes('输入框') || 
                        t.includes('发送') || t.includes('清空')) return;
                    if (t.length > bestLen) { 
                        bestLen = t.length; 
                        best = el; 
                        console.log(`[DEBUG] Universal found: ${t.slice(0, 30)}...`);
                    }
                });
            }
            
            const result = best ? best.innerText.trim() : '';
            console.log('[DEBUG] Final result length:', result.length);
            return result;
        }""") or ""
    except Exception as e:
        print(f"    _get_last_answer 异常: {e}")
        return ""


def _get_references(page: Page) -> list:
    """
    文心一言引用抓取：参考 baidu.py 方式
    1. 查找包含「参考N个网页」字样的按钮
    2. 点击展开按钮
    3. 提取所有外部链接
    """
    try:
        refs = []
        internal_domains = ['baidu.com', 'bdstatic.com', 'bcebos.com']
        expected = 0
        button_found = False

        # ===== 阶段1：查找并点击展开按钮 =====
        try:
            # 获取页面所有可能的参考按钮
            all_els = page.evaluate("""() => {
                const results = [];
                document.querySelectorAll('*').forEach(el => {
                    const t = (el.innerText || '').trim();
                    const r = el.getBoundingClientRect();
                    // 匹配：参考N个网页
                    if ((t.includes('参考') && /参考\\s*\\d+\\s*个\\s*网页/i.test(t))
                            && r.width > 0 && r.height > 0 && t.length < 200 && r.left > 50) {
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
                // 优先选择宽度 >= 80 的元素，再按位置排序
                results.sort((a, b) => {
                    const aIsMain = a.width >= 80 ? 0 : 1;
                    const bIsMain = b.width >= 80 ? 0 : 1;
                    if (aIsMain !== bIsMain) return aIsMain - bIsMain;
                    return a.top - b.top;
                });
                return results;
            }""")
            
            if all_els:
                print(f"    阶段1 - 找到 {len(all_els)} 个候选按钮")
                for i, el in enumerate(all_els[:3]):
                    print(f"      [{i}] text=\"{el['text']}\", top={el['top']}, width={el['width']}")
                
                # 选择包含"参考"字样的按钮
                target = None
                for el in all_els:
                    if "参考" in el['text']:
                        target = el
                        break
                if not target:
                    target = all_els[0]

                # 提取预期数量
                m = re.search(r'(\d+)\s*个\s*网页', target['text'])
                if m:
                    expected = int(m.group(1))
                
                print(f"    选中目标按钮: \"{target['text']}\"，预期 {expected} 篇参考资料")
                
                # 先滚动到按钮位置，确保在视口内
                page.evaluate("""() => {
                    const allEls = document.querySelectorAll('*');
                    for (const el of allEls) {
                        const t = el.innerText || '';
                        const r = el.getBoundingClientRect();
                        if (t.includes('参考') && /参考\\s*\\d+\\s*个\\s*网页/i.test(t)
                            && r.width > 0 && r.height > 0 && t.length < 300) {
                            el.scrollIntoView({ behavior: 'instant', block: 'center' });
                            return { found: true };
                        }
                    }
                    return { found: false };
                }""")
                time.sleep(1)
                
                # 再次获取元素位置（滚动后可能位置变化）
                new_target_info = page.evaluate("""() => {
                    const allEls = document.querySelectorAll('*');
                    for (const el of allEls) {
                        const t = el.innerText || '';
                        const r = el.getBoundingClientRect();
                        if (t.includes('参考') && /参考\\s*\\d+\\s*个\\s*网页/i.test(t)
                            && r.width > 0 && r.height > 0 && t.length < 300 && r.top > -100 && r.top < window.innerHeight) {
                            return {
                                found: true,
                                x: r.x + r.width / 2,
                                y: r.y + r.height / 2,
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
                    target_x = target['x']
                    target_y = target['y']
                    print(f"    使用备用坐标: ({target_x:.0f}, {target_y:.0f})")
                
                # 点击展开按钮（使用 page.click 代替 mouse.click，更稳定）
                print(f"    点击展开按钮...")
                try:
                    # 尝试通过 text 选择器点击
                    page.click(f"text='{target['text']}'", timeout=3000)
                    print(f"    ✓ 通过 text 选择器点击成功")
                except Exception as e1:
                    print(f"    通过 text 选择器点击失败: {e1}")
                    try:
                        # 备用：使用 mouse.click
                        page.mouse.click(target_x, target_y)
                        print(f"    ✓ 通过鼠标点击成功")
                    except Exception as e2:
                        print(f"    点击失败: {e2}")
                
                # 等待展开
                print(f"    等待展开动画完成...")
                time.sleep(4)
                
                button_found = True
                print(f"    已点击展开按钮")
        except Exception as e:
            print(f"    阶段1 - 查找/点击引用按钮失败: {e}")
            import traceback
            traceback.print_exc()

        # ===== 阶段2：提取引用链接 =====
        if button_found:
            print("    阶段2 - 尝试提取引用链接...")
            refs = _extract_yiyan_references(page, internal_domains)
        
        # ===== 阶段3：备用提取方式（直接查找链接）=====
        if not refs:
            print("    阶段3 - 尝试备用提取方式...")
            refs = _extract_yiyan_references_fallback(page, internal_domains)
        
        # ===== 阶段4：去重 =====
        seen, unique = set(), []
        for r in refs:
            if r["url"] not in seen:
                seen.add(r["url"])
                unique.append(r)

        print(f"    引用参考: 共 {len(unique)} 篇")
        return unique

    except Exception as e:
        print(f"    引用参考抓取失败: {e}")
        import traceback
        traceback.print_exc()
        return []


def _extract_yiyan_references(page: Page, internal_domains: list) -> list:
    """从展开的引用面板中提取引用链接（简化版：直接查找右侧面板区域）"""
    refs = []
    try:
        # 等待面板完全展开
        time.sleep(4)
        
        # 尝试最直接的方式：查找右侧面板中所有可点击的元素
        items_info = page.evaluate("""() => {
            const results = [];
            const rightPanelX = window.innerWidth * 0.5;  // 放宽到屏幕中间
            
            // 查找右侧区域内的所有元素
            document.querySelectorAll('div').forEach(el => {
                const r = el.getBoundingClientRect();
                const t = (el.innerText || '').trim();
                
                // 右侧面板区域，有一定大小，有文本内容
                if (r.left > rightPanelX && r.width > 150 && r.height > 25 && r.height < 200 && t.length > 5) {
                    // 检查是否有子链接或可点击
                    const hasLink = el.querySelector('a');
                    const cs = window.getComputedStyle(el);
                    const isClickable = cs.cursor === 'pointer' || hasLink;
                    
                    if (isClickable || hasLink) {
                        results.push({
                            x: r.x + r.width/2,
                            y: r.y + r.height/2,
                            text: t.split('\\n')[0].substring(0, 100),
                            top: r.top,
                            left: r.left,
                            hasLink: !!hasLink
                        });
                    }
                }
            });
            
            // 按垂直位置排序
            results.sort((a, b) => a.top - b.top);
            return results;
        }""")
        
        print(f"    找到 {len(items_info)} 个右侧面板条目")
        if items_info:
            for i, item in enumerate(items_info[:12]):
                print(f"      [{i}] text='{item['text']}', top={item['top']:.0f}, left={item['left']:.0f}, hasLink={item['hasLink']}")
        
        # 如果找到条目，尝试点击获取URL
        for item in items_info[:30]:
            try:
                title = item.get('text', '').strip()
                if not title or len(title) < 3:
                    continue
                
                # 点击条目，等待新标签页
                with page.context.expect_page(timeout=6000) as new_page_info:
                    page.mouse.click(item['x'], item['y'])
                
                new_page = new_page_info.value
                try:
                    new_page.wait_for_load_state("domcontentloaded", timeout=8000)
                except Exception:
                    pass
                new_url = new_page.url
                new_page.close()
                page.bring_to_front()
                time.sleep(0.5)
                
                # 过滤内部域名
                if (new_url and new_url.startswith('http')
                        and not any(d in new_url for d in internal_domains)):
                    refs.append({"title": title[:120], "url": new_url, "content": ""})
                    print(f"    OK [{len(refs)}] {title[:40]} -> {new_url[:70]}")
                    
                    if len(refs) >= 30:
                        break
                        
            except Exception as e:
                print(f"    跳过: {str(e)[:40]}")
                continue
                
    except Exception as e:
        print(f"    _extract_yiyan_references 失败: {e}")
        import traceback
        traceback.print_exc()
    
    return refs


def _extract_yiyan_references_fallback(page: Page, internal_domains: list) -> list:
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
        print(f"    _extract_yiyan_references_fallback 失败: {e}")
    
    return refs


def _take_screenshot(page: Page, question: str, brand_keywords: list = None, output_dir: str = None) -> str:
    """
    长截图：GoFullPage 同款算法。
    用 JS 给滚动容器打标记，按固定步长精确设置 scrollTop，
    每步截图后按坐标直接拼接，零图像匹配，零重复。
    """
    try:
        from utils import get_timestamp_dir, find_keyword_positions, draw_marks
        
        # 确保输出目录存在
        if not output_dir:
            print("    截图: 未指定输出目录")
            return ""
        
        timestamp_dir = get_timestamp_dir()
        shot_dir = os.path.join(output_dir, timestamp_dir, "screenshots")
        os.makedirs(shot_dir, exist_ok=True)
        safe_name = re.sub(r'[\\/:*?"<>|]', "_", question).strip(".")[:80]
        shot_path = os.path.join(shot_dir, f"{safe_name}.png")
        
        print(f"    截图准备: {shot_path}")

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
        
        vp = page.viewport_size
        if not vp or "width" not in vp or "height" not in vp:
            print("    截图: 获取视口大小失败")
            return ""
        
        clip_w = vp["width"] - clip_x
        print(f"    截图区域: x={clip_x}, w={clip_w}")

        # 顶部边界：检测 fixed/sticky header 和顶部导航栏
        clip_y = page.evaluate("""() => {
            let bottom = 0;
            document.querySelectorAll('*').forEach(el => {
                const cs = window.getComputedStyle(el);
                const r  = el.getBoundingClientRect();
                if ((cs.position === 'fixed' || cs.position === 'sticky')
                        && r.top <= 50 && r.bottom >= 30
                        && r.width > window.innerWidth * 0.8
                        && r.height > 20 && r.height < 150
                        && cs.display !== 'none') {
                    bottom = Math.max(bottom, Math.round(r.bottom));
                }
            });
            return Math.max(bottom, 10);
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
        print(f"    截图区域: y={clip_y}, h={clip_h}")
        
        if clip_h <= 0:
            print(f"    截图: 截取高度无效 ({clip_h})")
            return ""

        # ── 2. 找滚动容器，打标记，获取总高度 ────────────
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
        
        print(f"    滚动信息: 总高度={total_scroll}, 可视高度={client_h}, 找到滚动容器={found}")

        # ── 3. 查找关键词位置 ───────────────────────────
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

        # ── 3. 按坐标步进截图 ────────────────────────────
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

        # ── 4. 按坐标直接拼接 ────────────────────────────
        if not frames:
            print("    截图: 未获取到帧")
            return ""

        if len(frames) == 1:
            frames[0][1].save(shot_path, optimize=True, quality=95)
            print(f"\n    截图: 1 帧，总高 {frames[0][1].height}px")
            return shot_path

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

        # ── 5. 绘制品牌词红框 ───────────────────────────
        if keyword_marks:
            canvas = draw_marks(canvas, keyword_marks, clip_x, clip_y)

        canvas.save(shot_path, optimize=True, quality=95)
        print(f"\n    截图: {len(frames)} 帧拼接，总高 {total_h}px")
        return shot_path

    except Exception as e:
        import traceback
        print(f"    截图失败: {e}")
        print(f"    错误详情: {traceback.format_exc()[:500]}")
        return ""
