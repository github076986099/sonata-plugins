musicbrainz.py
================================

what this is
---------------------

a sonata plugin that interprets files' metadata about musicbrainz, queries the
musicbrainz server and displays information acquired (currently, only
hyperlinks).

by doing so, the plugin tries to explore the needs of plugins in sonata.

what this is not
---------------------

this plugin will be absolutely useless if the files are not musicbrainz tagged,
eg by musicbrainz picard. it will not try to guess which song this is in
musicbrainz, and does not support writing any tags. picard is more suited for
this job. (adding an option to launch picard on an unknown file is probably as
far as it will get on that issue.)

open issues
---------------------

no caching is done, resulting in hits on the mb servers on every track change
(this is even a security issue, enabling them to track what you hear, in
theory). will have to investigate if there is some cross-app way of doing so.

plugin_class.py
================================

as i prefer an object based approach to plugins over a couple of callbacks,
i've created this framework for sonata plugins. its main class, Plugin (a base
class for plugins) gives the child classes hook_foobar functions that can be
registered as capabilities and call the on_foobar functions. a particular
callback, hook_enablables, is special in that it manages the creation and
destruction of a single instance of the plugin class. care is taken not to let
that instance be referenced somewhere where the reference is not removed in
time, so the object can really be deleted when the plugin is switched off.

see class_based_demo.py for an example, or just look at musicbrainz.py.

sonata plugin api wishlist
=============================

(draft; maybe some of this is already working)

multi-source album art and lyrics
--------------------------------------

different plugins can hook to the lyrics and return (image, level_of_trust)
tuples. for instance, the builtin lyricwiki can give an educated guess and will
thus return ("~/.lyrics/Foo: Bar", 50), while the musicbrainz plugin can be
sure by matching the musicbrainz tag id, giving ("~/.lyrics/0000-11111-...-ffff", 90).

for album art, an embedded album art image could give a (,100) answer because
it's in the metadata and we assume them to be correct. (this example indicates
that it might be better to pass an open file descriptor (or StringIO object)
back instead of a filename.)

at the same time, plugins might be interested in seeing other plugins' answers
so they can offer enhancing their data set, whichever it is.

caching has to be done on a per-plugin base (maybe coordinated, but in no case
enforced) as it is not applicable in some cases (eg embedded album art would
not need any caching).

real song object
-------------------------

the current song is one of the few ways for the plugins to really interact with
sonata. having to use mpdh to query it for attributes is not very object
oriented. the object could then provide methods like .get_filename(), so
plugins can follow the mpd to filesystem mapping of sonata without thinking
about connections.

per-plugin gettext
--------------------

i have no idea how this should be implemented, so for now this is just a note
not to forget that this could become an issue if plugins should be trranslated.
