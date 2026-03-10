FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (layer-cached separately from source code)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY . .

# Copy entrypoint and make executable
RUN chmod +x /app/entrypoint.sh

ENV FLASK_APP=app.main:create_app
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_RUN_PORT=5000

EXPOSE 5000

ENTRYPOINT ["/app/entrypoint.sh"]
