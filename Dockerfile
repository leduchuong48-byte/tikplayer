FROM python:3.12-slim

ARG JELLYFIN_FFMPEG_VERSION=7.1.3-6
ARG JELLYFIN_FFMPEG_URL=https://github.com/jellyfin/jellyfin-ffmpeg/releases/download/v7.1.3-6/jellyfin-ffmpeg_7.1.3-6_portable_linux64-gpl.tar.xz

LABEL org.opencontainers.image.title="Tikplayer"
LABEL org.opencontainers.image.version="2.4"

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    vainfo \
    intel-media-va-driver \
    libvpl2 \
    libmfx-gen1.2 \
    xz-utils \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /usr/lib/jellyfin-ffmpeg && \
    curl -fsSL -o /tmp/jellyfin-ffmpeg.tar.xz "$JELLYFIN_FFMPEG_URL" && \
    tar -xJf /tmp/jellyfin-ffmpeg.tar.xz -C /usr/lib/jellyfin-ffmpeg && \
    ln -sf /usr/lib/jellyfin-ffmpeg/ffmpeg /usr/local/bin/ffmpeg && \
    ln -sf /usr/lib/jellyfin-ffmpeg/ffprobe /usr/local/bin/ffprobe && \
    chmod +x /usr/lib/jellyfin-ffmpeg/ffmpeg /usr/lib/jellyfin-ffmpeg/ffprobe && \
    rm -f /tmp/jellyfin-ffmpeg.tar.xz

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn -r requirements.txt

COPY . .

# 下载前端依赖到本地，消除CDN依赖
RUN mkdir -p /app/static && \
    curl -fsSL -o /app/static/hls.min.js "https://registry.npmmirror.com/hls.js/1.6.15/files/dist/hls.min.js" && \
    curl -fsSL -o /app/static/artplayer.js "https://registry.npmmirror.com/artplayer/5.3.0/files/dist/artplayer.js"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/docs || exit 1

ENTRYPOINT []
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
