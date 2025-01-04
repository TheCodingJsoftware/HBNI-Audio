@echo off

:: Get the current date and time for versioning
for /f "tokens=2 delims==" %%I in ('"wmic os get localdatetime /value | findstr LocalDateTime"') do set datetime=%%I

:: Format the version as year.month.day.hour
set VERSION=%datetime:~0,4%.%datetime:~4,2%.%datetime:~6,2%.%datetime:~8,2%

:: Build, tag, and push the Docker image
docker build -t hbni-audio-archive:%VERSION% .
docker tag hbni-audio-archive:%VERSION% jarebear/hbni-audio-archive:%VERSION%
docker push jarebear/hbni-audio-archive:%VERSION%
