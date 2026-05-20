FROM python:3.12-slim

ARG DEBIAN_FRONTEND=noninteractive
ARG UID=1000
ARG GID=1000

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        gstreamer1.0-plugins-bad \
        gstreamer1.0-plugins-base \
        gstreamer1.0-plugins-good \
        gstreamer1.0-plugins-ugly \
        gstreamer1.0-tools \
        libgl1 \
        libglib2.0-0 \
        libportaudio2 \
        portaudio19-dev \
        pulseaudio-utils \
        python3-tk \
        tk \
        v4l-utils \
        xauth \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid "${GID}" avc \
    && useradd --uid "${UID}" --gid "${GID}" --create-home --shell /bin/bash avc

WORKDIR /workspace

COPY requirements.lock requirements.txt ./
RUN python3 -m pip install --upgrade pip setuptools wheel \
    && python3 -m pip install -r requirements.lock \
    && python3 -m pip install --no-deps deepfilternet || true

COPY . /workspace
COPY docker/linux/entrypoint.sh /usr/local/bin/avc-docker-entrypoint
RUN chmod +x /usr/local/bin/avc-docker-entrypoint

ENV HOME=/home/avc
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/workspace

ENTRYPOINT ["avc-docker-entrypoint"]
CMD ["./bin/avc", "--help"]
