import sys
import traceback
import logging
import weakref

class meta(type):
    """A metaclass is needed to create adhoc class (not instance) members as wrappers"""
    # let me explain why this dance is necessary ...
    #
    # first idea was to let MyPlugin.hook_foo return the bound on_foo method of
    # the MyPlugin instance at the time hook_foo is evaluated. this worked due
    # to the current implementation of sonata (the hook_foo method is queried
    # immediately before it is called), but turned out to have problems when a
    # wrapper function was created because there were checks on the identity of
    # hook_foo (it is used as a key in looking up the tab to destroy when
    # unloading)
    #
    # the current implementation makes sure
    #  * no references to plugin instances are around, ever
    #  * SomePlugin.hook_foo always has the same (identical) value
    #  * the on_foo methods can be wrapped
    #
    # i might add that wrapping is necessary to catch all exceptions and avoid
    # passing out references to the instances. as a compromise (between not
    # letting references out and good exception practice of not randomly
    # dropping any), a string representation of the exception is re-raised
    # after reporting it via logging.
    _hook_cache = {}
    def __getattr__(cls, attr):
        if attr.startswith('hook_'):
            on_name = 'on_%s'%attr[5:]
            if hasattr(cls, on_name):
                cache_key = (cls, on_name)
                if cache_key not in cls._hook_cache:
                    def wrapped(*args, **kwargs):
                        instance = cls._get_instance()
                        method = getattr(instance, on_name)
                        try:
                            return method(*args, **kwargs)
                        except:
                            e_type, e_value, e_traceback = sys.exc_info()
                            logging.error("Exception in plugin %s: %s"%(cls.__name__, e_value))
                            logging.info("".join(traceback.format_exception(e_type, e_value, e_traceback)))
                            del instance, method # these deletes are crucial in not letting a reference to the plugin instance out
                            raise Exception("There was an exception in the %s plugin (%s)."%(cls.__name__, e_value))
                    cls._hook_cache[cache_key] = wrapped
                return cls._hook_cache[cache_key]
            else:
                raise AttributeError, attr # the corresponding on_... does not exist here
        else:
            raise AttributeError, attr # is not of a kind handled here

class Plugin(object):
    """Parent class for sonata plugins for single-object-per-plugin-and-process
    style plugin initialization

    For a usage example, see class_based_demo.py.

    Capabilities have to be announced to sonata as MyClass.hook_something,
    which is a wrapper for MyClass.on_something(self, ...).

    The something part can be arbitrary but for the enablables capability, for
    which it has to be hook_enablables / on_enablables (the on_enablables will
            be called after creation and before destruction of the object).
    """

    __metaclass__ = meta

    __instances = {} # per class

    @classmethod
    def hook_enablables(cls, state):
        # drops any return values. can plugins defend against being
        # switched off? if yes, this will have to be respected here.
        if state:
            logging.info("Creating plugin instance %r", cls.__name__)
            instance = cls.__create_instance()
            if hasattr(instance, 'on_enablables'):
                instance.on_enablables(True)
        else:
            instance = cls._get_instance()
            if hasattr(instance, 'on_enablables'):
                instance.on_enablables(False)
            del instance
            cls.__destroy_instance()
            logging.info("Destroyed plugin instance %r", cls.__name__)

    @classmethod
    def _get_instance(cls):
        """Internal method used by hooks to get the (single) instance of the
        plugin running in sonata."""
        try:
            return cls.__instances[cls]
        except KeyError:
            raise Exception("Plugin instance requested (eg by signalling) without prior enablables(True)")

    @classmethod
    def __create_instance(cls):
        if cls in cls.__instances:
            raise Exception("Duplicate class creation")

        instance = cls()
        cls.__instances[cls] = instance
        logging.debug("created %r", instance)
        return instance

    @classmethod
    def __destroy_instance(cls):
        # not strictly needed because caught by _get_instance anyway, but more
        # meaningful
        if cls not in cls.__instances:
            raise Exception("Can not destroy plugin that was not previously created")

        pointer = weakref.ref(cls._get_instance())
        del cls.__instances[cls]
        # check if del was successful in the sense that it deleted the last reference (which it should)
        if pointer() is not None:
            # yes this is brutal. in non-development situations, a warning might be sufficient
            #
            # this can, for example, happen if an exception is thown "outside";
            # the exception somehow contains a reference to our object.
            raise Exception("There is still a reference to the instance lingering somewhere.")

        logging.debug("instance of %r successfully destroyed.", cls)
