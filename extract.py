#!/usr/bin/env python3
"""Usage:
  extract.py [--database=<database>] [--include-tags=<tags>] [--exclude-tags=<tags>] [--from-date=<Y/m/d>] [--export-path=<path>] [--thumbnail-path=<path>] [-e]
"""
from docopt import docopt

import sqlalchemy
from shotwellextractor.entities import *

import sqlite3
import os.path
import json
import shutil
import time
import datetime

import exifread.utils
from exifread import process_file
from exifread.tags import DEFAULT_STOP_TAG, FIELD_TYPES



arguments = docopt(__doc__, version='0.1.1rc')
if arguments['--database'] is not None:
    path = os.path.expanduser(arguments['--database'])
else:
    path = os.path.expanduser("~/.local/share/shotwell/data/photo.db")


engine = create_engine('sqlite:///' + path)

Session = sessionmaker(bind=engine)
session = Session()

exclude = []
if arguments['--exclude-tags'] is not None:
    exclude = arguments['--exclude-tags'].split(',')

include = []
if arguments['--include-tags'] is not None:
    include = arguments['--include-tags'].split(',')

from_date = None
if arguments['--from-date'] is not None:
    from_date = arguments['--from-date']
    from_date = time.mktime(datetime.datetime.strptime(from_date, "%Y/%m/%d").timetuple())
else:
    from_date = 0

export_path = "output/"
if arguments['--export-path'] is not None:
    export_path = arguments['--export-path']

thumbnail_path = os.path.expanduser("~/.cache/shotwell/thumbs/thumbs128")
if arguments['--thumbnail-path'] is not None:
    thumbnail_path = os.path.expanduser(arguments['--thumbnail-path'])
    if not os.path.isdir(thumbnail_path):
        exit()

with_exif = arguments['-e']


# Watchout, this could be dangerous. Perhaps it shouldn't be the default.
shutil.rmtree(export_path)
os.mkdir(export_path)
os.mkdir(export_path + "/pictures")
os.mkdir(export_path + "/tags")
os.mkdir(export_path + "/thumbnails")

def dump_json(obj, dest):
    js = json.dumps(obj)
    with open(dest, 'w+') as f:
        f.write(js)

def as_dict(obj, attr):
    attr = attr.split(",")
    return {c: getattr(obj, c) for c in attr}

# Read tags and extract primitive values from exifread special types that
# can't be json serialized.
def read_exif(filename):
    e = {}
    f = open(filename, 'rb')

    try:
        exif = process_file(f)
    except Exception as exc:
        print(filename, type(exc))
        return e

    if 'JPEGThumbnail' in exif:
        del exif['JPEGThumbnail']
    if 'TIFFThumbnail' in exif:
        del exif['TIFFThumbnail']

    exif_tag_names = list(exif.keys())
    exif_tag_names.sort()

    for etn in exif_tag_names:
        if type(exif[etn].values) == str:
            e[etn] = exif[etn].values

        elif type(exif[etn].values) == int:
            e[etn] = exif[etn].values

        elif type(exif[etn].values) == list:
            tmp = []
            for v in exif[etn].values:
                if type(v) == exifread.utils.Ratio:
                    tmp.append((v.num, v.den))
                elif type(v) == int:
                    tmp.append(v)
                else:
                    print(etn, v, type(v))

            e[etn] = tmp

    return e

# Silently remove elements
def remove_ids_from_list(l, ids):
    try:
        [l.remove(i) for i in ids]
    except ValueError:
        pass

def chunks(l, n):
    """ Yield successive n-sized chunks from l.
    """
    for i in range(0, len(l), n):
        yield l[i:i+n]

# Print running config
print("From Date:", from_date)
print("Exclude:", exclude)
print("Include:", include)
print("Thumbnails:", thumbnail_path)
print("Output:", export_path)
print("Exif:", with_exif)

if include == []:
    tags = session.query(Tag).all()
else:
    tags = session.query(Tag).filter(Tag.name.in_(include))

if len(exclude) > 0:
    exlusions = []
    exclude_tags = session.query(Tag).filter(Tag.name.in_(exclude))
    exclude_photos = []
    for ex_tag in exclude_tags:
        exclude_photos.extend(ex_tag.photo_list)

    exclude_photos = list(set(exclude_photos))
else:
    exclude_photos = []


photo_list = []
if include == []:
    q = session.query(Photo).filter(Photo.timestamp > from_date).all()
    photo_list = [p.id for p in q]
else:
    q = session.query(Tag).filter(Tag.name.in_(include)).all()
    for t in q:
        photo_list.extend(t.photo_list)

photo_list = list(set(photo_list))
unfiltered_count = len(photo_list)
#[photo_list.remove(ex) for ex in exclude_photos]
remove_ids_from_list(photo_list, exclude_photos)
filtered_count = len(photo_list)
print("Exporting:", str(filtered_count), "(" + str(unfiltered_count - filtered_count) + " filtered)")


all_pictures = []


tag_picture_hash = {t.name: t.photo_list for t in tags}
tagsjs = {}
tagsjs['NoTag'] = {'name':"NoTag", 'pictures':[], 'picture_count': 0, 'thumbnail': None}

# Can't get GPS if we don't read EXIF
if with_exif:
    tagsjs['WithGPS'] = {'name':"WithGPS", 'pictures':[], 'picture_count': 0, 'thumbnail': None}

events = {}

# We have to do this in chunks. sqlite borks with too many values ...
for chunk in chunks(photo_list, 100):
        photo_chunk = session.query(Photo).filter(Photo.id.in_(chunk)).filter(Photo.exposure_time > from_date)
        for p in photo_chunk:
            p.tags = []
            for tag in tag_picture_hash:

                if p.id in tag_picture_hash[tag]:
                    p.tags.append(tag)
                    if tag not in tagsjs:
                        tago = {'name': tag, 'thumbnail': p.thumbnail, 'picture_count': 1, 'pictures': [p]}
                        tagsjs[tag] = tago
                    else:
                        tagsjs[tag]['pictures'].append(p)
                        tagsjs[tag]['picture_count'] = tagsjs[tag]['picture_count'] + 1


            if len(p.tags) == 0:
                p.tags.append('NoTag')
                tagsjs['NoTag']['picture_count'] = tagsjs['NoTag']['picture_count'] + 1
                tagsjs['NoTag']['pictures'].append(p)

            pdict = as_dict(p, "id,path,thumbnail,exposure_time,orientation,tags")
            pdict['size'] = {'height': p.height, 'width': p.width}
            dt = p.exposure_time
            if p.exposure_time == 0:
                dt = p.time_created

            if p.title is None:
                p.title = datetime.datetime.fromtimestamp(int(dt)).strftime('%Y-%m-%d %H:%M:%S')


            pdict['datetime'] = datetime.datetime.fromtimestamp(int(dt)).strftime('%Y-%m-%d %H:%M:%S')

            if with_exif:
                pdict['exif'] = read_exif(p.filename)

                if 'GPS GPSLongitudeRef' in pdict['exif']:
                    tagsjs['WithGPS']['picture_count'] = tagsjs['WithGPS']['picture_count'] + 1
                    p.tags.append('WithGPS')
                    tagsjs['WithGPS']['pictures'].append(p)

            dump_json(pdict, export_path + "/pictures/" + str(p.id) + ".json")

            all_pictures.append(as_dict(p, "id,thumbnail,path"))
            try:
                shutil.copy(thumbnail_path + "/" + p.thumbnail, export_path + "/thumbnails/" + p.thumbnail)
            except FileNotFoundError:
                print(p.thumbnail, "not found ... skipping copy")


tags_file = [{'name': t, 'picture_count': tagsjs[t]['picture_count'], 'thumbnail': tagsjs[t]['thumbnail']} for t in tagsjs]

for t in tagsjs:
    to = {'name': t, 'pictures': [], 'thumbnail': tagsjs[t]['thumbnail']}
    for p in tagsjs[t]['pictures']:
        to['pictures'].append(as_dict(p, "id,thumbnail,title,path"))

    to['picture_count'] = len(to['pictures'])
    dump_json(to, export_path + "/tags/" + t + ".json")

dump_json(all_pictures, export_path + "/pictures/all-pictures.json")
dump_json(tags_file, export_path + "/tags/all-tags.json")
