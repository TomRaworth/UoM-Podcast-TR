# -*- coding:utf-8 -*-
# Galicaster, Multistream Recorder and Player
#
#       galicaster/utils/sidebyside
#
# Copyright (c) 2011, Teltek Video Research <galicaster@teltek.es>
#
# This work is licensed under the Creative Commons Attribution-
# NonCommercial-ShareAlike 3.0 Unported License. To view a copy of 
# this license, visit http://creativecommons.org/licenses/by-nc-sa/3.0/ 
# or send a letter to Creative Commons, 171 Second Street, Suite 300, 
# San Francisco, California, 94105, USA.

# TODO:
#  - Add background picture to mixer.

from os import path

from gi.repository import Gst
Gst.init(None)

layouts = {'sbs': 
           {'screen_width': 640, 'screen_height': 480, 'screen_aspect': '4/3', 'screen_xpos': 640,'screen_ypos': 120, 'screen_zorder': 0, 
            'camera_width': 640, 'camera_height': 480, 'camera_aspect': '4/3', 'camera_xpos': 0, 'camera_ypos': 120, 'camera_zorder': 0, 
            'out_width': 1280, 'out_height': 720},
           'pip_screen': 
           {'screen_width': 160, 'screen_height': 120, 'screen_aspect': '4/3', 'screen_xpos': 640,'screen_ypos': 480, 'screen_zorder': 1, 
            'camera_width': 800, 'camera_height': 600, 'camera_aspect': '4/3', 'camera_xpos': 0, 'camera_ypos': 0, 'camera_zorder': 0, 
            'out_width': 800, 'out_height': 600},
           'pip_camera': 
           {'screen_width': 800, 'screen_height': 600, 'screen_aspect': '4/3', 'screen_xpos': 0,'screen_ypos': 0, 'screen_zorder': 0, 
            'camera_width': 160, 'camera_height': 120, 'camera_aspect': '4/3', 'camera_xpos': 640, 'camera_ypos': 480, 'camera_zorder': 1, 
            'out_width': 800, 'out_height': 600},}

def create_sbs(out, camera, screen, audio=None, layout='sbs', logger=None):
    """
    Side By Side creator
    
    :param out: output file path
    :param camera: camera video file path
    :param screen: screen video file path 
    :param audio: audio file path or "screen" o "camera" string to re-use files
    """

    pipestr = """
    videomixer name=mix 
        sink_0::xpos=0 sink_0::ypos=0 sink_0::zorder=0
        sink_1::xpos=640 sink_1::ypos=120 sink_1::zorder=1 !
    videoconvert name=colorsp_saida ! 
    x264enc quantizer=45 speed-preset=6 ! queue ! 
    mp4mux name=mux  ! queue ! filesink location="{OUT}"

    filesrc location="{SCREEN}" ! decodebin name=dbscreen ! deinterlace ! 
    aspectratiocrop aspect-ratio={screen_aspect} ! videoscale ! videorate !
    videoconvert name=colorsp_screen !
    video/x-raw,width=640,height=480,framerate=25/1,pixel-aspect-ratio=1/1,interlace-mode=progressive !
    videobox right=-640 top=-120 bottom=-120 ! queue !
    mix.sink_0 

    filesrc location="{CAMERA}" ! decodebin name=dbcamera ! deinterlace ! 
    aspectratiocrop aspect-ratio={camera_aspect} ! videoscale ! videorate !
    videoconvert name=colorsp_camera !
    video/x-raw,width=640,height=480,framerate=25/1,pixel-aspect-ratio=1/1,interlace-mode=progressive ! queue !
    mix.sink_1 
    """

    pipestr_audio = """
    db{SRC}. ! audioconvert ! queue ! voaacenc bitrate=128000 ! queue ! mux. 
    """

    pipestr_audio_file = """
    filesrc location="{AUDIO}" ! decodebin name=dbaudio ! 
    audioconvert ! queue ! voaacenc bitrate=128000 ! queue ! mux.
    """

    if not layout in layouts:
        if logger:
            logger.error('Layout not exists')
        raise IOError, 'Error in SideBySide proccess'

    if not camera or not screen:
        if logger:
            logger.error('SideBySide Error: Two videos needed')
        raise IOError, 'Error in SideBySide proccess'

    for track in [camera, screen, audio]:    
        if track and not path.isfile(camera):
            if logger:
                logger.error('SideBySide Error: Not  a valid file %s', track)
            raise IOError, 'Error in SideBySide proccess'

    embeded = False
    if audio:
        pipestr = "".join((pipestr, pipestr_audio_file.format(AUDIO=audio)))
        if logger:
            logger.debug('Audio track detected: %s', audio)
    else:
        if logger:
            logger.debug('Audio embeded')
        embeded = True

    parameters = {'OUT': out, 'SCREEN': screen, 'CAMERA': camera}
    parameters.update(layouts[layout])

    pipeline = Gst.parse_launch(pipestr.format(**parameters))
    bus = pipeline.get_bus()

    # connect callback to fetch the audio stream
    if embeded:
        mux = pipeline.get_by_name('mux')    
        dec_camera = pipeline.get_by_name('dbcamera')
        dec_screen = pipeline.get_by_name('dbscreen')    
        dec_camera.connect('pad-added', on_audio_decoded, pipeline, mux)
        dec_screen.connect('pad-added', on_audio_decoded, pipeline, mux)


    pipeline.set_state(Gst.State.PLAYING)
    msg = bus.timed_pop_filtered(Gst.CLOCK_TIME_NONE, Gst.MessageType.ERROR | Gst.MessageType.EOS)
    pipeline.set_state(Gst.State.NULL)
    
    if msg.type == Gst.MessageType.ERROR:
        err, debug = msg.parse_error()
        if logger:
            logger.error('SideBySide Error: %s', err)
        raise IOError, 'Error in SideBySide proccess'

    return True
    

def on_audio_decoded(element, pad, bin, muxer):
    name = pad.query_caps(None).to_string()
    element_name = element.get_name()[:8]
    sink = None

    # only one audio will be muxed
    created=bin.get_by_name('sbs-audio-convert')
    pending = False if created else True

    if name.startswith('audio/x-raw') and pending:
        # db%. audioconvert ! queue ! faac bitrate = 12800 ! queue ! mux.
        convert = Gst.ElementFactory.make('audioconvert', 'sbs-audio-convert-{0}'.format(element_name))
        q1 = Gst.ElementFactory.make('queue','sbs-audio-queue-{0}'.format(element_name))
        f = Gst.ElementFactory.make('voaacenc','sbs-audio-encoder-{0}'.format(element_name))
        f.set_property('bitrate',128000)
        q2 = Gst.ElementFactory.make('queue','sbs-audio-queue2-{0}'.format(element_name))

        #link
        bin.add(convert)
        bin.add(q1)
        bin.add(f)
        bin.add(q2)
        convert.link(q1)
        q1.link(f)
        f.link(q2)
        q2.link(muxer)
        #keep activating
        convert.set_state(Gst.State.PLAYING)
        q1.set_state(Gst.State.PLAYING)
        f.set_state(Gst.State.PLAYING)
        q2.set_state(Gst.State.PLAYING)
        pad.link(convert.get_static_pad('sink'))

    return sink

    

