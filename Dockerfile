# syntax=docker/dockerfile:1

# TODO: update to python 3.12
FROM python:3.12-slim-bullseye
WORKDIR /app
COPY requirements.txt requirements.txt
RUN apt update

# Pillow dependencies
RUN apt-get -qq update && DEBIAN_FRONTEND=noninteractive apt-get -y install \
    cmake \
    curl \
    ghostscript \
    git \
    libffi-dev \
    libfreetype6-dev \
    libfribidi-dev \
    libharfbuzz-dev \
    libjpeg-turbo-progs \
    libjpeg62-turbo-dev \
    liblcms2-dev \
    libopenjp2-7-dev \
    libtiff5-dev \
    libwebp-dev \
    libssl-dev \
    meson \
    netpbm \
    python3-dev \
    python3-numpy \
    python3-setuptools \
    python3-tk \
    sudo \
    tcl8.6-dev \
    tk8.6-dev \
    virtualenv \
    wget \
    xvfb \
    zlib1g-dev

RUN apt-get install -y gcc g++ python3-dev git ffmpeg libjpeg-dev
RUN pip3 install -r requirements.txt
COPY . .
CMD [ "python3", "kidney-bot/main.py"]