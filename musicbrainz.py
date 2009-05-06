# encoding: utf-8

from __future__ import with_statement

### BEGIN PLUGIN INFO
# [plugin]
# plugin_format: 0, 0
# name: Musicbrainz plugin
# version: 0, 0, 1
# description: A simple musicbrainz plugin that provides additional information for musicbrainz tagged files
# author: chrysn
# author_email: chrysn@fsfe.org
## url: non yet
# [capabilities]
# tabs: MusicBrainzPlugin.hook_construct_tab
# playing_song_observers: MusicBrainzPlugin.hook_song_change
# enablables: MusicBrainzPlugin.hook_enablables
# lyrics_fetching: MusicBrainzPlugin.hook_lyrics_fetching
### END PLUGIN INFO


############################################# general blah blah
#
# Version history:
# 0.0.1: first usable (because non-blocking) version
__version__ = "0.0.1"
#
#
# Points that need to be fixed for future releases:
#  * have caching for MusicBrainz metadata
#  * enhance display of fan page, Wikipedia and online communities (there can
#    be more than one and additional information is required)
#  * use Amazon ASIN to reliably identify the cover image
#  * use MusicBrainz track id to uniquely identify lyrics
#  * offer creating the required information from the current (guessed)
#    implementation if the user decides that the guess is correct
#
# License:
#   Copyright (C) 2009 chrysn <chrysn@fsfe.org>
__author__ = "chrysn <chrysn@fsfe.org>"
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
__licence__ = "GPLv3+"
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.



############################################# a suggestion for the plugin framework

# maybe we should not have capabilities, but just specify the
# class name like:

## [plugin]
## plugin_format: 0, 0
## url: ...
## class: MusicBrainzPlugin
#
#import sonata.plugin
#
#class MusicBrainzPlugin(sonata.plugin.TabConstructor, sonata.plugin.OnSongChange):
#    def construct_tabs(self, ...):
#        return [(a,b,c,d), (e,f,g,h)]

# the TabConstructor etc would work like interfaces (python3: ABCs), which
# define well known method calls like construct_tabs


############################################# code starts here

import threading
import gtk

import logging
logging.root.setLevel(logging.INFO)

# not the ways sonata goes for, but more pythonic
import sexy
import webbrowser

# sonata imports
from sonata import misc

# musicbrainz
import musicbrainz2.webservice as mb_ws
import musicbrainz2.utils as mb_u
import musicbrainz2.model as mb_mod

# my preferred way of developing plugins
from plugin_class import Plugin


############################################# might even be useful in misc
class html(unicode):
    """just like a unicode object, but will escape all arguments to %
    formatting (except if they are html themselves) or .join()."""

    @classmethod
    def __escape(cls, item):
        if isinstance(item, cls):
            # these are not the bad characters you are looking for.
            return item
        else:
            return misc.escape_html(item)

    def __mod__(self, args):
        if isinstance(args, tuple):
            args = tuple(map(self.__escape, args))
        elif isinstance(args, dict):
            args = dict((k, self.__escape(v)) for (k,v) in args.iteritems())
        else:
            args = self.__escape(args)
        return html(unicode(self)%args)

    def join(self, chunks):
        return html(unicode.join(self, map(self.__escape, chunks)))

    def __repr__(self):
        return u'html(%s)'%unicode.__repr__(self)

############################################# musicbrainz helpers
def get_hyperlink(o, label):
    label = label or (o.getTitle() if hasattr(o, 'getTitle') else o.getName())
    return html('<a href="%s.html">%s</a>')%(o.getId(), label)


############################################# the tab
class MusicBrainzDisplay(gtk.VBox):
    """GTK widget for inclusion in a tab. Should not be bothered with sonata
    internals or sonata plugin API issues. Will happily work together with what
    the musicbrainz API provides."""

    # define how relations should be displayed
    relation_type2label = {
            u'http://musicbrainz.org/ns/rel-1.0#Discogs': _('Discogs'),
            u'http://musicbrainz.org/ns/rel-1.0#IMDb': _('IMDb'),
            u'http://musicbrainz.org/ns/rel-1.0#AmazonAsin': _('Amazon'), # FIXME: albums w/ two asins should have a better ui for that
            u'http://musicbrainz.org/ns/rel-1.0#Wikipedia': _('Wikipedia'), # FIXME: show language in link
            u'http://musicbrainz.org/ns/rel-1.0#OfficialHomepage': _('home page'),
            u'http://musicbrainz.org/ns/rel-1.0#Fanpage': _('fan page'), # FIXME: can be many
            u'http://musicbrainz.org/ns/rel-1.0#Myspace': _('myspace'),
            u'http://musicbrainz.org/ns/rel-1.0#DownloadForFree': _('download for free'), # useless for this song, but there might be more
            u'http://musicbrainz.org/ns/rel-1.0#PurchaseForDownload': _('purchase'),
            u'http://musicbrainz.org/ns/rel-1.0#Musicmoz': _('MusicMoz'),
            u'http://musicbrainz.org/ns/rel-1.0#Discography': _('discography'),
            u'http://musicbrainz.org/ns/rel-1.0#Review': _('review'),
            u'http://musicbrainz.org/ns/rel-1.0#Youtube': _('youtube'),
            u'http://musicbrainz.org/ns/rel-1.0#OnlineCommunity': _('online community'), # FIXME: give more detailed information in link (stripped version of url)
            u'http://musicbrainz.org/ns/rel-1.0#Blog': _('blog'),
            # cummulative FIXME:
            # * for non-1:1 relations, there's a need for more detailed display
            #   (have seen numerous fan pages, they should go by url in an own
            #   section)
            # * didn't find a comprehensive list, that's what showed up when
            #   going through parts of my music
            # * (here for first occurrence): sooner or later (rather later),
            #   plugins will want to bring their own gettext translations; for
            #   now, _(x) == x will be a sane default
           }

    def __init__(self):
        super(MusicBrainzDisplay, self).__init__()

        self.label = sexy.UrlLabel()
        self.label.props.use_markup = True
        self.label.connect('url_activated', self.on_link_clicked)
        self.label.set_alignment(0, 0)

        self.pack_start(self.label, expand=False)

    def set_fetching(self):
        self.label.set_markup(_("Fetching musicbrainz data..."))

    def set_empty(self):
        self.label.set_markup(_("No current song."))

    def set_data(self, mb_data):
        # will manipulate data
        mb_data = mb_data.copy()

        # don't show duplicate information about artist and album artist
        if 'albumartist' in mb_data and 'artist' in mb_data and mb_data['albumartist'].getId() == mb_data['artist'].getId():
            mb_data['bothartist'] = mb_data['albumartist']
            del mb_data['albumartist']
            del mb_data['artist']

        infos = []
        for key, label in [
                ('album', _('Album')),
                ('albumartist', _('Album artist')),
                ('bothartist', _('Artist, album artist')),
                ('artist', _('Artist')),
                ('track', _('Track')),
                ]:
            if key in mb_data:
                current_name = mb_data[key].getTitle() if hasattr(mb_data[key], 'getTitle') else mb_data[key].getName() # function name differs for tracks / releases / artists

                links = [get_hyperlink(mb_data[key], _('MusicBrainz'))]
                logging.info("Got %d relations for %s", len(mb_data[key].getRelations()), key)
                for rel in mb_data[key].getRelations():
                    logging.debug(vars(rel))
                    if rel.getType() in self.relation_type2label:
                        links.append(html('<a href="%s">%s</a>')%(rel.getTargetId(), self.relation_type2label[rel.getType()]))
                    else:
                        links.append(html(u"%s → %s")%(rel.getType(), rel.getTargetId()))
                        logging.warning("No information on how to display relations of type %r", rel.getType())

                link_html = html(", ").join(links)

                infos.append(html('<b>%s:</b> %s <small>(%s)</small>')%(label, current_name, link_html))

        self.label.set_markup('\n'.join(infos))

    @staticmethod
    def on_link_clicked(widget, url):
        webbrowser.open(url)

############################################# the thread fetching the data
class MusicBrainzDownloadThread(threading.Thread):
    # FIXME: this is a single use run once thread created once per fetching
    # data. ideally, there should be one thread doing all the work as long as
    # the plugin is loaded
    def __init__(self, songinfo, display, lock):
        self.songinfo = songinfo
        self.display = display
        self.lock = lock
        super(MusicBrainzDownloadThread, self).__init__()
        self.daemon = True # not needed any more when sonata quits

        self.die = False # this will be set to True from outside if the thread has been running for too long

    def run(self):
        mb_data = self.extract_mb_data(self.songinfo)

        with self.lock:
            if self.die:
                logging.warning("Received data from musicbrainz, but the plugin does not want them any more.")
                return

            self.display.set_data(mb_data)

    @staticmethod
    def extract_mb_data(songinfo): # this just happens to be executed inside a thread, nothing threading specific here
        ids = {
                'album': songinfo.get('musicbrainz_albumid', None),
                'albumartist': songinfo.get('musicbrainz_albumartistid', None),
                'artist': songinfo.get('musicbrainz_artistid', None),
                'track': songinfo.get('musicbrainz_trackid', None), # for mp3, starts working after mpd bug #2324 is fixed; after 0.15beta1
                }

        # mb library: take all urls you can get
        artist_inc = mb_ws.ArtistIncludes(urlRelations=True)
        release_inc = mb_ws.ReleaseIncludes(urlRelations=True)
        track_inc = mb_ws.TrackIncludes(urlRelations=True)

        mb_data = {}

        # FIXME: Do this in parallel or even better in one query.
        if ids['album']:
            mb_data['album'] = mb_ws.Query().getReleaseById(ids['album'], release_inc)
        if ids['track']:
            mb_data['track'] = mb_ws.Query().getTrackById(ids['track'], track_inc)
        if ids['artist']:
            mb_data['artist'] = mb_ws.Query().getArtistById(ids['artist'], artist_inc)
        if ids['albumartist']:
            # FIXME: timeout issues when fetching "various artists"
            if ids['albumartist'] != '89ad4ac3-39f7-470e-963a-56509c546377': # exclude "various artists" for now
                mb_data['albumartist'] = mb_ws.Query().getArtistById(ids['albumartist'], artist_inc)

        return mb_data

############################################# the plugin
class MusicBrainzPlugin(Plugin):
    ############################### object maintenance

    def __init__(self):
        # download threads have to acquire this for checking if they should
        # really update the display (or just die) and updating the display.
        self.fetcher_lock = threading.Lock()

        # this variable makes sure the plugin knows which thread (there can
        # only be one) to tell to just die instead of setting the display
        # before a new thread is created. the lock prevents a situation in
        # which a thread checks that it does not need to die, and much later
        # (after a new thread has been created and possibly started setting
        # data itself) overwrite the display.
        self.fetcher_thread = None

    def __del__(self):
        # when the plugin_class framework finally admits failure to guarantee
        # __del__etion, rename this to close
        self._close_fetcher_thread()

    def _close_fetcher_thread(self):
        if self.fetcher_thread is not None:
            self.fetcher_thread.die = True # instead of updating the display, just die. i would immediately raise a YouAreUselessNow exception in the thread if i knew how to do that.
            del self.fetcher_thread.display # the thread is supposed not to access it any more anyway, and another reference is freed, which is good i suppose
            self.fetcher_thread = None

    ############################### hooks
    def on_construct_tab(self):
        self.display = MusicBrainzDisplay()
        self.display.show_all()

        # means new_tab(page, stock, text, focus)
        return (self.display, None, _("MusicBrainz"), None)

    def on_song_change(self, songinfo):
        self._close_fetcher_thread()

        if songinfo:
            self.display.set_fetching()

            self.fetcher_thread = MusicBrainzDownloadThread(songinfo, self.display, self.fetcher_lock)
            self.fetcher_thread.start()
            # songs will be fetched in background now
        else:
            self.display.set_empty()

    def on_lyrics_fetching(self, callback, artist, title):
        logging.info("on lyrics fetching, %r"%((callback,artist,title),))
        callback(None, "bad data, i want songinfo!")
