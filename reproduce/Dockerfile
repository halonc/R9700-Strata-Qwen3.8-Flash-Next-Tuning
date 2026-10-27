FROM rocm/dev-ubuntu-24.04:10.1.0-full
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-aiohttp python3-jinja2 python3-yaml python3-regex python3-numpy \
      python3-pil curl \
    && rm -rf /var/lib/apt/lists/*
ENV LD_LIBRARY_PATH=/opt/rocm/lib:/opt/rocm/lib/llvm/lib
WORKDIR /opt/strata
COPY strata /opt/strata/strata
COPY strata-vision /opt/strata/strata-vision
COPY serve/ /opt/strata/serve/
COPY tools/ /opt/strata/tools/
COPY autosave.sh /opt/strata/autosave.sh
COPY entrypoint.sh /opt/strata/entrypoint.sh
RUN chmod +x /opt/strata/autosave.sh /opt/strata/entrypoint.sh
CMD ["/opt/strata/entrypoint.sh"]
