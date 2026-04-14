FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git wget curl ca-certificates \
    libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 libgbm1 \
    libasound2 libxshmfence1 libxrandr2 libxfixes3 libxdamage1 \
    libx11-xcb1 libxcb-dri3-0 fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    fastapi "uvicorn[standard]" playwright httpx requests

RUN pip install --no-cache-dir \
    git+https://github.com/dreammis/social-auto-upload.git

RUN playwright install chromium --with-deps

COPY server.py /app/server.py

EXPOSE 8080
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
