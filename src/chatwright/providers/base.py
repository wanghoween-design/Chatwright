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
        self._modal_seen = False  # 登录弹窗宽限期状态
        self._modal_since = 0.0

    def _modal_persisted(self, visible: bool, timeout: float = 6.0) -> bool:
        """登录弹窗是否已持续可见 timeout 秒。

        部分网站（Kimi 等）打开页面时会先短暂显示登录界面，1-2 秒后自动登录，
        因此不能一看到弹窗就判定「未登录」，需要持续可见超过宽限期才算。
        """
        now = time.monotonic()
        if visible:
            if not self._modal_seen:
                self._modal_seen = True
                self._modal_since = now
            return now - self._modal_since >= timeout
        self._modal_seen = False
        return False

    async def _restore_window(self) -> None:
        """把当前页面窗口恢复到前台（出现验证码需要人工操作时调用）。"""
        try:
            cdp = await self.page.context.new_cdp_session(self.page)
            window_id = (await cdp.send("Browser.getWindowForTarget"))["windowId"]
            await cdp.send(
                "Browser.setWindowBounds",
                {
                    "windowId": window_id,
                    "bounds": {
                        "windowState": "normal",
                        "left": 120,
                        "top": 80,
                        "width": 1100,
                        "height": 800,
                    },
                },
            )
        except Exception:
            try:
                await self.page.bring_to_front()
            except Exception:
                pass

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
        await self._wait_for_reply(timeout=timeout, exclude=message)  # 等待流式生成完成
        return await self._extract_last_reply(exclude=message)  # 抓取最后一条助手消息的文本

    async def apply_options(self, options: dict) -> None:
        """发送前应用可选设置（思考模式 / 模型切换 / 文件上传）。子类按需重写。"""
        if options.get("file"):
            await self._upload_file(str(options["file"]))
        if options.get("thinking"):
            await self._enable_thinking()
        if options.get("model"):
            await self._pick_model(str(options["model"]))

    async def _enable_thinking(self) -> None:
        """默认实现：尝试点击常见的「深度思考 / 思考」开关，找不到就忽略。"""
        await self._click_text_if_visible(["深度思考", "思考", "DeepThink", "Thinking"])

    async def _pick_model(self, model: str) -> None:
        """模型切换高度平台相关，基类默认不实现（子类按需重写）。"""
        pass

    async def _upload_file(self, path: str) -> None:
        """默认实现：找页面上的文件输入框并设置文件。"""
        box = self.page.locator("input[type='file']").first
        if await box.count() == 0:
            raise RuntimeError("当前页面没有找到文件上传入口，该平台可能不支持上传")
        await box.set_input_files(path)

    async def _click_text_if_visible(self, texts: list[str], timeout: int = 3000) -> bool:
        """点第一个可见的指定文字元素（用于思考开关、按钮等），找不到返回 False。"""
        for text in texts:
            loc = self.page.locator(f"text={text}")
            n = await loc.count()
            for i in range(n):
                try:
                    if await loc.nth(i).is_visible():
                        await loc.nth(i).click(timeout=timeout)
                        return True
                except Exception:
                    continue
        return False

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

    async def _wait_for_reply(
        self,
        timeout: int = 120,
        stable: float | None = None,
        min_wait: float | None = None,
        exclude: str = "",
        max_continue: int = 2,
    ) -> None:
        """等待 AI 流式回复生成完成。

        原理（防抖检测）：
          AI 回复是逐字流式输出的，每 0.5 秒轮询一次最后一条消息的文本。
          当文本连续 stable 秒没有变化、总等待超过 min_wait、且页面没有生成中
          指示（停止按钮 / 搜索提示），才认为生成已经结束。
          更长的稳定期与最短等待时间可以避免「思考 / 联网搜索停顿」被误判为
          回答完毕而截断；结束后若出现「继续生成」按钮会自动点击续写。

        为什么不用"检测停止按钮消失"等方案：
          - 不同平台的停止按钮样式不同，需要子类分别实现
          - 文本稳定检测是平台无关的，基类就能搞定
          - 即使平台 UI 改版，只要消息气泡还在就不会失效

        参数：
          timeout: 最长等待秒数，超时后返回已抓取的文本（不抛异常）
          stable:  文本连续不变多少秒后判定为"生成完毕"
        """
        stable = self.WAIT_STABLE if stable is None else stable
        min_wait = self.WAIT_MIN if min_wait is None else min_wait
        last = ""  # 上一次轮询时的文本内容
        stable_since = 0.0  # 文本已连续不变的时间
        continues = 0  # 已自动点「继续生成」的次数
        start = time.monotonic()  # 记录开始时间（单调时钟，不受系统时间调整影响）
        while time.monotonic() - start < timeout:  # 还没超时就继续轮询
            await self._check_interrupt()  # 子类可在此检测登录弹窗等异常，快速失败
            cur = (await self._extract_last_reply(exclude=exclude)).strip()  # 获取当前最新回复文本
            if cur and cur == last:
                stable_since += 0.5
                if (
                    stable_since >= stable
                    and time.monotonic() - start >= min_wait
                    and not await self._is_generating()
                ):
                    # 连续 stable 秒无变化且没有生成中指示 → 可能完成
                    # 若页面有「继续生成」按钮，点一下续写，避免模型截断
                    if continues < max_continue and await self._continue_generating():
                        continues += 1
                        stable_since = 0.0
                        continue
                    return
            else:
                stable_since = 0.0
                last = cur  # 更新"上次文本"，继续下一轮等待
            await self.page.wait_for_timeout(500)
        # 超时了也正常返回（不抛异常），此时 last 里保存着已抓取到的部分文本

    # 类属性：子类可覆盖，控制「最短等待」和「稳定期」，防止长回答被误判截断
    WAIT_STABLE: float = 4.0
    WAIT_MIN: float = 5.0

    async def _continue_generating(self) -> bool:
        """【可选钩子】回答结束后若有「继续生成」按钮，点击续写。返回是否点了。"""
        return await self._click_text_if_visible(["继续生成", "继续", "Continue generating", "Continue"])

    async def _is_generating(self) -> bool:
        """【可选钩子】页面是否仍在生成（停止按钮 / 加载指示）。默认认为已结束。"""
        return False

    async def _check_interrupt(self) -> None:
        """【可选钩子】等待回复期间的检查点。

        子类可重写：检测登录弹窗、验证码等会阻塞回复的异常状态，
        出现时抛异常快速失败，避免傻等到超时。
        """
        pass

    async def _extract_last_reply(self, exclude: str = "") -> str:
        """从页面上抓取最后一条助手消息的文本。

        优先走「全页文字普查」：收集页面所有可见文本，以用户消息为锚点，
        取锚点后最大的非推荐文本块；找不到锚点时取最后一个非推荐长文本。
        部分平台（豆包等）回复容器类名不固定，只有普查能稳定抓到。
        """
        if self._prefer_census():
            text = await self._js_last_text(exclude)
            if text:
                return text
            return await self._bubbles_last_text(exclude)
        text = await self._bubbles_last_text(exclude)
        if text:
            return text
        return await self._js_last_text(exclude)

    async def _bubbles_last_text(self, exclude: str = "") -> str:
        """从平台自定义的气泡选择器里倒序找第一个非空非推荐文本。"""
        bubbles = await self._bubbles()
        n = await bubbles.count()
        for i in range(n - 1, -1, -1):  # 从最后一个往前找非空文本
            try:
                text = (await bubbles.nth(i).inner_text()).strip()
            except Exception:
                continue
            if text and not self._looks_like_junk(text, exclude):
                return text
        return ""

    def _prefer_census(self) -> bool:
        """是否优先用全页文字普查抓回复（页面结构不稳定的平台开启）。"""
        return False

    def _looks_like_junk(self, text: str, exclude: str = "") -> bool:
        """判断文本是否像「推荐问题 / 下载广告」等非真实回复内容。"""
        if not text or text == exclude:
            return True
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        # 推荐问题块：多数行以问号结尾（如「XX怎么做？YY有哪些案例？」）
        if len(lines) >= 2:
            q = sum(1 for ln in lines if ln.endswith(("？", "?")))
            if q / len(lines) > 0.4:
                return True
        # 下载广告块：包含「下载 XX 电脑版 / 客户端」字样
        if "下载" in text and any(w in text for w in ("电脑版", "手机版", "客户端")):
            return True
        return False

    async def _message_container(self) -> str:
        """【可选钩子】消息区域的选择器，用于 JS 启发式抓取兜底。"""
        return "body"

    async def _js_last_text(self, exclude: str = "") -> str:
        """全页文字普查：收集页面所有可见文本，以用户消息为锚点，
        取锚点后最大的非推荐文本块（真实回答）。

        页面结构通常是：用户消息 → 真实回答 → 推荐问题 / 下载广告。
        不依赖具体类名，适合豆包这类回复容器类名不固定的网站。
        """
        return await self.page.evaluate(
            r"""([exclude]) => {
                const isJunk = (t) => {
                    const lines = t.split('\n').map((s) => s.trim()).filter(Boolean);
                    // 思考过程块（元宝等以「已深度思考(用时…」开头）
                    if (t.indexOf('已深度思考') === 0) return true;
                    // 功能按钮块（豆包输入区：「快速/图像生成/…/更多」全是短短语）
                    const shortLines = t.split('\n').map((s) => s.trim()).filter(Boolean);
                    if (shortLines.length >= 4 && shortLines.every((s) => s.length <= 6)) return true;
                    if (lines.length >= 2) {
                        const q = lines.filter((s) => /[?？]\s*$/.test(s)).length;
                        if (q / lines.length > 0.4) return true;
                    }
                    // 单行问句（推荐问题 chip，如「XX怎么做？」；整块就一行且很短）
                    if (lines.length === 1 && t.length <= 60 && /[?？]\s*$/.test(t)) return true;
                    // 下载广告
                    if (/下载/.test(t) && /电脑版|手机版|客户端/.test(t)) return true;
                    return false;
                };
                const inJunk = (el) => el.closest &&
                    el.closest("[class*='suggest'], [class*='recommend'], " +
                               "[class*='input-engine'], [class*='input-guidance'], " +
                               "[class*='input-content'], [class*='chat__input'], " +
                               "[class*='input-box'], [class*='think']");
                const items = [];
                const walk = (el) => {
                    // 推荐/建议容器整块排除（豆包 suggest-message-list-wrapper 等）
                    if (inJunk(el)) return;
                    if (el.children.length <= 3000) {
                        const tc = (el.textContent || '').trim();
                        if (tc.length >= 5) {
                            const r = el.getBoundingClientRect();
                            if (r.width > 0 && r.height > 0) {
                                const t = (el.innerText || '').trim();
                                if (t) items.push({ el, t, exact: t === exclude });
                            }
                        }
                    }
                    for (const c of el.children) walk(c);
                };
                walk(document.body);

                // 找最后一个与用户消息完全相同的元素（用户气泡）
                let idx = -1;
                for (let i = items.length - 1; i >= 0; i--) {
                    if (items[i].exact) { idx = i; break; }
                }
                if (idx >= 0) {
                    // 锚点后的所有文本，取最大的非推荐块 = 完整回答
                    const after = items.slice(idx + 1).filter((it) => it.t.length >= 20);
                    after.sort((a, b) => b.t.length - a.t.length);
                    for (const it of after) {
                        // 跳过内部包含推荐区的父容器（如「回答 + 后续建议」的包裹层）
                        if (it.el.querySelector &&
                            it.el.querySelector("[class*='suggest'], [class*='recommend']")) continue;
                        if (!isJunk(it.t) && it.el.tagName !== 'A') return it.t;
                    }
                    // 回答很短（如「好的」）时：取锚点后第一个非空非推荐文本
                    for (let i = idx + 1; i < items.length; i++) {
                        const t = items[i].t;
                        if (t && !isJunk(t) &&
                            !(items[i].el.querySelector &&
                              items[i].el.querySelector("[class*='suggest'], [class*='recommend']"))) {
                            return t;
                        }
                    }
                }

                // 兜底：找不到锚点时，取最后一个非推荐/广告的长文本
                let best = '';
                for (const it of items) {
                    const t = it.t;
                    if (t.length < 40 || isJunk(t)) continue;
                    if (it.el.querySelector &&
                        it.el.querySelector("[class*='suggest'], [class*='recommend']")) continue;
                    if (it.el.tagName === 'A' || (it.el.closest && it.el.closest('a'))) continue;
                    best = t;
                }
                return best;
            }""",
            [exclude],
        )
