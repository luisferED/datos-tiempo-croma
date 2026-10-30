FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 QT_QPA_PLATFORM=xcb WEB_ONLY=1 DATA_DIR=/data UPLOAD_DIR=/data/uploads_web HTTP_BIND=0.0.0.0 HTTP_PORT=6670
RUN apt-get update && apt-get install -y --no-install-recommends xvfb xauth libegl1 libgl1 libglib2.0-0 libdbus-1-3 libfontconfig1 libx11-xcb1 libxcb1 libxcb-sync1 libxcb-shm0 libxcb-render0 libxrender1 libxi6 libsm6 libice6 libxext6 libfreetype6 libopengl0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xfixes0 libxcb-xinerama0 libxcb-xkb1 libxkbcommon-x11-0 fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && python -c "from PIL import features; assert features.check_feature('libjpeg_turbo')" && useradd --uid 10001 --create-home renderer && mkdir /data && chown renderer:renderer /data
COPY app.py runtime_support.py pipeline_profile.py jpeg_pipeline.py ./
COPY assets ./assets
COPY tools/container-entrypoint.sh /usr/local/bin/container-entrypoint
RUN chmod 755 /usr/local/bin/container-entrypoint
USER renderer
EXPOSE 6670
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:6670/healthz',timeout=3)"
ENTRYPOINT ["/usr/local/bin/container-entrypoint"]


# Optional synthetic performance profile; never mounts production data.
FROM runtime AS benchmark
USER root
RUN pip install --no-cache-dir psutil==7.2.2 && mkdir /reports && chown renderer:renderer /reports
COPY tools/benchmark.py tools/test_broadcast_sequence.py tools/mjpeg_receiver.py /app/tools/
USER renderer
HEALTHCHECK NONE
CMD ["python", "/app/tools/benchmark.py", "--seconds", "900", "--output", "/reports/performance.json"]

# Default production image excludes benchmark tools and psutil.
FROM runtime AS production
