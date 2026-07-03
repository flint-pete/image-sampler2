# Image Sampler Plugin

This plugin utilizes [PyWaggle](https://github.com/waggle-sensor/pywaggle) library to capture frames from a stream. Captured frames are stored in a local storage as a jpeg image.

## Usage
Please refer to the [description](ecr-meta/ecr-science-description.md#how-to-use).

## Developer Notes

As of Dec 2020, this stores captured frames into a jpeg image. As the PyWaggle's data upload feature becomes real, it will utilize the feature rather than storing files on its own.
