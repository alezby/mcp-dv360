FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt requirements_web.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements_web.txt

COPY src/ src/
COPY web_app/ web_app/
COPY run_app.py .

ENV PORT=8080
EXPOSE 8080

CMD exec uvicorn web_app.main:app --host 0.0.0.0 --port $PORT
