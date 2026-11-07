# Official Python image. Update the digest and requirements together in a reviewed PR.
FROM python:3.15-slim-bookworm@sha256:4e03260adeeebafccd084f3584e6b84823aba5651cfb53ef8a078ed441ddf9cd
COPY publish/requirements.txt /opt/requirements.txt
RUN python -m pip install --no-cache-dir --require-hashes --only-binary=:all: -r /opt/requirements.txt
COPY package/src /opt/reporter
COPY publish/render.py /opt/render.py
ENV PYTHONDONTWRITEBYTECODE=1
USER 65534:65534
ENTRYPOINT ["python", "-I", "/opt/render.py"]
