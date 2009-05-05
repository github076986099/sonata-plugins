# encoding: utf-8

# this is the magic interpreted by Sonata, referring to construct_tab below:

### BEGIN PLUGIN INFO
# [plugin]
# plugin_format: 0, 0
# name: Musicbrainz plugin
# version: 0, 0, 0
# description: A simple musicbrainz plugin that provides additional information for musicbrainz tagged files
# author: chrysn
# author_email: chrysn@fsfe.org
# url: non yet
# [capabilities]
# tabs: construct_tab
# playing_song_observers: on_song_change
# enablables: on_enable
### END PLUGIN INFO


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

############################################# real end of plugin info


import gtk

import logging
logging.root.setLevel(logging.INFO)

from weakref import ref as weakref

# not the ways sonata goes for, but more pythonic
import sexy
import webbrowser

# sonata imports
from sonata import misc

# up to now, no musicbrainz api used
import musicbrainz2.webservice as mb_ws
import musicbrainz2.utils as mb_u
import musicbrainz2.model as mb_mod

############################################# might even be useful in misc
class html(unicode):
    """just like a unicode object, but will escape all arguments to % formatting"""

    def __mod__(self, args):
        # FIXME: cover the case of single and dictionary argument
        args = tuple(misc.escape_html(x) for x in args)
        return unicode(self)%args

############################################# musicbrainz helpers
def get_hyperlink(o, label):
    label = label or (o.getTitle() if hasattr(o, 'getTitle') else o.getName())
    return html('<a href="%s.html">%s</a>')%(o.getId(), label)


############################################# the plugin
class MusicBrainzPlugin(object):
    # FIXME: plugin instance stuff does not work yet; there are many creations and no deletions!
    __singleton = staticmethod(lambda:None)

    ############################### initialization
    def __new__(cls):
        """Implement singleton behavior in a way that if every real reference
        to the instance is dropped (references through the class don't count
        and are implemented as weakrefs), the singleton is destroyed
        and re-created when neeed again"""
        if cls.__singleton() is None:
            r = super(cls, MusicBrainzPlugin).__new__(cls)
            cls.__singleton = weakref(r)
            return r
        return cls.__singleton()

    def __init__(self):
        logging.info('creating new MusicBrainzPLugin instance')
    def __del__(self):
        # finishing things off here is quite dangerous (would, for example, not
        # work if on_link_clicked was not a staticmethod).
        # having a proper close() method that also finished off the singleton
        # instance would make things easier, yet still leave the issue of
        # objects staying in memory longer than they need.
        logging.info('deleting MusicBrainzPLugin instance')

    ############################### hooks
    def construct_tab(self):
        vbox = gtk.VBox()
        self.label = sexy.UrlLabel()
        self.label.props.use_markup = True
        self.label.connect('url_activated', self.on_link_clicked)
        self.label.set_alignment(0, 0)
        # ... don't know what might be added here later
        vbox.pack_start(self.label, expand=False)
        vbox.show_all()

        # means new_tab(page, stock, text, focus)
        return (vbox, None, _("MusicBrainz"), None)
        # FIXME (here for first occurrence): sooner or later (rather later),
        # plugins will want to bring their own gettext translations; for now,
        # _(x) == x will be a sane default

    def on_song_change(self, songinfo):
        if songinfo:
            self.mb_data = self._extract_mb_data(songinfo)

            # help  in development
            logging.info("song changed")
            for k,v in sorted(songinfo.items()):
                logging.info("\t %s %r", k,v)
        else:
            self.mb_data = {}

        self._update_display()

    ############################### recurring events
    def _extract_mb_data(self, songinfo):
        """Store the musicbrainz data in the plugin object for easy access, set
        to None if not present"""

        self.current = {
                'album': songinfo.get('musicbrainz_albumid', None),
                'albumartist': songinfo.get('musicbrainz_albumartistid', None),
                'artist': songinfo.get('musicbrainz_artistid', None),
                'track': songinfo.get('musicbrainz_trackid', None), # FIXME: for regular songs, this is not passed from mpd. works for cue flac songs, though (tag is set in files' metadata, so it should work)
                }
        artist_inc = mb_ws.ArtistIncludes(urlRelations=True)
        release_inc = mb_ws.ReleaseIncludes(urlRelations=True)
        track_inc = mb_ws.TrackIncludes(urlRelations=True)
        # FIXME: this is blocking. either find a way to do this w/o blocking, or move into another thread.
        if self.current['album']:
            self.current['album'] = mb_ws.Query().getReleaseById(self.current['album'], release_inc)
        if self.current['track']:
            self.current['track'] = mb_ws.Query().getTrackById(self.current['track'], track_inc)
        if self.current['artist']:
            self.current['artist'] = mb_ws.Query().getArtistById(self.current['artist'], artist_inc)
        # FIXME: timeout issues when fetching "various artists" (increasing timeout would cause even longer ui lockup, cf last fixme)
        if self.current['albumartist']:
            if self.current['albumartist'] != '89ad4ac3-39f7-470e-963a-56509c546377': # exclude "various artists" for now
                self.current['albumartist'] = mb_ws.Query().getArtistById(self.current['albumartist'], artist_inc)
            else:
                self.current['albumartist'] = None

    relation_type2label = { # how relations should be displayed
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
            u'http://musicbrainz.org/ns/rel-1.0#OnlineCommunity': _('online community'), # FIXME: give more detailed information in link
            u'http://musicbrainz.org/ns/rel-1.0#Blog': _('blog'),
            # cummulative FIXME:
            # * for non-1:1 relations, there's a need for more detailed display
            #   (have seen numerous fan pages, they should go by url in an own
            #   section)
            # * didn't find a comprehensive list, that's what showed up when
            #   going through parts of my music
           }

    def _update_display(self):
        """Show information about `current` song in the tab"""
        current = self.current.copy()
        if current['albumartist'] and current['artist'] and current['albumartist'].getId() == current['artist'].getId():
            current['bothartist'] = current['albumartist']
            del current['albumartist']
            del current['artist']

        infos = []
        for key, label in [
                ('album', _('Album')),
                ('albumartist', _('Album artist')),
                ('bothartist', _('Artist, album artist')),
                ('artist', _('Artist')),
                ('track', _('Track')),
                ]:
            if key in current and current[key]:
                current_name = current[key].getTitle() if hasattr(current[key], 'getTitle') else current[key].getName()

                links = [get_hyperlink(current[key], _('MusicBrainz'))]
                logging.info("Got %d relations for %s", len(current[key].getRelations()), key)
                for rel in current[key].getRelations():
                    logging.debug(vars(rel))
                    if rel.getType() in self.relation_type2label:
                        links.append(html('<a href="%s">%s</a>')%(rel.getTargetId(), self.relation_type2label[rel.getType()]))
                    else:
                        links.append(html(u"%s → %s"%(rel.getType(), rel.getTargetId())))

                infos.append(html('<b>%s:</b> %s')%(label, current_name) + ' <small>(%s)</small>'%(", ".join(links),))

        self.label.set_markup('\n'.join(infos))

    @staticmethod
    def on_link_clicked(widget, url):
        webbrowser.open(url)


def construct_tab():
    logging.info('construct_tab called')
    return MusicBrainzPlugin().construct_tab()

def on_song_change(songinfo):
    logging.info('on_song_change called, %r', songinfo)
    return MusicBrainzPlugin().on_song_change(songinfo)

plugin_instance = None

def on_enable(state):
    # make sure the plugin instance is persistent as long as the plugin is
    # loaded
    global plugin_instance
    if state == True:
        logging.info("the MusicBrainzPlugin should report creation of a new instance and no destruction")
        plugin_instance = MusicBrainzPlugin()
    else:
        logging.info("now the MusicBrainzPlugin should report its destruction")
        plugin_instance = None
        logging.info("did it?")
