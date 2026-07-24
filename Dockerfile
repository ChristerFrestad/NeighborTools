FROM python:3.12-slim

WORKDIR /app

# App is a single index.html + server + PWA files
COPY server.py index.html manifest.webmanifest sw.js ./

# Data lives here (mounted as volume in Portainer)
RUN mkdir -p /data

ENV PORT=8080
ENV DATA_DIR=/data

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health')" || exit 1

CMD ["python3", "server.py"]
