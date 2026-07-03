RELEASE?=0.0.0
PLATFORM?=linux/amd64,linux/arm64
IMAGE=image-sampler

all: image

image:
	docker buildx build -t "waggle/plugin-$(IMAGE):$(RELEASE)" --load .

push:
	docker buildx build -t "waggle/plugin-$(IMAGE):$(RELEASE)" --platform "$(PLATFORM)" --push .
