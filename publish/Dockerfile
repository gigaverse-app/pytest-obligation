# Official Python image. Update the digest and requirements together in a reviewed PR.
FROM python:3.15-slim-bookworm@sha256:575f8bc12ec26542e0678bc6b60e385218248019d433157ec327264a78c3a853
COPY publish/requirements.txt /opt/requirements.txt
RUN python -m pip install --no-cache-dir --require-hashes --only-binary=:all: -r /opt/requirements.txt
COPY package/src /opt/reporter
COPY publish/render.py /opt/render.py
ENV PYTHONDONTWRITEBYTECODE=1
USER 65534:65534
ENTRYPOINT ["python", "-I", "/opt/render.py"]
