FROM python:3.12-slim

WORKDIR /stress

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8089

CMD ["locust", "-f", "locustfile.py"]
