FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app/analysis.py .
COPY app/fetch_data.py .

# Create data directories
RUN mkdir -p data/raw_data data/clean_data data/stats_data data/images

# Default command
CMD ["python", "analysis.py", "--month", "all"]
