# 引用链接舆情分析频道

## 概述

独立频道，用于采集引用参考链接网页内容并分析舆情。

## 功能

1. **采集引用链接网页内容**
   - 从现有数据库中读取采集结果的引用链接
   - 自动采集网页内容（标题、正文）
   - 支持重试机制和错误处理

2. **舆情分析**
   - 基于关键词的情感分析
   - 支持正向/负向关键词配置
   - 支持AI智能分析（预留接口）
   - 统计分析结果

## 架构

```
reference_sentiment/
├── __init__.py          # 模块初始化
├── config.py            # 配置文件
├── models.py            # 数据库模型
├── crawler.py           # 网页内容采集模块
├── analyzer.py          # 舆情分析模块
├── scheduler.py         # 调度器模块
├── content/             # 网页内容存储目录
├── results/             # 分析结果存储目录
└── logs/                # 日志目录
```

## 数据库表

### reference_contents
存储引用链接的网页内容

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 主键 |
| collection_result_id | Integer | 关联的采集结果ID |
| url | String(500) | 引用链接URL |
| title | String(255) | 网页标题 |
| content | Text | 网页内容（纯文本） |
| html_content | Text | 网页HTML内容 |
| crawl_status | String(20) | 采集状态 |
| crawl_error | Text | 采集错误信息 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

### reference_sentiments
存储舆情分析结果

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 主键 |
| reference_content_id | Integer | 关联的内容ID |
| collection_result_id | Integer | 关联的采集结果ID |
| sentiment | String(20) | 情感倾向 |
| sentiment_score | Integer | 情感分数（0-100） |
| keywords | Text | 关键词（JSON） |
| analysis_details | Text | 分析详情（JSON） |
| analysis_status | String(20) | 分析状态 |
| analysis_error | Text | 分析错误信息 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

## 使用方法

### 1. 安装依赖

```bash
pip install requests beautifulsoup4 sqlalchemy
```

### 2. 运行调度器

#### Windows
```bash
start_reference_sentiment.bat
```

#### Linux/Mac
```bash
chmod +x start_reference_sentiment.sh
./start_reference_sentiment.sh
```

#### 直接运行Python
```bash
python reference_sentiment/scheduler.py
```

### 3. 命令行参数

```bash
python reference_sentiment/scheduler.py [选项]

选项:
  --once              只运行一次
  --interval INT      调度间隔（秒），默认60
  --limit INT         每次处理数量，默认10
```

### 4. 示例

```bash
# 只运行一次
python reference_sentiment/scheduler.py --once

# 循环运行，间隔30秒
python reference_sentiment/scheduler.py --interval 30

# 每次处理20条
python reference_sentiment/scheduler.py --limit 20
```

## 配置说明

在 `reference_sentiment/config.py` 中可以配置：

- `DATABASE_URI`: 数据库连接字符串
- `CRAWL_TIMEOUT`: 网页请求超时时间（秒）
- `CRAWL_RETRY_TIMES`: 失败重试次数
- `SENTIMENT_BATCH_SIZE`: 批量分析数量
- `SENTIMENT_INTERVAL`: 分析间隔（秒）

## 与现有系统的关系

1. **数据同步**
   - 从现有数据库读取 `monitor_tasks`（监控问题）
   - 从现有数据库读取 `collection_results`（采集结果和引用链接）
   - 从现有数据库读取 `sentiment_configs`（舆情配置）

2. **独立运行**
   - 不修改现有程序
   - 使用独立的数据库表
   - 独立的日志文件

3. **数据关联**
   - 通过 `collection_result_id` 关联到现有采集结果
   - 通过 `task_id` 关联到现有监控任务

## 舆情分析

### 关键词分析

基于配置的正向/负向关键词进行情感分析：

- **正向**: 包含更多正向关键词
- **负向**: 包含更多负向关键词
- **中性**: 正负关键词平衡或无关键词

### 情感分数

- 0-40: 负向
- 41-59: 中性
- 60-100: 正向

### AI分析（预留）

支持集成AI平台进行智能舆情分析，配置方法：

1. 在现有系统的舆情配置中启用AI分析
2. 配置AI平台API信息
3. 调度器会自动使用AI进行分析

## 日志

日志文件位置: `reference_sentiment/logs/reference_sentiment.log`

## 注意事项

1. 确保现有数据库可访问
2. 网络连接正常（用于采集网页内容）
3. 定期检查日志文件
4. 可根据需要调整调度间隔和批量大小

## 故障排查

### 采集失败

- 检查网络连接
- 检查URL是否可访问
- 查看日志中的错误信息

### 分析失败

- 检查舆情配置是否正确
- 查看日志中的错误信息

### 数据库连接失败

- 检查数据库路径是否正确
- 检查数据库文件权限