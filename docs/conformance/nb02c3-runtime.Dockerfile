# Offline execution image. The independently reviewed wheelhouse is build input.
FROM python@sha256:3121f8b0804aa3698ab750d9a39ea4a42657a385c9b133722b915e55c51551a6

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH=/opt/venv/bin:/usr/local/bin:/usr/bin:/bin

RUN python -m venv --without-pip /opt/venv
COPY requirements.txt /opt/runtime-requirements.txt
COPY runtime-prepare.py /opt/runtime-prepare.py
COPY wheelhouse.json /opt/runtime-wheelhouse.json
RUN --mount=type=bind,source=wheels,target=/wheels,ro \
    /usr/local/bin/python -m pip --python /opt/venv/bin/python install \
      --no-index --find-links=/wheels --require-hashes --no-deps --no-cache-dir --no-compile \
      -r /opt/runtime-requirements.txt \
    && /usr/local/bin/python -m pip --python /opt/venv/bin/python check \
    && /opt/venv/bin/python /opt/runtime-prepare.py audit > /opt/runtime-manifest.json

USER 65532:65532
CMD ["/opt/venv/bin/python"]
