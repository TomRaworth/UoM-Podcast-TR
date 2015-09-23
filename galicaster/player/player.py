# -*- coding:utf-8 -*-
# Galicaster, Multistream Recorder and Player
#
#       galicaster/player/player
#
# Copyright (c) 2011, Teltek Video Research <galicaster@teltek.es>
#
# This work is licensed under the Creative Commons Attribution-
# NonCommercial-ShareAlike 3.0 Unported License. To view a copy of 
# this license, visit http://creativecommons.org/licenses/by-nc-sa/3.0/ 
# or send a letter to Creative Commons, 171 Second Street, Suite 300, 
# San Francisco, California, 94105, USA.
#
#   pipestr = ( ' filesrc location=video1 ! decodebin name=audio ! queue ! xvimagesink name=play1 '
#               ' filesrc location=video2 ! decodebin ! queue ! xvimagesink name=play2 ' 
#               ' audio. ! queue ! level name=VUMETER message=true interval=interval ! autoaudiosink name=play3 ')
#
#

import gi
from gi.repository import Gtk, Gst, Gdk
# Needed for window.get_xid(), xvimagesink.set_window_handle(), respectively:
from gi.repository import GdkX11, GstVideo

import os

#from galicaster.core import context
from galicaster.utils.gstreamer import WeakMethod
from galicaster.utils.mediainfo import get_duration

#logger = context.get_logger()

class Player(object):

    def __init__(self, files, players = {}):
        """
        Initialize the player
        This class is event-based and needs a mainloop to work properly.

        :param files: a ``dict`` a file name list to play
        :param players: a ``dict`` a Gtk.DrawingArea list to use as player
        """
        #FIXME comprobar que existen los files sino excepcion
        if not isinstance(files, dict):
            raise TypeError(
                '%s: need a %r; got a %r: %r' % ('files', dict, type(files), files)
            )
        #FIXME check the values are Gtk.DrawingArea
        if not isinstance(players, dict):
            raise TypeError(
                '%s: need a %r; got a %r: %r' % ('players', dict, type(players), players)
            )

        #self.dispatcher = context.get_dispatcher() 
        self.files = files
        self.players = players
        self.duration = 0
        self.has_audio = False
        self.pipeline_complete = False
        self.audio_sink = None

        self.__get_duration_and_run()


    def create_pipeline(self):
        self.pipeline = Gst.Pipeline.new("galicaster_player")
        bus = self.pipeline.get_bus()

        # Create bus and connect several handlers
        bus.add_signal_watch()
        bus.enable_sync_message_emission()
        bus.connect('message::eos', WeakMethod(self, '_on_eos'))
        bus.connect('message::error', WeakMethod(self, '_on_error'))
        bus.connect('message::element', WeakMethod(self, '_on_message_element'))
        bus.connect('message::state-changed', WeakMethod(self, '_on_state_changed'))
        bus.connect('sync-message::element', WeakMethod(self, '_on_sync_message'))

        # Create elements
        for name, location in self.files.iteritems():
            logger.info('playing %r', location)
            src = Gst.ElementFactory.make('filesrc', 'src-' + name)
            src.set_property('location', location)
            dec = Gst.ElementFactory.make('decodebin', 'decode-' + name)
            
            # Connect handler for 'pad-added' signal
            dec.connect('pad-added', WeakMethod(self, '_on_new_decoded_pad'))
            
            # Link elements
            self.pipeline.add(src)
            self.pipeline.add(dec)
            src.link(dec)

        return None


    def get_status(self):
        """
        Get the player status
        """
        return self.pipeline.get_state(Gst.CLOCK_TIME_NONE)


    def is_playing(self):
        """
        Get True if is playing else False
        """
        return (self.pipeline.get_state(Gst.CLOCK_TIME_NONE)[1] == Gst.State.PLAYING)


    def get_time(self):
        """
        Get the player current time.
        """
        return self.pipeline.get_clock().get_time()


    def play(self):
        """
        Start to play
        """
        #logger.debug("player playing")
        if not self.pipeline_complete:
            self.pipeline.set_state(Gst.State.PAUSED)
            self.pipeline_complete = True
        else:
            self.pipeline.set_state(Gst.State.PLAYING)
        return None


    def pause(self):
        """
        Pause the player
        """
        #logger.debug("player paused")
        self.pipeline.set_state(Gst.State.PAUSED)
        self.pipeline.get_state(Gst.CLOCK_TIME_NONE)


    def stop(self):
        """
        Stop the player

        Pause the reproduction and seek to begin
        """
        #logger.debug("player stoped")
        self.pipeline.set_state(Gst.State.PAUSED)
        self.seek(0) 
        self.pipeline.get_state(Gst.CLOCK_TIME_NONE)
        return None


    def quit(self):
        """
        Close the pipeline
        """
        #logger.debug("player deleted")
        self.pipeline.set_state(Gst.State.NULL)
        self.pipeline.get_state(Gst.CLOCK_TIME_NONE)
        return None


    def seek(self, pos, recover_state=False):
        """
        Seek the player

        param: pos time in nanoseconds
        """
        result = self.pipeline.seek(1.0, 
            Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.ACCURATE, # REVIEW sure about ACCURATE
            Gst.SeekType.SET, pos, 
            Gst.SeekType.NONE, -1) 
        if recover_state and self.pipeline.get_state(Gst.CLOCK_TIME_NONE)[1] == Gst.State.PAUSED:
            self.pipeline.set_state(Gst.State.PLAYING)
        return result


    def get_duration(self):       
        return self.duration


    def get_position(self, format=Gst.Format.TIME):
        return self.pipeline.query_position(format)


    def get_volume(self):
        if self.audio_sink == None:
            return 100
        return self.audio_sink.get_property('volume')


    def set_volume(self, volume):
        if self.audio_sink != None:
            self.audio_sink.set_property('volume', volume)
	
    def _on_state_changed(self, bus, message):
        old, new, pending = message.parse_state_changed()
        if (isinstance(message.src, Gst.Pipeline) and 
            (old, new) == (Gst.State.READY, Gst.State.PAUSED) ):
            self.pipeline.set_state(Gst.State.PLAYING)

    def _on_new_decoded_pad(self, element, pad):         
        name = pad.query_caps(None).to_string()
        element_name = element.get_name()[7:]
        #logger.debug('new decoded pad: %r in %r', name, element_name)
        sink = None

        if name.startswith('audio/'):
            #if element_name == 'presenter' or len(self.files) == 1:
            if not self.has_audio:
                self.has_audio = True
                self.audio_sink = Gst.ElementFactory.make('autoaudiosink', 'audio')
                vumeter = Gst.ElementFactory.make('level', 'level') 
                vumeter.set_property('message', True)
                vumeter.set_property('interval', 100000000) # 100 ms
                self.pipeline.add(self.audio_sink)
                self.pipeline.add(vumeter)
                pad.link(vumeter.get_static_pad('sink'))
                vumeter.link(self.audio_sink)
                vumeter.set_state(Gst.State.PAUSED)
                assert self.audio_sink.set_state(Gst.State.PAUSED)
                
        elif name.startswith('video/'):
            vconvert = Gst.ElementFactory.make('videoconvert', 'vconvert-' + element_name)
            self.pipeline.add(vconvert)

            sink = Gst.ElementFactory.make('xvimagesink', 'sink-' + element_name) 
            sink.set_property('force-aspect-ratio', True)
            self.pipeline.add(sink)

            pad.link(vconvert.get_static_pad('sink'))
            vconvert.link(sink)
            vconvert.set_state(Gst.State.PAUSED)
            
            assert sink.set_state(Gst.State.PAUSED)
            
        return sink


    def _on_eos(self, bus, msg):
        #logger.info('Player EOS')
        self.stop()
        #self.dispatcher.emit("play-stopped")


    def _on_error(self, bus, msg):
        error = msg.parse_error()[1]
        #logger.error(error)
        self.stop()


    def _on_sync_message(self, bus, message):
        if message.get_structure() is None:
            return
        if message.get_structure().get_name() == 'prepare-window-handle':
            name = message.src.get_property('name')[5:]

            #logger.debug("on sync message 'prepare-window-handle' %r", name)

            try:
                gtk_player = self.players[name]
                if not isinstance(gtk_player, Gtk.DrawingArea):
                    raise TypeError()
                Gdk.threads_enter()
                Gdk.Display.get_default().sync()
                message.src.set_window_handle(gtk_player.get_property('window').get_xid())
                message.src.set_property('force-aspect-ratio', True)
                Gdk.threads_leave()

            except TypeError:
                pass
                #logger.error('players[%r]: need a %r; got a %r: %r' % (
                #        name, Gtk.DrawingArea, type(gtk_player), gtk_player))
            except KeyError:
                pass


    def _on_message_element(self, bus, message):
        if message.get_structure().get_name() == 'level':
            self.__set_vumeter(message)


    def __set_vumeter(self, message):
        struct = message.get_structure()
        
        if  float(struct.get_value('rms')[0]) == float("-inf"):
            valor = "Inf"
        else:            
            valor = float(struct.get_value('rms')[0])
        self.dispatcher.emit("update-play-vumeter", valor)


    def __discover(self, filepath):
        self.duration = get_duration(filepath) 
        #logger.info("Duration ON_DISCOVERED: " + str(self.duration))        
        self.create_pipeline()
        return True


    def __get_duration_and_run(self):
        # choose lighter file
        size = location = None
        for key,value in self.files.iteritems():
            new = os.path.getsize(value)
            if not size or new > size:
                location = value
        return self.__discover(location)
