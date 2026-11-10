RELEASE?=0.0.0
PLATFORM?=linux/amd64,linux/arm64
IMAGE=image-sampler
PY?=.venv-test/bin/python

all: image

image:
	docker buildx build -t "waggle/plugin-$(IMAGE):$(RELEASE)" --load .

push:
	docker buildx build -t "waggle/plugin-$(IMAGE):$(RELEASE)" --platform "$(PLATFORM)" --push .

# Run the unit suite in the local test venv (canonical verification command).
# A fresh clone (or a requirements.txt change) rebuilds the venv first.
# Pillow is test-only (fixture JPEGs); without it 8 test modules skip.
.venv-test/.stamp: requirements.txt Makefile
	python3 -m venv .venv-test
	.venv-test/bin/pip install -q -r requirements.txt pytest Pillow
	touch $@

test: .venv-test/.stamp
	$(PY) -m pytest -q

.PHONY: all image push test
