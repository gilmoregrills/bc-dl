#!/usr/bin/env python3
"""Barebones download server. Stdlib only.

Downloads a URL, unzips it if it is a zip, then POSTs the folder path onwards.

Env:
  DOWNLOAD_PATH  directory to save downloads into (default ./downloads)
  NOTIFY_URL     URL to POST {"path": <folder>} to after a download
  PORT           listen port (default 8047)
"""
import json
import os
import shutil
import urllib.parse
import urllib.request
import zipfile
from http.server import HTTPServer, SimpleHTTPRequestHandler

DOWNLOAD_PATH = os.environ.get("DOWNLOAD_PATH", "/downloads")
NOTIFY_URL = os.environ.get("NOTIFY_URL")
PORT = int(os.environ.get("PORT", "8047"))
HERE = os.path.dirname(os.path.abspath(__file__))


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=HERE, **kw)

    def do_GET(self):
        if self.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self):
        if self.path != "/download":
            self.send_error(404)
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            dest = self.fetch(body["url"])
            msg = f"saved {dest}\n"
            folder = DOWNLOAD_PATH
            if zipfile.is_zipfile(dest):
                folder = self.unzip(dest)
                msg += f"unzipped to {folder}\n"
            if NOTIFY_URL:
                msg += self.notify(folder)
            else:
                msg += "NOTIFY_URL not set, skipped notify\n"
        except Exception as e:
            self.reply(500, f"error: {e}\n")
            return
        self.reply(200, msg)

    def fetch(self, url):
        os.makedirs(DOWNLOAD_PATH, exist_ok=True)
        name = os.path.basename(urllib.parse.urlparse(url).path) or "download"
        dest = os.path.join(DOWNLOAD_PATH, name)
        with urllib.request.urlopen(url) as r, open(dest, "wb") as f:
            while chunk := r.read(65536):
                f.write(chunk)
        return dest

    def unzip(self, dest):
        folder = os.path.join(
            DOWNLOAD_PATH, os.path.splitext(os.path.basename(dest))[0]
        )
        shutil.rmtree(folder, ignore_errors=True)
        with zipfile.ZipFile(dest) as z:
            z.extractall(folder)
        os.remove(dest)
        return folder

    def notify(self, folder):
        req = urllib.request.Request(
            NOTIFY_URL,
            data=json.dumps({"localDirectoryName": folder}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as r:
            return f"notified {NOTIFY_URL}: {r.status}\n"

    def reply(self, code, text):
        data = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    print(f"listening on :{PORT}, saving to {DOWNLOAD_PATH}, notifying {NOTIFY_URL}")
    HTTPServer(("", PORT), Handler).serve_forever()
