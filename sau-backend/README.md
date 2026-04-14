# SAU Backend

`social-auto-upload` 的 FastAPI 包装层，负责将视频自动发布到抖音和小红书。

---

## 架构

```
llm-01 (sau-backend Docker)
  └─ POST /upload/douyin       ← n8n 调用，自动发布
  └─ POST /upload/xhs          ← n8n 调用，自动发布
  └─ POST /cookie/login/douyin ← 登录时手动调用一次
  └─ POST /cookie/login/xhs    ← 登录时手动调用一次
  └─ GET  /clients             ← 查看已注册的远程测屏客户端
```

---

## Cookie 登录步骤（首次使用时执行一次）

### 方式一：远程 Chrome（推荐）

llm-01 是无头服务器，登录需要真实浏览器。在你的 **Mac 或 Windows** 上：

**Mac:**
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --remote-debugging-address=0.0.0.0 \
  --no-first-run --no-default-browser-check
```

**Windows (PowerShell):**
```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 `
  --remote-debugging-address=0.0.0.0 `
  --no-first-run --no-default-browser-check
```

然后在 llm-01 上触发登录（替换成你 Mac/Windows 的实际 IP）：

```bash
# 抖音登录
curl -X POST "http://llm-01.localdomain:8080/cookie/login/douyin?cdp_url=http://192.168.1.100:9222"

# 小红书登录
curl -X POST "http://llm-01.localdomain:8080/cookie/login/xhs?cdp_url=http://192.168.1.100:9222"
```

Playwright 会远程控制你权机的 Chrome 弹出登录页面，扫码/手机登录后 cookie 自动保存到 llm-01。

### 方式二：本地 Chromium（需要显示器或 VNC）

不传 `cdp_url` 参数时会尝试在服务器本地启动 Chromium。

```bash
curl -X POST "http://llm-01.localdomain:8080/cookie/login/douyin"
```

---

## 多客户端管理

如果你有多台 Mac/Windows 设备，可以在 `.env` 里注册已知客户端地址：

```env
SAU_CDP_CLIENTS=http://192.168.1.100:9222,http://192.168.1.101:9222
```

然后查看哪台在线：

```bash
curl http://llm-01.localdomain:8080/clients
```

---

## 接口列表

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 |
| GET | `/clients` | 列出已注册远程浏览器 |
| POST | `/upload/douyin` | 发布抖音视频 |
| POST | `/upload/xhs` | 发布小红书视频 |
| POST | `/cookie/login/douyin?cdp_url=` | 触发抖音登录 |
| POST | `/cookie/login/xhs?cdp_url=` | 触发小红书登录 |
