# Separate candidate-runtime prerequisite; no SDK/evaluator/agent is installed.
FROM python@sha256:3121f8b0804aa3698ab750d9a39ea4a42657a385c9b133722b915e55c51551a6

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:/usr/local/bin:/usr/bin:/bin

RUN python -m venv --without-pip /opt/venv \
    && /usr/local/bin/python -I -B -c 'from pathlib import Path; import shutil,sys; base=Path("/usr/local"); site=base/"lib/python3.13/site-packages"; site.is_dir() and not site.is_symlink() or sys.exit("site_packages"); [(shutil.rmtree(p) if p.is_dir() and not p.is_symlink() else p.unlink()) for p in site.iterdir()]; [(p.unlink()) for p in (base/"bin").glob("pip*")]; shutil.rmtree(base/"lib/python3.13/ensurepip/_bundled"); [shutil.rmtree(p) for p in (base/"lib/python3.13").rglob("__pycache__")]'
COPY runtime-audit.py /opt/runtime-audit.py
RUN /opt/venv/bin/python -I -B -X pycache_prefix=/__absent_bytecode_cache \
    /opt/runtime-audit.py > /opt/runtime-manifest.json

USER 65532:65532
CMD ["/opt/venv/bin/python"]
