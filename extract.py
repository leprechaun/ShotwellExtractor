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

# Allow the overriding of shotwell's database
if arguments['--database'] is not None:
    db_path = os.path.expanduser(arguments['--database'])
else:
    db_path = os.path.expanduser("~/.local/share/shotwell/data/photo.db")



# Any picture contained in this tag list will be excluded from the export
exclude = []
if arguments['--exclude-tags'] is not None:
    exclude = arguments['--exclude-tags'].split(',')

# If non empty, export will only include pictures from these tags
include = []
if arguments['--include-tags'] is not None:
    include = arguments['--include-tags'].split(',')

# Exclude any picture dating before this date
from_date = None
if arguments['--from-date'] is not None:
    from_date = arguments['--from-date']
    from_date = time.mktime(datetime.datetime.strptime(from_date, "%Y/%m/%d").timetuple())
else:
    from_date = 0

# Override the default export path
export_path = "output/"
if arguments['--export-path'] is not None:
    export_path = arguments['--export-path']

# Override the default shotwell thumbnails path
thumbnail_path = os.path.expanduser("~/.cache/shotwell/thumbs/thumbs128")
if arguments['--thumbnail-path'] is not None:
    thumbnail_path = os.path.expanduser(arguments['--thumbnail-path'])
    if not os.path.isdir(thumbnail_path):
        exit()

# Whether you want to read exif or not. It's expensive.
with_exif = arguments['-e']

engine = create_engine('sqlite:///' + db_path)

Session = sessionmaker(bind=engine)
session = Session()


# Watchout, this could be dangerous. Perhaps it shouldn't be the default.
shutil.rmtree(export_path)
os.mkdir(export_path)
os.mkdir(export_path + "/pictures")
os.mkdir(export_path + "/tags")
os.mkdir(export_path + "/thumbnails")
os.mkdir(export_path + "/events")

def dump_json(obj, dest):
    js = json.dumps(obj)
    with open(dest, 'w+') as f:
        f.write(js)

def as_dict(obj, attr):
    attr = attr.split(",")
    return {c: getattr(obj, c) for c in attr}

# Read tags and extract primitive values from exifread special types that
# can't be json serialized.

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

class PictureRef(object):
    def get_dict(self, picture, with_exif=False):
        o = {}
        o['id'] = picture.id

        o['datetime'] = picture.datetime
        o['path'] = picture.path

        if picture.title is None:
            o['title'] = o['datetime']
        else:
            o['title'] = picture.title

        if with_exif:
            o['exif'] = self.read_exif(picture.filename)

        o['tags'] = picture.tags
        o['size'] = {'height': picture.height, 'width': picture.width}
        return o

    def read_exif(self, filename):
        e = {}
        f = open(filename, 'rb')

        try:
            exif = process_file(f)
        except Exception as exc:
            print(filename, exc)
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

class PictureList(object):
    def __init__(self, name):
        self._name = name
        self._pictures = []

    def add_picture(self, picture):
        self._pictures.append(picture)

    def picture_count(self):
        return len(self._pictures)

    def get_dict(self):
        o = {}
        o['name'] = self._name
        o['picture_count'] = len(self._pictures)
        o['pictures'] = [self.get_picture_dict(p) for p in self._pictures]
        if len(self._pictures) > 0:
            o['thumbnail'] = self._pictures[0].thumbnail

        return o

    def get_picture_dict(self, picture):
        o = {}
        o['id'] = picture.id
        o['thumbnail'] = picture.thumbnail

        o['title'] = picture.title
        if o['title'] is None:
            o['title'] = picture.datetime

        return o

    def get_ref(self):
        o = {}
        o['name'] = self._name
        o['picture_count'] = len(self._pictures)
        if len(self._pictures) > 0:
            o['thumbnail'] = self._pictures[0].thumbnail

        return o

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
tagsjs['NoTag'] = PictureList('NoTag')
tagsjs['WithGPS'] = PictureList('WithGPS')

events = {}

# We have to do this in chunks. sqlite borks with too many values ...
for chunk in chunks(photo_list, 100):
        photo_chunk = session.query(Photo).filter(Photo.id.in_(chunk)).filter(Photo.exposure_time > from_date)
        for p in photo_chunk:
            p.tags = []
            for tag in tag_picture_hash:

                # If tag contains the picture id, append the tag
                if p.id in tag_picture_hash[tag]:
                    p.tags.append(tag)

                    # create the tag object if it doesn't exit
                    if tag not in tagsjs:
                        tago = PictureList(tag)
                        tagsjs[tag] = tago

                    tagsjs[tag].add_picture(p)


            # If the picture isn't tagged
            if len(p.tags) == 0:
                # Create artificial 'NoTag'
                p.tags.append('NoTag')
                tagsjs['NoTag'].add_picture(p)

            pr = PictureRef()

            # Make the events hash
            d = p.date
            if d not in events:
                events[d] = PictureList(d)

            events[d].add_picture(p)

            # Dump the picture json to disk
            dump_json(pr.get_dict(p, with_exif), export_path + "/pictures/" + str(p.id) + ".json")

            # Append a picture ref for all pictures
            all_pictures.append(as_dict(p, "id,thumbnail"))

            # Copy the thumbnail over
            try:
                shutil.copy(thumbnail_path + "/" + p.thumbnail, export_path + "/thumbnails/" + p.thumbnail)
            except FileNotFoundError:
                print(p.thumbnail, "not found ... skipping copy")



all_tags = []
for t in tagsjs:
    dump_json(tagsjs[t].get_dict(), export_path + "/tags/" + t + ".json")
    all_tags.append(tagsjs[t].get_ref())

dump_json(all_tags, export_path + "/tags/all-tags.json")

all_events = []
for event in events:
    dump_json(events[event].get_dict(), export_path + "events/" + event + ".json")
    all_events.append(events[event].get_ref())

dump_json(all_events, export_path + "/events/all-events.json")
