#
# Advene: Annotate Digital Videos, Exchange on the NEt
# Copyright (C) 2008 Olivier Aubert <olivier.aubert@liris.cnrs.fr>
#
# Advene is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# Advene is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Advene; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
#
from gettext import gettext as _
import subprocess
import os
import signal
import sys

import advene.core.config as config
from advene.rules.elements import RegisteredAction
import advene.util.helper as helper

import advene.model.tal.context

CREATE_NO_WINDOW = 0x8000000

name="Text-To-Speech actions"

def register(controller=None):
    for c in (CustomArgTTSEngine, CustomTTSEngine, EspeakTTSEngine, MacOSXTTSEngine, FestivalTTSEngine, TTSEngine):
        if c.can_run():
            controller.log("TTS: Using " + c.__doc__.splitlines()[0])
            engine = c(controller)
            break

    controller.register_action(RegisteredAction(
            name="Pronounce",
            method=engine.action_pronounce,
            description=_("Pronounce a text"),
            parameters={'message': _("String to pronounce.")},
            defaults={'message': 'annotation/content/data'},
            predefined={'message': (
                    ( 'annotation/content/data', _("The annotation content") ),
                    )},
            category='generic',
            ))

class TTSEngine:
    """Generic TTSEngine.
    """
    def __init__(self, controller=None):
        self.controller=controller
        self.gui=self.controller.gui
        self.language=None

    def can_run():
        """Can this engine run ?
        """
        return True
    can_run=staticmethod(can_run)

    def parse_parameter(self, context, parameters, name, default_value):
        """Helper method used in actions.
        """
        if name in parameters:
            try:
                result=context.evaluateValue(parameters[name])
            except advene.model.tal.context.AdveneTalesException, e:
                try:
                    rulename=context.evaluateValue('rule')
                except advene.model.tal.context.AdveneTalesException:
                    rulename=_("Unknown rule")
                self.controller.log(_("Rule %(rulename)s: Error in the evaluation of the parameter %(parametername)s:") % {'rulename': rulename,
                                                                                                                          'parametername': name})
                self.controller.log(unicode(e.message)[:160])
                result=default_value
        else:
            result=default_value
        return result

    def set_language(self, language):
        self.language=language

    def pronounce(self, sentence):
        """Engine-specific method.
        """
        self.controller.log("TTS: pronounce " + sentence)
        return True

    def action_pronounce (self, context, parameters):
        """Pronounce action.
        """
        message=self.parse_parameter(context, parameters, 'message', _("No message..."))
        self.pronounce(message)
        return True

class FestivalTTSEngine(TTSEngine):
    """Festival TTSEngine.

    Note: If it is not the case (depends on the version), festival
    must be configured to play audio through the ALSA subsystem, in
    order to be able to mix it with the movie sound if necessary.

    For this, in older Festival versions (at least until 1.4.3), the
    ~/.festivalrc file should contain:

(Parameter.set 'Audio_Command "aplay -q -c 1 -t raw -f s16 -r $SR $FILE")
(Parameter.set 'Audio_Method 'Audio_Command)


    """
    def __init__(self, controller=None):
        TTSEngine.__init__(self, controller=controller)
        self.festival_path=helper.find_in_path('festival')
        self.aplay_path=helper.find_in_path('aplay')
        if self.festival_path is None:
            self.controller.log(_("TTS disabled. Cannot find the application 'festival' in PATH"))
        if self.aplay_path is None:
            self.controller.log(_("TTS disabled. Cannot find the application 'aplay' in PATH"))
        self.festival_process=None

    def init(self):
        if self.festival_path is not None and self.aplay_path is not None:
            self.festival_process = subprocess.Popen([ self.festival_path, '--pipe' ], stdin=subprocess.PIPE)
            # Configure festival to use aplay
            self.festival_process.stdin.write("""(Parameter.set 'Audio_Command "%s -q -c 1 -t raw -f s16 -r $SR $FILE")\n""" % self.aplay_path)
            self.festival_process.stdin.write("""(Parameter.set 'Audio_Method 'Audio_Command)\n""")


    def can_run():
        """Can this engine run ?
        """
        return (helper.find_in_path('festival') is not None)
    can_run=staticmethod(can_run)

    def pronounce (self, sentence):
        try:
            self.init()
            if self.festival_process is not None:
                self.festival_process.stdin.write('(SayText "%s")\n' % helper.unaccent(sentence))
        except OSError, e:
            self.controller.log(u"TTS Error: " + unicode(e.message))
        return True

class MacOSXTTSEngine(TTSEngine):
    """MacOSX TTSEngine.
    """
    def can_run():
        """Can this engine run ?
        """
        return (config.data.os == 'darwin')
    can_run=staticmethod(can_run)

    def pronounce (self, sentence):
        subprocess.call( [ '/usr/bin/say', sentence ] )
        return True

"""
Win32: install pytts + pywin32 (from sf.net) + mfc71.dll + spchapi.exe (from www.microsoft.com/reader/developer/downloads/tts.mspx
)
On some flavors of Windows you can use:
import pyTTS

tts = pyTTS.Create()
tts.Speak('This is the sound of my voice.')

On Mac OS X you can use:
import os

http://farm.tucows.com/blog/_archives/2005/1/19/266813.html

http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/114216
http://www.daniweb.com/code/snippet326.html
http://www.mindtrove.info/articles/pytts.html
"""
class EspeakTTSEngine(TTSEngine):
    """Espeak TTSEngine.
    """
    def __init__(self, controller=None):
        TTSEngine.__init__(self, controller=controller)
        self.language=None
        self.espeak_path=helper.find_in_path('espeak')
        if self.espeak_path is None and config.data.os == 'win32':
            # Try c:\\Program Files\\eSpeak
            if os.path.isdir('c:\\Program Files\\eSpeak'):
                self.espeak_path='c:\\Program Files\\eSpeak\\command_line\\espeak.exe'
            elif os.path.isdir('C:\\Program Files (x86)\\eSpeak'):
                #winXp 64b
                self.espeak_path='C:\\Program Files (x86)\\eSpeak\\command_line\\espeak.exe'
        self.espeak_process=None

    def can_run():
        """Can this engine run ?
        """
        return (os.path.isdir('c:\\Program Files\\eSpeak') or os.path.isdir('C:\\Program Files (x86)\\eSpeak') or helper.find_in_path('espeak') is not None)
    can_run=staticmethod(can_run)

    def close(self):
        """Close the espeak process.
        """
        if self.espeak_process is not None:
            if config.data.os == 'win32':
                import win32api
                win32api.TerminateProcess(int(self.espeak_process._handle), -1)
            else:
                os.kill(self.espeak_process.pid, signal.SIGTERM)
                self.espeak_process.wait()
            self.espeak_process=None

    def pronounce (self, sentence):
        lang=config.data.preferences.get('tts-language', 'en')
        if self.language != lang:
            # Need to restart espeak to use the new language
            self.close()
            self.language=lang
        try:
            if self.espeak_process is None:
                self.espeak_process = subprocess.Popen([ self.espeak_path, '-v', self.language ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, creationflags = CREATE_NO_WINDOW)
            # FIXME: we should encode sentence to a specific encoding (utf8 ?)
            self.espeak_process.stdin.write(sentence + "\n")
        except OSError, e:
            self.controller.log("TTS Error: ", unicode(e.message).encode('utf8'))
        return True


class SAPITTSEngine(TTSEngine):
    """SAPI (win32) TTSEngine.
    """
    def __init__(self, controller=None):
        TTSEngine.__init__(self, controller=controller)
        self.sapi=None

    def can_run():
        """Can this engine run ?
        """
        try:
            import win32com.client
            voice = win32com.client.Dispatch("sapi.SPVoice")
        except:
            voice = None
        return voice
    can_run=staticmethod(can_run)

    def pronounce (self, sentence):
        if self.sapi is None:
            self.sapi=win32com.client.Dispatch("sapi.SPVoice")
        self.sapi.Speak( sentence )
        return True

class CustomTTSEngine(TTSEngine):
    """Custom TTSEngine.

    It tries to run a 'prononce' ('prononce.bat' on win32) script,
    which takes strings on its stdin and pronounces them.
    """
    if config.data.os == 'win32':
        prgname='prononce.bat'
    else:
        prgname='prononce'

    def __init__(self, controller=None):
        TTSEngine.__init__(self, controller=controller)
        self.language=None
        self.prg_path=helper.find_in_path(CustomTTSEngine.prgname)
        self.prg_process=None

    def can_run():
        """Can this engine run ?
        """
        return helper.find_in_path(CustomTTSEngine.prgname) is not None
    can_run=staticmethod(can_run)

    def close(self):
        """Close the process.
        """
        if self.prg_process is not None:
            if config.data.os == 'win32':
                import win32api
                win32api.TerminateProcess(int(self.prg_process._handle), -1)
            else:
                os.kill(self.prg_process.pid, signal.SIGTERM)
                self.prg_process.wait()
            self.prg_process=None

    def pronounce (self, sentence):
        lang=config.data.preferences.get('tts-language', 'en')
        if self.language != lang:
            self.close()
            self.language=lang
        try:
            if self.prg_process is None:
                self.prg_process = subprocess.Popen([ self.prg_path, '-v', self.language ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, creationflags = CREATE_NO_WINDOW)
            self.prg_process.stdin.write(sentence + "\n")
        except OSError, e:
            self.controller.log("TTS Error: ", unicode(e.message).encode('utf8'))
        return True

class CustomArgTTSEngine(TTSEngine):
    """CustomArg TTSEngine.

    It tries to run a 'prononcearg' ('prononcearg.bat' on win32) script,
    which takes strings as arguments and pronounces them.
    """
    if config.data.os == 'win32':
        prgname='prononcearg.bat'
    else:
        prgname='prononcearg'

    def __init__(self, controller=None):
        TTSEngine.__init__(self, controller=controller)
        self.language=None
        self.prg_path=helper.find_in_path(CustomArgTTSEngine.prgname)

    def can_run():
        """Can this engine run ?
        """
        return helper.find_in_path(CustomArgTTSEngine.prgname) is not None
    can_run=staticmethod(can_run)

    def close(self):
        """Close the process.
        """
        pass

    def pronounce (self, sentence):
        lang=config.data.preferences.get('tts-language', 'en')
        if self.language != lang:
            self.close()
            self.language=lang
        try:
            fse = sys.getfilesystemencoding()
            subprocess.Popen([ self.prg_path, '-v', self.language, (sentence.replace('\n',' ') + u"\n").encode(fse, 'ignore') ], creationflags = CREATE_NO_WINDOW)
        except OSError, e:
            try:
                m = unicode(e.message)
            except UnicodeDecodeError:
                print "TTS: Error decoding error message with standard encoding"
                m = unicode(e.message, fse, 'ignore')
            self.controller.log("TTS Error: ", m.encode('ascii', 'ignore'))
        return True
