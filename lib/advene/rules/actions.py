
import advene.core.config as config

from gettext import gettext as _

import advene.util.vlclib as vlclib

from advene.rules.elements import RegisteredAction, Action, Condition

import cStringIO

class DefaultActionsRepository:
    def __init__(self, controller=None):
        self.controller=controller

    def parse_parameter(self, context, parameters, name, default_value):
        if parameters.has_key(name):
            result=context.evaluateValue(parameters[name])
        else:
            result=default_value
        return result

    def snapshot2png(self, image, output=None):
        return vlclib.snapshot2png(image, output)
        
    def get_default_actions(self):
        l=[]
        l.append(RegisteredAction(
            name="Message",
            method=self.Message,
            description=_("Display a message"),
            parameters={'message': _("Message to display")}
            )
                 )
        l.append(RegisteredAction(
            name="PlayerStart",
            method=self.PlayerStart,
            description=_("Start the player"),
            parameters={'position': _("Start position (in ms)")}
            )
                 )
        l.append(RegisteredAction(
            name="PlayerStop",
            method=self.PlayerStop,
            description=_("Stop the player"),
#            parameters={'position': _("Stop position (in ms)")}
            )
                 )
        l.append(RegisteredAction(
            name="PlayerPause",
            method=self.PlayerPause,
            description=_("Pause the player"),
#            parameters={'position': _("Pause position (in ms)")}
            )
                 )
        l.append(RegisteredAction(
            name="PlayerResume",
            method=self.PlayerResume,
            description=_("Resume the player"),
#            parameters={'position': _("Resume position (in ms)")}
            )
                 )
        l.append(RegisteredAction(
            name="Snapshot",
            method=self.Snapshot,
            description=_("Take a snapshot"),
#            parameters={'position': _("Snapshot position (in ms)")}
            )
                 )
        l.append(RegisteredAction(
            name="Caption",
            method=self.Caption,
            description=_("Display a caption"),
            parameters={'message': _("Message to display"),
                        'duration': _("Duration of the caption")}
            )
                 )
        l.append(RegisteredAction(
            name="AnnotationCaption",
            method=self.AnnotationCaption,
            description=_("Caption the annotation"),
            parameters={'message': _("Message to display")}
            )
                 )
        l.append(RegisteredAction(
            name="AnnotationMute",
            method=self.AnnotationMute,
            description=_("Zero the volume during the annotation"),
            )
                 )
        l.append(RegisteredAction(
            name="SoundOff",
            method=self.SoundOff,
            description=_("Zero the volume"),
            )
                 )
        l.append(RegisteredAction(
            name="SoundOn",
            method=self.SoundOn,
            description=_("Restore the volume"),
            )
                 )

        return l

    def Message(self, context, parameters):
        """Display a message."""
        message=self.parse_parameter(context, parameters, 'message', "An event occurred.")
        print _("** Message ** ") + message
        return True

    def PlayerStart (self, context, parameters):
        """Start the player."""
        position=self.parse_parameter(context, parameters, 'position', None)
        if position is not None:
            position=long(position)
        self.controller.player.update_status ("start", position)
        return True

    def PlayerStop (self, context, parameters):
        """Stop the player."""
        position=self.parse_parameter(context, parameters, 'position', None)
        if position is not None:
            position=long(position)
        self.controller.player.update_status ("stop", position)
        return True
        
    def PlayerPause (self, context, parameters):
        """Pause the player."""
        position=self.parse_parameter(context, parameters, 'position', None)
        if position is not None:
            position=long(position)        
        self.controller.player.update_status ("pause", position)
        return True
        
    def PlayerResume (self, context, parameters):
        """Resume the playing."""
        position=self.parse_parameter(context, parameters, 'position', None)
        if position is not None:
            position=long(position)        
        self.controller.player.update_status ("resume", position)
        return True

    def Snapshot (self, context, parameters):
        """Take a snapshot at the given position (in ms)."""
        if not config.data.player['snapshot']:
            return False
        pos=self.parse_parameter(context, parameters, 'position', None)
        if pos is None:
            pos=self.controller.player.current_position_value
        else:
            pos = long(pos)
        if abs(pos - self.controller.player.current_position_value) > 100:
            # The current position is too far away from the requested position
            # FIXME: do something useful (warning) ?
            return
        self.controller.update_snapshot(position=pos)
        return True

    def Caption (self, context, parameters):
        """Display a message as a caption for a given duration.

        If the 'duration' parameter is not defined, a default duration will be used.
        """
        message=self.parse_parameter(context, parameters, 'message', "Default caption.")
        duration=self.parse_parameter(context, parameters, 'duration', None)

        begin = self.controller.player.relative_position
        if duration is not None:
            duration=long(duration)
        else:
            duration=config.data.preferences['default_caption_duration']

        c=self.controller
        end = c.create_position (value=duration,
                                 key=c.player.MediaTime,
                                 origin=c.player.RelativePosition)
        c.player.display_text (message, begin, end)
        return True

    def AnnotationCaption (self, context, parameters):
        """Display a message as a caption during the triggering annotation timeframe.
        """
        message=self.parse_parameter(context, parameters, 'message', "Default caption.")
        annotation=context.evaluateValue('annotation')

        if annotation is not None:
            begin = self.controller.player.relative_position
            duration=annotation.fragment.end - self.controller.player.current_position_value
            c=self.controller
            end = c.create_position (value=duration,
                                     key=c.player.MediaTime,
                                     origin=c.player.RelativePosition)
            c.player.display_text (message, begin, end)
        return True

    def SoundOff (self, context, parameters):
        """Zero the video volume."""
        v=self.controller.player.sound_get_volume()
        if v > 0:
            config.data.volume = v        
        self.controller.player.sound_set_volume(0)
        return True
    
    def SoundOn (self, context, parameters):
        """Restore the video volume."""
        if config.data.volume != 0:
            self.controller.player.sound_set_volume(config.data.volume)
        return True

    def AnnotationMute(self, context, parameters):
        """Zero the volume for the duration of the annotation."""
        annotation=context.evaluateValue('annotation')
        if annotation is None:
            return True
        self.SoundOff(context, parameters)
        # We create a new internal rule which will match the end of the
        # current annotation :
        cond=Condition(lhs='annotation/id',
                       operator='equals',
                       rhs="string:%s" % annotation.id)
        self.controller.event_handler.internal_rule(event='AnnotationEnd',
                                                    condition=cond,
                                                    method=self.SoundOn)
        return True
