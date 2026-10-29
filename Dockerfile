# Start from a small official Linux image that already has Python 3.14.
FROM python:3.14-slim

# Don't write .pyc cache files, and print logs straight away (no buffering).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Every command below runs inside this folder in the image.
WORKDIR /code

# Libraries first: this layer is reused as long as requirements.txt doesn't change.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Then our own code (this changes often, so it comes last).
COPY app/ app/

# Run as a normal user, not root, and give that user a folder for uploads.
RUN useradd --create-home appuser \
    && mkdir -p /data/uploads \
    && chown appuser /data/uploads
USER appuser

# The app listens on port 8000 inside the container.
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]