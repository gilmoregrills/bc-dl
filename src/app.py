#!/usr/bin/env python3
import json
import logging
import os
import shutil
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from http.server import HTTPServer, SimpleHTTPRequestHandler


def env(name, default=None):
    v = os.environ.get(name)
    if v is None:
        return default
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1].strip()
    return v or default


DOWNLOAD_PATH = env("DOWNLOAD_PATH", "/downloads")
NOTIFY_URL = env("NOTIFY_URL")
PORT = int(env("PORT", "8047"))
LOG_LEVEL = env("LOG_LEVEL", "INFO").upper()
HERE = os.path.dirname(os.path.abspath(__file__))

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)-8s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("bc-dl")


def describe(path):
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return "missing"
    except OSError as e:
        return f"unstattable ({e})"
    if os.path.islink(path):
        return f"symlink -> {os.readlink(path)}"
    if os.path.isdir(path):
        try:
            n = len(os.listdir(path))
        except OSError:
            n = "?"
        return f"directory ({n} entries)"
    return f"file ({st.st_size} bytes)"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=HERE, **kw)

    def log_message(self, fmt, *args):
        log.info("http %s - %s", self.address_string(), fmt % args)

    def do_GET(self):
        if self.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self):
        if self.path != "/download":
            log.warning("POST to unknown path %r, returning 404", self.path)
            self.send_error(404)
            return
        started = time.monotonic()
        try:
            length = int(self.headers["Content-Length"])
            raw = self.rfile.read(length)
            log.info(
                "POST /download body (%d bytes): %s",
                length,
                raw.decode(errors="replace"),
            )
            body = json.loads(raw)
            url = body["url"]
            log.info("download requested: %s", url)

            dest = self.fetch(url)
            msg = f"saved {dest}\n"

            is_zip = zipfile.is_zipfile(dest)
            log.info("is_zipfile(%s) = %s", dest, is_zip)
            folder = DOWNLOAD_PATH
            if is_zip:
                folder = self.unzip(dest)
                msg += f"unzipped to {folder}\n"
            else:
                log.info("not a zip, notifying with download root %s", folder)

            if NOTIFY_URL:
                msg += self.notify(folder)
            else:
                log.warning("NOTIFY_URL not set, skipping notify for %s", folder)
                msg += "NOTIFY_URL not set, skipped notify\n"
        except Exception as e:
            log.exception(
                "request failed after %.1fs: %s", time.monotonic() - started, e
            )
            self.reply(500, f"error: {e}\n")
            return
        log.info("request complete in %.1fs", time.monotonic() - started)
        self.reply(200, msg)

    def fetch(self, url):
        log.info(
            "ensuring download dir %s (currently: %s)",
            DOWNLOAD_PATH,
            describe(DOWNLOAD_PATH),
        )
        os.makedirs(DOWNLOAD_PATH, exist_ok=True)

        parsed = urllib.parse.urlparse(url)
        name = os.path.basename(parsed.path) or "download"
        dest = os.path.join(DOWNLOAD_PATH, name)
        log.info(
            "fetch: url path=%r -> basename=%r -> dest=%s (existing: %s)",
            parsed.path,
            name,
            dest,
            describe(dest),
        )

        written = 0
        started = time.monotonic()
        with urllib.request.urlopen(url) as r:
            log.info(
                "fetch: HTTP %s, content-type=%s, content-length=%s, final-url=%s",
                r.status,
                r.headers.get("Content-Type"),
                r.headers.get("Content-Length"),
                r.url,
            )
            with open(dest, "wb") as f:
                while chunk := r.read(65536):
                    f.write(chunk)
                    written += len(chunk)
        log.info(
            "fetch: wrote %d bytes to %s in %.1fs (now: %s)",
            written,
            dest,
            time.monotonic() - started,
            describe(dest),
        )
        return dest

    def unzip(self, dest):
        stem = os.path.splitext(os.path.basename(dest))[0]
        folder = os.path.join(DOWNLOAD_PATH, stem + "-unzipped")
        log.info("unzip: archive=%s -> stem=%r -> target folder=%s", dest, stem, folder)
        if os.path.abspath(folder) == os.path.abspath(dest):
            log.error(
                "unzip: target folder is still the same path as the archive (%s); "
                "extractall would fail with 'Not a directory'.",
                folder,
            )
        log.info("unzip: target folder currently: %s", describe(folder))

        shutil.rmtree(folder, ignore_errors=True)
        log.info("unzip: after rmtree, target folder is: %s", describe(folder))

        with zipfile.ZipFile(dest) as z:
            names = z.namelist()
            log.info("unzip: archive contains %d entries", len(names))
            for n in names[:10]:
                log.info("unzip:   entry %s", n)
            if len(names) > 10:
                log.info("unzip:   ... and %d more", len(names) - 10)
            log.debug("unzip: full namelist: %s", names)
            z.extractall(folder)

        log.info("unzip: extracted to %s (now: %s)", folder, describe(folder))
        os.remove(dest)
        log.info("unzip: removed archive %s", dest)
        return folder

    def notify(self, folder):
        abs_folder = os.path.abspath(folder)
        if abs_folder != folder:
            log.info("notify: resolved %s -> %s", folder, abs_folder)
        payload = json.dumps({"localDirectoryName": abs_folder}).encode()
        log.info("notify: POST %s payload=%s", NOTIFY_URL, payload.decode())
        req = urllib.request.Request(
            NOTIFY_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as r:
            resp = r.read(2048).decode(errors="replace")
            log.info("notify: HTTP %s, response=%s", r.status, resp)
            return f"notified {NOTIFY_URL} with {abs_folder}: {r.status}\n"

    def reply(self, code, text):
        data = text.encode()
        log.info("reply: %d, %d bytes: %s", code, len(data), text.strip())
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    log.info(
        "listening on :%s, saving to %s, notifying %s, log level %s",
        PORT,
        DOWNLOAD_PATH,
        NOTIFY_URL,
        LOG_LEVEL,
    )
    log.info("download dir %s currently: %s", DOWNLOAD_PATH, describe(DOWNLOAD_PATH))
    HTTPServer(("", PORT), Handler).serve_forever()
