"""Player factory.
"""

import advene.core.config as config

from gettext import gettext as _

class PlayerFactory:
    def __init__(self):
        pass

    def get_player(self):
        if config.data.os == 'win32':
            import advene.player.dummy
            return advene.player.dummy.Player()
        else:
            import advene.player.vlcorbit
            return advene.player.vlcorbit.Player()
