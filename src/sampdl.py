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
    jsonify,
)
import gunicorn.app.base
from yt_dlp import YoutubeDL, DownloadError

import re
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


def download_ffmpeg():
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
    # make executable
    import stat

    st = os.stat("ffmpeg")
    os.chmod("ffmpeg", st.st_mode | stat.S_IEXEC)
    # reload PATH
    import site
    from importlib import reload

    reload(site)


if not shutil.which("ffmpeg"):
    download_ffmpeg()

print(os.environ["PATH"])
print("> ffmpeg:", shutil.which("ffmpeg"))
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


class Worker:
    def __init__(self, endpoint, urls, ydlopts, tmpdir, aszip) -> None:
        global data
        self.threadId = data["manager"].Value("i", None)
        self.ydlopts = data["manager"].dict(ydlopts)
        self.endpoint = data["manager"].Value("s", endpoint)
        self.urls = data["manager"].list(urls)
        self.tmpdir_str = data["manager"].Value("s", str(tmpdir))
        self.aszip = data["manager"].Value("b", aszip)
        self.is_running = data["manager"].Value("b", False)
        self.progress: Value = data["manager"].Value("d", None)
        self.loaded: Value = data["manager"].Value("i", None)
        self.playlist_count = data["manager"].Value("i", None)

    def __dict__(self):
        return {
            "is_running": self.is_running.value,
            "progress": self.progress.value,
            "loaded": self.loaded.value,
            "playlist_count": self.playlist_count.value,
        }

    def spawn_thread(self) -> None:
        def _run():
            self.tmpdir = Path(self.tmpdir_str.value)

            def progress_hook(info):
                # import json
                # open("progress.json", "w").write(json.dumps(info, indent=4))
                if info["info_dict"]["playlist"]:
                    self.playlist_count.value = info["info_dict"]["playlist_count"]

            def post_hook(info):
                loaded = self.loaded.value + 1
                self.loaded.value = loaded
                if self.playlist_count.value > 1:
                    self.progress.value = round(
                        loaded / self.playlist_count.value * 100, 1
                    )

            with YoutubeDL(self.ydlopts) as ydl:
                ydl.add_progress_hook(progress_hook)
                ydl.add_post_hook(post_hook)
                for url in self.urls:
                    try:
                        ydl.download([url])
                    except DownloadError as e:
                        print(e)
            tmpfiles = list(self.tmpdir.glob("./*"))
            files = []
            if not (self.aszip.value or len(tmpfiles) > 5):
                for tmpfile in tmpfiles:
                    fileuuid = str(uuid4())
                    shutil.copyfile(tmpfile, DATADIR / fileuuid)
                    files.append(File(fileuuid, tmpfile.name.replace("_", " ")))
            else:
                shutil.make_archive(DATADIR / self.session.uuid, "zip", self.tmpdir)
                files.append(
                    File(
                        self.session.uuid + ".zip",
                        f"{len(tmpfiles)} {self.endpoint.value}s.zip",
                    )
                )
                
            shutil.rmtree(self.tmpdir)
            
            self.session.files.extend(files)

        # thread = Thread(target=_run)
        # thread.start()
        # self.threadId.value = self.thread.ident

    def __delete__(self) -> None:
        print("Deleting worker", self)
        self.session.workers.remove(dict(self))


class Session:
    def __init__(self) -> None:
        global data
        self.uuid: str = str(uuid4())
        self.files: List[File] = data["manager"].list()
        self.workers: List[Dict] = data["manager"].list()
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
def flask_download(file):
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


@app.route("/s/api/progress")
def flask_progress():
    global data
    sessions: Dict[str, Session] = data["sessions"]
    if "sesh" in request.cookies:
        sesh = request.cookies["sesh"]
        if sesh in sessions:
            return jsonify(list(map(dict, sessions[sesh].workers)))
        abort(400, description="Invalid session")
    abort(400, description="No session")


@app.template_filter("ctime")
def timectime(s):
    return time.ctime(s)  # datetime.datetime.fromtimestamp(s)


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
                worker = Worker(endpoint, urls, ydlopts, tmpdir, aszip)
                session.workers.append(worker.__dict__())
                worker.spawn_thread()
        return redirect(posturl)
    if request.method == "GET":
        newsesh = True
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
                    newsesh = False
                else:
                    del sessions[sesh]

        if newsesh:
            session = Session()
            sessions[session.uuid] = session
        response = make_response(
            render_template(
                "video.html",
                zs=files_sorted,
                workers=list(map(dict, session.workers)),
                codecs=codecs,
                form_action=posturl,
                endpoint=endpoint,
                links=otherurls,
            )
        )
        if newsesh:
            response.set_cookie("sesh", session.uuid, max_age=MAX_SESSION_AGE)
        return response


endpoints = {
    "audio": {"func": wrapper, "args": [AUDIOCODECS, True]},
    "video": {"func": wrapper, "args": [VIDEOCODECS]},
}


def create_endpoints():
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
        pycode = f"""\nglobal {funcname}, args_{ep} \nargs_{ep} = [othereps, *args[:]] \ndef {funcname}(): \n    return {obj["func"].__name__}('{ep}', url_for({funcname}.__name__), *args_{ep})\n"""
        exec(pycode)
        # print(globals().keys())
        # print(pycode)
        app.add_url_rule(
            f"/s/{ep}", view_func=globals()[funcname], methods=["GET", "POST"]
        )

    @app.route("/")
    @app.route("/s", methods=["GET"])
    def flask_s():
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


def main():
    create_endpoints()
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
    data["manager"] = manager
    data["sessions"] = manager.dict()

    HttpServer(app, options).run()


if __name__ == "__main__":
    main()
