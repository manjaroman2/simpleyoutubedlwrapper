from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    send_from_directory,
    make_response,
)
from yt_dlp import YoutubeDL, DownloadError
import re
from uuid import uuid4
import random
from time import time, ctime
import shutil
from threading import Thread
from queue import Queue

from config import * 

random.seed(time())
urlregex = re.compile(
    r"""(?i)\b((?:https?:(?:/{1,3}|[a-z0-9%])|[a-z0-9.\-]+[.](?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)/)(?:[^\s()<>{}\[\]]+|\([^\s()]*?\([^\s()]+\)[^\s()]*?\)|\([^\s]+?\))+(?:\([^\s()]*?\([^\s()]+\)[^\s()]*?\)|\([^\s]+?\)|[^\s`!()\[\]{};:'".,<>?«»“”‘’])|(?:(?<!@)[a-z0-9]+(?:[.\-][a-z0-9]+)*[.](?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)\b/?(?!@)))"""
)
app = Flask(__name__)
app.secret_key = SECRET_KEY
if DATADIR.is_dir():
    shutil.rmtree(DATADIR)
DATADIR.mkdir()
print("> DATADIR:", DATADIR)
FILES = dict()
LOADING = dict()
AGE = dict()
WORKERS = {}


@app.route("/sampdl/dl/<string:file>")
def download(file):
    if "sesh" in request.cookies:
        sesh = request.cookies["sesh"]
        global FILES
        if sesh in FILES:
            for z in FILES[sesh]:
                if z["file"] == file:
                    return send_from_directory(
                        DATADIR, z["file"], as_attachment=True, download_name=z["name"]
                    )
    return redirect(url_for("sampdl"))


@app.template_filter("ctime")
def timectime(s):
    return ctime(s)  # datetime.datetime.fromtimestamp(s)


def worker(sesh, urls, ydlopts, tmpdir, aszip):
    global LOADING, FILES
    q: Queue = LOADING[sesh]
    progress = 0
    q.put(progress)
    add = 1 / len(urls) * 100
    with YoutubeDL(ydlopts) as ydl:
        for url in urls:
            try:
                ydl.download([url])
                progress += add
                q.put(progress)
            except DownloadError as e:
                print(e)

    del LOADING[sesh]
    tmpfiles = list(tmpdir.glob("./*"))
    files = []
    skip = False
    if not aszip:
        if len(tmpfiles) < 10:
            for tmpfile in tmpfiles:
                fileuuid = str(uuid4())
                shutil.copyfile(tmpfile, DATADIR / fileuuid)
                files.append(
                    {
                        "file": fileuuid,
                        "time": time(),
                        "name": tmpfile.name.replace("_", " "),
                    }
                )
            skip = True
    if not skip:
        shutil.make_archive(DATADIR / sesh, "zip", tmpdir)
        files.append(
            {
                "file": sesh + ".zip",
                "time": time(),
                "name": f"{len(tmpfiles)}.zip",
            }
        )
    shutil.rmtree(tmpdir)
    FILES[sesh].extend(files)


def wrapper(posturl, codecs, extractaudio=False):
    global FILES, AGE, LOADING
    if request.method == "POST":
        if "sesh" in request.cookies:
            sesh = request.cookies["sesh"]
            if sesh not in AGE:
                return
            if "link" in request.form and "codec" in request.form:
                aszip = "zip" in request.form
                codec = request.form["codec"]
            if codec not in codecs:
                codec = codecs[0]
            urls = urlregex.findall(request.form["link"])
            if urls:
                uuid = str(uuid4())
                tmpdir = DATADIR / uuid
                tmpdir.mkdir()
                ydlopts = {
                    "concurrent-fragments": 4,
                    "restrictfilenames": True,
                    "format": f"{codec}/bestaudio/best",
                    # ℹ️ See help(yt_dlp.postprocessor) for a list of available Postprocessors and their arguments
                    "outtmpl": {
                        # "default": (tmpdir / "%(title).150B [%(id)s].%(ext)s").as_posix() # https://github.com/yt-dlp/yt-dlp/issues/2329
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
                args = (sesh, urls, ydlopts, tmpdir, aszip)
                thread = Thread(target=worker, args=args)
                LOADING[sesh] = Queue()
                WORKERS[sesh] = thread
                thread.start()
        return redirect(posturl)
    if request.method == "GET":

        def newsesh():
            sesh = str(uuid4())
            FILES[sesh] = list()
            AGE[sesh] = datetime.datetime.now()
            return sesh

        def killsesh(sesh):
            print("Deleting sesh", sesh)
            if sesh in AGE:
                del AGE[sesh]
            if sesh in FILES:
                for f in FILES[sesh]:
                    (DATADIR / f["file"]).unlink()
                del FILES[sesh]

        files_sorted = []
        loading = None
        response = None
        if "sesh" in request.cookies:
            sesh = request.cookies["sesh"]
            if sesh in AGE:
                sesh_creation_date = AGE[sesh]
                if (datetime.datetime.now() - sesh_creation_date) < MAX_SESSION_AGE:
                    if sesh in FILES:
                        files_sorted = sorted(
                            FILES[sesh], key=lambda z: z["time"], reverse=True
                        )
                    if sesh in LOADING:
                        q: Queue = LOADING[sesh]
                        if not q.empty():
                            loading = LOADING[sesh].get()
                    response = make_response(
                        render_template(
                            "video.html",
                            zs=files_sorted,
                            loading=loading,
                            codecs=codecs,
                            form_action=posturl,
                        )
                    )
        if not response:
            killsesh(sesh)
            sesh = newsesh()
            response = make_response(
                render_template(
                    "video.html",
                    zs=files_sorted,
                    loading=loading,
                    codecs=codecs,
                    form_action=posturl,
                )
            )
            response.set_cookie("sesh", sesh, max_age=MAX_SESSION_AGE)
        return response


ENDPOINTS = {"audio": {"args": [AUDIOCODECS, True]}, "video": {"args": [VIDEOCODECS]}}

# im gonna meet the devil for this
# unforgivable sins were commited
for ep, obj in ENDPOINTS.items():
    args = obj["args"]
    funcname = f"flask_{ep}"
    obj["funcname"] = funcname
    pycode = f"""global {funcname} 
args_{ep} = args[:]
def {funcname}():
    return wrapper(url_for({funcname}.__name__), *args_{ep})"""
    exec(pycode)
    app.add_url_rule(f"/s/{ep}", view_func=locals()[funcname], methods=["GET", "POST"])

@app.route("/")
@app.route("/s", methods=["GET"])
def s():
    return render_template(
        "index.html",
        endpoints=[{"link": url_for(obj["funcname"]), "name": ep} for ep, obj in ENDPOINTS.items()],
    )

app.run(host="0.0.0.0", debug=False)
