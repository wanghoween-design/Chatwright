# Chatwright 🦐

> Chat + Playwright：把「用浏览器和网页 AI 聊天」封装成一个网页应用和标准接口。
> **不需要任何 API Key**，底层是一个机器人在浏览器里替你输入问题、等待回复、把答案抄回来。

**一句话：打开一个网页，输入一个问题，勾选几个 AI，一次全问完，结果并排对比。**

## 能做什么

| 功能 | 说明 |
|------|------|
| 多平台同时对话 | 一条消息同时发给 DeepSeek / Kimi / 通义千问，结果卡片并排展示 |
| 多轮对话 / 上下文 | 默认在同一个对话里继续，模型记得上下文；可新建对话、随时切回旧对话 |
| 网页版界面 | 输入框 + 平台勾选 + 实时进度 + 单条复制，浏览器里直接操作 |
| 无需 API Key | 通过 Playwright 浏览器自动化操作网页版 AI |
| 登录态自动保存 | 每个平台独立保存登录状态，登录一次长期有效 |
| 登录管理 | 网页里直接「去登录 / 重新登录 / 注销」 |
| 本地演示模式 | 内置 Mock 页面，不联网也能完整演示流程 |
| 标准 MCP 接口 | 可接入 Claude Desktop / Cursor 等 MCP 客户端 |
| 终端交互 | 也可以直接在命令行里和某个平台对话 |

## 平台支持现状（2026-08 实测）

| 平台 | 状态 | 说明 |
|------|------|------|
| DeepSeek | ✅ 可用 | 需要登录一次（在页面点「去登录」） |
| 通义千问 | ✅ 可用 | www.qianwen.com，游客模式直接可用，无需登录 |
| Kimi | 🔧 需登录 | Kimi 强制要求登录后才能对话（登录后回复气泡选择器还需最后校准） |
| 本地演示（Mock） | ✅ 可用 | 无需登录、无需网络 |

> 注：Kimi / 通义等网页版产品可能调整页面结构，若某平台失效，按测试目录里的探针脚本重新校准即可。

## 快速开始（Windows）

### 方式一：双击启动（最简单）

1. 双击项目根目录的 **`启动网站.bat`**
2. 会自动弹出黑色服务窗口，并打开浏览器访问 `http://127.0.0.1:8765`
3. 想停止服务：关掉黑色窗口即可

### 方式二：命令行启动

```bash
cd Chatwright
.venv\Scripts\python run_web.py
```

然后手动打开浏览器访问 **http://127.0.0.1:8765**

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
5. 完成后点卡片上的「复制」，可以单独复制某条回复

### 对话管理（多轮上下文）

- **默认在同一对话里继续**：同一对话里连续发送的消息，各平台都能看到上文，
  模型会记得你之前说的内容（比如让它记一个数字，下一轮能答上来）
- **新建对话**：点左侧「＋ 新建对话」，所有平台从全新会话开始；
  之前的对话折叠到左侧列表里，不会丢失
- **切回旧对话**：点左侧列表里的任意旧对话，各平台页面会自动跳回当时
  的对话继续聊，上下文还在

### 登录 / 重新登录 / 注销

平台卡片右侧会显示登录状态和操作按钮：

| 状态 | 按钮 | 作用 |
|------|------|------|
| 未登录 | 「去登录」 | 弹出浏览器窗口，手动登录一次，回到页面点「已登录，保存」 |
| 已登录 | 「重登」 | 用全新浏览器会话重新登录（适合换账号 / 登录态失效时） |
| 已登录 | 「注销」 | 删除本地保存的登录状态，之后该平台需要重新登录 |

登录流程：点按钮 → 弹出真实浏览器窗口 → 在窗口里登录 → 回到网页点「已登录，保存」
→ 登录状态自动保存在本地浏览器配置目录（`state/` 下），下次免登录。

> 说明：登录状态用「持久化浏览器配置目录」保存（不是只存 cookie），
> 兼容 Kimi 这类把登录凭证存在 sessionStorage / 浏览器指纹里的网站。

### 常见问题

- **Kimi 报「需要先登录才能对话」**：正常，Kimi 强制要求登录。点 Kimi 卡片上的「去登录」完成登录后重试。
- **某个平台失败会影响其他平台吗？** 不会。每个平台独立运行，失败只显示在它自己的卡片上。
- **DeepSeek 登录态失效了？** 点 DeepSeek 卡片上的「重登」重新登录一次即可。
- **登录窗口没弹出来？** 检查浏览器是否拦截了弹出窗口，或看黑色服务窗口里有没有报错。
- **点「已登录，保存」提示登录没完成？** 说明浏览器窗口里的登录还没成功（登录框仍在）。
  回到弹出的浏览器窗口完成登录，再点一次「已登录，保存」即可。
- **每次发送都是新会话**：当前每次发送都会开新对话，多轮连续对话在路线图中。

## 终端版（可选）

```bash
set PLAYWRIGHT_BROWSERS_PATH=%cd%\.pw-browsers
.venv\Scripts\python chat.py            # DeepSeek（默认）
.venv\Scripts\python chat.py --kimi     # Kimi
.venv\Scripts\python chat.py --qwen     # 通义千问
.venv\Scripts\python chat.py --mock     # 本地演示
```

首次使用某平台需要先登录（登录态保存在 `state/` 目录）：

```bash
.venv\Scripts\python tests\login_any.py deepseek
.venv\Scripts\python tests\login_any.py kimi
.venv\Scripts\python tests\login_any.py qwen
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
               DeepSeek ✅ / Kimi 🔧 / Qwen ✅ / Mock ✅
```

核心设计：所有网页 AI 的对话流程都一样（打开页面 → 输入发送 → 等流式回复 → 抓取结果），
差异只在页面元素选择器。基类 `WebChatProvider` 用模板方法模式固定通用流程，
新平台只需实现三个钩子：

| 钩子方法 | 职责 |
|----------|------|
| `_after_open()` | 打开页面后的处理（登录检测、关弹窗） |
| `_type_and_submit(message)` | 在输入框填入消息并提交 |
| `_bubbles()` | 定位页面上的助手回复气泡 |

## 项目结构

```
Chatwright/
├── 启动网站.bat                 # 双击启动网页版（自动打开浏览器）
├── run_web.py                   # 网页版启动入口
├── chat.py                      # 终端交互入口
├── requirements.txt             # 依赖：mcp / playwright / fastapi / uvicorn
├── src/chatwright/
│   ├── webapp.py                # 网页版后端（FastAPI）：聊天任务 + 登录管理
│   ├── web/static/index.html    # 网页版前端
│   ├── server.py                # MCP Server
│   ├── browser.py               # 浏览器生命周期 + 登录态持久化
│   └── providers/               # 各平台 Provider（模板方法模式）
│       ├── base.py              # 抽象基类（通用流程）
│       ├── deepseek.py / kimi.py / qwen.py / mock.py
├── tests/                       # 端到端自测、DOM 探针、登录助手
└── state/                       # 登录态文件（自动生成，已 gitignore）
```

## 路线图

- [ ] Kimi 登录后校准回复气泡选择器
- [ ] 自愈式元素定位：选择器漂移时自动重新定位，抵抗 UI 改版
- [ ] 多轮连续对话（当前每次发送都是新会话）
- [ ] 流式返回：边生成边显示
- [ ] headless 生产化 + 反检测策略

## ⚠️ 重要声明

- 自动化访问网页 AI 可能违反其服务条款，本项目仅用于**个人学习 / 作品集演示**，
  请勿作为生产方案对外售卖或大规模调用。
- 网页 AI 的 DOM 结构会变动，平台选择器失效时需按实测重新校准
  （参考 `tests/` 下的探针脚本）。
