"""网页 AI 聊天 Provider 抽象基类。

设计模式：模板方法模式（Template Method）

核心思想：
  所有"网页 AI"平台（DeepSeek / ChatGPT / Kimi / 通义……）的对话流程都一样：
    打开页面 → 输入并发送 → 等待流式生成完成 → 抓取最后一条回复
  唯一的差异在于"每个平台的网页元素怎么定位"。

因此采用模板方法模式：
  - 基类（本文件）定义通用流程骨架，包含完整的游戏逻辑
  - 子类只需重写三个"钩子方法"，告诉基类怎么操作具体平台的页面元素：
      _after_open()        打开页面后的处理（如登录态检测、关闭新手引导弹窗）
      _type_and_submit()    如何在输入框中填入消息并提交（按 Enter 或点发送按钮）
      _bubbles()            如何定位页面上的"助手消息气泡"元素

使用方式：
  继承 WebChatProvider → 实现三个抽象方法 → 就能自动获得完整的聊天流程
"""

from __future__ import annotations  # 允许类型注解使用 Python 3.10+ 语法

import time  # 用于超时计时
from abc import ABC, abstractmethod  # 抽象基类支持

from playwright.async_api import Locator, Page  # Playwright 的页面和元素定位器类型


class WebChatProvider(ABC):
    """所有网页 AI 聊天平台的抽象基类。

    子类必须实现：
      - _type_and_submit(message)  在页面上输入并发送消息
      - _bubbles()                 返回页面上所有"助手消息气泡"的定位器

    子类可选择重写：
      - _after_open()              页面打开后的初始化操作（如关闭弹窗）
    """

    def __init__(self, page: Page, base_url: str):
        self.page = page          # Playwright 页面对象，所有操作都通过它进行
        self.base_url = base_url  # 目标平台的网址（如 DeepSeek 的 URL）
        self._opened = False      # 标记页面是否已经打开过，避免重复导航

    async def open(self) -> None:
        """打开目标网页（仅首次调用时执行导航，后续调用直接跳过）。

        流程：导航到目标 URL → 调用子类的 _after_open() 钩子处理后续初始化
        """
        if not self._opened:  # 懒加载：只在第一次调用时导航
            await self.page.goto(self.base_url, wait_until="domcontentloaded")
            await self._after_open()  # 调用子类钩子（如关闭弹窗、检测登录态）
            self._opened = True

    async def _after_open(self) -> None:
        """【钩子方法】子类可重写：页面打开后的自定义操作。

        典型用途：关闭新手引导弹窗、检测登录态、处理 Cookie 同意框等。
        默认实现什么都不做（不是所有平台都需要额外操作）。
        """
        pass

    async def send(self, message: str, timeout: int = 120) -> str:
        """【模板方法】端到端发送一条消息并等待回复，返回回复文本。

        这是整个类的核心流程，定义了"发消息→等回复→取结果"的标准步骤：
          1. open()           — 确保页面已打开
          2. _type_and_submit — 在输入框中输入消息并提交（子类实现）
          3. _wait_for_reply  — 等待 AI 流式生成完毕
          4. _extract_last_reply — 从页面上抓取最后一条回复文本
        """
        await self.open()  # 确保页面已打开（首次才真正导航）
        await self._type_and_submit(message)  # 子类实现：在页面上输入并发送消息
        await self._wait_for_reply(timeout=timeout)  # 等待流式生成完成
        return await self._extract_last_reply()  # 抓取最后一条助手消息的文本

    @abstractmethod
    async def _type_and_submit(self, message: str) -> None:
        """【抽象方法 — 子类必须实现】把消息填入输入框并提交。

        子类需要根据具体平台的页面结构，找到输入框元素，填入文本，
        然后触发提交（按 Enter 键或点击发送按钮）。
        """
        ...

    @abstractmethod
    async def _bubbles(self) -> Locator:
        """【抽象方法 — 子类必须实现】返回页面上所有"助手消息气泡"元素的定位器。

        返回的 Locator 应该能匹配到页面上所有 AI 助手的回复消息元素。
        基类会用 .last 取最后一个作为最新回复。

        为什么返回 Locator 而不是元素列表：
          - Locator 是"惰性"的，只有真正操作时才去查找元素
          - 每次调用都能拿到最新的页面状态（适合流式生成场景）
        """
        ...

    async def _wait_for_reply(self, timeout: int = 120, stable: float = 1.5) -> None:
        """等待 AI 流式回复生成完成。

        原理（防抖检测）：
          AI 回复是逐字流式输出的，每 0.5 秒轮询一次最后一条消息的文本。
          当文本连续 stable 秒（默认 1.5 秒）没有变化，就认为生成已经结束。

        为什么不用"检测停止按钮消失"等方案：
          - 不同平台的停止按钮样式不同，需要子类分别实现
          - 文本稳定检测是平台无关的，基类就能搞定
          - 即使平台 UI 改版，只要消息气泡还在就不会失效

        参数：
          timeout: 最长等待秒数，超时后返回已抓取的文本（不抛异常）
          stable:  文本连续不变多少秒后判定为"生成完毕"
        """
        last = ""  # 上一次轮询时的文本内容
        start = time.monotonic()  # 记录开始时间（单调时钟，不受系统时间调整影响）
        while time.monotonic() - start < timeout:  # 还没超时就继续轮询
            cur = (await self._extract_last_reply()).strip()  # 获取当前最新回复文本
            if cur and cur == last:  # 文本非空且和上次一样 → 生成可能已结束
                return  # 提前返回（正常完成路径）
            last = cur  # 更新"上次文本"，继续下一轮等待
            await self.page.wait_for_timeout(int(stable * 1000))  # 等 stable 秒后再检查
        # 超时了也正常返回（不抛异常），此时 last 里保存着已抓取到的部分文本

    async def _extract_last_reply(self) -> str:
        """从页面上抓取最后一条助手消息的文本。

        调用子类实现的 _bubbles() 获取所有助手消息定位器，
        取最后一个元素的 inner_text 作为最新回复。
        """
        bubbles = await self._bubbles()  # 子类返回的助手消息定位器
        if await bubbles.count() == 0:  # 页面上还没有任何助手消息
            return ""
        return (await bubbles.last.inner_text()).strip()  # 取最后一条消息的文本
