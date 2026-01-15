FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir aiohttp

COPY main.py .

EXPOSE 8080

CMD ["python", "main.py"]
