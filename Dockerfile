FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility,video

WORKDIR /workspace

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    curl \
    ffmpeg \
    gstreamer1.0-tools \
    gstreamer1.0-libav \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libnss3 \
    libsm6 \
    libusb-1.0-0 \
    libv4l-0 \
    libxext6 \
    libxrender1 \
    pciutils \
    python3 \
    python3-pip \
    python3-venv \
    tini \
    usbutils \
    v4l-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN python3 -m pip install --upgrade pip setuptools wheel
RUN python3 -m pip install -r /tmp/requirements.txt

COPY src /workspace/src
COPY config /workspace/config
COPY docs /workspace/docs

RUN mkdir -p /workspace/config /workspace/models /workspace/scripts /workspace/src

COPY scripts/container-entrypoint.sh /usr/local/bin/container-entrypoint.sh
RUN chmod +x /usr/local/bin/container-entrypoint.sh

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/container-entrypoint.sh"]
CMD ["python3", "-m", "src.app.main", "--config", "config/settings.example.json", "--max-frames", "1"]
