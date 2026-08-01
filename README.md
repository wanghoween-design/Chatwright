# Chatwright 🦐

> Chat + Playwright：把「用浏览器和网页 AI 聊天」封装成一个网页应用。
> **不需要任何 API Key**，底层是一个机器人在浏览器里替你输入问题、等待回复、把答案抄回来。

**一句话：打开一个网页，输入一个问题，勾选几个 AI，一次全问完，结果并排对比。**

当前版本：**v1.5.5**（页面标题旁会显示版本号，重启后核对是否加载了新代码）

## 能做什么

| 功能 | 说明 |
|------|------|
| 多平台同时对话 | 一条消息同时发给 DeepSeek / 通义千问 / 元宝 / 豆包 / 智谱，结果卡片并排展示 |
| 多轮对话 / 上下文 | 默认在同一个对话里继续，模型记得上下文；可新建对话、随时切回旧对话 |
| 单平台停止 | 每个平台卡片上有「停止」按钮，不用等所有模型答完 |
| Markdown 渲染 | 表格 / 代码块 / 加粗 / 链接等格式正常显示 |
| 思考模式（按平台） | 每个平台可单独勾选「思考」，自动尝试开启网页上的深度思考开关 |
| 无头模式 | 侧边栏一键切换：聊天不弹浏览器窗口（登录仍需窗口） |
| 登录管理 | 网页里直接「去登录 / 重新登录 / 注销」，登录态本地保存 |
| 附件上传 | 发送时可附带文件（各平台支持度不同，功能框架已就绪） |
| 标准 MCP 接口 | 可接入 Claude Desktop / Cursor 等 MCP 客户端 |
| 终端交互 | 也可以直接在命令行里和某个平台对话 |

## 平台支持现状（2026-08 实测通过）

| 平台 | 状态 | 说明 |
|------|------|------|
| DeepSeek | ✅ 可用 | 需要登录一次（页面点「去登录」） |
| 通义千问 | ✅ 可用 | www.qianwen.com，游客模式直接可用 |
| 元宝 | ✅ 可用 | 需微信/手机/QQ 登录；常驻窗口保活 |
| 豆包 | ✅ 可用 | 需登录；常驻窗口保活；发送需点发送按钮（已自动处理） |
| 智谱（ChatGLM） | ✅ 可用 | 游客/登录均可；使用真实 Chrome，从首页进入避免风控墙 |

> Kimi 因登录态绑定浏览器实例、换窗口即失效，已暂时移除，后续可替换为其他网页 AI。
> 各平台网页版可能调整结构，失效时参考 `DEVELOPMENT_LOG.md` 的历史排查记录，
> 或用调试接口（`/api/debug/session/{平台}`）拉取真实 DOM 校准。

## 快速开始（Windows）

### 方式一：双击启动（最简单）

1. 双击项目根目录的 **`启动网站.bat`**
2. 会自动弹出黑色服务窗口，并打开浏览器访问 `http://127.0.0.1:8765`
3. 想停止服务：关掉黑色窗口即可

> 脚本会自动结束占用 8765 端口的旧进程，确保每次启动的都是最新代码。

### 方式二：命令行启动

```bash
cd Chatwright
.venv\Scripts\python run_web.py
```

然后打开浏览器访问 **http://127.0.0.1:8765**

### 首次安装（全新环境）

```bash
cd Chatwright
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\playwright install chromium
```

> ⚠️ 不要直接双击 `src/chatwright/web/static/index.html` 打开页面——那是纯静态文件，
> 连不上后端，平台列表不会显示。必须通过上面两种方式启动服务后访问 `http://127.0.0.1:8765`。

## 网页版使用说明

### 发送问题

1. 在输入框输入问题（支持中文，按 `Ctrl + Enter` 快速发送）
2. 勾选要问的平台（默认全选）
3. 点击「发送到所选平台」
4. 每个平台一张卡片，状态从「等待中 → 对话中 → 完成 / 失败」实时变化
5. 对话中可点卡片上的「**停止**」只停单个平台，其他平台照常运行
6. 完成后点「复制」可单独复制某条回复

### 对话管理（多轮上下文）

- **默认在同一对话里继续**：同一对话里连续发送的消息，各平台都能看到上文
- **新建对话**：点左侧「＋ 新建对话」，所有平台从全新会话开始；旧对话折叠到左侧列表
- **切回旧对话**：点左侧列表里的任意旧对话，各平台页面自动跳回当时的对话继续聊

### 登录 / 重新登录 / 注销

平台卡片右侧显示登录状态和操作按钮：

| 状态 | 按钮 | 作用 |
|------|------|------|
| 未登录 | 「去登录」 | 弹出浏览器窗口，手动登录一次，点「已登录，保存」 |
| 已登录 | 「重登」 | 用全新浏览器会话重新登录（换账号 / 登录态失效时） |
| 已登录 | 「注销」 | 删除本地保存的登录状态 |

> 登录态保存在本地浏览器配置目录（`state/` 下）。元宝 / 豆包 / 智谱使用「常驻窗口」模式：
> 登录后窗口保持运行（自动最小化到任务栏），**请勿关闭任务栏里的窗口**，否则需要重新登录。
> 每次重启服务后，这些平台通常需要重新登录一次。

### 发送选项

- **思考模式**：勾选平台后，在输入框下方按平台单独勾选「XX 思考」
- **模型**：各平台模型列表待校准，目前使用网页默认模型
- **附件**：选择一个文件随消息上传（需要平台支持上传）
- **无头模式**：侧边栏开关，开启后聊天不弹浏览器窗口（豆包/智谱因反自动化仍使用常驻窗口）

### 常见问题

- **某个平台失败会影响其他平台吗？** 不会，每个平台独立运行。
- **智谱出现「访问验证」？** 已自动处理：等待 30 秒风控清除，持续存在会恢复窗口提示。
  若仍失败，通常是当前网络被风控，稍后再试即可。
- **豆包弹出图片/滑块验证码？** 窗口会自动恢复到前台，按提示完成验证后重新发送。
- **元宝 / 豆包返回了思考过程或推荐内容？** 已内置过滤（思考块按类名排除、
  推荐/广告/输入按钮块按结构与文本特征排除）。
- **重启服务后版本没变？** 双击 `启动网站.bat` 后在页面按 `Ctrl+F5` 强制刷新，
  标题旁应显示 v1.5.5。

## 终端版（可选）

```bash
set PLAYWRIGHT_BROWSERS_PATH=%cd%\.pw-browsers
.venv\Scripts\python chat.py            # DeepSeek（默认）
.venv\Scripts\python chat.py --qwen     # 通义千问
.venv\Scripts\python chat.py --yuanbao  # 元宝
.venv\Scripts\python chat.py --doubao   # 豆包
.venv\Scripts\python chat.py --zhipu    # 智谱
```

首次使用某平台需要先登录（登录态保存在 `state/` 目录）：

```bash
.venv\Scripts\python tests\login_any.py deepseek
.venv\Scripts\python tests\login_any.py qwen
.venv\Scripts\python tests\login_any.py yuanbao
.venv\Scripts\python tests\login_any.py doubao
.venv\Scripts\python tests\login_any.py zhipu
```

## MCP 版（可选）

```bash
cd src
set PYTHONPATH=.
.venv\Scripts\python -m chatwright.server
```

接入 Claude Desktop，在 `claude_desktop_config.json` 中添加：

```json
{
  "mcpServers": {
    "chatwright": {
      "command": "你的 python 路径",
      "args": ["-m", "chatwright.server"],
      "env": { "PYTHONPATH": "Chatwright 项目的 src 绝对路径" }
    }
  }
}
```

暴露的工具：

| 工具 | 说明 |
|------|------|
| `web_ai_chat(message, mock=False, timeout=120)` | 和网页 AI 聊天并返回回复文本 |
| `web_ai_new_session()` | 开启新对话（清空上下文） |
| `web_ai_save_login()` | 保存当前浏览器登录态，下次自动复用 |

## 架构

```
        网页版 UI（浏览器）                  MCP 客户端（Claude / Cursor）
              │                                   │
        FastAPI 后端 (webapp.py)              MCP Server (server.py)
              └────────────────┬──────────────────┘
                               │
                      BrowserManager (browser.py)
                      Playwright 驱动 Chromium + 登录态持久化
                               │
                     Provider（可插拔，模板方法模式）
               DeepSeek ✅ / 通义 ✅ / 元宝 ✅ / 豆包 ✅ / 智谱 ✅
```

核心设计：

- 所有网页 AI 的对话流程都一样（打开页面 → 输入发送 → 等流式回复 → 抓取结果），
  基类 `WebChatProvider` 用模板方法模式固定通用流程，新平台只需实现少量钩子；
- 回复抓取采用「全页文字普查」：以用户消息为锚点，取其后最大的非推荐文本块，
  不依赖各平台的具体类名，推荐/广告/思考块/输入按钮按类名与文本特征排除；
- 登录状态使用持久化浏览器配置目录，兼容 cookie、sessionStorage 等不同登录机制。

## 项目结构

```
Chatwright/
├── 启动网站.bat                 # 双击启动网页版（自动杀旧进程、打开浏览器）
├── run_web.py                   # 网页版启动入口
├── chat.py                      # 终端交互入口
├── requirements.txt             # 依赖：mcp / playwright / fastapi / uvicorn
├── DEVELOPMENT_LOG.md           # 开发问题日志（每条含现象/病因/解决，可 grep 检索）
├── src/chatwright/
│   ├── webapp.py                # 网页版后端（FastAPI）：聊天任务 + 登录管理 + 调试接口
│   ├── web/static/index.html    # 网页版前端
│   ├── server.py                # MCP Server
│   ├── browser.py               # 浏览器生命周期 + 登录态持久化 + 反检测
│   └── providers/               # 各平台 Provider（模板方法模式）
│       ├── base.py              # 抽象基类（通用流程 + 文字普查抓取）
│       ├── deepseek.py / qwen.py / yuanbao.py / doubao.py / zhipu.py
│       └── kimi.py / mock.py    # 已下线平台，文件保留备参考
├── tests/                       # 端到端自测、DOM 探针、登录助手
└── state/                       # 登录态/浏览器配置（自动生成，已 gitignore）
```

## 调试接口（排查用）

| 接口 | 用途 |
|------|------|
| `/api/version` | 查看运行中的服务版本 |
| `/api/debug/session/{平台}` | 查看平台会话的 URL、页面正文、文字清单、候选选择器命中 |
| `/api/debug/login/{平台}` | 查看登录窗口的真实页面内容（排查登录失败） |

## 路线图

- [ ] Coze 式画布布局：左侧模型列表 + 中间画布 + 并行/链式连线 + 连线指令节点
- [ ] 各平台模型切换列表校准（目前用网页默认模型）
- [ ] 文件上传的逐平台校准
- [ ] 自愈式元素定位：选择器漂移时自动重新定位
- [ ] 流式返回：边生成边显示
- [ ] 引入国外网页 AI（替换已下线的 Kimi 位置）

## ⚠️ 重要声明

- 自动化访问网页 AI 可能违反其服务条款，本项目仅用于**个人学习 / 作品集演示**，
  请勿作为生产方案对外售卖或大规模调用。
- 网页 AI 的 DOM 结构会变动，平台失效时按 `DEVELOPMENT_LOG.md` 的历史排查记录
  与调试接口重新校准即可。
