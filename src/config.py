from pathlib import Path
import datetime
from uuid import uuid4

SECRET_KEY = uuid4().hex
AUDIOCODECS = ["flac", "wav", "mp3"]
VIDEOCODECS = ["mp4"]
MAX_SESSION_AGE = datetime.timedelta(days=30)
DATADIR = Path().cwd() / "data"
RESTRICT_FILENAMES = False
