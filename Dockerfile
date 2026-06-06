FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY douyin_download.py douyin_tool_server.py ./
COPY tools ./tools
COPY web ./web

EXPOSE 8765

CMD ["python", "douyin_tool_server.py", "--host", "0.0.0.0", "--port", "8765"]
