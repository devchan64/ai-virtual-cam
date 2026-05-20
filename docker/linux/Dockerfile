FROM python:3.12-slim

ARG DEBIAN_FRONTEND=noninteractive
ARG UID=1000
ARG GID=1000

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        fonts-noto-cjk \
        gstreamer1.0-plugins-bad \
        gstreamer1.0-plugins-base \
        gstreamer1.0-plugins-good \
        gstreamer1.0-plugins-ugly \
        gstreamer1.0-tools \
        libgl1 \
        libglib2.0-0 \
        libportaudio2 \
        libx11-xcb1 \
        libxcb-cursor0 \
        libxcb-icccm4 \
        libxcb-image0 \
        libxcb-keysyms1 \
        libxcb-randr0 \
        libxcb-render-util0 \
        libxcb-render0 \
        libxcb-shape0 \
        libxcb-shm0 \
        libxcb-sync1 \
        libxcb-util1 \
        libxcb-xfixes0 \
        libxcb-xinerama0 \
        libxcb1 \
        libxkbcommon-x11-0 \
        locales \
        portaudio19-dev \
        pulseaudio-utils \
        python3-tk \
        tk \
        v4l-utils \
        xauth \
    && sed -i 's/^# *ko_KR.UTF-8 UTF-8/ko_KR.UTF-8 UTF-8/' /etc/locale.gen \
    && locale-gen \
    && update-locale LANG=ko_KR.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    if ! getent group "${GID}" >/dev/null; then \
      groupadd --gid "${GID}" avc; \
    fi; \
    if ! getent passwd "${UID}" >/dev/null; then \
      useradd --uid "${UID}" --gid "${GID}" --create-home --shell /bin/bash avc; \
    fi

WORKDIR /workspace

COPY requirements.lock requirements.txt ./
RUN python3 -m pip install --upgrade pip setuptools wheel \
    && python3 -m pip install -r requirements.lock \
    && python3 -m pip install --no-deps deepfilternet || true

COPY . /workspace
COPY docker/linux/entrypoint.sh /usr/local/bin/avc-docker-entrypoint
RUN chmod +x /usr/local/bin/avc-docker-entrypoint

ENV HOME=/home/avc
ENV LANG=ko_KR.UTF-8
ENV LC_ALL=ko_KR.UTF-8
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/workspace

ENTRYPOINT ["avc-docker-entrypoint"]
CMD ["./bin/avc", "--help"]
