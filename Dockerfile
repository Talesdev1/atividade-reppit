FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# catálogo de sequências: /app/var é o único diretório que precisa de volume.
# (não monte volume em /app/data: esconderia data/top/dataset_final.csv do COPY . .)
RUN mkdir -p /app/var
ENV DECIFRAME_DB=/app/var/deciframe.db
VOLUME ["/app/var"]

EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "main:app"]
