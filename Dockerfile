FROM python:3.10.5

WORKDIR /app

RUN wget https://github.com/isis-project/isis-fonts/blob/master/NanumGothic.ttf?raw=true -O NanumGothic.ttf 
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
CMD ["python", "-O", "main.py"]
