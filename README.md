# Camera Proxy

Camera Proxy is a Python webserver which can display a video stream from battery based Reolink cameras.

The communication protocol used by battery based Reolink cameras is named Baichuan Protocol, a derivative of the Swann DVR Protocol over UDP transmition.

**IMPORTANT**: that repository is a fork of [jdillenkofer/camera_proxy](https://github.com/jdillenkofer/camera_proxy) which is the initiator of Baichuan UDP protocol implementation within Python. 

## Main features

| Name | Description | Status | Implemented |
|------|-------------|-------------|-------|
| MJPEG Service | Motion JPEG service provides a video streaming endpoint over HTTP. | Done | <ul><li>✅ Flask server with args</li><li>✅ Dynamic endpoints per camera defined in `settings.json`</li></ul> |
| BC Protocol | Communication protocol used by Reolink cameras over UDP | In Progress | <ul><li>✅ Broadcast Discovery</li><li>✅ Legacy login</li><li>✅ Modern login</li><li>✅ Legacy login</li><li>✅ Start video streaming</li><li>✅ Get camera battery state<br />*(reported only at streaming time within console log)*</li><li>⬜️ Get camera information</li></ul> |
| P2P Protocol | Peer-To-Peer Reolink protocol used for camera's discovery and streaming through a relay. | In Progress | <ul><li>✅ Discovery\*</li><li>⬜️ Streaming from a relay</li></ul> |

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
  - Provides an RTP endpoint per camera defined wihtin `settings.json` ([GStreamer](https://gitlab.freedesktop.org/gstreamer/gst-python) or [rtmplite3](https://github.com/KnugiHK/rtmplite3))
  - H264 video streaming pass-through?
  - Video streaming decoding with hardware acceleration (VA-API, CUDA) with ffmpeg/libav or OpenCV!


# How to use it?
The application can be executed within a Docker container or from any environment with Python.

## Endpoints
As soon as the application is running the folowwing endpoints are available.

 > /api/v1/cameras/{camera_name} \
 > /api/v1/cameras/{camera_name}/stream

Details : [api-swagger.yaml](docs/api-swagger.yaml)

## Docker
The Baichuan protocol uses broadcast requests within the camera network for the initial discovery. \
Meaning the container must run within the network `Host`.

### Building a Docker image

```bash 
$ docker build https://<github_repo_url>/camera_proxy.git#<branch_name> -t <tag_name>
```

Exemple:
```bash 
$ docker build https://github.com/vherrlein/camera_proxy.git#develop -t camera_proxy:dev-amd64
```

*For additionnal information regarding to Docker image building : \
[Docker build command line reference](https://docs.docker.com/engine/reference/commandline/build/)*

### Prepare Docker configs
In order to provide camera's settings, a docker config should be added before runing any container.

*Note: Another solution could be using an external json file which can be mounted to the container throught docker volumes settings.*

Exemple:
```bash 
$ cat << EOF
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
EOF | docker config create my-cameras-settings -
```
__Important note__: the **camera name** is **CASE SENSITIVE**.

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

### Start-up with Docker compose
Run the following commande at `docker-compose.yml` location.
```bash
$ docker-compose up
```

Open a web browser to `http://YOUR_DOCKER_SERVER_IP:9090/api/v1/cameras/camera1`

__Important note__: the **camera name** is **CASE SENSITIVE**.

## Standalone or Development Environment

### Requirements

An Operating system with `Python 3.9+` installed. \
Tested OS:
- Windows 10 Pro with Python 3.9.1
- Ubuntu server 20.10 with Python 3.9.1

### Pre-requisites

#### Import the git repo

Run trhe following command line within your target folder path.
```bash
$ git clone https://github.com/vherrlein/camera_proxy.git
```

#### Install Python depencies

Run the following command line at the project root location.

```console
pip install -r requirements.txt
```

**Important note**: For Windows 10 users, it would be easier to install the `netifaces`  module from a pre-built binaries **prior** executing the command line above. \
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
            "backupImage": "../public/images/klingel.jpg"
        }
    ]
}
```

__Important note__: the **camera name** is **CASE SENSITIVE**.

Run the main.py from the root directory:

```console
python src/main.py
```

## License
[MIT](license.txt)