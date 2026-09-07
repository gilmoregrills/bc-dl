# bc-dl

Downloads a URL, unzips it if it is a zip, then POSTs the folder path to [bisque](https://github.com/gilmoregrills/bisque) or something else that accept [slskd]() style webhooks.

## Setup

### Environment Variables

| Variable Name | Description |
| -------------- | --------------- |
| DOWNLOAD_PATH | directory to save downloads into (default ./downloads) |
| NOTIFY_URL | URL to POST {"path": <folder>} to after a download |
| PORT | listen port (default 8047) |

### Example - Docker Compose

```yaml
services:
  beets:
    image: ghcr.io/gilmoregrills/bc-dl:<VERSION>
    container_name: bc-dl
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Etc/UTC
      - NOTIFY_URL="https://bisque.my-domain"
    volumes:
      - /path/to/downloads:/downloads # can be different if you specify a different DOWNLOAD_PATH
    ports:
      - 8047:8047 # can be different if you specify a different PORT
    restart: unless-stopped
```
