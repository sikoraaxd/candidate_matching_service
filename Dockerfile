FROM python:3.11-slim-bookworm

RUN apt-get -y update --allow-insecure-repositories && \
    apt-get -y upgrade

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir -r requirements.txt && \ 
    pip install --upgrade pip

EXPOSE 8501

ENV PYTHONUNBUFFERED=1 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_HEADLESS=true \
    C_FORCE_ROOT=1 

CMD ["streamlit", "run", "page.py", "--server.port=8501", "--server.enableCORS=false"]