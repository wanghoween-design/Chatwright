"""Chatwright MCP Server 入口。

核心思路：
  把"和网页版 AI 聊天"这件事封装成 MCP 标准工具，这样任何支持 MCP 协议的
  客户端（Claude Desktop、Cursor、自建 Agent 等）都能像调函数一样使用它，
  而底层其实是用 Playwright 浏览器自动化——帮你在网页上自动输入、等待回复、
  再把回复文本抓回来。

工作流程：
  1. 服务器启动时，自动打开一个浏览器窗口（首次需要你手动登录 DeepSeek）
  2. 客户端调用 web_ai_chat 工具 → 服务器在浏览器中自动输入消息 → 等待
     AI 流式生成完毕 → 抓取最后一条回复的文本返回给客户端
  3. 登录态可以保存，下次启动自动复用，不用重复登录

运行方式：
    cd src
    PYTHONPATH=. python -m chatwright.server
  使用 stdio 传输，MCP 客户端零配置即可连接
"""

from __future__ import annotations  # 允许在类型注解中使用 Python 3.10+ 的语法（如 str | int）

from contextlib import asynccontextmanager  # 用于定义异步上下文管理器（管理服务器启动/关闭生命周期）
from pathlib import Path  # 跨平台文件路径处理

from mcp.server.fastmcp import FastMCP  # MCP 服务器框架，一行代码就能暴露工具函数

# 以下是项目内部模块：
from chatwright.browser import BrowserManager  # 浏览器生命周期管理（启动、停止、保存登录态）
from chatwright.providers.deepseek import DeepSeekProvider  # DeepSeek 网页端的自动化操作逻辑
from chatwright.providers.mock import MockProvider  # 本地 mock 页面，用于演示和自测（不需要联网）

# mock 模式使用的本地 HTML 文件路径，用于不需要真实 DeepSeek 账号的演示/测试场景
# 路径计算：当前文件 → src/chatwright/ → src/ → 项目根目录 → tests/mock_chat.html
MOCK_HTML = Path(__file__).resolve().parent.parent.parent / "tests" / "mock_chat.html"

# 先创建一个临时的 mcp 实例（下面会用带 lifespan 的覆盖它，这行其实可以删掉）
mcp = FastMCP("Chatwright")


@asynccontextmanager
async def lifespan(_app):
    """服务器生命周期管理器。

    作用：在 MCP 服务器启动时自动打开浏览器，关闭时自动清理资源。
    这样所有工具函数共享同一个浏览器页面，避免重复启动/关闭。

    流程：
      启动 → 创建 BrowserManager → 启动浏览器并打开一个页面
      → yield 将 bm 和 page 通过上下文传递给所有工具函数
      → 服务器关闭时 → 自动调用 bm.stop() 关闭浏览器
    """
    bm = BrowserManager(headless=False)  # headless=False 表示显示浏览器窗口（方便首次登录）
    page = await bm.start()  # 启动浏览器并获取默认页面
    try:
        yield {"bm": bm, "page": page}  # 将浏览器管理器和页面对象注入到 MCP 上下文中
    finally:
        await bm.stop()  # 无论发生什么，服务器关闭时都清理浏览器资源


# 用带 lifespan 的版本覆盖上面的 mcp，这样服务器启动时会自动管理浏览器生命周期
mcp = FastMCP("Chatwright", lifespan=lifespan)


@mcp.tool()  # @mcp.tool() 装饰器将这个函数注册为 MCP 工具，客户端就能远程调用它
async def web_ai_chat(message: str, mock: bool = False, timeout: int = 120) -> str:
    """【核心工具】和网页版 AI 聊天，返回它的回复文本（无需任何 API key）。

    Args:
        message: 要发送的消息内容。
        mock: True 时对接本地 mock 演示页（无需登录，适合演示/自测）；
              False（默认）对接真实网页 DeepSeek。
        timeout: 等待回复生成的最长秒数，默认 120。

    底层由 Playwright 在浏览器中完成：打开网页 → 输入 → 等待流式生成完成 →
    抓取最后一条回复文本。首次对接真实站需手动登录一次，登录态会自动保存复用。
    """
    # 从 MCP 上下文中取出 lifespan 阶段注入的浏览器页面对象
    ctx = mcp.get_context().request_context.lifespan_context
    page = ctx["page"]

    # 根据 mock 参数选择不同的 Provider（策略模式）：
    #   - MockProvider：使用本地 HTML 文件模拟 AI 聊天，适合开发调试
    #   - DeepSeekProvider：操控真实的 DeepSeek 网页，需要已登录
    if mock:
        provider = MockProvider(page, base_url="file://" + str(MOCK_HTML))
    else:
        provider = DeepSeekProvider(page)

    # 调用 provider.send() 完成：在浏览器中输入消息 → 等待 AI 回复 → 返回文本
    return await provider.send(message, timeout=timeout)


@mcp.tool()
async def web_ai_new_session() -> str:
    """开启一个新的对话（清空上下文）。

    原理：直接导航到 DeepSeek 首页，相当于在浏览器中点击"新对话"按钮。
    之前的聊天上下文不会带到新会话中。
    """
    ctx = mcp.get_context().request_context.lifespan_context
    page = ctx["page"]
    await page.goto("https://chat.deepseek.com")  # 导航到 DeepSeek 首页，自动开启新会话
    return "新会话已开启"


@mcp.tool()
async def web_ai_save_login() -> str:
    """把当前浏览器登录态（cookie 等）保存到本地文件，供下次启动时自动复用。

    使用场景：首次登录 DeepSeek 后调用此工具保存登录态，之后重启服务器
    就不用再手动登录了。
    """
    ctx = mcp.get_context().request_context.lifespan_context
    bm: BrowserManager = ctx["bm"]
    await bm.save_state()  # 将浏览器的 cookie、localStorage 等持久化到本地 JSON 文件
    return f"登录态已保存到 {bm.__class__ and 'state/chatwright_storage.json'}"


if __name__ == "__main__":
    # 以 stdio 传输模式启动 MCP 服务器
    # stdio 模式意味着通过标准输入/输出与客户端通信（而非 HTTP）
    # MCP 客户端（如 Claude Desktop）会自动启动这个进程并双向通信
    mcp.run(transport="stdio")
