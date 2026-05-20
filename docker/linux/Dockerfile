FROM python:3.12-slim

ARG DEBIAN_FRONTEND=noninteractive
ARG UID=1000
ARG GID=1000

COPY docker/linux/apt-packages-base.txt /tmp/apt-packages-base.txt
COPY docker/linux/apt-packages-xcb.txt /tmp/apt-packages-xcb.txt

RUN apt-get update \
    && xargs -a /tmp/apt-packages-base.txt apt-get install -y --no-install-recommends \
    && xargs -a /tmp/apt-packages-xcb.txt apt-get install -y --no-install-recommends \
    && sed -i 's/^# *ko_KR.UTF-8 UTF-8/ko_KR.UTF-8 UTF-8/' /etc/locale.gen \
    && locale-gen \
    && update-locale LANG=ko_KR.UTF-8 \
    && rm -f /tmp/apt-packages-base.txt /tmp/apt-packages-xcb.txt \
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
