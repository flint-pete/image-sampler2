# Fully-qualified base image name so this builds under both Docker and podman
# (podman has no default unqualified-search registry).
FROM docker.io/waggle/plugin-base:1.1.1-base

RUN apt-get update \
  && apt-get install -y \
  wget \
  curl

# COPY the full plugin: app + all its modules (acquire/metadata/nodemeta/upload).
COPY app.py acquire.py metadata.py nodemeta.py upload.py requirements.txt /app/
RUN pip3 install --no-cache-dir -U -r /app/requirements.txt

ENTRYPOINT ["python3", "-u", "/app/app.py"]
