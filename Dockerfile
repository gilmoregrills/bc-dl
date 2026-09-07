FROM python:3.13-alpine

WORKDIR /app
COPY src/ /app/

CMD ["python3", "app.py"]
