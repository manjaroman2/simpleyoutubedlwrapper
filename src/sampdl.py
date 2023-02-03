from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    send_from_directory,
)
from yt_dlp import YoutubeDL, DownloadError
from yt_dlp.utils import parse_codecs
import re
from pathlib import Path
from uuid import uuid4
import random
from time import time, ctime
import shutil
from threading import Thread, Lock


random.seed(time())

SECRET_KEY = "3e4614e803a6bfa5112705b7"


urlregex = re.compile(
    r"""(?i)\b((?:https?:(?:/{1,3}|[a-z0-9%])|[a-z0-9.\-]+[.](?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)/)(?:[^\s()<>{}\[\]]+|\([^\s()]*?\([^\s()]+\)[^\s()]*?\)|\([^\s]+?\))+(?:\([^\s()]*?\([^\s()]+\)[^\s()]*?\)|\([^\s]+?\)|[^\s`!()\[\]{};:'".,<>?«»“”‘’])|(?:(?<!@)[a-z0-9]+(?:[.\-][a-z0-9]+)*[.](?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)\b/?(?!@)))"""
)
app = Flask(__name__)
app.secret_key = SECRET_KEY
datadir = Path().cwd() / "data"
if datadir.is_dir():
    shutil.rmtree(datadir)
datadir.mkdir()
print("> datadir:", datadir)
zips = dict()
LOADING = dict()
LOADINGLOCK = Lock()
age = dict()
WORKERS = {}


@app.route("/")
def hello_world():
    return redirect(url_for("sampdl"))


@app.route("/sampdl/dl/<string:file>")
def download(file):
    if "sesh" in session:
        sesh = session["sesh"]
        if sesh in zips:
            for z in zips[sesh]:
                if z["file"] == file:
                    return send_from_directory(
                        datadir, z["file"], as_attachment=True, download_name=z["name"]
                    )
    return redirect(url_for("sampdl"))


@app.template_filter("ctime")
def timectime(s):
    return ctime(s)  # datetime.datetime.fromtimestamp(s)


def sampdl_post():
    if "sesh" in session:
        sesh = session["sesh"]
        if sesh not in age:
            return
        if "link" in request.form and "codec" in request.form:
            aszip = "zip" in request.form
            codec = request.form["codec"]
            if not (codec := parse_codecs(codec)["acodec"]):
                codec = "flac"
            urls = urlregex.findall(request.form["link"])
            if urls:
                uuid = str(uuid4())
                tmpdir = datadir / uuid
                tmpdir.mkdir()
                ydlopts = {
                    "concurrent-fragments": 4,
                    "restrictfilenames": True,
                    "format": f"{codec}/bestaudio/best",
                    # ℹ️ See help(yt_dlp.postprocessor) for a list of available Postprocessors and their arguments
                    "postprocessors": [
                        {  # Extract audio using ffmpeg
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": codec,
                        }
                    ],
                    "outtmpl": {
                        # "default": (tmpdir / "%(title).150B [%(id)s].%(ext)s").as_posix() # https://github.com/yt-dlp/yt-dlp/issues/2329
                        "default": (
                            tmpdir / "%(title).150B.%(ext)s"
                        ).as_posix()  # https://github.com/yt-dlp/yt-dlp/issues/2329
                    },
                }

                def worker():
                    LOADINGLOCK.acquire()
                    LOADING[sesh] = 0
                    LOADINGLOCK.release()
                    add = 1 / len(urls) * 100
                    with YoutubeDL(ydlopts) as ydl:
                        for url in urls:
                            try:
                                ydl.download([url])
                                LOADINGLOCK.acquire()
                                LOADING[sesh] += add
                                LOADINGLOCK.release()
                            except DownloadError as e:
                                print(e)

                    LOADINGLOCK.acquire()
                    del LOADING[sesh]
                    LOADINGLOCK.release()
                    tmpfiles = list(tmpdir.glob("./*"))
                    files = []
                    skip = False
                    if not aszip:
                        if len(tmpfiles) < 10:
                            for tmpfile in tmpfiles:
                                fileuuid = str(uuid4())
                                shutil.copyfile(tmpfile, datadir / fileuuid)
                                files.append(
                                    {
                                        "file": fileuuid,
                                        "time": time(),
                                        "name": tmpfile.name,
                                    }
                                )
                            skip = True
                    if not skip:
                        shutil.make_archive(datadir / uuid, "zip", tmpdir)
                        files.append(
                            {
                                "file": uuid + ".zip",
                                "time": time(),
                                "name": f"{len(tmpfiles)}_zipbomb.zip",
                            }
                        )
                    shutil.rmtree(tmpdir)
                    zips[sesh].extend(files)

                thread = Thread(target=worker)
                thread.start()
                WORKERS[uuid] = thread


@app.route("/sampdl", methods=["GET", "POST"])
def sampdl():
    if request.method == "POST":
        r = sampdl_post()
        return redirect(url_for("sampdl"))
    if request.method == "GET":

        def newsesh():
            sesh = str(uuid4())
            zips[sesh] = list()
            age[sesh] = time()
            session["sesh"] = sesh

        zs = []
        loading = None
        if "sesh" in session:
            sesh = session["sesh"]
            if sesh in zips:
                zs = sorted(zips[sesh], key=lambda z: z["time"], reverse=True)
                zs = [z for z in zs if z["file"] != "_DUMMY"]
            elif sesh not in age:
                newsesh()
            LOADINGLOCK.acquire()
            if sesh in LOADING:
                loading = LOADING[sesh]
            LOADINGLOCK.release()
        else:
            newsesh()
        return render_template("index.html", zs=zs, loading=loading)


# yt-dlp -x --audio-format wav --audio-quality 0 -o "~/music/sampledl/%(title)s.%(ext)s" --restrict-filenames $1"
# print(help(postprocessor))
app.run(host="0.0.0.0", debug=False)
