FROM python:3.12-slim

WORKDIR /workspace
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install deps first for better caching
COPY Day09/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# ⬇️ Copy your whole repo so Day07/Day08/Day09 are in the image
COPY . /workspace

# Make packages importable from /workspace
ENV PYTHONPATH=/workspace

# ---- app Dockerfile only ----
# CMD ["python","Day09/app/main.py"]

# ---- worker Dockerfile only ----
# CMD ["python","Day09/worker/worker_entry.py"]
