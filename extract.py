#!/usr/bin/env python3
"""Usage:
  extract.py [--database=<database>] [--include-tags=<tags>] [--exclude-tags=<tags>] [--from-date=<date>] [--export-path=<path>] [--thumbnail-path=<path>]
"""
from docopt import docopt

import sqlite3
import os.path
import json
import shutil
import time
import datetime

import sqlalchemy
#from sqlalchemy import create_engine
#from sqlalchemy.orm import sessionmaker

from shotwellextractor.entities import *

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

if arguments['--thumbnail-path'] is not None:
    thumbnail_path = os.path.expanduser(arguments['--thumbnail-path'])
    if not os.path.isdir(thumbnail_path):
        exit()

shutil.rmtree(export_path)
os.mkdir(export_path)
os.mkdir(export_path + "/pictures")
os.mkdir(export_path + "/tags")
os.mkdir(export_path + "/thumbnails")

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

print("From Date:", from_date)
print("Exclude:", exclude)
print("Include:", include)

if include == []:
    tags = session.query(Tag).all()
else:
    tags = session.query(Tag).filter(Tag.name.in_(include))

if exclude is not []:
    exlusions = []
    exclude_tags = session.query(Tag).filter(Tag.name.in_(exclude))
    exclude_photos = []
    for ex_tag in exclude_tags:
        exclude_photos.extend(ex_tag.photo_list)

    exclude_photos = list(set(exclude_photos))

photo_list = []
for tag in tags:
    photo_list.extend(tag.photo_list)

photo_list = []
q = session.query(Photo).filter(Photo.timestamp > from_date).all()
photo_list = [p.id for p in q]

photo_list = list(set(photo_list))
print("Unfiltered pictures:", str(len(photo_list)))
#[photo_list.remove(ex) for ex in exclude_photos]
remove_ids_from_list(photo_list, exclude_photos)
print("Filtered pictures:", str(len(photo_list)))

def dump_json(obj, dest):
    js = json.dumps(obj)
    with open(dest, 'w+') as f:
        f.write(js)

def as_dict(obj, attr):
    attr = attr.split(",")
    return {c: getattr(obj, c) for c in attr}

all_pictures = []


tag_picture_hash = {t.name: t.photo_list for t in tags}
tagsjs = {}
tagsjs['NoTag'] = {'name':"NoTag", 'pictures':[], 'picture_count': 0, 'thumbnail': None}

for chunk in chunks(photo_list, 100):
        photo_chunk = session.query(Photo).filter(Photo.id.in_(chunk))
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
            dump_json(pdict, export_path + "/pictures/" + str(p.id) + ".json")

            all_pictures.append(as_dict(p, "id,thumbnail,path"))
            shutil.copy(thumbnail_path + "/" + p.thumbnail, export_path + "/thumbnails/" + p.thumbnail)

tags_file = [{'name': t, 'picture_count': tagsjs[t]['picture_count'], 'thumbnail': tagsjs[t]['thumbnail']} for t in tagsjs]

for t in tagsjs:
    to = {'name': t, 'pictures': [], 'thumbnail': tagsjs[t]['thumbnail']}
    for p in tagsjs[t]['pictures']:
        to['pictures'].append(as_dict(p, "id,thumbnail,title,path"))
    dump_json(to, export_path + "/tags/" + t + ".json")

dump_json(all_pictures, export_path + "/pictures/all-pictures.json")
dump_json(tags_file, export_path + "/tags/all-tags.json")
