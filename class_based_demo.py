# encoding: utf-8

# this is the magic interpreted by Sonata, referring to construct_tab below:

### BEGIN PLUGIN INFO
# [plugin]
# plugin_format: 0, 0
# name: demo (class based)
# version: 0, 0, 0
# description: A demo plugin for class based plugins (one instance per plugin and process)
# author: chrysn
# author_email: chrysn@fsfe.org
## url: non yet
# [capabilities]
# enablables: DemoPlugin.hook_enablables
# playing_song_observers: DemoPlugin.hook_song_change
### END PLUGIN INFO

from plugin_class import Plugin

import logging
logging.root.setLevel(logging.DEBUG)

class DemoPlugin(Plugin):
    def on_song_change(self, info):
        print "Hey, a new song!"
        print info
