#!/bin/bash

# Get the current date and time for versioning: YYYY.MM.DD.HH
VERSION=$(date +%Y.%m.%d.%H)

# Build the Docker image with the versioned tag
docker build -t jarebear/hbni-audio-archive:$VERSION .

# Tag the Docker image as "latest"
docker tag jarebear/hbni-audio-archive:$VERSION jarebear/hbni-audio-archive:latest

# Push both the versioned tag and the "latest" tag
docker push jarebear/hbni-audio-archive:$VERSION
docker push jarebear/hbni-audio-archive:latest
