FROM python:3.9.1-buster

WORKDIR app

RUN apt-get update
RUN apt-get install -y libavformat-dev libavdevice-dev libavcodec-dev libavfilter-dev libavutil-dev libswscale-dev libswresample-dev
RUN pip install av
RUN pip install flask
RUN pip install pillow
RUN pip install netifaces

COPY ./src src
#COPY ./settings.json settings.json
#settings.json must be provided by docker configs
COPY ./public public

EXPOSE 8000

CMD ["python", "src/main.py", "--port", "9090"]
