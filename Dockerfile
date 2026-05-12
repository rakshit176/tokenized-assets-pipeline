FROM python:3.12-slim

LABEL maintainer="rakshit176" \
      description="Tokenized Assets Data Extraction Pipeline"

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt \
    && rm -rf ~/.cache/pip

# Install Playwright browsers
RUN playwright install chromium --with-deps

# Copy application code
COPY . .

# Create output directory
RUN mkdir -p /app/output

# Default to batch help
ENTRYPOINT ["python", "step_run.py"]
CMD ["--help"]
