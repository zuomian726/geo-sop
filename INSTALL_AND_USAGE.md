# GEO-SOP AI监控平台 - 安装和使用说明

## 一、项目简介

GEO-SOP是一个AI平台监控系统，用于监控各大AI平台（豆包、文心一言、千问等）对特定关键词的回答内容，并进行GEO稿件引用分析。

## 二、环境要求

| 项目 | 要求 | 说明 |
|------|------|------|
| 操作系统 | Windows 10/11 | 推荐64位系统 |
| Python版本 | 3.10+（推荐3.13） | 需支持SQLAlchemy 2.0+ |
| 内存 | 8GB+ | 运行浏览器自动化需要 |
| 磁盘空间 | 至少5GB | 包含虚拟环境和浏览器缓存 |

## 三、安装步骤

### 3.1 方法一：使用安装脚本（推荐）

1. **打开命令提示符（CMD）或PowerShell**
2. **进入项目目录**：
   ```bash
   cd c:\Users\houch\Desktop\pythonTools\site\GEO-SOP\GEObeta
   ```
3. **运行安装脚本**：
   ```bash
   .\install.bat
   ```

安装脚本会自动完成以下步骤：
- 删除旧的虚拟环境（如果存在）
- 在 `web_app` 目录下创建新的虚拟环境
- 安装项目依赖包
- 安装Playwright浏览器

### 3.2 方法二：手动安装

如果安装脚本失败，可以手动执行以下步骤：

1. **进入项目目录**：
   ```bash
   cd c:\Users\houch\Desktop\pythonTools\site\GEO-SOP\GEObeta
   ```

2. **创建虚拟环境**：
   ```bash
   python -m venv web_app\venv
   ```

3. **激活虚拟环境**：
   ```bash
   web_app\venv\Scripts\activate.bat
   ```

4. **安装依赖**：
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

5. **安装Playwright浏览器**：
   ```bash
   playwright install
   ```

## 四、启动应用

### 4.1 开发模式启动

1. **进入web_app目录**：
   ```bash
   cd c:\Users\houch\Desktop\pythonTools\site\GEO-SOP\GEObeta\web_app
   ```

2. **激活虚拟环境（如果未激活）**：
   ```bash
   venv\Scripts\activate.bat
   ```

3. **启动应用**：
   ```bash
   python app.py
   ```

4. **访问应用**：
   - 打开浏览器，访问 http://127.0.0.1:5001
   - 默认用户名：`admin`
   - 默认密码：`admin123`

### 4.2 快捷方式启动（Windows）

创建快捷方式文件 `启动应用.lnk`，双击即可运行：

```
目标位置：powershell.exe
目标：-Command "cd c:\Users\houch\Desktop\pythonTools\site\GEO-SOP\GEObeta\web_app; venv\Scripts\python.exe app.py; Start-Process http://127.0.0.1:5001"
```

## 五、功能说明

### 5.1 仪表盘（Dashboard）

**访问地址**：http://127.0.0.1:5001/dashboard

#### 5.1.1 AI平台登录验证
- 检查各大AI平台的登录状态
- 显示登录验证日志
- 支持手动触发登录检查

#### 5.1.2 GEO稿件被引用分析
- 管理GEO稿件列表
- 批量添加稿件URL（一行一个）
- 分析AI回答中引用GEO稿件的情况

### 5.2 任务结果（Results）

**访问地址**：http://127.0.0.1:5001/task/{task_id}/results

#### 5.2.1 问题列表视图
- 查看监控问题的采集结果
- 按日期范围筛选数据
- 统计品牌关键词命中情况

#### 5.2.2 答案浏览视图
- 查看AI平台的具体回答内容
- **引用参考匹配标记**：如果引用参考与GEO稿件匹配，会显示绿色标签"GEO稿件匹配: X"
- 支持重新采集单条答案
- 查看采集截图

### 5.3 数据导出

#### 5.3.1 导出数据
- 导出问题列表和答案数据
- 支持按平台筛选

#### 5.3.2 导出GEO结果
- 生成Excel表格，包含两个Sheet：
  - **Sheet1（GEO结果汇总）**：序号、AI平台、关键词、KPI、达标天数、日期
  - **Sheet2（GEO结果截图）**：包含达标答案的截图

## 六、URL匹配规则

在"答案浏览"视图的"引用参考"部分，系统会自动匹配GEO稿件，匹配规则如下：

1. **直接包含**：引用URL包含稿件URL，或稿件URL包含引用URL
2. **域名匹配**：两个URL的域名相同（如 `m.99.com.cn` 和 `www.99.com.cn`）
3. **清理后匹配**：去掉协议、扩展名、前缀后进行包含匹配
4. **数字匹配**：检查URL中5位以上的数字串是否相同

**示例**：
- 引用URL: `https://m.99.com.cn/a/2269587/`
- 稿件URL: `99.com.cn/2269587.htm`
- **匹配结果**：成功（域名相同且包含相同数字串）

## 七、目录结构

```
GEObeta/
├── install.bat              # 一键安装脚本
├── requirements.txt         # 项目依赖
├── browser_config.json      # 浏览器配置
├── answers/                 # AI回答数据存储目录
│   ├── doubao/              # 豆包回答数据
│   ├── wenxin/              # 文心一言回答数据
│   └── qianwen/             # 千问回答数据
├── browser_profile/         # 浏览器配置文件（缓存登录状态）
└── web_app/                 # Web应用目录
    ├── venv/                # Python虚拟环境
    ├── app.py               # Flask应用入口
    ├── models.py            # 数据模型
    ├── collector.py         # 数据采集模块
    ├── scheduler.py         # 定时调度模块
    ├── static/              # 静态资源
    ├── templates/           # 前端模板
    └── instance/            # SQLite数据库文件
```

## 八、常见问题

### 8.1 安装失败

**问题**：`pip install` 失败

**解决方案**：
- 确保Python版本 >= 3.10
- 升级pip：`python -m pip install --upgrade pip`
- 检查网络连接

### 8.2 浏览器登录失败

**问题**：AI平台登录验证失败

**解决方案**：
- 检查浏览器配置文件是否存在
- 尝试手动登录一次AI平台
- 确保浏览器profile目录有写入权限

### 8.3 数据采集失败

**问题**：定时任务没有采集到数据

**解决方案**：
- 检查日志输出
- 确认AI平台登录状态正常
- 检查网络连接

## 九、注意事项

1. **首次运行**：首次启动需要等待Playwright浏览器初始化
2. **浏览器缓存**：`browser_profile` 目录存储浏览器登录状态，请勿删除
3. **数据库备份**：定期备份 `web_app/instance/` 目录下的数据库文件
4. **性能优化**：建议定期清理 `answers/` 目录下的旧数据
5. **安全提醒**：生产环境请修改默认密码，设置强密码策略

---

**版本**：v1.0  
**最后更新**：2026年5月  
**开发团队**：GEObeta Team