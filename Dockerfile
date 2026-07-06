# Fully-qualified base image name so this builds under both Docker and podman
# (podman has no default unqualified-search registry).
FROM docker.io/waggle/plugin-base:1.1.1-base

# NOTE: no apt-get layer. image-sampler2 fetches frames via Python stdlib urllib
# (see acquire.py) and shells out to nothing, so wget/curl are not needed. The
# old upstream `apt-get install wget curl` step also tripped a buildkit sandbox
# bug on the ECR Jenkins builder (runc: can't mask /proc/acpi), so dropping it
# both slims the image and unblocks the multi-arch build.

# COPY the full plugin: app + all its modules (acquire/metadata/nodemeta/upload).
COPY app.py acquire.py metadata.py nodemeta.py upload.py requirements.txt /app/
RUN pip3 install --no-cache-dir -U -r /app/requirements.txt

ENTRYPOINT ["python3", "-u", "/app/app.py"]
