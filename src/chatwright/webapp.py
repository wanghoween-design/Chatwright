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
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from chatwright.browser import BrowserManager, STATE_DIR
from chatwright.providers.deepseek import DeepSeekProvider, DEFAULT_URL as DEEPSEEK_URL
from chatwright.providers.kimi import KimiProvider, DEFAULT_URL as KIMI_URL
from chatwright.providers.qwen import QwenProvider, DEFAULT_URL as QWEN_URL
from chatwright.providers.mock import MockProvider
from chatwright.providers.doubao import DoubaoProvider, DEFAULT_URL as DOUBAO_URL
from chatwright.providers.yuanbao import YuanbaoProvider, DEFAULT_URL as YUANBAO_URL
from chatwright.providers.zhipu import ZhipuProvider, DEFAULT_URL as ZHIPU_URL

# ---------------------------------------------------------------------------
# 平台注册表
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent.parent
MOCK_HTML = ROOT / "tests" / "mock_chat.html"
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
    "kimi": {
        "label": "Kimi",
        "desc": "月之暗面 · kimi.com",
        "state_file": "kimi_storage.json",
        "cls": KimiProvider,
        "url": None,
        "login_url": KIMI_URL,
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
    "mock": {
        "label": "本地演示",
        "desc": "Mock 页面 · 无需登录",
        "state_file": None,
        "cls": MockProvider,
        "url": "file://" + str(MOCK_HTML),
        "login_url": None,
    },
    "doubao": {
        "label": "豆包",
        "desc": "字节 · www.doubao.com",
        "state_file": "doubao_storage.json",
        "cls": DoubaoProvider,
        "url": None,
        "login_url": DOUBAO_URL,
    },
    "yuanbao": {
        "label": "元宝",
        "desc": "腾讯 · yuanbao.tencent.com",
        "state_file": "yuanbao_storage.json",
        "cls": YuanbaoProvider,
        "url": None,
        "login_url": YUANBAO_URL,
    },
    "zhipu": {
        "label": "智谱",
        "desc": "智谱 · chatglm.cn（游客可用）",
        "state_file": "zhipu_storage.json",
        "guest_ok": True,
        "cls": ZhipuProvider,
        "url": None,
        "login_url": ZHIPU_URL,
    },
}

app = FastAPI(title="Chatwright Web UI")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    platforms: list[str]
    conv_id: str = ""  # 前端会话 id，用于区分对话（后端只透传）


class LoginFinish(BaseModel):
    save: bool = True


class SwitchRequest(BaseModel):
    urls: dict[str, str] = {}  # {platform: 该对话在此平台的页面 URL}


class NewConversationRequest(BaseModel):
    platforms: list[str] = []


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
    created: float = field(default_factory=time.monotonic)
    status: str = "running"  # running | done
    results: dict[str, dict[str, Any]] = field(default_factory=dict)
    task: Optional[asyncio.Task] = None


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
            }
        )
    return out


# ---------------------------------------------------------------------------
# 会话管理
# ---------------------------------------------------------------------------

async def _get_session(platform: str) -> PlatformSession:
    """取平台的常驻浏览器会话；没有则创建（首次使用时）。"""
    sess = SESSIONS.get(platform)
    if sess is not None:
        return sess
    cfg = PLATFORMS[platform]
    persistent = cfg["state_file"] is not None
    bm = (
        BrowserManager(headless=True, state_filename=cfg["state_file"], persistent=persistent)
        if persistent
        else BrowserManager(headless=True)
    )
    page = await bm.start()
    provider = cfg["cls"](page, base_url=cfg["url"]) if cfg["url"] else cfg["cls"](page)
    sess = PlatformSession(platform=platform, bm=bm, provider=provider)
    SESSIONS[platform] = sess
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

    job = ChatJob(id=uuid.uuid4().hex[:12], message=message, platforms=picks, conv_id=req.conv_id)
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
                job.results[platform] = await _chat_one(platform, job.message)
            except Exception as e:  # 单平台意外崩溃不能让整个任务挂死
                job.results[platform] = {"status": "error", "error": f"{type(e).__name__}: {e}"}
            job.results[platform]["elapsed"] = round(time.monotonic() - started, 1)

    await asyncio.gather(*(one(p) for p in job.platforms))
    job.status = "done"


async def _chat_one(platform: str, message: str) -> dict[str, Any]:
    """在平台的常驻会话里发消息（复用同一页面 → 保留对话上下文）。"""
    sess = await _get_session(platform)
    try:
        reply = await sess.provider.send(message, timeout=120)
        url = sess.bm.page.url if sess.bm.page else ""
        return {"status": "done", "reply": reply, "url": url}
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}


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
            await _stop_session(platform)
            done.append(platform)
    return {"ok": True, "platforms": done}


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
        if platform in LOGIN_SESSIONS:
            return {"ok": True, "message": "登录窗口已经在打开状态"}
        # 先关掉可能正在跑的 headless 会话，避免同一 profile 被两个浏览器占用
        await _stop_session(platform)
        # 用持久化 profile 打开可见浏览器：登录成功后状态自动保存在本地目录
        bm = BrowserManager(headless=False, state_filename=cfg["state_file"], persistent=True)
        await bm.start()
        await bm.page.goto(cfg["login_url"], wait_until="domcontentloaded")
        if platform == "kimi":
            # Kimi 全新窗口不会自动弹登录框，帮用户把登录界面打开
            await _open_kimi_login_modal(bm.page)
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
        await _safe_stop(bm)  # 持久化 profile：关闭即自动保存全部登录状态
        _login_marker(platform).write_text("ok", encoding="utf-8")
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
    elif platform == "deepseek":
        if "login" in page.url or "sign_in" in page.url:
            return False, "浏览器还停留在 DeepSeek 登录页，登录似乎还没完成。请完成登录后再点「已登录，保存」。"
    elif platform == "qwen":
        if "login" in page.url:
            return False, "浏览器还停留在通义千问登录页，登录似乎还没完成。请完成登录后再点「已登录，保存」。"
    return True, ""


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

    if removed:
        return {"ok": True, "message": f"已注销 {cfg['label']} 的本地登录态"}
    return {"ok": True, "message": f"{cfg['label']} 没有可注销的本地登录态"}


if __name__ == "__main__":
    import uvicorn

    print("Chatwright Web UI → http://127.0.0.1:8765")
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")
