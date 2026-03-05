FROM lscr.io/linuxserver/ffmpeg:latest

LABEL org.opencontainers.image.title="Tikplayer"
LABEL org.opencontainers.image.version="2.3"

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --break-system-packages --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn -r requirements.txt

COPY . .

# 下载前端依赖到本地，消除CDN依赖
RUN mkdir -p /app/static && \
    curl -fsSL -o /app/static/hls.min.js "https://registry.npmmirror.com/hls.js/1.6.15/files/dist/hls.min.js" && \
    curl -fsSL -o /app/static/artplayer.js "https://registry.npmmirror.com/artplayer/5.3.0/files/dist/artplayer.js"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/docs || exit 1

ENTRYPOINT []
CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
