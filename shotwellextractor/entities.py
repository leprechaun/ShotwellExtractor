#!/usr/bin/env python3

from sqlalchemy import Table, MetaData, Column, ForeignKey, Integer, String
from sqlalchemy.orm import mapper
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import relationship

from sqlalchemy import event

import os.path
import datetime
import urllib.parse

Base = declarative_base()

class Photo(Base):
    __tablename__ = "phototable"

    id = Column(Integer, primary_key=True)
    filename = Column(String)
    width = Column(Integer)
    height = Column(Integer)
    filesize = Column(Integer)
    exposure_time = Column(Integer)
    timestamp = Column(Integer)
    orientation = Column(Integer)
    original_orientation = Column(Integer)
    import_id = Column(Integer)
    event_id = Column(Integer)
    transformations = Column(String)
    md5 = Column(String)
    thumbnail_md5 = Column(String)
    exif_md5 = Column(String)
    time_created = Column(Integer)
    flags = Column(Integer)
    rating = Column(Integer)
    file_format = Column(Integer)
    title = Column(String)
    backlinks = Column(String)
    time_reimported = Column(Integer)
    editable_id = Column(Integer)
    metadata_dirty = Column(Integer)
    developer = Column(String)
    develop_shotwell_id = Column(Integer)
    develop_camera_id = Column(Integer)
    develop_embedded_id = Column(Integer)
    comment = Column(String)

    @property
    def path(self):
        return self.filename.lstrip("/home/leprechaun/Pictures")

    @property
    def datetime(self):
        if self.exposure_time is not None:
            dt = self.exposure_time
        else:
            dt = self.time_created

        dt = datetime.datetime.fromtimestamp(int(dt)).strftime('%Y-%m-%d %H:%M:%S')
        return dt

    @property
    def date(self):
        if self.exposure_time is not None:
            dt = self.exposure_time
        else:
            dt = self.time_created

        dt = datetime.datetime.fromtimestamp(int(dt)).strftime('%Y-%m-%d')
        return dt

    @property
    def thumbnail(self):
        id = str(hex(self.id)).lstrip("0x")
        # thumb0000000000000a0c
        return "thumb" + id.rjust(16, "0") + ".jpg"

    def __repr__(self):
        return "<Photo(#%s '%s')>" % (self.id, self.filename)

class Event(Base):
    __tablename__ = "eventtable"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    primary_photo_id = Column(String)
    time_created = Column(Integer)
    primary_source_id = Column(String)
    comment = Column(String)

    @property
    def primary_source_translated(self):
        t = str(self.primary_source_id)
        t = t.ltrim("thumb").ltrim("0")
        return int(t, 16)


class Tag(Base):
    __tablename__ = "tagtable"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    photo_id_list = Column(String)
    time_created = Column(Integer)

    @property
    def photo_list(self):
        if self.photo_id_list is None:
            return []

        l = self.photo_id_list.split(",")
        # last is always empty
        l.pop()

        # strip "thumb" out and we've got hex left
        l = [id[5:] for id in l]
        l = [int(id.lstrip("0"),16) for id in l]
        return l

    @photo_list.setter
    def photo_list(self, photo_list):
        self.photo_id_list = ",".join(photo_list)

    def __repr__(self):
        return "<Tag(#%s '%s')>" % (self.id, self.name)
