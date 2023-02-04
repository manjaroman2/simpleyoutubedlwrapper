from pathlib import Path
import datetime

SECRET_KEY = "3e4614e803a6bfa5112705b7"
AUDIOCODECS = ["flac", "wav", "mp3"]
VIDEOCODECS = ["mp4"]
MAX_SESSION_AGE = datetime.timedelta(days=30)
DATADIR = Path().cwd().parent / "data"
DEBUG = False
RESTRICT_FILENAMES = False
