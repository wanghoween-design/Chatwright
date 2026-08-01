"""Chatwright Web UI —— 一条消息，同时分发到多个网页 AI，结果并排展示。

启动方式（在 Chatwright 项目根目录）：
    .venv\\Scripts\\python run_web.py
    然后浏览器打开 http://127.0.0.1:8765

功能：
  - 多平台聊天：POST /api/chat 创建一个任务，后台并发跑各平台浏览器自动化
  - 进度轮询：GET /api/jobs/{job_id} 返回每个平台的状态（等待中/对话中/完成/失败）
  - 登录管理：POST /api/login/{platform} 弹出可见浏览器供手动登录，
    POST /api/login/{platform}/finish 保存登录态，下次自动复用
"""

from __future__ import annotations

import asyncio
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

# ---------------------------------------------------------------------------
# 平台注册表
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent.parent
MOCK_HTML = ROOT / "tests" / "mock_chat.html"
WEB_DIR = Path(__file__).resolve().parent / "web"
STATIC_DIR = WEB_DIR / "static"

# 每个平台：标签、描述、登录态文件名（None = 无需登录）、Provider 类、
# 特珠 base_url（None = 用 Provider 自己的默认 URL）、登录跳转 URL
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
}

app = FastAPI(title="Chatwright Web UI")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    platforms: list[str]


class LoginFinish(BaseModel):
    save: bool = True


@dataclass
class ChatJob:
    id: str
    message: str
    platforms: list[str]
    created: float = field(default_factory=time.monotonic)
    status: str = "running"  # running | done
    results: dict[str, dict[str, Any]] = field(default_factory=dict)
    task: Optional[asyncio.Task] = None


JOBS: dict[str, ChatJob] = {}
LOGIN_SESSIONS: dict[str, BrowserManager] = {}
PLATFORM_LOCKS: dict[str, asyncio.Lock] = {}


# ---------------------------------------------------------------------------
# 页面
# ---------------------------------------------------------------------------

@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


# ---------------------------------------------------------------------------
# 平台列表（含登录状态）
# ---------------------------------------------------------------------------

@app.get("/api/platforms")
async def platforms() -> list[dict[str, Any]]:
    out = []
    for key, cfg in PLATFORMS.items():
        state_file = cfg["state_file"]
        out.append(
            {
                "id": key,
                "label": cfg["label"],
                "desc": cfg["desc"],
                "needs_login": state_file is not None,
                "logged_in": state_file is not None and (STATE_DIR / state_file).exists(),
            }
        )
    return out


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

    job = ChatJob(id=uuid.uuid4().hex[:12], message=message, platforms=picks)
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
        "status": job.status,
        "elapsed": round(time.monotonic() - job.created, 1),
        "results": job.results,
    }


async def _run_job(job: ChatJob) -> None:
    """并发把消息发给每个平台，逐个更新进度。"""

    async def one(platform: str) -> None:
        # 每个平台一把锁，避免多个任务同时操作同一份登录态
        lock = PLATFORM_LOCKS.setdefault(platform, asyncio.Lock())
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
    """在独立浏览器中跑一个平台，返回 {status: done|error, reply?, error?}。"""
    cfg = PLATFORMS[platform]
    bm = (
        BrowserManager(headless=True, state_filename=cfg["state_file"])
        if cfg["state_file"]
        else BrowserManager(headless=True)
    )
    try:
        page = await bm.start()
        provider = cfg["cls"](page, base_url=cfg["url"]) if cfg["url"] else cfg["cls"](page)
        reply = await provider.send(message, timeout=120)
        return {"status": "done", "reply": reply}
    except Exception as e:  # 单平台失败不影响其他平台
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}
    finally:
        await bm.stop()


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
# 登录流程（弹出可见浏览器，手动登录后保存登录态）
# ---------------------------------------------------------------------------

@app.post("/api/login/{platform}")
async def start_login(platform: str) -> dict[str, Any]:
    cfg = PLATFORMS.get(platform)
    if cfg is None or cfg["state_file"] is None:
        raise HTTPException(status_code=400, detail="该平台无需登录")
    if platform in LOGIN_SESSIONS:
        return {"ok": True, "message": "登录窗口已经在打开状态"}

    # 登录/重新登录统一用全新浏览器会话（不加载旧登录态），
    # 这样页面会稳定显示登录入口，登录成功后覆盖保存即可
    bm = BrowserManager(headless=False, state_filename=cfg["state_file"], load_storage=False)
    await bm.start()
    await bm.page.goto(cfg["login_url"], wait_until="domcontentloaded")
    LOGIN_SESSIONS[platform] = bm
    return {"ok": True, "message": "登录窗口已打开，请完成登录后点击确认"}


@app.post("/api/login/{platform}/finish")
async def finish_login(platform: str, body: LoginFinish) -> dict[str, Any]:
    bm = LOGIN_SESSIONS.get(platform)
    if bm is None:
        raise HTTPException(status_code=400, detail="没有进行中的登录流程")
    if body.save:
        # 保存前先确认登录真的完成了，避免把"没登录成功"的状态存下来
        ok, reason = await _login_looks_complete(platform, bm)
        if not ok:
            return {"ok": False, "message": reason, "login_pending": True}
        await bm.save_state()
        LOGIN_SESSIONS.pop(platform, None)
        await _safe_stop(bm)
        return {"ok": True, "message": f"登录态已保存（{bm.state_path.name}）"}
    # 取消登录
    LOGIN_SESSIONS.pop(platform, None)
    await _safe_stop(bm)
    return {"ok": True, "message": "已取消登录"}


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


@app.post("/api/logout/{platform}")
async def logout_platform(platform: str) -> dict[str, Any]:
    """注销登录：删除该平台保存在本地的登录态（cookie 等）。"""
    cfg = PLATFORMS.get(platform)
    if cfg is None or cfg["state_file"] is None:
        raise HTTPException(status_code=400, detail="该平台无需登录")

    # 若有正在进行的登录流程，一并关闭，避免残留浏览器窗口
    bm = LOGIN_SESSIONS.pop(platform, None)
    if bm is not None:
        try:
            await bm.stop()
        except Exception:
            pass

    state_file = STATE_DIR / cfg["state_file"]
    if state_file.exists():
        state_file.unlink()
        return {"ok": True, "message": f"已注销 {cfg['label']} 的本地登录态"}
    return {"ok": True, "message": f"{cfg['label']} 没有可注销的本地登录态"}


if __name__ == "__main__":
    import uvicorn

    print("Chatwright Web UI → http://127.0.0.1:8765")
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")
