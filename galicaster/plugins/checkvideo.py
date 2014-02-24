# -*- coding:utf-8 -*-
# Galicaster, Multistream Recorder and Player
#
#       galicaster/plugins/checkvideo
#
# Copyright (c) 2012, Teltek Video Research <galicaster@teltek.es>
#
# This work is licensed under the Creative Commons Attribution-
# NonCommercial-ShareAlike 3.0 Unported License. To view a copy of 
# this license, visit http://creativecommons.org/licenses/by-nc-sa/3.0/ 
# or send a letter to Creative Commons, 171 Second Street, Suite 300, 
# San Francisco, California, 94105, USA.

"""This plugin checks repository mediapackages for a valid video file. An empty video file can be generated
if there is not presentation and the video source has gone to 'sleep'"""

import datetime
import os
import shutil

from galicaster.core import context
from galicaster.mediapackage import mediapackage
from galicaster.classui import get_video_path

logger = context.get_logger()
worker = context.get_worker()
conf = context.get_conf()

INVALID_VIDEO_FILE_SIZE = 10240
EMPTY_AVI_VIDEO_FILE_SIZE = 792
EMPTY_MP4_VIDEO_FILE_SIZE = 473

PLACEHOLDER_VIDEO_FILE = "no_video320x180.mp4"
PLACEHOLDER_VIDEO_FILE_MIMETYPE = 'video/mp4'

def init():	
    try:
        dispatcher = context.get_dispatcher()
        dispatcher.connect('recording-closed', check_video)  

    except ValueError:
	pass

def check_video(self, mpUri):
    minvideosize = {
      'video/avi' : EMPTY_AVI_VIDEO_FILE_SIZE,
      'video/msvideo' : EMPTY_AVI_VIDEO_FILE_SIZE,
      'video/mp4' : EMPTY_MP4_VIDEO_FILE_SIZE,
      'default' : INVALID_VIDEO_FILE_SIZE
    }
    flavour = 'presentation/source'
    mp_list = context.get_repository()
    for uid,mp in mp_list.iteritems():
        if (mp.getURI() == mpUri) :
            #logger.info("Found MP")
            for t in mp.getTracks(flavour):
                mimetype = t.getMimeType()
                #logger.info("Examine track type %s", mimetype)
                if (mimetype.split('/')[0].lower() == 'video') :
                    #logger.info("Found video track %s",t.getURI())
                    if mimetype not in minvideosize :
                        mimetype = 'default'
                    finfo = os.stat(t.getURI())
                    if (finfo.st_size <= minvideosize[mimetype]) :
                        logger.info("Filesize invalid, %dbytes", finfo.st_size)
                        mp.remove(t)
                        ext = PLACEHOLDER_VIDEO_FILE.split('.')[1].lower();
                        filename = 'presentation.' + ext
                        dest = os.path.join(mpUri, os.path.basename(filename))
                        logger.info("Copying %s to %s", get_video_path(PLACEHOLDER_VIDEO_FILE), dest)
                        shutil.copyfile(get_video_path(PLACEHOLDER_VIDEO_FILE), dest)
                        mp.add(dest, mediapackage.TYPE_TRACK, flavour, PLACEHOLDER_VIDEO_FILE_MIMETYPE, mp.getDuration()) # FIXME MIMETYPE
                        mp_list.update(mp)
                        logger.info("Replaced empty video file with placeholder UID:%s - URI: %s", uid, mpUri)
  