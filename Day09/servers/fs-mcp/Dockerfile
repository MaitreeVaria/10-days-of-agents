FROM python:3.12-slim
WORKDIR /workspace/Day09/servers/fs-mcp
COPY Day09/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
# server.py is mounted from host; container just executes it
CMD ["python", "server.py"]
