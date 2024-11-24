FROM python:3.12.5-slim

WORKDIR /app

COPY . /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5053

ENV PORT=5053
ENV MAX_POSTGRES_WORKERS=50
ENV POSTGRES_USER="admin"
ENV POSTGRES_PASSWORD=""
ENV POSTGRES_DB="hbni"
ENV POSTGRES_HOST="172.17.0.1"
ENV POSTGRES_PORT="5434"
ENV STATIC_RECORDINGS_PATH="/app/static/Recordings"
ENV STATIC_PATH="/app/static"
ENV TZ="Canada/Manitoba"

CMD python main.py
