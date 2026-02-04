FROM registry.access.redhat.com/ubi9/ubi:latest
USER 0
RUN dnf install -y python3 python3-pip && dnf clean all
USER 1001
WORKDIR /app
COPY requirements.txt .
RUN pip3 install -r requirements.txt
COPY src src
# Run App + Chaos (both processes, wait for either to exit)
CMD ["sh", "-c", "uvicorn src.app.main:app --host 0.0.0.0 --port 8080 & uvicorn src.chaos.main:app --host 0.0.0.0 --port 9000 & wait"]
