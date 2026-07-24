FROM python:3.12-slim
WORKDIR /app
COPY server.py index.html manifest.webmanifest sw.js ./
ENV PORT=8080
ENV DATA_DIR=/data
VOLUME /data
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health')"
CMD ["python3", "server.py"]
