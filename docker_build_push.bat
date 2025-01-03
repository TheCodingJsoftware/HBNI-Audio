@echo off
set VERSION=2.0.2

docker build -t hbni-audio-archive:%VERSION% .
docker tag hbni-audio-archive:%VERSION% jarebear/hbni-audio-archive:%VERSION%
docker tag hbni-audio-archive:%VERSION% jarebear/hbni-audio-archive:latest
docker push jarebear/hbni-audio-archive:%VERSION%
docker push jarebear/hbni-audio-archive:latest