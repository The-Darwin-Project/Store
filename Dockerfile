# Store/Dockerfile
# Darwin Store - Test subject application with chaos injection
FROM registry.access.redhat.com/ubi9/ubi:latest

USER 0
RUN dnf install -y python3 python3-pip && dnf clean all

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy src as a package (preserves src.app and src.chaos import paths)
COPY src src

USER 1001

# Run Store app (port 8080) + Chaos controller (port 9000)
# NOTE: The chaos process is the test subject's fault injection interface.
# Do NOT remove it -- it is intentional, not a CPU load source.
CMD ["sh", "-c", "uvicorn src.app.main:app --host 0.0.0.0 --port 8080 & uvicorn src.chaos.main:app --host 0.0.0.0 --port 9000 & wait"]
