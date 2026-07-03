# Image Sampling

Image sampling samples still images from a camera stream. This is one of the fundamental ways for collecting data that will later be used in training machine learning models. This also gives a guidance on how an inferencing was performed; an image taken approximately at the same time when the inference was performed (on the same scene) visually shows the context.

# How to Use
To run the program,

```bash
# Captures and publishes an image from the camera stream
python3 app.py --stream bottom_camera
```

### Capturing an Image from Multiple Streams

```bash
python3 app.py \
  --stream bottom_camera \
  --stream top_camera
```

### Naming streams

```bash
# The count and order of the names
# must match with given streams
python3 app.py \
  --name street \
  --stream bottom_camera \
  --name sky \
  --stream top_camera
```

### Capturing and Saving Images Locally

```bash
# This does not publish images to the cloud,
# instead they are saved locally
python3 app.py \
  --stream bottom_camera \
  --out-dir /path/to/local/storage
```

The directory will have a directory for each stream and be structured with subdirectories helping to organize the images.

> NOTE: The directory structure recognizes those slashes (/) when creating subdirectories if the stream is a URL like rtsp://IP:PORT/stream. It will be /OUTDIR/RTSP:/IP:PORT/...

### Capturing Images using Cronjob

```bash
# Capturing an image from the stream every hour.
# Note that the program runs forever.
python3 app.py \
  --stream bottom_camera \
  --cronjob "0 * * * *"
```