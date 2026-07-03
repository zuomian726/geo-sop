# AI 多平台问答采集工具

自动化采集多个AI平台的问答内容，支持完整截图和引用参考数据抓取。

## 功能特点

- ✅ **多平台支持**：支持豆包、DeepSeek、元宝、Kimi、千问、文心等6个AI平台
- ✅ **完整截图**：使用GoFullPage算法，从顶部到底部完整拼接对话截图
- ✅ **引用抓取**：自动抓取AI回答的引用参考链接和标题
- ✅ **自动登录**：保存登录状态，无需每次手动登录
- ✅ **批量采集**：支持多个问题批量采集
- ✅ **时间归档**：按时间戳自动组织保存数据

## 系统要求

- Python 3.8+
- Google Chrome 浏览器
- Windows/Linux/macOS

## 安装依赖

```bash
pip install playwright pillow
python -m playwright install chromium
```

## 快速开始

### 1. 准备问题文件

编辑 `question.txt` 文件，每行一个问题：

```
今日热门新闻
今日热门体育新闻
今日热门经济新闻
```

### 2. 首次登录（保存登录状态）

```bash
# 登录豆包
python main.py --login doubao

# 登录DeepSeek
python main.py --login deepseek

# 登录其他平台
python main.py --login yuanbao
python main.py --login kimi
python main.py --login qianwen
python main.py --login wenxin
```

登录后，浏览器会自动保存登录状态到 `browser_profile/{平台}/` 目录。

### 3. 开始采集

```bash
# 采集所有平台
python main.py

# 采集指定平台
python main.py --platforms deepseek yuanbao

# 显示浏览器窗口（调试模式）
python main.py --platforms doubao --debug
```

## 命令行参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--platforms` | 指定要采集的平台（可多个） | `--platforms deepseek kimi` |
| `--questions` | 指定问题文件路径 | `--questions my_questions.txt` |
| `--login` | 手动登录指定平台并保存状态 | `--login doubao` |
| `--debug` | 显示浏览器窗口（调试用） | `--debug` |

## 支持的平台

| 平台 | 标识符 | 网址 | 特点 |
|------|--------|------|------|
| 豆包 | `doubao` | https://www.doubao.com/chat | 支持反向滚动容器截图 |
| DeepSeek | `deepseek` | https://chat.deepseek.com | 支持"已阅读N个网页"引用 |
| 元宝 | `yuanbao` | https://yuanbao.tencent.com/chat | 支持data-url引用抓取 |
| Kimi | `kimi` | https://www.kimi.com | 月之暗面出品 |
| 千问 | `qianwen` | https://www.qianwen.com | 阿里云出品 |
| 文心 | `wenxin` | https://wenxin.baidu.com | 百度出品 |

## 输出目录结构

```
answers/
├── deepseek/
│   └── 202604211545/              # 时间戳目录（YYYYMMDDHHMM）
│       ├── 今日热门新闻.json       # 问答数据
│       └── screenshots/
│           └── 今日热门新闻.png    # 完整截图
├── doubao/
│   └── 202604211545/
│       ├── 今日热门体育新闻.json
│       └── screenshots/
│           └── 今日热门体育新闻.png
└── yuanbao/
    └── 202604211545/
        ├── 今日热门经济新闻.json
        └── screenshots/
            └── 今日热门经济新闻.png
```

### JSON 数据格式

```json
{
  "question": "今日热门新闻",
  "platform": "deepseek",
  "timestamp": "2026-04-21T15:45:30.123456",
  "answer": "AI回答的完整内容...",
  "references": [
    {
      "title": "新闻标题",
      "url": "https://example.com/news",
      "content": ""
    }
  ]
}
```

## 配置文件

### config.py

```python
# 输出目录
OUTPUT_DIR = "answers"

# 等待AI回答的最长时间（秒）
ANSWER_TIMEOUT = 300

# 是否无头模式运行（不显示浏览器）
HEADLESS = True
```

## 核心功能说明

### 1. 截图功能

使用 **GoFullPage 算法**实现完整截图：

- **自动检测滚动容器**：找到对话内容的滚动容器
- **精确步进滚动**：按固定步长设置 scrollTop
- **坐标拼接**：根据实际滚动位置直接拼接，零图像匹配
- **排除固定元素**：自动排除顶部导航栏和底部输入框

**特殊处理**：
- 豆包：支持反向滚动容器（`flex-direction: column-reverse`）
- 所有平台：自动检测并排除固定头部（默认70px）

### 2. 引用抓取

不同平台的引用抓取策略：

| 平台 | 引用入口 | 抓取方式 |
|------|----------|----------|
| DeepSeek | "已阅读 N 个网页" | 点击展开，抓取 `<a href>` |
| 豆包 | "参考 N 篇资料" | 点击展开，抓取 `<a href>` |
| 元宝 | "源" 按钮 | 点击展开，抓取 `data-url` 属性 |
| Kimi | "引用" 按钮 | 点击展开，抓取链接 |
| 千问 | "N 篇来源" | 点击展开，抓取链接 |
| 文心 | "参考资料" | 点击展开，抓取链接 |

### 3. 登录状态管理

- **浏览器配置文件**：使用 Playwright 的 `user_data_dir` 保存登录状态
- **自动检测**：每次运行自动检测是否已登录
- **手动登录**：未登录时等待用户手动登录（最长5分钟）
- **持久化**：登录状态保存在 `browser_profile/{平台}/` 目录

## 常见问题

### Q1: 为什么截图只有一部分？

**A**: 可能是固定头部检测失败。解决方法：
- 检查 `clip_y` 的值（会在调试模式下显示）
- 如果为0，说明没有检测到固定头部，会使用默认值70px
- 可以手动调整各平台代码中的默认值

### Q2: 为什么引用参考数量不对？

**A**: 不同平台的引用机制不同：
- **DeepSeek**: "已阅读10个网页"可能只展示8-9个链接（正常）
- **元宝**: 引用URL存储在 `data-url` 属性中
- **豆包**: 需要点击"参考N篇资料"展开

### Q3: 如何处理登录失效？

**A**: 重新登录即可：
```bash
python main.py --login {平台名}
```

### Q4: 截图太大怎么办？

**A**: 截图大小取决于对话长度。可以：
- 缩短问题，减少AI回答长度
- 修改代码中的图片质量参数（`quality=95` 改为 `quality=85`）

### Q5: 为什么有些平台采集失败？

**A**: 可能的原因：
- 网络问题：检查网络连接
- 页面结构变化：AI平台可能更新了页面结构
- 登录失效：重新登录
- 超时：增加 `ANSWER_TIMEOUT` 配置

## 调试技巧

### 1. 显示浏览器窗口

```bash
python main.py --platforms doubao --debug
```

### 2. 查看详细日志

程序会输出详细的执行日志：
- `等待豆包回答(67)(202)...` - 答案长度变化
- `(s=0)(s=429)` - 滚动位置
- `截图: 3 帧拼接，总高 1797px` - 截图信息
- `引用参考: 7/10 篇` - 引用抓取结果

### 3. 检查输出文件

```bash
# 查看最新的输出目录
ls -lt answers/{平台}/

# 查看JSON内容
cat answers/deepseek/202604211545/今日热门新闻.json
```

## 技术架构

```
main.py                 # 主程序入口
├── config.py          # 配置文件
├── utils.py           # 工具函数（保存、加载等）
├── browser_utils.py   # 浏览器启动工具
└── platforms/         # 各平台实现
    ├── deepseek.py
    ├── doubao.py
    ├── yuanbao.py
    ├── kimi.py
    ├── qianwen.py
    └── wenxin.py

    
browser_profile/
├── deepseek/          # DeepSeek 的浏览器配置
│   ├── Default/       # 默认配置文件
│   ├── Cookies        # Cookie 数据
│   ├── Local Storage/ # 本地存储
│   └── ...
├── doubao/            # 豆包的浏览器配置
├── yuanbao/           # 元宝的浏览器配置
├── kimi/              # Kimi 的浏览器配置
├── qianwen/           # 千问的浏览器配置
└── wenxin/            # 文心的浏览器配置

```

### 各平台模块结构

每个平台模块包含以下函数：

```python
def query(page: Page, question: str) -> tuple[str, list]:
    """主查询函数，返回(答案, 引用列表)"""
    
def _get_last_answer(page: Page) -> str:
    """获取AI回答内容"""
    
def _get_references(page: Page) -> list:
    """获取引用参考"""
    
def _take_screenshot(page: Page, question: str) -> str:
    """截取完整对话截图"""
```

## 更新日志

### v1.0.0 (2026-04-21)

- ✅ 支持6个AI平台
- ✅ GoFullPage截图算法
- ✅ 引用参考抓取
- ✅ 时间戳目录组织
- ✅ 自动登录状态管理
- ✅ 反向滚动容器支持（豆包）
- ✅ data-url引用抓取（元宝）
- ✅ 固定头部自动排除

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！

## 联系方式

如有问题，请提交 Issue。
