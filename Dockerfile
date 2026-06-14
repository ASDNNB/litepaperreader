FROM python:3.11-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -e .
RUN pip install --no-cache-dir openai pyyaml

ENV LITEPAPER_MODE=mock
ENV LITEPAPER_API_KEY=""

EXPOSE 8765

VOLUME /data

ENTRYPOINT ["python", "mcp_server.py"]
CMD ["--db", "/data/index.db"]
