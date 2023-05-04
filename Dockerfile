# syntax=docker/dockerfile:1

FROM python:3.12-rc-slim
WORKDIR /app
COPY requirements.txt requirements.txt
RUN apt update
RUN apt-get install -y gcc g++ python3-dev git ffmpeg
RUN pip3 install -r requirements.txt
COPY . .
CMD [ "python3", "main.py"]