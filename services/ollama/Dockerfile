# Derived Ollama image that runs as an unprivileged user (uid/gid 10001).
# The upstream image runs as root; Ollama only needs a writable HOME (key file)
# and a writable models directory, both provided by the named volume below.
ARG OLLAMA_IMAGE=ollama/ollama:0.40.17
FROM ${OLLAMA_IMAGE}

RUN groupadd --gid 10001 ollama \
 && useradd --uid 10001 --gid 10001 --home-dir /home/ollama --create-home --shell /usr/sbin/nologin ollama \
 && mkdir -p /home/ollama/.ollama/models \
 && chown -R 10001:10001 /home/ollama

COPY --chmod=0755 model-init.sh /usr/local/bin/vie-model-init
COPY --chmod=0755 healthcheck.sh /usr/local/bin/vie-healthcheck

ENV HOME=/home/ollama \
    OLLAMA_MODELS=/home/ollama/.ollama/models \
    OLLAMA_HOST=0.0.0.0:11434 \
    OLLAMA_NO_CLOUD=1 \
    DO_NOT_TRACK=1

USER 10001:10001
WORKDIR /home/ollama
VOLUME ["/home/ollama/.ollama"]
EXPOSE 11434
ENTRYPOINT ["/bin/ollama"]
CMD ["serve"]
