# Use pre-configured image containing both Python 3.10 and Node.js 22
FROM nikolaik/python-nodejs:python3.10-nodejs22-slim

# Set timezone and ensure non-interactive apt installations
ENV TZ=Asia/Shanghai
ENV DEBIAN_FRONTEND=noninteractive

# Set working directory inside the container
WORKDIR /app

# Install system dependencies (FFmpeg, FFprobe, and curl for logs/health checks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file first to utilize Docker build cache
COPY requirements.txt /app/

# Install required Python pip dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy all source files from current host directory to app directory
COPY . /app/

# Expose FastAPI default port
EXPOSE 7878

# Boot FastAPI server
CMD ["uvicorn", "web_app:app", "--host", "0.0.0.0", "--port", "7878"]
