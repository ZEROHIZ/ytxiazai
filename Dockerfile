# Stage 1: Get official Node.js binary from Node slim image
FROM node:20-slim AS node_image

# Stage 2: Main Python image
FROM python:3.10-slim

# Copy node binary from Node image stage
COPY --from=node_image /usr/local/bin/node /usr/local/bin/node

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
