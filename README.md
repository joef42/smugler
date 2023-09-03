# smugler
Uploads pictures/videos to Smugmug reflecting the local folder structures with folders/albums in Smugmug.

## Installation

* Get API key and secret from https://api.smugmug.com/api/developer/apply
* Create smuglerconf.yaml from example and insert API key and secret
* ```pip install -r requirements.txt```

## Usage
```
usage: smugler.py [-h] [--refresh REFRESH] [--debug] {sync} imagePath

Sync folder to Smugmug

positional arguments:
  {sync}             sync: Upload images to Smugmug
  imagePath          Path to local gallery

options:
  -h, --help         show this help message and exit
  --refresh REFRESH  Refresh Folders/Albums with the given name from Smugmug. * for everything.
  --debug            Print additional debug trace
  ```
