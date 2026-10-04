# Build context is this directory: docker build panel/
FROM python:3.12-slim

ARG APP_UID=568
ARG APP_GID=568

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt /tmp/requirements.txt
RUN pip install --require-hashes -r /tmp/requirements.txt
RUN groupadd --gid "${APP_GID}" panel \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --no-create-home --shell /usr/sbin/nologin panel

COPY mordhau_panel /app/mordhau_panel
ENV PYTHONPATH=/app

USER panel
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import socket; socket.create_connection(('127.0.0.1', 8080), 2)"
CMD ["python", "-m", "mordhau_panel"]
