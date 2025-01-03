FROM python:3.12.5-slim

WORKDIR /app

COPY . /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5053

ENV PORT=5053
ENV TZ="America/Guatemala"
ENV MAX_POSTGRES_WORKERS=200
ENV POSTGRES_USER="admin"
ENV POSTGRES_PASSWORD=""
ENV POSTGRES_DB="hbni"
ENV POSTGRES_HOST="172.17.0.1"
ENV POSTGRES_PORT="5434"
ENV STATIC_RECORDINGS_PATH="/app/static/Recordings"
ENV RECORDING_STATUS_PATH="/app/static/recording_status.json"
ENV ICECAST_BROADCASTING_SOURCE="https://broadcast.hbni.net"
ENV ICECAST_BROADCASTING_HOST="172.17.0.1"
ENV ICECAST_BROADCASTING_PORT="8000"
ENV ICECAST_BROADCASTING_PASSWORD=""
ENV SECRET_KEY="5715fae086efbfa183dbd70f7cdd8eb1e37ee0468976a3306b1e7bc35599b52ce116924a685fd6179a0e44db80e8946b4e2a929aab10c56f08858718a2cb4989"
CMD ["python", "main.py"]
