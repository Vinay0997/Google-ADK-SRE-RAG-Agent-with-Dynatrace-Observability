FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY streamlit_app.py .

EXPOSE 8080

CMD ["sh", "-c", "streamlit run streamlit_app.py --server.port=${PORT:-8080} --server.address=0.0.0.0 --server.headless=true"]
