# Camera Proxy

---

**This project has been archived, and is no longer under active maintainenance.**
It's purpose was only a proof of concept for the support of battery powered cameras for the people from the [neolink](https://github.com/thirtythreeforty/neolink) project.
If you require a supported solution for your battery powered cameras, I suggest you to use neolink instead.

---

Camera Proxy is a Python webserver which can display a video stream from the reolink argus 2 camera over http.

## Dependencies

```console
pip install -r requirements.txt
```

## Usage

Create a settings.json with one or more camera entries:
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

Just run the main.py from the root directory:

```console
python src/main.py
```

## License
[MIT](license.txt)