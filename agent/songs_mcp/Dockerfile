FROM python:3.12-slim
RUN pip install --no-cache-dir fastmcp==4.0.11 clickhouse-connect==1.9.0
COPY server.py /app/server.py
CMD ["python", "/app/server.py"]
