FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000 8501
CMD ["sh", "-c", "python -m app.rag.vector_store && uvicorn app.api.main:app --host 0.0.0.0 --port 8000 & streamlit run ui/dashboard.py --server.port 8501 --server.address 0.0.0.0"]
