# built from the project root (see docker-compose.yml): the app also serves frontend/ and reads data/
FROM python:3.12-slim
WORKDIR /project/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY frontend/ ../frontend/
COPY data/ ../data/
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
