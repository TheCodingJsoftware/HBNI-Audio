@echo off
REM Build the Docker image with the tag "hbni-audio-archive"
docker image build -t hbni-audio-archive:latest .

REM Tag the Docker image as "latest" for pushing to Docker Hub
docker tag hbni-audio-archive:latest jarebear/hbni-audio-archive:latest

REM Push the "latest" tag to the Docker registry
docker push jarebear/hbni-audio-archive:latest

echo Script execution complete.
