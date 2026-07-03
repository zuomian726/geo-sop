import os
import re
import json
import time
from datetime import datetime
from PIL import ImageDraw


# 全局变量：存储当前运行的时间戳目录
_current_timestamp_dir = None


def get_timestamp_dir(force_new=False):
    """获取当前运行的时间戳目录（YYYYMMDDHHMM格式）
    
    Args:
        force_new: 强制生成新的时间戳目录（用于单独重新采集）
    """
    global _current_timestamp_dir
    if force_new or _current_timestamp_dir is None:
        _current_timestamp_dir = datetime.now().strftime("%Y%m%d%H%M")
    return _current_timestamp_dir


def reset_timestamp_dir():
    """重置时间戳目录（用于新的运行）"""
    global _current_timestamp_dir
    _current_timestamp_dir = None


def load_questions(filepath="question.txt"):
    questions = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                questions.append(line)
    return questions


def safe_filename(question: str, max_len=80) -> str:
    name = re.sub(r'[\\/:*?"<>|]', "_", question)
    name = name.strip().strip(".")
    return name[:max_len]


def save_answer(question: str, platform: str, answer: str, references: list, output_dir: str) -> str:
    # 使用全局时间戳目录
    timestamp_dir = get_timestamp_dir()
    platform_dir = os.path.join(output_dir, platform, timestamp_dir)
    os.makedirs(platform_dir, exist_ok=True)
    
    filename = safe_filename(question)
    filepath = os.path.join(platform_dir, f"{filename}.json")
    data = {
        "question": question,
        "platform": platform,
        "timestamp": datetime.now().isoformat(),
        "answer": answer,
        "references": references,
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return filepath


def save_cookies(context, platform: str, cookies_dir: str):
    os.makedirs(cookies_dir, exist_ok=True)
    path = os.path.join(cookies_dir, f"{platform}.json")
    cookies = context.cookies()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)


def load_cookies(context, platform: str, cookies_dir: str) -> bool:
    path = os.path.join(cookies_dir, f"{platform}.json")
    if not os.path.exists(path):
        return False
    with open(path, "r", encoding="utf-8") as f:
        cookies = json.load(f)
    context.add_cookies(cookies)
    return True


def print_result(platform: str, question: str, answer: str, references: list):
    print(f"\n{'='*60}")
    print(f"平台: {platform}  问题: {question}")
    print(f"答案: {answer[:300]}{'...' if len(answer) > 300 else ''}")
    if references:
        print(f"引用参考 ({len(references)} 条):")
        for i, ref in enumerate(references, 1):
            title = ref.get('title', '')
            url = ref.get('url', '')
            print(f"  [{i}] {title}  {url}")
    print("="*60)


def find_keyword_positions(page, keywords):
    """
    在页面中查找关键词所在的段落位置
    返回相对于滚动容器顶部的坐标列表
    """
    if not keywords:
        return []
        
    # 将关键词列表转换为 JS 数组字符串
    keywords_js = json.dumps(keywords, ensure_ascii=False)
    
    marks = page.evaluate(f"""(kws) => {{
        const marks = [];
        // 优先寻找已标记的滚动容器，否则用 documentElement
        const scrollContainer = document.querySelector('[data-gofullpage-target="1"]') || document.documentElement;
        const containerRect = scrollContainer.getBoundingClientRect();
        
        // 记录容器当前的滚动位置
        const scrollLeft = (scrollContainer === document.documentElement) ? window.scrollX : scrollContainer.scrollLeft;
        let scrollTop = (scrollContainer === document.documentElement) ? window.scrollY : scrollContainer.scrollTop;

        // 特殊处理豆包的反向滚动容器
        const cs = window.getComputedStyle(scrollContainer);
        const isReverse = cs.flexDirection === 'column-reverse' || 
                          cs.display === 'flex' && scrollContainer.className.includes('reverse');
        
        if (isReverse && scrollContainer !== document.documentElement) {{
            // 将实际 scrollTop 转换为虚拟位置（顶部为 0）
            const maxScroll = scrollContainer.scrollHeight - scrollContainer.clientHeight;
            scrollTop = maxScroll + scrollTop;
        }}

        const seenElements = new Set();

        function isBlockElement(el) {{
            const style = window.getComputedStyle(el);
            return ['block', 'flex', 'grid', 'table', 'list-item', 'article', 'section'].includes(style.display);
        }}

        function getSection(el) {{
            let current = el;
            while (current && current !== scrollContainer && current !== document.body) {{
                if (isBlockElement(current)) return current;
                current = current.parentElement;
            }}
            return el;
        }}

        // 遍历所有文本节点
        const walker = document.createTreeWalker(scrollContainer, NodeFilter.SHOW_TEXT, null, false);
        let node;
        while (node = walker.nextNode()) {{
            const text = node.textContent;
            for (const kw of kws) {{
                if (text.includes(kw)) {{
                    const section = getSection(node.parentElement);
                    if (!seenElements.has(section)) {{
                        seenElements.add(section);
                        const rect = section.getBoundingClientRect();
                        
                        // 计算相对于文档顶部的绝对坐标
                        // getBoundingClientRect() 是相对于当前视口的
                        const absX = rect.left + scrollLeft;
                        const absY = rect.top + scrollTop;
                        
                        marks.push({{
                            keyword: kw,
                            x: Math.round(absX),
                            y: Math.round(absY),
                            w: Math.round(rect.width),
                            h: Math.round(rect.height)
                        }});
                    }}
                    break; 
                }}
            }}
        }}
        return marks;
    }}""", keywords)
    return marks


def draw_marks(image, marks, clip_x, clip_y):
    """
    在图像上绘制红框标记
    """
    if not marks:
        return image
        
    draw = ImageDraw.Draw(image)
    for m in marks:
        # 映射坐标到截图画布
        # 截图是从 clip_x, clip_y 开始的
        x = m['x'] - clip_x
        y = m['y'] - clip_y
        w = m['w']
        h = m['h']
        
        # 绘制红框 (宽度为 3 像素)
        for i in range(3):
            draw.rectangle([x-i, y-i, x+w+i, y+h+i], outline="red")
            
    return image
