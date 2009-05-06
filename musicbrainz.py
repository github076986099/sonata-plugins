# encoding: utf-8

### BEGIN PLUGIN INFO
# [plugin]
# plugin_format: 0, 0
# name: Musicbrainz plugin
# version: 0, 0, 0
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

############################################# the plugin
class MusicBrainzPlugin(Plugin):
    ############################### object maintenance (for now, only logging. might do things like opening and closing the musicbrainz cache once there is one)

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
    def on_construct_tab(self):
        logging.info('construct_tab called')

        self.display = MusicBrainzDisplay()
        self.display.show_all()

        # means new_tab(page, stock, text, focus)
        return (self.display, None, _("MusicBrainz"), None)

    def on_song_change(self, songinfo):
        if songinfo:
            self.display.set_fetching()
            mb_data = self._extract_mb_data(songinfo)
            self.display.set_data(mb_data)
        else:
            self.display.set_empty()

    def on_lyrics_fetching(self, callback, artist, title):
        logging.info("on lyrics fetching, %r"%((callback,artist,title),))
        callback(None, "bad data, i want songinfo!")

    ############################### recurring events
    def _extract_mb_data(self, songinfo):
        """Store the musicbrainz data in the plugin object for easy access, set
        to None if not present"""

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

        # FIXME: this is blocking. either find a way to do this w/o blocking, or move into another thread.
        # Moreover, do this in parallel.
        if ids['album']:
            mb_data['album'] = mb_ws.Query().getReleaseById(ids['album'], release_inc)
        if ids['track']:
            mb_data['track'] = mb_ws.Query().getTrackById(ids['track'], track_inc)
        if ids['artist']:
            mb_data['artist'] = mb_ws.Query().getArtistById(ids['artist'], artist_inc)
        if ids['albumartist']:
            # FIXME: timeout issues when fetching "various artists" (increasing timeout would cause even longer ui lockup, cf last fixme)
            if ids['albumartist'] != '89ad4ac3-39f7-470e-963a-56509c546377': # exclude "various artists" for now
                mb_data['albumartist'] = mb_ws.Query().getArtistById(ids['albumartist'], artist_inc)

        return mb_data
