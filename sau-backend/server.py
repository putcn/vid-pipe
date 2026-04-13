"""
sau-backend: social-auto-upload 的 FastAPI HTTP 包装层
n8n Python Code 节点通过 HTTP 调用此服务完成抖音/小红书视频发布
"""
import os
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="SAU Backend", version="1.0.0")

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
async def login_douyin():
    """触发抖音扫码登录（需要在有显示器/VNC的环境执行）"""
    try:
        from uploader.douyin_uploader.main import douyin_setup
        cookie_file = Path(f"{COOKIE_DIR}/douyin_cookie.json")
        cookie_file.parent.mkdir(parents=True, exist_ok=True)
        await douyin_setup(cookie_file, handle=True)
        return {"success": True, "cookie_file": str(cookie_file)}
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.post("/cookie/login/xhs")
async def login_xhs():
    """触发小红书扫码登录"""
    try:
        from uploader.xhs_uploader.main import xhs_setup
        cookie_file = Path(f"{COOKIE_DIR}/xhs_cookie.json")
        cookie_file.parent.mkdir(parents=True, exist_ok=True)
        await xhs_setup(cookie_file, handle=True)
        return {"success": True, "cookie_file": str(cookie_file)}
    except Exception as e:
        return {"success": False, "message": str(e)}
