"""
sau-backend: social-auto-upload 的 FastAPI HTTP 包装层
n8n Python Code 节点通过 HTTP 调用此服务完成抖音/小红书视频发布

登录方式：
  本地模式： Playwright 在服务器本地启动 Chromium（需要显示器或 VNC）
  远程模式： Playwright 远程控制 Mac/Windows 上的 Chrome（推荐）

  远程模式使用方法：
    1. 在 Mac/Windows 上启动 Chrome 开启远程调试：

       Mac:
         /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \\
           --remote-debugging-port=9222 --remote-debugging-address=0.0.0.0 \\
           --no-first-run --no-default-browser-check

       Windows (PowerShell):
         & "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" `
           --remote-debugging-port=9222 --remote-debugging-address=0.0.0.0 `
           --no-first-run --no-default-browser-check

    2. 调用登录接口时传入 cdp_url 参数：
         POST /cookie/login/douyin?cdp_url=http://192.168.1.100:9222
         POST /cookie/login/xhs?cdp_url=http://192.168.1.100:9222

    3. 登录成功后 cookie 保存到 llm-01 的 COOKIE_DIR，后续发布无需再登录
"""
import os
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

app = FastAPI(title="SAU Backend", version="1.1.0")

COOKIE_DIR = os.environ.get("SAU_COOKIE_DIR", "/data/cookies")
VIDEO_DIR  = os.environ.get("SAU_VIDEO_DIR",  "/data/videos")


class UploadRequest(BaseModel):
    video_path:   str
    title:        str
    caption:      str
    tags:         List[str] = []
    cookie_file:  Optional[str] = None
    publish_type: int = 0   # 0=立即发布


@app.get("/health")
async def health():
    return {"status": "ok", "cookie_dir": COOKIE_DIR, "video_dir": VIDEO_DIR}


@app.get("/clients")
async def list_clients():
    """
    列出当前已注册的远程浏览器客户端（通过检测 CDP 地址可用性判断）
    请先在 .env 里配置 SAU_CDP_CLIENTS=http://192.168.1.100:9222,http://192.168.1.101:9222
    """
    import httpx
    clients_env = os.environ.get("SAU_CDP_CLIENTS", "")
    clients = [c.strip() for c in clients_env.split(",") if c.strip()]
    result = []
    async with httpx.AsyncClient(timeout=3) as client:
        for url in clients:
            try:
                r = await client.get(f"{url}/json/version")
                info = r.json()
                result.append({"url": url, "status": "online", "browser": info.get("Browser", "")})
            except Exception:
                result.append({"url": url, "status": "offline"})
    return {"clients": result}


async def _get_playwright_browser(cdp_url: Optional[str]):
    """
    返回 Playwright browser 实例。
    cdp_url 指定时连接远程 Chrome，否则启动本地 Chromium。
    """
    from playwright.async_api import async_playwright
    pw = await async_playwright().start()
    if cdp_url:
        browser = await pw.chromium.connect_over_cdp(cdp_url)
    else:
        browser = await pw.chromium.launch(headless=False)
    return pw, browser


@app.post("/upload/douyin")
async def upload_douyin(req: UploadRequest):
    video_path  = req.video_path
    cookie_file = req.cookie_file or f"{COOKIE_DIR}/douyin_cookie.json"

    if not Path(video_path).exists():
        raise HTTPException(400, f"视频文件不存在: {video_path}")
    if not Path(cookie_file).exists():
        raise HTTPException(400, f"Cookie不存在: {cookie_file}，请先调用 /cookie/login/douyin")

    try:
        from uploader.douyin_uploader.main import douyin_setup, DouYinVideo
        account_file = Path(cookie_file)
        await douyin_setup(account_file, handle=False)
        uploader = DouYinVideo(
            title=req.title,
            file_path=video_path,
            tags=req.tags,
            publish_date=0,
            account_file=account_file
        )
        await uploader.main()
        return {"success": True, "platform": "douyin", "title": req.title}
    except Exception as e:
        return {"success": False, "platform": "douyin", "message": str(e)}


@app.post("/upload/xhs")
async def upload_xhs(req: UploadRequest):
    video_path  = req.video_path
    cookie_file = req.cookie_file or f"{COOKIE_DIR}/xhs_cookie.json"

    if not Path(video_path).exists():
        raise HTTPException(400, f"视频文件不存在: {video_path}")
    if not Path(cookie_file).exists():
        raise HTTPException(400, f"Cookie不存在: {cookie_file}，请先调用 /cookie/login/xhs")

    try:
        from uploader.xhs_uploader.main import xhs_setup, XiaoHongShuVideo
        account_file = Path(cookie_file)
        await xhs_setup(account_file, handle=False)
        uploader = XiaoHongShuVideo(
            title=req.title,
            file_path=video_path,
            tags=req.tags,
            publish_date=0,
            account_file=account_file
        )
        await uploader.main()
        return {"success": True, "platform": "xhs", "title": req.title}
    except Exception as e:
        return {"success": False, "platform": "xhs", "message": str(e)}


@app.post("/cookie/login/douyin")
async def login_douyin(
    cdp_url: Optional[str] = Query(
        default=None,
        description="远程 Chrome CDP 地址，例如 http://192.168.1.100:9222。不传则尝试本地启动 Chromium"
    )
):
    """
    触发抖音扫码登录。

    远程模式（推荐）：
      在 Mac/Windows 上启动 Chrome:
        Mac:     /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --remote-debugging-address=0.0.0.0
        Windows: chrome.exe --remote-debugging-port=9222 --remote-debugging-address=0.0.0.0
      然后调用: POST /cookie/login/douyin?cdp_url=http://<mac-ip>:9222
    """
    try:
        from uploader.douyin_uploader.main import douyin_setup
        cookie_file = Path(f"{COOKIE_DIR}/douyin_cookie.json")
        cookie_file.parent.mkdir(parents=True, exist_ok=True)

        if cdp_url:
            # 远程模式: 连接已开启的 Chrome
            from playwright.async_api import async_playwright
            async with async_playwright() as pw:
                browser = await pw.chromium.connect_over_cdp(cdp_url)
                # social-auto-upload 的 setup 接受 browser 对象时进行登录
                await douyin_setup(cookie_file, handle=True, browser=browser)
                await browser.close()
        else:
            # 本地模式: 在服务器上启动 Chromium（需要显示器）
            await douyin_setup(cookie_file, handle=True)

        return {"success": True, "cookie_file": str(cookie_file), "mode": "remote" if cdp_url else "local"}
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.post("/cookie/login/xhs")
async def login_xhs(
    cdp_url: Optional[str] = Query(
        default=None,
        description="远程 Chrome CDP 地址，例如 http://192.168.1.100:9222。不传则尝试本地启动 Chromium"
    )
):
    """
    触发小红书扫码登录。

    远程模式（推荐）：
      在 Mac/Windows 上启动 Chrome:
        Mac:     /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --remote-debugging-address=0.0.0.0
        Windows: chrome.exe --remote-debugging-port=9222 --remote-debugging-address=0.0.0.0
      然后调用: POST /cookie/login/xhs?cdp_url=http://<mac-ip>:9222
    """
    try:
        from uploader.xhs_uploader.main import xhs_setup
        cookie_file = Path(f"{COOKIE_DIR}/xhs_cookie.json")
        cookie_file.parent.mkdir(parents=True, exist_ok=True)

        if cdp_url:
            from playwright.async_api import async_playwright
            async with async_playwright() as pw:
                browser = await pw.chromium.connect_over_cdp(cdp_url)
                await xhs_setup(cookie_file, handle=True, browser=browser)
                await browser.close()
        else:
            await xhs_setup(cookie_file, handle=True)

        return {"success": True, "cookie_file": str(cookie_file), "mode": "remote" if cdp_url else "local"}
    except Exception as e:
        return {"success": False, "message": str(e)}
