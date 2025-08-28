# Enterprise AI Gateway - Production Dockerfile
FROM python:3.11-slim as base

# Security: Create non-root user
RUN groupadd -r aigateway && useradd -r -g aigateway -d /app -s /sbin/nologin aigateway

# Install system dependencies
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# ============== DEPENDENCY STAGE ==============
FROM base as dependencies

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ============== PRODUCTION STAGE ==============
FROM dependencies as production

# Copy application files
COPY --chown=aigateway:aigateway . .

# Security: Remove unnecessary files
RUN rm -rf tests/ docs/ *.md requirements-dev.txt .git* && \
    find /app -type f -name "*.pyc" -delete && \
    find /app -type d -name "__pycache__" -delete

# Set permissions
RUN chmod -R 755 /app && \
    chmod -R 644 /app/*.py

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV ENVIRONMENT=production

# Security: Switch to non-root user
USER aigateway

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Expose port
EXPOSE 8080

# Production command
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]