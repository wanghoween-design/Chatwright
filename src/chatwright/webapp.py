"""Chatwright Web UI —— 一条消息，同时分发到多个网页 AI，结果并排展示。

启动方式（在 Chatwright 项目根目录）：
    .venv\\Scripts\\python run_web.py
    然后浏览器打开 http://127.0.0.1:8765

功能：
  - 多平台聊天：POST /api/chat 创建任务，后台并发跑各平台浏览器自动化
  - 对话管理：默认在同一对话里继续（保留上下文），支持新建对话、切换回旧对话
  - 登录管理：去登录 / 重新登录（全新会话）/ 注销，持久化浏览器配置目录
"""

from __future__ import annotations

import asyncio
import json
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from chatwright.browser import BrowserManager, STATE_DIR
from chatwright.providers.deepseek import DeepSeekProvider, DEFAULT_URL as DEEPSEEK_URL
from chatwright.providers.qwen import QwenProvider, DEFAULT_URL as QWEN_URL
from chatwright.providers.doubao import DoubaoProvider, DEFAULT_URL as DOUBAO_URL
from chatwright.providers.yuanbao import YuanbaoProvider, DEFAULT_URL as YUANBAO_URL
from chatwright.providers.zhipu import ZhipuProvider, DEFAULT_URL as ZHIPU_URL

# ---------------------------------------------------------------------------
# 平台注册表
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent.parent
WEB_DIR = Path(__file__).resolve().parent / "web"
STATIC_DIR = WEB_DIR / "static"

# 每个平台：标签、描述、登录态文件名（None = 无需登录）、Provider 类、
# 特殊 base_url（None = 用 Provider 自己的默认 URL）、登录跳转 URL
PLATFORMS: dict[str, dict[str, Any]] = {
    "deepseek": {
        "label": "DeepSeek",
        "desc": "深度求索 · chat.deepseek.com",
        "state_file": "deepseek_storage.json",
        "cls": DeepSeekProvider,
        "url": None,
        "login_url": DEEPSEEK_URL,
    },
    "qwen": {
        "label": "通义千问",
        "desc": "阿里 · www.qianwen.com（游客可用）",
        "state_file": "qwen_storage.json",
        "guest_ok": True,
        "cls": QwenProvider,
        "url": None,
        "login_url": QWEN_URL,
    },
    "doubao": {
        "label": "豆包",
        "desc": "字节 · www.doubao.com",
        "state_file": "doubao_storage.json",
        "live": True,
        "headless_ok": False,  # 豆包登录态绑定浏览器实例，固定用常驻窗口
        "cls": DoubaoProvider,
        "url": None,
        "login_url": DOUBAO_URL,
    },
    "yuanbao": {
        "label": "元宝",
        "desc": "腾讯 · yuanbao.tencent.com",
        "state_file": "yuanbao_storage.json",
        "live": True,
        "cls": YuanbaoProvider,
        "url": None,
        "login_url": YUANBAO_URL,
    },
    "zhipu": {
        "label": "智谱",
        "desc": "智谱 · chatglm.cn（游客可用）",
        "state_file": "zhipu_storage.json",
        "guest_ok": True,
        "live": True,          # 智谱有滑块验证，需常驻窗口人工过验证
        "headless_ok": False,  # 无头模式下智谱也保持可见窗口（验证墙需要人工）
        "chrome_first": True,  # 风控墙对自带 Chromium 识别严格，优先真实 Chrome
        "no_url_restore": True,  # 恢复旧对话 URL 会触发风控墙，一律从首页进入
        "cls": ZhipuProvider,
        "url": None,
        "login_url": ZHIPU_URL,
    },
}

app = FastAPI(title="Chatwright Web UI")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

APP_VERSION = "1.5.5"

CONFIG_FILE = STATE_DIR / "config.json"


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    platforms: list[str]
    conv_id: str = ""  # 前端会话 id，用于区分对话（后端只透传）
    options: dict[str, Any] = {}  # {thinking: bool, model: str, file: str}


class LoginFinish(BaseModel):
    save: bool = True


class SwitchRequest(BaseModel):
    urls: dict[str, str] = {}  # {platform: 该对话在此平台的页面 URL}


class NewConversationRequest(BaseModel):
    platforms: list[str] = []


class ConfigRequest(BaseModel):
    headless: bool = False


@dataclass
class PlatformSession:
    """一个平台常驻的浏览器会话：页面保持打开，对话上下文自然延续。"""

    platform: str
    bm: BrowserManager
    provider: Any


@dataclass
class ChatJob:
    id: str
    message: str
    platforms: list[str]
    conv_id: str = ""
    options: dict[str, Any] = field(default_factory=dict)
    created: float = field(default_factory=time.monotonic)
    status: str = "running"  # running | done
    results: dict[str, dict[str, Any]] = field(default_factory=dict)
    task: Optional[asyncio.Task] = None
    tasks: dict[str, asyncio.Task] = field(default_factory=dict)  # 各平台子任务（可单独停止）


JOBS: dict[str, ChatJob] = {}
SESSIONS: dict[str, PlatformSession] = {}
LOGIN_SESSIONS: dict[str, BrowserManager] = {}
PLATFORM_LOCKS: dict[str, asyncio.Lock] = {}


# ---------------------------------------------------------------------------
# 页面与平台列表
# ---------------------------------------------------------------------------

@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/version")
async def version() -> dict[str, str]:
    return {"name": "Chatwright", "version": APP_VERSION}


@app.get("/api/config")
async def get_config() -> dict[str, Any]:
    return {"headless": _headless_mode()}


@app.post("/api/config")
async def set_config(req: ConfigRequest) -> dict[str, Any]:
    """切换无头模式：live 平台也改用无头窗口（不弹网页）。"""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps({"headless": req.headless}), encoding="utf-8")
    # 切换后重建常驻会话，让新模式在下次聊天时生效
    for platform in list(SESSIONS):
        if PLATFORMS.get(platform, {}).get("live"):
            async with _platform_lock(platform):
                await _stop_session(platform)
    return {"ok": True, "headless": req.headless}


@app.get("/api/platforms")
async def platforms() -> list[dict[str, Any]]:
    out = []
    for key, cfg in PLATFORMS.items():
        state_file = cfg["state_file"]
        # 持久化模式：profile 目录存在即视为已登录
        logged_in = False
        if state_file is not None:
            # 登录成功标记（新流程验证通过后写入）或旧登录 JSON（会迁移进 profile）
            logged_in = _login_marker(key).exists() or (STATE_DIR / state_file).exists()
        out.append(
            {
                "id": key,
                "label": cfg["label"],
                "desc": cfg["desc"],
                "needs_login": state_file is not None,
                "logged_in": logged_in,
                "guest_ok": bool(cfg.get("guest_ok")),
                "models": cfg.get("models") or [],
            }
        )
    return out


# ---------------------------------------------------------------------------
# 会话管理
# ---------------------------------------------------------------------------

async def _get_session(platform: str) -> PlatformSession:
    """取平台的常驻浏览器会话；没有则创建（首次使用时）。"""
    sess = SESSIONS.get(platform)
    if sess is not None and not _session_dead(sess):
        return sess
    if sess is not None:
        await _stop_session(platform)  # 清理已关闭/崩溃的会话，重新创建
    cfg = PLATFORMS[platform]
    persistent = cfg["state_file"] is not None
    if persistent:
        # live 平台用可见常驻窗口（Kimi 等），其余平台用无头窗口
        bm = BrowserManager(
            headless=(not cfg.get("live")) or (_headless_mode() and cfg.get("headless_ok", True)),
            state_filename=cfg["state_file"],
            persistent=True,
        )
    else:
        bm = BrowserManager(headless=True)
    if cfg.get("chrome_first"):
        # 风控严格的平台优先用真实 Chrome（启动失败回退自带 Chromium）
        bm.channel = "chrome"
        try:
            page = await bm.start()
        except Exception:
            bm.channel = None
            page = await bm.start()
    else:
        page = await bm.start()
    provider = cfg["cls"](page, base_url=cfg["url"]) if cfg["url"] else cfg["cls"](page)
    sess = PlatformSession(platform=platform, bm=bm, provider=provider)
    SESSIONS[platform] = sess
    # 会话重建（浏览器被关闭等）后，跳回上次对话的 URL，保持同一对话上下文
    if cfg.get("state_file") and not cfg.get("no_url_restore"):
        last = _last_url_file(platform)
        if last.exists():
            url = last.read_text(encoding="utf-8").strip()
            if url:
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    provider._opened = True  # 不再跳回首页，直接用该对话
                except Exception:
                    pass
    if cfg.get("live"):
        # 常驻窗口创建后立即最小化到任务栏，避免打扰用户；登录时再恢复显示
        await _minimize_window(bm)
    return sess


async def _stop_session(platform: str) -> None:
    """停止并移除某平台的常驻会话（新建对话 / 登录 / 注销时用）。"""
    sess = SESSIONS.pop(platform, None)
    if sess is not None:
        try:
            await sess.bm.stop()
        except Exception:
            pass


def _platform_lock(platform: str) -> asyncio.Lock:
    return PLATFORM_LOCKS.setdefault(platform, asyncio.Lock())


def _login_marker(platform: str) -> Path:
    """登录成功标记文件：只有通过登录流程验证后才会写入。"""
    return STATE_DIR / f"{platform}.login"


def _headless_mode() -> bool:
    """是否启用无头模式（Kimi/豆包/元宝也用无头窗口，不弹网页）。"""
    try:
        return bool(json.loads(CONFIG_FILE.read_text(encoding="utf-8")).get("headless"))
    except Exception:
        return False


def _last_url_file(platform: str) -> Path:
    """最近一次成功对话的页面 URL（用于会话重建后回到原对话）。"""
    return STATE_DIR / f"{platform}.last_url"


def _session_dead(sess: PlatformSession) -> bool:
    """会话对应的浏览器/页面是否已被关闭（用户手动关窗、崩溃等）。"""
    try:
        if sess.bm.page is None:
            return True
        return sess.bm.page.is_closed()
    except Exception:
        return True


def _login_session_alive(bm: BrowserManager) -> bool:
    """登录窗口是否还活着（页面对象存在且浏览器未关闭）。"""
    try:
        return bm.page is not None and not bm.page.is_closed()
    except Exception:
        return False


async def _minimize_window(bm: BrowserManager) -> None:
    """把常驻窗口最小化到任务栏（保活会话但不打扰用户）。"""
    try:
        cdp = await bm.context.new_cdp_session(bm.page)
        window_id = (await cdp.send("Browser.getWindowForTarget"))["windowId"]
        await cdp.send(
            "Browser.setWindowBounds",
            {"windowId": window_id, "bounds": {"windowState": "minimized"}},
        )
    except Exception:
        try:
            await bm.page.evaluate("window.moveTo(-32000, -32000);")
        except Exception:
            pass


async def _restore_window(bm: BrowserManager) -> None:
    """把常驻窗口恢复显示（登录 / 重新登录时用）。"""
    try:
        cdp = await bm.context.new_cdp_session(bm.page)
        window_id = (await cdp.send("Browser.getWindowForTarget"))["windowId"]
        await cdp.send(
            "Browser.setWindowBounds",
            {
                "windowId": window_id,
                "bounds": {
                    "windowState": "normal",
                    "left": 100,
                    "top": 80,
                    "width": 1100,
                    "height": 800,
                },
            },
        )
    except Exception:
        try:
            await bm.page.evaluate("window.moveTo(120, 80); window.resizeTo(1100, 800);")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 聊天任务
# ---------------------------------------------------------------------------

@app.post("/api/chat")
async def create_chat(req: ChatRequest) -> dict[str, Any]:
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="消息不能为空")
    picks = [p for p in req.platforms if p in PLATFORMS]
    if not picks:
        raise HTTPException(status_code=400, detail="请至少选择一个平台")

    job = ChatJob(
        id=uuid.uuid4().hex[:12],
        message=message,
        platforms=picks,
        conv_id=req.conv_id,
        options=req.options or {},
    )
    job.task = asyncio.create_task(_run_job(job))
    JOBS[job.id] = job
    _prune_old_jobs()
    return {"job_id": job.id}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> dict[str, Any]:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {
        "id": job.id,
        "message": job.message,
        "conv_id": job.conv_id,
        "status": job.status,
        "elapsed": round(time.monotonic() - job.created, 1),
        "results": job.results,
    }


async def _run_job(job: ChatJob) -> None:
    """并发把消息发给每个平台，逐个更新进度。"""

    async def one(platform: str) -> None:
        lock = _platform_lock(platform)
        async with lock:
            job.results[platform] = {"status": "running", "elapsed": 0.0}
            started = time.monotonic()
            try:
                job.results[platform] = await _chat_one(platform, job.message, job.options)
            except asyncio.CancelledError:
                # 用户点击「停止」：标记为已停止，不影响其他平台
                job.results[platform] = {
                    "status": "stopped",
                    "elapsed": round(time.monotonic() - started, 1),
                }
                return
            except Exception as e:  # 单平台意外崩溃不能让整个任务挂死
                job.results[platform] = {"status": "error", "error": f"{type(e).__name__}: {e}"}
            job.results[platform]["elapsed"] = round(time.monotonic() - started, 1)

    for platform in job.platforms:
        job.tasks[platform] = asyncio.create_task(one(platform))
    await asyncio.gather(*job.tasks.values(), return_exceptions=True)
    job.status = "done"


class StopRequest(BaseModel):
    platforms: list[str] = []


@app.post("/api/jobs/{job_id}/stop")
async def stop_job(job_id: str, req: StopRequest) -> dict[str, Any]:
    """停止任务中的指定平台（不填 platforms 则停止全部未完成的平台）。"""
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    targets = [p for p in (req.platforms or []) if p in job.tasks]
    if not targets:
        targets = list(job.tasks)
    stopped = []
    for platform in targets:
        task = job.tasks.get(platform)
        if task is not None and not task.done():
            task.cancel()
            stopped.append(platform)
    return {"ok": True, "stopped": stopped}


async def _chat_one(platform: str, message: str, options: dict[str, Any]) -> dict[str, Any]:
    """在平台的常驻会话里发消息（复用同一页面 → 保留对话上下文）。"""
    for attempt in (1, 2):
        sess = await _get_session(platform)
        try:
            if options:
                # 选项按平台拆分：每个平台单独控制思考模式 / 模型，文件全局共享
                thinking = options.get("thinking")
                model = options.get("model")
                plat_opts = {
                    "thinking": thinking.get(platform) if isinstance(thinking, dict) else bool(thinking),
                    "model": (model.get(platform) if isinstance(model, dict) else model) or "",
                    "file": options.get("file") or "",
                }
                if any(plat_opts.values()):
                    await sess.provider.apply_options(plat_opts)
            reply = await sess.provider.send(message, timeout=120)
            url = sess.bm.page.url if sess.bm.page else ""
            if url and PLATFORMS[platform].get("state_file"):
                # 记住当前对话 URL，会话重建后可跳回继续聊
                try:
                    _last_url_file(platform).write_text(url, encoding="utf-8")
                except Exception:
                    pass
            return {"status": "done", "reply": reply, "url": url}
        except Exception as e:
            if attempt == 1 and _session_dead(sess):
                # 浏览器被关闭/崩溃：重建会话后自动重试一次
                await _stop_session(platform)
                continue
            return {"status": "error", "error": f"{type(e).__name__}: {e}"}
    return {"status": "error", "error": "会话重建重试后仍然失败"}


def _prune_old_jobs(keep: int = 50) -> None:
    """简单清理：只保留最近的完成/失败任务，避免内存无限增长。"""
    if len(JOBS) <= keep * 2:
        return
    old = sorted(
        [j for j in JOBS.values() if j.status == "done"],
        key=lambda j: j.created,
    )
    for job in old[: len(JOBS) - keep]:
        JOBS.pop(job.id, None)


# ---------------------------------------------------------------------------
# 对话管理（新建 / 切换）
# ---------------------------------------------------------------------------

@app.post("/api/conversations/new")
async def new_conversation(req: NewConversationRequest) -> dict[str, Any]:
    """新建对话：让指定平台从新会话开始（旧对话仍可通过 URL 切回）。"""
    done = []
    for platform in req.platforms:
        if platform not in PLATFORMS:
            continue
        async with _platform_lock(platform):
            # 新建对话：清掉记住的旧对话 URL，确保从新会话开始
            try:
                last = _last_url_file(platform)
                if last.exists():
                    last.unlink()
            except Exception:
                pass
            if PLATFORMS[platform].get("live"):
                # 常驻窗口不能关（登录会失效），导航回首页即为新会话
                sess = SESSIONS.get(platform)
                if sess is not None:
                    target = PLATFORMS[platform].get("url") or PLATFORMS[platform]["login_url"]
                    try:
                        await sess.bm.page.goto(target, wait_until="domcontentloaded", timeout=30000)
                        sess.provider._opened = True
                    except Exception:
                        pass
            else:
                await _stop_session(platform)
            done.append(platform)
    return {"ok": True, "platforms": done}


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)) -> dict[str, Any]:
    """接收前端上传的文件，保存到本地临时目录，供各平台上传使用。"""
    upload_dir = STATE_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "file").name  # 去掉路径，只留文件名
    path = upload_dir / f"{uuid.uuid4().hex[:10]}_{safe_name}"
    with path.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"ok": True, "path": str(path), "name": safe_name}


@app.get("/api/debug/session/{platform}")
async def debug_session(platform: str) -> dict[str, Any]:
    """调试接口：返回某平台当前会话页面的关键 DOM（用于校准选择器）。"""
    sess = SESSIONS.get(platform)
    if sess is None or sess.bm.page is None:
        return {"session": False}
    page = sess.bm.page
    try:
        message_list = ""
        ml = page.locator(".message-list")
        if await ml.count():
            message_list = await ml.first.evaluate("el => el.outerHTML")
        body = await page.evaluate("() => (document.body.innerText||'').slice(-800)")
        # 文字清单：把页面上所有可见的文本元素列出来（用于分析哪些该留哪些该去）
        inventory = []
        try:
            inventory = await page.evaluate(
                """() => {
                    const out = [];
                    const els = document.querySelectorAll('div, p, li, span, h1, h2, h3, blockquote, article');
                    for (const el of els) {
                        const t = (el.innerText || '').trim();
                        if (t.length < 2 || el.children.length > 10) continue;
                        const r = el.getBoundingClientRect();
                        if (r.width === 0 || r.height === 0) continue;
                        out.push({tag: el.tagName, cls: (el.className||'').toString().slice(0,70),
                                  len: t.length, text: t.slice(0,70)});
                    }
                    return out.slice(-30);
                }"""
            )
        except Exception:
            pass
        candidates = {}
        for sel in [
            "[class*='markdown']",
            "[class*='message']",
            "[class*='answer']",
            "[class*='assistant']",
            "[class*='suggest']",
            "[class*='recommend']",
            "[class*='hot']",
            "[class*='chat']",
        ]:
            try:
                loc = page.locator(sel)
                n = await loc.count()
                hits = []
                for i in range(max(0, n - 8), n):  # 只看最后 8 个命中
                    try:
                        hits.append(
                            await loc.nth(i).evaluate(
                                "el => ({cls: (el.className||'').toString().slice(0,100), "
                                "text: (el.innerText||'').trim().slice(0,90), "
                                "len: (el.innerText||'').trim().length})"
                            )
                        )
                    except Exception:
                        continue
                if hits:
                    candidates[sel] = {"count": n, "last8": hits}
            except Exception:
                continue
        return {
            "session": True,
            "url": page.url,
            "message_list_html": message_list[:4000],
            "body_tail": body,
            "text_inventory": inventory,
            "candidates": candidates,
        }
    except Exception as e:
        return {"session": True, "error": f"{type(e).__name__}: {e}"}


@app.get("/api/debug/login/{platform}")
async def debug_login(platform: str) -> dict[str, Any]:
    """调试接口：返回登录窗口当前页面的 URL 与正文（用于排查登录失败）。"""
    bm = LOGIN_SESSIONS.get(platform)
    if bm is None or bm.page is None:
        return {"login_session": False}
    try:
        return {
            "login_session": True,
            "url": bm.page.url,
            "body": await bm.page.evaluate("() => (document.body.innerText||'').slice(-600)"),
        }
    except Exception as e:
        return {"login_session": True, "error": f"{type(e).__name__}: {e}"}


@app.post("/api/conversations/switch")
async def switch_conversation(req: SwitchRequest) -> dict[str, Any]:
    """切回旧对话：把各平台页面导航到该对话保存的 URL，上下文随之恢复。"""
    results: dict[str, str] = {}
    for platform, url in (req.urls or {}).items():
        if platform not in PLATFORMS or not url:
            continue
        async with _platform_lock(platform):
            try:
                sess = await _get_session(platform)
                await sess.bm.page.goto(url, wait_until="domcontentloaded", timeout=30000)
                sess.provider._opened = True  # 之后发送消息时不再跳回首页
                results[platform] = "ok"
            except Exception as e:
                results[platform] = f"error: {type(e).__name__}: {e}"
    return {"ok": True, "results": results}


# ---------------------------------------------------------------------------
# 登录流程（弹出可见浏览器，手动登录后保存）
# ---------------------------------------------------------------------------

@app.post("/api/login/{platform}")
async def start_login(platform: str) -> dict[str, Any]:
    cfg = PLATFORMS.get(platform)
    if cfg is None or cfg["state_file"] is None:
        raise HTTPException(status_code=400, detail="该平台无需登录")

    async with _platform_lock(platform):
        existing = LOGIN_SESSIONS.get(platform)
        if existing is not None and _login_session_alive(existing):
            return {"ok": True, "message": "登录窗口已经在打开状态"}
        if existing is not None:
            # 登录窗口已关闭（用户关闭/崩溃）：清理登记，重新打开新窗口
            LOGIN_SESSIONS.pop(platform, None)
            await _safe_stop(existing)
        # 登录都必须在可见窗口里完成：先关掉可能正在跑的会话，
        # 避免同一 profile 被两个浏览器占用
        await _stop_session(platform)
        bm = BrowserManager(headless=False, state_filename=cfg["state_file"], persistent=True)
        if platform == "zhipu":
            # 智谱滑块验证对自带 Chromium 指纹识别严格，优先用真实 Chrome
            bm.channel = "chrome"
            try:
                await bm.start()
            except Exception:
                bm.channel = None
                await bm.start()
        else:
            try:
                await bm.start()  # 其余平台先试自带 Chromium（实测豆包登录正常）
            except Exception:
                bm.channel = "chrome"  # 启动失败时回退到真实 Chrome
                await bm.start()
        await bm.page.goto(cfg["login_url"], wait_until="domcontentloaded")
        if platform == "kimi":
            # Kimi 全新窗口不会自动弹登录框，帮用户把登录界面打开
            await _open_kimi_login_modal(bm.page)
        if cfg.get("live"):
            # 重新登录 / 再次打开时把窗口移回屏幕内，方便操作
            await _restore_window(bm)
        LOGIN_SESSIONS[platform] = bm
    return {"ok": True, "message": "登录窗口已打开，请完成登录后点击确认"}


@app.post("/api/login/{platform}/finish")
async def finish_login(platform: str, body: LoginFinish) -> dict[str, Any]:
    bm = LOGIN_SESSIONS.get(platform)
    if bm is None:
        raise HTTPException(status_code=400, detail="没有进行中的登录流程")
    if body.save:
        # 保存前先确认登录真的完成了，避免把"没登录成功"的状态存下来
        await bm.page.wait_for_timeout(3000)  # 等页面稳定，避免过早误判
        ok, reason = await _login_looks_complete(platform, bm)
        if not ok:
            return {"ok": False, "message": reason, "login_pending": True}
        LOGIN_SESSIONS.pop(platform, None)
        _login_marker(platform).write_text("ok", encoding="utf-8")
        if PLATFORMS[platform].get("live"):
            if _headless_mode():
                # 无头模式：登录窗口关闭，登录态已保存在 profile，聊天用无头会话
                await _safe_stop(bm)
            else:
                # 常驻模式：登录窗口保留为聊天会话，最小化到任务栏保活
                cfg = PLATFORMS[platform]
                provider = (
                    cfg["cls"](bm.page, base_url=cfg["url"])
                    if cfg["url"]
                    else cfg["cls"](bm.page)
                )
                SESSIONS[platform] = PlatformSession(platform=platform, bm=bm, provider=provider)
                await _minimize_window(bm)
        else:
            await _safe_stop(bm)  # 普通模式：关闭即自动保存全部登录状态
        return {"ok": True, "message": f"{PLATFORMS[platform]['label']} 登录态已保存"}
    # 取消登录
    LOGIN_SESSIONS.pop(platform, None)
    await _safe_stop(bm)
    return {"ok": True, "message": "已取消登录"}


async def _open_kimi_login_modal(page) -> None:
    """Kimi 新窗口打开后不会自动显示登录框，主动点一下「Log In / 登录」。"""
    await page.wait_for_timeout(3000)
    modal = page.locator("[class*='login-modal']")
    if await modal.count() > 0 and await modal.first.is_visible():
        return  # 登录框已经在显示
    # 找一个可见的登录按钮（英文/中文界面都试）
    for text in ("Log In", "登录"):
        buttons = page.locator(f"button:has-text('{text}')")
        for i in range(await buttons.count()):
            try:
                if await buttons.nth(i).is_visible():
                    await buttons.nth(i).click(timeout=5000)
                    await page.wait_for_timeout(2000)
                    return
            except Exception:
                continue


async def _login_looks_complete(platform: str, bm: BrowserManager) -> tuple[bool, str]:
    """检查浏览器当前是否已经完成登录（登录框/登录页是否还在）。"""
    page = bm.page
    if platform == "kimi":
        modal = (
            page.locator("[class*='login-modal']")
            .or_(page.locator("text=手机号登录"))
            .or_(page.locator("text=扫码登录"))
        )
        if await modal.count() > 0 and await modal.first.is_visible():
            return False, "浏览器里的 Kimi 登录框还在显示，登录似乎还没完成。请完成登录后再点「已登录，保存」。"
        # 第二重校验：页面上不应再有可见的「Log In / 登录」按钮
        for text in ("Log In", "登录"):
            buttons = page.locator(f"button:has-text('{text}')")
            for i in range(await buttons.count()):
                try:
                    if await buttons.nth(i).is_visible():
                        return False, "Kimi 页面右上角仍显示「登录」按钮，说明登录还没生效。请完成登录后再点「已登录，保存」。"
                except Exception:
                    continue
    elif platform == "yuanbao":
        modal = page.locator("[class*='hyc-login']")
        if await modal.count() > 0 and await modal.first.is_visible():
            return False, "元宝的登录窗口还在显示，登录似乎还没完成。请用微信/手机/QQ 完成登录后再点「已登录，保存」。"
    elif platform == "doubao":
        if "login" in page.url or "region-ban" in page.url:
            return False, "浏览器还停留在豆包的登录/限制页，登录似乎还没完成。请完成登录后再点「已登录，保存」。"
        if await _visible_text_button_exists(page, ("登录", "Log In")):
            return False, "豆包页面右上角仍显示「登录」按钮，说明登录还没生效。请完成登录后再点「已登录，保存」。"
    elif platform == "deepseek":
        if "login" in page.url or "sign_in" in page.url:
            return False, "浏览器还停留在 DeepSeek 登录页，登录似乎还没完成。请完成登录后再点「已登录，保存」。"
    elif platform == "qwen":
        if "login" in page.url:
            return False, "浏览器还停留在通义千问登录页，登录似乎还没完成。请完成登录后再点「已登录，保存」。"
    return True, ""


async def _visible_text_button_exists(page, texts: tuple[str, ...]) -> bool:
    """页面上是否存在可见的指定文字按钮。"""
    for text in texts:
        buttons = page.locator(f"button:has-text('{text}')")
        n = await buttons.count()
        for i in range(n):
            try:
                if await buttons.nth(i).is_visible():
                    return True
            except Exception:
                continue
    return False


async def _safe_stop(bm: BrowserManager) -> None:
    try:
        await bm.stop()
    except Exception:
        pass  # 用户可能已经手动关掉了浏览器窗口


# ---------------------------------------------------------------------------
# 注销登录
# ---------------------------------------------------------------------------

@app.post("/api/logout/{platform}")
async def logout_platform(platform: str) -> dict[str, Any]:
    """注销登录：删除该平台保存在本地的持久化 profile。"""
    cfg = PLATFORMS.get(platform)
    if cfg is None or cfg["state_file"] is None:
        raise HTTPException(status_code=400, detail="该平台无需登录")

    async with _platform_lock(platform):
        # 关闭进行中的登录流程与常驻会话，避免文件被占用
        login_bm = LOGIN_SESSIONS.pop(platform, None)
        if login_bm is not None:
            await _safe_stop(login_bm)
        await _stop_session(platform)

        removed = False
        profile = STATE_DIR / (Path(cfg["state_file"]).stem + "_profile")
        if profile.exists():
            shutil.rmtree(profile, ignore_errors=True)
            removed = True
        state_file = STATE_DIR / cfg["state_file"]
        if state_file.exists():
            state_file.unlink()
            removed = True
        marker = _login_marker(platform)
        if marker.exists():
            marker.unlink()
            removed = True
        try:
            last = _last_url_file(platform)
            if last.exists():
                last.unlink()
        except Exception:
            pass

    if removed:
        return {"ok": True, "message": f"已注销 {cfg['label']} 的本地登录态"}
    return {"ok": True, "message": f"{cfg['label']} 没有可注销的本地登录态"}


if __name__ == "__main__":
    import uvicorn

    print("Chatwright Web UI → http://127.0.0.1:8765")
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")
