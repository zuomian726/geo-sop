"""
排名解析工具 - 解析AI回答中的分组列表排名信息
"""
import re

def parse_grouped_rankings(answer_text):
    """
    解析分组列表（无编号）格式的排名信息
    
    支持的格式：
    一、泌尿外科（公立三甲）
    李汉忠 | 北京协和医院
    叶雄俊 | 中国医学科学院肿瘤医院
    
    私立高端
    朱刚 | 北京和睦家医院
    
    返回：
        list: 包含排名信息的字典列表，每个字典包含：
            - rank: 综合排名（按出现顺序）
            - group: 所属分组（如"泌尿外科"、"胃肠外科"等科室）
            - sub_group: 子分组（如"公立三甲"、"私立高端"）
            - name: 医生姓名
            - hospital: 医院名称
    """
    results = []
    
    # 匹配章节标题（一、XXX）
    chapter_pattern = r'^([一二三四五六七八九十]+)[、．.]\s*([^\n]+)$'
    # 匹配医生信息（姓名 | 医院）
    doctor_pattern = r'([\u4e00-\u9fa5]{2,4})\s*[｜|\\/]\s*([^\n]+)'
    
    lines = answer_text.split('\n')
    current_group = ""
    current_sub_group = ""
    rank = 0
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # 检查是否是章节标题
        chapter_match = re.match(chapter_pattern, line)
        if chapter_match:
            current_group = chapter_match.group(2).strip()
            current_sub_group = ""
            
            # 尝试从章节标题中提取子分组
            # 格式如："泌尿外科（公立三甲）"
            bracket_match = re.search(r'[（(]([^）)]+)[）)]', current_group)
            if bracket_match:
                current_sub_group = bracket_match.group(1)
                current_group = re.sub(r'\s*[（(][^）)]+[）)]\s*', '', current_group).strip()
            continue
        
        # 检查是否是医生信息
        doctor_match = re.search(doctor_pattern, line)
        if doctor_match:
            rank += 1
            name = doctor_match.group(1).strip()
            hospital = doctor_match.group(2).strip()
            
            results.append({
                "rank": rank,
                "group": current_group,
                "sub_group": current_sub_group,
                "name": name,
                "hospital": hospital
            })
            continue
        
        # 检查是否是子分组标题（非标题、非医生的短文本行）
        # 子分组标题特征：较短（2-20字符）、不包含逗号句号等句子结束符
        if 2 <= len(line) <= 20 and not any(c in line for c in ['，', '。', '、', '：', '；', '！', '？']):
            # 检查是否像子分组标题（通常是分类名称）
            sub_group_keywords = ['公立', '私立', '三甲', '高端', '普通', '专家', '团队', '中心']
            if any(kw in line for kw in sub_group_keywords):
                current_sub_group = line
                continue
    
    return results


def parse_numbered_rankings(answer_text):
    """
    解析带编号列表格式的排名信息
    
    支持的格式：
    1. 北大一院（国内泌尿TOP1）- 李学松
    2. 北京协和医院 - 纪志刚
    3. 和睦家（私立高端）- 朱刚
    
    返回：
        list: 包含排名信息的字典列表
    """
    results = []
    
    # 匹配带编号的列表项
    pattern = r'(\d+)[．.、]\s*([^\n]+)'
    
    for match in re.finditer(pattern, answer_text):
        rank = int(match.group(1))
        content = match.group(2).strip()
        
        # 尝试提取医生姓名和医院
        name = ""
        hospital = ""
        
        # 尝试多种分隔符
        separators = ['-', '—', '–', '|', '｜', '：', ':']
        found = False
        
        for sep in separators:
            if sep in content:
                parts = content.split(sep, 1)
                # 判断哪部分是姓名（通常较短，2-4个汉字）
                part1 = parts[0].strip()
                part2 = parts[1].strip()
                
                if 2 <= len(part1) <= 4 and len(part2) > 4:
                    name = part1
                    hospital = part2
                elif 2 <= len(part2) <= 4 and len(part1) > 4:
                    name = part2
                    hospital = part1
                else:
                    # 默认左边是医院，右边是姓名
                    hospital = part1
                    name = part2
                found = True
                break
        
        if not found:
            # 尝试从内容中提取姓名（2-4个汉字）
            name_match = re.search(r'([\u4e00-\u9fa5]{2,4})', content)
            if name_match:
                name = name_match.group(1)
                hospital = content.replace(name, "").strip()
        
        results.append({
            "rank": rank,
            "group": "",
            "sub_group": "",
            "name": name,
            "hospital": hospital
        })
    
    return results


def parse_section_rankings(answer_text):
    """
    解析章节式排名格式（章节标题 + 编号列表 + 多行医生信息）
    
    支持的格式：
    三、核心专家团队
    1. 首席专家
    刘东明（上海大区泌尿首席、主任医师 / 教授）：仁济背景，擅长泌尿系肿瘤...
    齐隽（前泌尿首席、博导）：留加专家，肾移植、前列腺、泌尿肿瘤微创
    2. 院内主治
    周览（医学硕士）：20 余年临床，擅长...
    
    返回：
        list: 包含排名信息的字典列表
    """
    results = []
    
    # 匹配章节标题（一、XXX）
    chapter_pattern = r'^([一二三四五六七八九十]+)[、．.]\s*([^\n]+)$'
    # 匹配编号列表项（1. XXX）
    numbered_pattern = r'^(\d+)[．.]\s*([^\n]+)$'
    # 匹配医生信息行（姓名（头衔）：专长）
    doctor_pattern = r'^([\u4e00-\u9fa5]{2,4})\s*[（(]([^）)]+)[）)]\s*[：:]'
    
    lines = answer_text.split('\n')
    current_group = ""
    current_sub_group = ""
    rank = 0
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # 检查是否是章节标题
        chapter_match = re.match(chapter_pattern, line)
        if chapter_match:
            current_group = chapter_match.group(2).strip()
            # 检查是否是"专家团队"相关章节
            if not any(kw in current_group for kw in ['专家', '团队', '医生', '医师']):
                current_group = ""
            continue
        
        # 检查是否是编号列表项（子分组）
        numbered_match = re.match(numbered_pattern, line)
        if numbered_match:
            current_sub_group = numbered_match.group(2).strip()
            continue
        
        # 检查是否是医生信息行
        doctor_match = re.match(doctor_pattern, line)
        if doctor_match:
            rank += 1
            name = doctor_match.group(1).strip()
            title = doctor_match.group(2).strip()
            
            results.append({
                "rank": rank,
                "group": current_group,
                "sub_group": current_sub_group,
                "name": name,
                "hospital": title  # 将头衔作为医院字段存储
            })
            continue
    
    return results


def extract_rankings(answer_text):
    """
    综合解析排名信息，自动识别格式
    
    返回：
        list: 包含排名信息的字典列表
    """
    # 先尝试解析章节式排名（最常见的格式）
    section_results = parse_section_rankings(answer_text)
    if section_results:
        # 验证结果是否合理（至少有一个有效姓名）
        if any(len(item["name"]) >= 2 for item in section_results):
            return section_results
    
    # 尝试解析带编号的排名
    numbered_results = parse_numbered_rankings(answer_text)
    if numbered_results:
        # 验证结果是否合理（排除不合理的大数字排名）
        valid_results = [r for r in numbered_results if r["rank"] <= 100 and len(r["name"]) >= 2]
        if valid_results:
            return valid_results
    
    # 尝试解析分组列表格式
    grouped_results = parse_grouped_rankings(answer_text)
    if grouped_results:
        return grouped_results
    
    return []


def get_doctor_rank(answer_text, doctor_name):
    """
    获取指定医生的排名
    
    参数：
        answer_text: AI回答文本
        doctor_name: 医生姓名
    
    返回：
        dict: 排名信息，包含rank, group, name, hospital
              如果未找到返回None
    """
    rankings = extract_rankings(answer_text)
    
    for item in rankings:
        if item["name"] == doctor_name:
            return item
    
    return None


def format_rankings(rankings):
    """
    格式化排名信息为可读文本
    
    返回：
        str: 格式化的排名文本
    """
    if not rankings:
        return "未找到排名信息"
    
    result = []
    current_group = ""
    
    for item in rankings:
        # 如果分组变化，添加分组标题
        if item["group"] and item["group"] != current_group:
            current_group = item["group"]
            sub_group_str = f"（{item['sub_group']}）" if item["sub_group"] else ""
            result.append(f"\n【{current_group}{sub_group_str}】")
        
        sub_group_str = f"（{item['sub_group']}）" if item["sub_group"] and not current_group else ""
        result.append(f"{item['rank']}. {item['name']} | {item['hospital']}{sub_group_str}")
    
    return "\n".join(result)
