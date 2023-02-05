from __future__ import annotations
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    send_from_directory,
    make_response,
    abort,
)
import gunicorn.app.base
import ffmpeg
from yt_dlp import YoutubeDL, DownloadError
import re
from uuid import uuid4
import argparse
from multiprocessing import Manager, Value
import random
import time
import shutil
from threading import Thread, current_thread
from typing import Dict, List
import os
import requests
import tarfile
from config import *


if not shutil.which("ffmpeg"):
    ffmpegurl = "https://johnvansickle.com/ffmpeg/builds/ffmpeg-git-amd64-static.tar.xz"
    tar = Path("ffmpeg.tar.xz")
    if not tar.is_file():
        print(f"Downloading ffmpeg from {ffmpegurl}")
        open("ffmpeg.tar.xz", "wb").write(requests.get(ffmpegurl).content)
    print("extracting ffmpeg")
    with tarfile.open("ffmpeg.tar.xz") as f:
        for m in f.getmembers():
            if Path(m.name).name == "ffmpeg":
                (Path().cwd() / "ffmpeg").write_bytes(f.extractfile(m).read())
                break
    tar.unlink()

print(shutil.which("ffmpeg"))
random.seed(time.time())
app = Flask(__name__)
app.secret_key = SECRET_KEY
# https://gist.github.com/nishad/ff5d02394afaf8cca5818f023fb88a21
urlregex = re.compile(
    r"""(?i)\b((?:https?:(?:/{1,3}|[a-z0-9%])|[a-z0-9.\-]+[.](?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)/)(?:[^\s()<>{}\[\]]+|\([^\s()]*?\([^\s()]+\)[^\s()]*?\)|\([^\s]+?\))+(?:\([^\s()]*?\([^\s()]+\)[^\s()]*?\)|\([^\s]+?\)|[^\s`!()\[\]{};:'".,<>?«»“”‘’])|(?:(?<!@)[a-z0-9]+(?:[.\-][a-z0-9]+)*[.](?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)\b/?(?!@)))"""
)


class File:
    def __init__(self, file, name) -> None:
        self.file = file
        self.href = f"/s/dl/{self.file}"
        self.time = time.time()
        self.name = name


class Session:
    def __init__(self) -> None:
        global data
        self.uuid: str = str(uuid4())
        self.files: List[File] = data["manager"].list()
        self.loading: Value = data["manager"].Value("d", 0.0)
        self.workers: List[int] = data["manager"].list()
        self.age: datetime.datetime = datetime.datetime.now()
        print(f"new sesh {self}")

    def is_valid(self):
        return (datetime.datetime.now() - self.age) < MAX_SESSION_AGE

    def __delete__(self) -> None:
        print("Deleting sesh", self)
        for f in self.files:
            (DATADIR / f.file).unlink()

    def __repr__(self) -> str:
        return f"Session[{self.uuid}]"


@app.route("/s/dl/<string:file>")
def download(file):
    global data
    sessions: Dict[str, Session] = data["sessions"]
    if "sesh" in request.cookies:
        sesh = request.cookies["sesh"]
        if sesh in sessions:
            session = sessions[sesh]
            for f in session.files:
                if f.file == file:
                    return send_from_directory(
                        DATADIR, f.file, as_attachment=True, download_name=f.name
                    )
    return redirect(url_for("sampdl"))


@app.template_filter("ctime")
def timectime(s):
    return time.ctime(s)  # datetime.datetime.fromtimestamp(s)


def worker(session: Session, endpoint, urls, ydlopts, tmpdir, aszip):
    def progress_hook(info):
        # import json
        # open("progress.json", "w").write(json.dumps(info, indent=4))
        progress = round(info["downloaded_bytes"] / info["total_bytes"], 1) * 100
        session.loading.value = progress

    def post_hook(info):
        pass

    with YoutubeDL(ydlopts) as ydl:
        ydl.add_progress_hook(progress_hook)
        ydl.add_post_hook(post_hook)
        for url in urls:
            try:
                ydl.download([url])
            except DownloadError as e:
                print(e)
    tmpfiles = list(tmpdir.glob("./*"))
    files = []
    skip = False
    if not aszip:
        if len(tmpfiles) < 5:
            for tmpfile in tmpfiles:
                fileuuid = str(uuid4())
                shutil.copyfile(tmpfile, DATADIR / fileuuid)
                files.append(File(fileuuid, tmpfile.name.replace("_", " ")))
            skip = True
    if not skip:
        shutil.make_archive(DATADIR / session.uuid, "zip", tmpdir)
        files.append(File(session.uuid + ".zip", f"{len(tmpfiles)} {endpoint}s.zip"))
    shutil.rmtree(tmpdir)
    session.files.extend(files)
    session.workers.remove(current_thread().ident)


def wrapper(endpoint, posturl, otherurls, codecs, extractaudio=False):
    global data
    sessions: Dict[str, Session] = data["sessions"]
    if request.method == "POST":
        if "sesh" in request.cookies:
            sesh = request.cookies["sesh"]
            if sesh not in sessions:
                abort(400, description="Invalid session")
            if "link" in request.form and "codec" in request.form:
                aszip = "zip" in request.form
                codec = request.form["codec"]
            else:
                abort(400, description="Missing form data")
            if codec not in codecs:
                codec = codecs[0]
            if urls := urlregex.findall(request.form["link"]):
                session = sessions[sesh]
                uuid = str(uuid4())
                tmpdir = DATADIR / uuid
                tmpdir.mkdir()
                ydlopts = {
                    "quiet": True,
                    "concurrent-fragments": 4,
                    "restrictfilenames": RESTRICT_FILENAMES,
                    "format": f"{codec}/bestaudio/best",
                    # ℹ️ See help(yt_dlp.postprocessor) for a list of available Postprocessors and their arguments
                    "outtmpl": {
                        "default": (
                            tmpdir / "%(title).150B.%(ext)s"
                        ).as_posix()  # https://github.com/yt-dlp/yt-dlp/issues/2329
                    },
                }
                if extractaudio:
                    ydlopts["postprocessors"] = [
                        {  # Extract audio using ffmpeg
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": codec,
                        }
                    ]
                args = (session, endpoint, urls, ydlopts, tmpdir, aszip)
                thread = Thread(target=worker, args=args)
                thread.start()
                session.workers.append(thread.ident)
        return redirect(posturl)
    if request.method == "GET":
        files_sorted = []
        response = None
        if "sesh" in request.cookies:
            sesh = request.cookies["sesh"]
            if sesh in sessions:
                session = sessions[sesh]
                if session.is_valid():
                    files_sorted = sorted(
                        session.files, key=lambda f: f.time, reverse=True
                    )
                    loading = None
                    if len(session.workers) > 0:
                        loading = session.loading.value
                    response = make_response(
                        render_template(
                            "video.html",
                            zs=files_sorted,
                            loading=loading,
                            codecs=codecs,
                            form_action=posturl,
                            endpoint=endpoint,
                            links=otherurls,
                        )
                    )
                else:
                    del sessions[sesh]
        if not response:
            session = Session()
            sessions[session.uuid] = session
            response = make_response(
                render_template(
                    "video.html",
                    zs=files_sorted,
                    loading=None,
                    codecs=codecs,
                    form_action=posturl,
                    endpoint=endpoint,
                    links=otherurls,
                )
            )
            response.set_cookie("sesh", session.uuid, max_age=MAX_SESSION_AGE)
        return response


endpoints = {
    "audio": {"func": wrapper, "args": [AUDIOCODECS, True]},
    "video": {"func": wrapper, "args": [VIDEOCODECS]},
}
endpoint_list = list(endpoints.keys())

# im gonna meet the devil for this
# unforgivable sins were commited
# im not seeing the pearl white gates of heaven
for i in range(len(endpoint_list)):
    ep = endpoint_list[i]
    othereps = [f"/s/{x}" for x in endpoint_list]
    epurl = othereps.pop(i)
    obj = endpoints[ep]
    args = obj["args"]
    funcname = f"flask_{ep}"
    obj["funcname"] = funcname
    pycode = f"""global {funcname} \nargs_{ep} = [othereps, *args[:]] \ndef {funcname}(): \n    return {obj["func"].__name__}('{ep}', url_for({funcname}.__name__), *args_{ep})"""
    exec(pycode)
    app.add_url_rule(f"/s/{ep}", view_func=locals()[funcname], methods=["GET", "POST"])


@app.route("/")
@app.route("/s", methods=["GET"])
def s():
    return render_template(
        "index.html",
        endpoints=[
            {"link": url_for(obj["funcname"]), "name": ep}
            for ep, obj in endpoints.items()
        ],
    )


class HttpServer(gunicorn.app.base.BaseApplication):
    def __init__(self, app, options=None):
        self.options = options or {}
        self.application = app
        super().__init__()

    def load_config(self):
        config = {
            key: value
            for key, value in self.options.items()
            if key in self.cfg.settings and value is not None
        }
        for key, value in config.items():
            self.cfg.set(key.lower(), value)

    def load(self):
        return self.application


if __name__ == "__main__":
    global data
    parser = argparse.ArgumentParser()
    parser.add_argument("--num-workers", type=int, default=5)
    parser.add_argument("--port", type=str, default="8080")
    args = parser.parse_args()
    options = {
        "bind": "%s:%s" % ("0.0.0.0", args.port),
        "workers": args.num_workers,
    }

    # initialize
    if DATADIR.is_dir():
        shutil.rmtree(DATADIR)
    DATADIR.mkdir()
    print("> datadir:", DATADIR)
    data = {}
    data["master_pid"] = os.getpid()
    manager = Manager()
    data["manager"] = Manager()
    data["sessions"] = manager.dict()

    HttpServer(app, options).run()
