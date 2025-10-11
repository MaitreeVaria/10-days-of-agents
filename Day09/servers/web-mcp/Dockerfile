FROM python:3.12-slim
WORKDIR /workspace/Day09/servers/web-mcp
COPY Day09/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
CMD ["python", "server.py"]
