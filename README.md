## simple ytdl wrapper  ~ 200 lines 

Change SECRET_KEY in sampdl.py, if you don't want your cookies stolen

### todo

* limit the size of download, maybe <1GB
* better ui (progress bar)

* cleanup sessions / old files
* cleanup code


### install 

install ffmpeg for audio extraction 

```
pip install -r requirements.txt
python src/sampdl.py
```

### notes


* if youre good with kubernets or something i would love to see this scaled 
* youtube doesn't like webapps that offer this functionality so spreading it across multiple instances would be cool
* its just an idea, i don't know if its necessary i wrote this first and foremost for myself because i need a look for music for sampling 