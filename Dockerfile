FROM python:3.11-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -e . 2>/dev/null || true
RUN pip install --no-cache-dir pyyaml 2>/dev/null || true

EXPOSE 8765

VOLUME /data

CMD ["python", "mcp_server.py", "--db", "/data/index.db"]
