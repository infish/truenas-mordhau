FROM ubuntu:22.04

ARG APP_UID=568
ARG APP_GID=568

ENV DEBIAN_FRONTEND=noninteractive
ENV STEAMCMDDIR=/opt/steamcmd
ENV HOME=/home/steam
ENV DATA_DIR=/data

RUN dpkg --add-architecture i386 \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        file \
        lib32gcc-s1 \
        lib32stdc++6 \
        libc6-i386 \
        libcurl4 \
        libcurl4:i386 \
        libcurl3-gnutls \
        libcurl3-gnutls:i386 \
        libgcc-s1 \
        libgcc-s1:i386 \
        libstdc++6 \
        libstdc++6:i386 \
        libtinfo6 \
        libtinfo6:i386 \
        locales \
        tini \
        tzdata \
        zlib1g \
        zlib1g:i386 \
    && locale-gen en_US.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8

RUN groupadd --gid "${APP_GID}" steam \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --create-home --shell /bin/bash steam \
    && mkdir -p "${STEAMCMDDIR}" "${DATA_DIR}" \
    && curl -fsSL "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz" \
        | tar -xz -C "${STEAMCMDDIR}" \
    && chown -R steam:steam "${STEAMCMDDIR}" "${DATA_DIR}" "${HOME}"

COPY --chown=steam:steam entrypoint.sh /usr/local/bin/entrypoint.sh

RUN chmod 0755 /usr/local/bin/entrypoint.sh

USER steam
WORKDIR /data

EXPOSE 37000/tcp 37000/udp 37001/tcp 37001/udp 37002/tcp 37002/udp 37003/tcp 37003/udp

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
