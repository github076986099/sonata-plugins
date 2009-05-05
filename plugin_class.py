import logging
import weakref

class meta(type):
    """A metaclass is needed to create adhoc class (not instance) members as wrappers"""
    def __getattr__(cls, attr):
        if attr.startswith('hook_'):
            instance = cls._get_instance()
            return getattr(instance, 'on_%s'%attr[5:])
        else:
            raise AttributeError, attr

class Plugin(object):
    """Parent class for sonata plugins for single-object-per-plugin-and-process
    style plugin initialization

    For a usage example, see class_based_demo.py.

    Capabilities have to be announced to sonata as MyClass.hook_something, which is a wrapper for MyClass.on_something(self, ...).

    The something part can be arbitrary but for the enablables capability, for which it has to be hook_enablables / on_enablables (the on_enabables will be called after creation and before destruction of the object).
    """

    __metaclass__ = meta

    __instances = {} # per class

    @classmethod
    def hook_enablables(cls, state):
        # drops any return values. can plugins defend against being
        # switched off? if yes, this will have to be respected here.
        if state:
            instance = cls.__create_instance()
            if hasattr(instance, 'on_enablables'):
                instance.on_enablables(True)
        else:
            instance = cls._get_instance()
            if hasattr(instance, 'on_enablables'):
                instance.on_enablables(False)
            del instance
            cls.__destroy_instance()

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
            print pointer()
            raise Exception("There is still a reference to the instance lingering somewhere.")

        logging.debug("instance of %r successfully destroyed.", cls)
