# S.N.A.P/docker/Dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files and install dependencies via pyproject.toml
COPY pyproject.toml .
COPY app/ ./app/
RUN pip install --no-cache-dir .

# Create data directories
RUN mkdir -p data/uploads data/repos data/projects

# Set Python path
ENV PYTHONPATH=/app

# Default environment variables (credentials must be provided via env/secrets)
ENV SANDBOX_ENVIRONMENT=production
ENV SANDBOX_LOG_LEVEL=INFO
ENV SANDBOX_LOG_JSON=true
# SANDBOX_POSTGRES_DSN must be set at runtime via environment variable

# Expose port (if adding API later)
EXPOSE 8080

# Run as non-root user
RUN useradd -m -u 1000 snap && chown -R snap:snap /app
USER snap

# Default command (can be overridden)
CMD ["python", "-c", "from app.main import startup; startup(); print('Snap tool ready')"]
