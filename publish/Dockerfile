# Python 3.11.17, official image. Update the digest and requirements together in a reviewed PR.
FROM python:3.11-slim-bookworm@sha256:f06d01d4ba3f8ad5af45a3ec87df19c1d317d8e8961edc0fabda61811af6f7cf
COPY publish/requirements.txt /opt/requirements.txt
RUN python -m pip install --no-cache-dir --require-hashes --only-binary=:all: -r /opt/requirements.txt
COPY package/src /opt/reporter
COPY publish/render.py /opt/render.py
ENV PYTHONDONTWRITEBYTECODE=1
USER 65534:65534
ENTRYPOINT ["python", "-I", "/opt/render.py"]
