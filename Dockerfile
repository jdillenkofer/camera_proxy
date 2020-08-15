FROM python:3.6-buster

WORKDIR app

RUN apt-get update
RUN apt-get install -y libavformat-dev libavdevice-dev libavcodec-dev libavfilter-dev libavutil-dev libswscale-dev libswresample-dev
RUN pip install av
RUN pip install flask
RUN pip install pillow

COPY ./src src
COPY ./secrets.json secrets.json
COPY ./public public

EXPOSE 8000

CMD ["python", "src/main.py"]
