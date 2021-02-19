FROM python:3.9.1-buster

WORKDIR app

RUN apt-get update
RUN apt-get install -y libavformat-dev libavdevice-dev libavcodec-dev libavfilter-dev libavutil-dev libswscale-dev libswresample-dev

COPY ./requirements.txt requirements.txt

RUN pip install -r requirements.txt

COPY ./src src
COPY ./public public

# settings.json must be provided by docker configs

EXPOSE 9090

CMD ["python", "src/main.py", "--port", "9090"]
