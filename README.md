# Camera Proxy

Camera Proxy is a Python webserver which can display a video stream from battery based Reolink cameras.

The communication protocol used by battery based Reolink cameras is named Baichuan Protocol, a derivative of the Swann DVR Protocol over UDP transmition.

**IMPORTANT**: that repository is a fork of [jdillenkofer/camera_proxy](https://github.com/jdillenkofer/camera_proxy) which is the initiator of Baichuan UDP protocol implementation within Python. 

## Main features

| Name | Description | Status | Implemented |
|------|-------------|-------------|-------|
| MJPEG Service | Motion JPEG service provides a video streaming endpoint over HTTP. | Done | ✅ Flask server with args<br />✅ Dynamic endpoints per camera defined in `settings.json` |
| BC Protocol | Communication protocol used by Reolink cameras over UDP | In Progress | ✅ Broadcast Discovery<br />✅ Legacy login<br />✅ Modern login<br />✅ Start video streaming<br />✅ Get camera battery state<br />*(reported only at streaming time within console log)*<br />⬜️ Get camera information |
| P2P Protocol | Peer-To-Peer Reolink protocol used for camera's discovery and streaming through a relay. | In Progress | ✅ Discovery\*<br />⬜️ Streaming from a relay |

*\*Works only within the same camera network, remote connection by a Reolink relay is not implemented yet.*

## Apply to
> **Important**: Only for Reolink cameras which doesn't implements modern streaming protocols. \
> For others Reolink cameras, please review that repository [thirtythreeforty/neolink](https://github.com/thirtythreeforty/neolink)

Cameras tested or reported working.

| Product Name                                        | BC (UDP)           | P2P                |
|-----------------------------------------------------|--------------------|--------------------|
| [Argus 2](https://reolink.com/product/argus-2/)     | :heavy_check_mark: | :heavy_check_mark: |
| [Argus Eco](https://reolink.com/product/argus-eco/) | :heavy_check_mark: | :heavy_check_mark: |

## What's next ?

- Project
  - Source code refactoring
  - New design pattern
  - Documentations
- New features
  - Add additionnal settings for docker container isolation (UDP listening port, range port map...)
  - Provides an RTP endpoint per camera defined in `settings.json` file ([GStreamer](https://gitlab.freedesktop.org/gstreamer/gst-python) or [rtmplite3](https://github.com/KnugiHK/rtmplite3))
  - H264 video streaming pass-through?
  - Video streaming decoding with hardware acceleration (VA-API, CUDA) with ffmpeg/libav or OpenCV!


# How to use it?
The application can be executed within a Docker container or from any environment with Python.

## Endpoints
As soon as the application is running the following endpoints are available.

 > /api/v1/cameras/{camera_name} \
 > /api/v1/cameras/{camera_name}/stream

Details : [api-swagger.yaml](docs/api-swagger.yaml)

## Docker
The Baichuan protocol uses broadcast requests to discover the target camera. \
Meaning the container must ran within `Host` network mode for that discovery mode. \
However, since P2P protocol is implemented, the container could be isolated but UDP listening port is currently dynamic and cannot be defined yet.


### Building a Docker image

```bash 
$ docker build https://<github_repo_url>/camera_proxy.git#<branch_name> -t <tag_name>
```

Example:
```bash 
$ docker build https://github.com/vherrlein/camera_proxy.git#develop -t camera_proxy:dev-amd64
```

*For additional information regarding to Docker image building : \
[Docker build command line reference](https://docs.docker.com/engine/reference/commandline/build/)*

### Prepare Docker configs
In order to provide camera's settings, a docker config should be added before running any container.

*Note: Another solution could use an external json file which would be mounted to the container as a docker volume.*

Example:
```bash 
$ cat << EOF | docker config create my-cameras-settings -
{
    "cameras": [
        {
            "name": "camera1",
            "deviceSid": "12345678910ABC5D",
            "username": "admin",
            "password": "password"
        }
    ]
}
EOF
```
__Important note__: the **camera name** is **CASE SENSITIVE**.


*Note: Another solution could use an external settings.json file which would be mounted to the container as a docker volume. Example:*
``` 
--mount type=bind,source="$(pwd)"/settings.json,target=/app/settings.json,readonly
```


### Docker compose
Sample `docker-compose.yml`
```yaml
version: "3.3"
services:
  camera_proxy:
    image: camera_proxy:dev-amd64
    configs:
      - source: my-cameras-settings
        target: app/settings.json
    networks:
      - outside
    restart: always
    deploy:
      resources:
        limits:
          memory: 2G

configs:
  my-cameras-settings:
    external: true

networks:
  outside:
    external:
      name: "host"
```

### Start-up with Docker Swarm
Run the following command at `docker-compose.yml` location.

```bash
$ docker stack deploy --compose-file docker-compose.yml camera_proxy
```

Open a web browser to `http://YOUR_DOCKER_SERVER_IP:9090/api/v1/cameras/camera1`

__Important note__: the **camera name** is **CASE SENSITIVE**.

### Console Logs
As soon as a connection is made on one of camera's endpoints the following console logs appears. \
Sample
```console
 * Serving Flask app "main" (lazy loading)
 * Environment: production
   WARNING: This is a development server. Do not use it in a production deployment.
   Use a production WSGI server instead.
 * Debug mode: off
[MainThread-1]  * Running on http://0.0.0.0:9090/ (Press CTRL+C to quit)
[DecoderThread-9] Decoder deamon started
[CameraThread-8] Sending discovery packet
[CameraThread-8] Received discovery packet answer from XXX.XXX.XXX.XXX
[CameraThread-8] Sending legacy login packet
[CameraThread-8] Receiving nonce packet
[CameraThread-8] Received nonce: 0-AhnEZyUg6ew0ETWED156
[CameraThread-8] Sending modern login packet
[CameraThread-8] Send start video cmd
[CameraThread-8] Battery Percentage: 98
[Thread-1-7] 172.18.0.5 - - [22/Feb/2021 08:26:20] "GET /api/v1/cameras/camera1/stream HTTP/1.1" 200 -
[Thread-1-7] FPS approx: 0.87, Queue Size: 0
[Thread-1-7] FPS approx: 5.69, Queue Size: 0
[Thread-1-7] FPS approx: 7.70, Queue Size: 0
[Thread-1-7] FPS approx: 9.23, Queue Size: 0
[Thread-1-7] FPS approx: 6.61, Queue Size: 0
[DecoderThread-9] Decoder - Reduction Factor: 1.00, Queue size: 1, Processing time avg: 0.1034s
[Thread-1-7] FPS approx: 9.02, Queue Size: 0
[Thread-1-7] FPS approx: 8.36, Queue Size: 0
[Thread-1-7] FPS approx: 9.46, Queue Size: 0
[Thread-1-7] FPS approx: 7.44, Queue Size: 0
[Thread-1-7] FPS approx: 8.70, Queue Size: 0
```

## Standalone or Development Environment

### Requirements

An Operating System with `Python 3.9+` installed. \
Tested OS:
- Windows 10 Pro with Python 3.9.1
- Ubuntu server 20.10 with Python 3.9.1

### Pre-requisites

#### Import the git repo

Run the following command line within your target folder path.
```bash
$ git clone https://github.com/vherrlein/camera_proxy.git
```

#### Install Python dependencies

Run the following command line at the project root location.

```console
pip install -r requirements.txt
```

**Important note**: For Windows 10 users, it would be easier to install the `netifaces`  module from a pre-built binary **prior** executing the command line above. \
Eg. source of pre-built binaries: https://www.lfd.uci.edu/~gohlke/pythonlibs/ 

### Usage

Create a `settings.json` file with one or more camera entries at the project root location:
```json
{
    "cameras": [
        {
            "name": "camera1",
            "deviceSid": "12345678910ABC5D",
            "username": "admin",
            "password": "password",
            "ipaddress": "192.168.1.44",
            "comm_port": 12345,
            "backupImage": "../public/images/klingel.jpg"
        }
    ]
}
```
The following values are optional:
- **backupImage**: The image to be shown if no camera image can be obtained.
- **comm_port**: The communication port to be used by the proxy to send out the broadcast. This can be used to open a specific port in your firewall settings for this camera proxy.
- **ipaddress**: The known IP address for the camera (on the local network). When set, the proxy only tries the local discovery and skips the P2P discovery. This is useful to keep traffic within the local subnet.


__Important note__: the **camera name** is **CASE SENSITIVE**.

Run the main.py from the root directory:

```console
python src/main.py
```

## License
[MIT](./docs/license.txt)