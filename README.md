# Chatwright 🦐

> **Chat + Playwright** —— 把"用浏览器跟网页 AI 聊天"封装成一个标准 MCP 工具。
> Agent 无需任何 API key，也能和网页版 AI（DeepSeek / Kimi / 通义千问 …）对话，底层是一个机器人在浏览器里替它敲字。

## 它解决什么问题

网页 AI 通常只暴露网页界面、不提供免费 API。传统做法要么付费买 key，要么被限流。
Chatwright 换了个思路：**用 RPA（浏览器自动化）模拟人操作网页，把"和网页 AI 聊天"封装成 MCP 工具**。
对上层 Agent 来说，它"以为"自己在调一个聊天接口；实际上背后是 Playwright 在浏览器里输入、等待流式生成、抓取回复。

这是「RPA 封装成 MCP」最具体的落地形态之一——垂直场景 = 网页 AI 对话，护城河 = 流式完成检测 + 登录态持久化 +（规划中的）自愈式元素定位。

## 架构

```
              MCP 客户端（Claude Desktop / Cursor / 自建 Agent）
                          │  stdio
                          ▼
               ┌─────────────────────────┐
               │     Chatwright MCP       │  暴露工具：
               │      Server (server.py)  │   • web_ai_chat(message)
               └───────────┬─────────────┘   • web_ai_new_session()
                           │ 调用             • web_ai_save_login()
                           ▼
               ┌─────────────────────────┐
               │  BrowserManager          │  Playwright 驱动 Chromium
               │  (browser.py)            │  + 登录态(storage_state)持久化
               └───────────┬─────────────┘
                           │ 操作页面
                           ▼
               ┌─────────────────────────┐
               │  Provider（可插拔）        │  WebChatProvider(模板方法基类)
               │  providers/              │   ├─ DeepSeekProvider ✅ 已对接
               │                          │   ├─ KimiProvider    🔧 选择器待校准
               │                          │   ├─ QwenProvider    🔧 选择器待校准
               │                          │   └─ MockProvider    ✅ 本地演示
               └─────────────────────────┘
```

**设计模式：模板方法（Template Method）**

通用对话流程在抽象基类 `WebChatProvider` 中定义，各平台只需重写三个钩子：

| 钩子方法 | 职责 |
|---------|------|
| `_after_open()` | 打开页面后的处理（如登录态检测、关闭弹窗） |
| `_type_and_submit(message)` | 在输入框中填入消息并提交 |
| `_bubbles()` | 定位页面上的"助手消息气泡"元素 |

因此新增一个网页 AI（ChatGPT / Gemini 网页版 …）只需写一个几十行的 Provider。

## 当前进度

| 模块 | 状态 | 说明 |
|------|------|------|
| 基类 `WebChatProvider` | ✅ 完成 | 模板方法模式，流式完成检测（防抖 1.5s） |
| `BrowserManager` | ✅ 完成 | Playwright 驱动 + 多平台独立登录态持久化 |
| `MockProvider` + mock 页面 | ✅ 完成 | 本地演示页，用于无网络自测 |
| `DeepSeekProvider` | ✅ 基本可用 | 已有登录态文件，选择器为启发式写法 |
| `KimiProvider` | 🔧 骨架就绪 | 输入框选择器已确认（`.chat-input-editor`），回复气泡待登录后校准 |
| `QwenProvider` | 🔧 骨架就绪 | 选择器全部为启发式猜测，需登录后实测校准 |
| MCP Server (`server.py`) | ✅ 基本可用 | stdio 传输，暴露 3 个工具 |
| 终端交互 (`chat.py`) | ✅ 完成 | 支持 `--deepseek / --kimi / --qwen / --mock` 多平台切换 |
| 统一登录助手 | ✅ 完成 | `tests/login_any.py <平台名>`，手动登录一次后自动保存 |

## 安装

```bash
cd Chatwright
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
playwright install chromium
```

依赖：`mcp>=1.2.0,<2` + `playwright>=1.40.0`

## 运行

### 1）本地自测（无需登录，推荐先跑这个验证流水线）

```bash
set PYTHONPATH=src
.venv\Scripts\python tests\test_mock.py
```

会打开无头浏览器，对接 `tests/mock_chat.html`，输出模拟回复并断言成功。

### 2）终端交互式对话

```bash
# 先设置浏览器路径（Windows）
set PLAYWRIGHT_BROWSERS_PATH=%cd%\.pw-browsers

# 选择平台
.venv\Scripts\python chat.py              # DeepSeek（默认）
.venv\Scripts\python chat.py --kimi       # Kimi
.venv\Scripts\python chat.py --qwen       # 通义千问
.venv\Scripts\python chat.py --mock       # 本地演示（无需登录）
```

首次使用新平台需先手动登录一次：

```bash
.venv\Scripts\python tests\login_any.py deepseek
.venv\Scripts\python tests\login_any.py kimi
.venv\Scripts\python tests\login_any.py qwen
```

登录态自动保存到 `state/<平台>_storage.json`，之后直接用。

### 3）作为 MCP Server 启动

```bash
cd src
set PYTHONPATH=.
.venv\Scripts\python -m chatwright.server
```

默认 stdio 传输。首次对接真实网页时浏览器以**可见模式**启动，
请在弹出的窗口里手动登录一次；登录态会自动保存到 `state/` 目录，之后复用。

### 4）接 Claude Desktop

在 Claude Desktop 的 `claude_desktop_config.json` 加入：

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

重启 Claude Desktop 后，直接对它说"用 Chatwright 跟网页 DeepSeek 聊一句：你好"即可。

## 提供的工具

| 工具 | 说明 |
|------|------|
| `web_ai_chat(message, mock=False, timeout=120)` | 发消息并等回完，返回回复文本；`mock=True` 走本地演示页 |
| `web_ai_new_session()` | 开新对话（清空上下文） |
| `web_ai_save_login()` | 保存当前登录态，下次自动复用 |

## 项目结构

```
Chatwright/
├── chat.py                       # 终端交互式对话入口（多平台）
├── requirements.txt              # mcp + playwright
├── src/
│   └── chatwright/
│       ├── __init__.py           # 包入口，版本号
│       ├── browser.py            # BrowserManager：浏览器生命周期 + 登录态持久化
│       ├── server.py             # MCP Server 入口，暴露 3 个工具
│       └── providers/
│           ├── __init__.py
│           ├── base.py           # WebChatProvider 抽象基类（模板方法模式）
│           ├── deepseek.py       # DeepSeek 网页版 Provider
│           ├── kimi.py           # Kimi 网页版 Provider
│           ├── qwen.py           # 通义千问网页版 Provider
│           └── mock.py           # 本地演示用 Provider
├── tests/
│   ├── mock_chat.html            # 本地模拟 AI 聊天页面
│   ├── test_mock.py              # Mock 端到端自测
│   ├── test_deepseek.py          # DeepSeek 真实站测试（需手动登录）
│   ├── run_deepseek.py           # 用已保存登录态快速测试 DeepSeek
│   ├── probe_deepseek.py         # DeepSeek DOM 探针（校准选择器用）
│   ├── probe_kimi_qwen.py        # Kimi / 通义 DOM 探针
│   ├── probe_kimi_interactive.py # Kimi 交互式探针
│   └── login_any.py              # 统一登录助手
└── state/
    └── chatwright_storage.json   # DeepSeek 登录态（自动生成）
```

## ⚠️ 重要声明（必读）

- 自动化访问网页 AI **可能违反其服务条款**，仅限**个人学习 / 作品集演示**使用，请勿作为生产方案对外售卖或大规模调用。
- 网页 AI 的 DOM 结构会变动，真实站选择器（见各 `providers/*.py`）需按实测校准。

## 路线图（v1+）

- [ ] **自愈式元素定位**：选择器漂移时由 LLM 依据页面快照重新定位，抵抗 UI 改版
- [ ] 多 Provider 完善：Kimi / 通义千问选择器校准 → ChatGPT / Gemini 网页版
- [ ] 流式返回：边生成边回传给 Agent（而非等整段完成）
- [ ] 会话管理：多会话切换、历史持久化
- [ ] headless 生产化 + 反检测策略

---

> 项目名由来：Chat + Playwright 双关，发音近 "chat right"。
