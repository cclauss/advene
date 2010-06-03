
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
"""Widget used to adjust times in Advene.

It depends on a Controller instance to be able to interact with the video player.
"""

import advene.core.config as config

import re
import gtk
import advene.util.helper as helper
from advene.gui.widget import TimestampRepresentation
from advene.gui.util import encode_drop_parameters, decode_drop_parameters, dialog
from gettext import gettext as _

class TimeAdjustment:
    """TimeAdjustment widget.

    Note: time values are integers in milliseconds.
    """
    def __init__(self, value=0, controller=None, videosync=False, editable=True, compact=False, callback=None):
        self.value=value
        self.controller=controller
        self.sync_video=videosync
        # Small increment
        self.small_increment=config.data.preferences['scroll-increment']
        # Large increment
        self.large_increment=config.data.preferences['second-scroll-increment']
        self.image=None
        self.editable=editable
        self.compact=compact
        # Callback is a method which will be called *before* setting
        # the new value. If it returns False, then the new value will
        # not be used.
        self.callback=callback
        self.widget=self.make_widget()
        self.update_display()

    def make_widget(self):

        def refresh_snapshot(item):
            self.image.refresh_snapshot()
            return True

        def image_button_clicked(button):
            event=gtk.get_current_event()
            if event.state & gtk.gdk.CONTROL_MASK:
                self.use_current_position(button)
                return True
            else:
                self.play_from_here(button)
                return True

        def image_button_press(button, event):
            if event.button == 3 and event.type == gtk.gdk.BUTTON_PRESS:
                # Display the popup menu
                menu = gtk.Menu()
                item = gtk.MenuItem(_("Refresh snapshot"))
                item.connect('activate', refresh_snapshot)
                menu.append(item)
                menu.show_all()
                menu.popup(None, None, None, 0, gtk.get_current_event_time())
                return True
            return False

        def make_button(incr_value, pixmap):
            """Helper function to build the buttons."""
            b=gtk.Button()
            i=gtk.Image()
            i.set_from_file(config.data.advenefile( ( 'pixmaps', pixmap) ))
            # FIXME: to re-enable
            # The proper way is to do
            #b.set_image(i)
            # but it works only on linux, gtk 2.10
            # and is broken on windows and mac
            al=gtk.Alignment()
            al.set_padding(0, 0, 0, 0)
            al.add(i)
            b.add(al)

            b.connect('clicked', self.update_value_cb, incr_value)
            if incr_value < 0:
                tip=_("Decrement value by %.2f s") % (incr_value / 1000.0)
            else:
                tip=_("Increment value by %.2f s") % (incr_value / 1000.0)
            b.set_tooltip_text(tip)
            return b

        vbox=gtk.VBox()

        hbox=gtk.HBox()
        hbox.set_homogeneous(False)

        if self.editable:
            vb=gtk.VBox()
            b=make_button(-self.large_increment, "2leftarrow.png")
            vb.pack_start(b, expand=False)
            b=make_button(-self.small_increment, "1leftarrow.png")
            vb.pack_start(b, expand=False)
            hbox.pack_start(vb, expand=False)

        if self.compact:
            width=50
        else:
            width=100
        self.image=TimestampRepresentation(self.value, self.controller, width, epsilon=1000/25, visible_label=False)
        self.image.connect('button-press-event', image_button_press)
        self.image.connect('clicked', image_button_clicked)
        self.image.set_tooltip_text(_("Click to play\nControl+click to set to current time\Scroll to modify value (with control/shift)\nRight-click to invalidate screenshot"))
        hbox.pack_start(self.image, expand=False)

        if self.editable:
            vb=gtk.VBox()
            b=make_button(self.large_increment, "2rightarrow.png")
            vb.pack_start(b, expand=False)
            b=make_button(self.small_increment, "1rightarrow.png")
            vb.pack_start(b, expand=False)
            hbox.pack_start(vb, expand=False)

        hb = gtk.HBox()

        if self.editable:
            self.entry=gtk.Entry()
            # Default width of the entry field
            self.entry.set_width_chars(len(helper.format_time(0.0)))
            self.entry.connect('activate', self.convert_entered_value)
            self.entry.connect('focus-out-event', self.convert_entered_value)
            self.entry.set_editable(self.editable)
            hb.pack_start(self.entry, expand=False)
        else:
            self.entry=None

        if self.editable:
            current_pos=gtk.Button()
            i=gtk.Image()
            i.set_from_file(config.data.advenefile( ( 'pixmaps', 'set-to-now.png') ))
            current_pos.set_tooltip_text(_("Set to current player position"))
            current_pos.add(i)
            current_pos.connect('clicked', self.use_current_position)
            hb.pack_start(current_pos, expand=False)

        vbox.pack_start(hbox, expand=False)
        vbox.pack_start(hb, expand=False)
        hb.set_style(self.image.box.get_style())
        #self.entry.set_style(self.image.box.get_style())
        vbox.set_style(self.image.box.get_style())
        vbox.show_all()

        hb.set_no_show_all(True)
        hbox.set_no_show_all(True)
        self.image.label.hide()
        hb.show()

        def handle_scroll_event(button, event):
            if event.state & gtk.gdk.CONTROL_MASK:
                i=config.data.preferences['scroll-increment']
            elif event.state & gtk.gdk.SHIFT_MASK:
                i=config.data.preferences['second-scroll-increment']
            else:
                # 1 frame
                i=1000/25

            if event.direction == gtk.gdk.SCROLL_DOWN:
                incr=-i
            elif event.direction == gtk.gdk.SCROLL_UP:
                incr=i

            v=self.value
            v += incr
            if self.callback and not self.callback(v):
                return True
            self.value=v
            self.update_display()
            return True

        if self.editable:
            # The widget can receive drops from annotations
            vbox.connect('drag-data-received', self.drag_received)
            vbox.drag_dest_set(gtk.DEST_DEFAULT_MOTION |
                               gtk.DEST_DEFAULT_HIGHLIGHT |
                               gtk.DEST_DEFAULT_ALL,
                               config.data.drag_type['annotation']
                               + config.data.drag_type['timestamp'],
                               gtk.gdk.ACTION_LINK)

            vbox.connect('scroll-event', handle_scroll_event)

        vbox.show_all()
        return vbox

    def drag_received(self, widget, context, x, y, selection, targetType, time):
        if targetType == config.data.target_type['annotation']:
            source_uri=unicode(selection.data, 'utf8').split('\n')[0]
            source=self.controller.package.annotations.get(source_uri)
            if self.callback and not self.callback(source.fragment.begin):
                return True
            self.value = source.fragment.begin
            self.update_display()
        elif targetType == config.data.target_type['timestamp']:
            data=decode_drop_parameters(selection.data)
            v=long(float(data['timestamp']))
            if self.callback and not self.callback(v):
                return True
            self.value=v
            self.update_display()
        else:
            print "Unknown target type for drop: %d" % targetType
        return True

    def drag_sent(self, widget, context, selection, targetType, eventTime):
        """Handle the drag-sent event.
        """
        if targetType == config.data.target_type['timestamp']:
            selection.set(selection.target, 8, encode_drop_parameters(timestamp=self.value))
            return True
        elif targetType in ( config.data.target_type['text-plain'],
                             config.data.target_type['TEXT'],
                             config.data.target_type['STRING'] ):
            selection.set(selection.target, 8, helper.format_time(self.value))
            return True
        return False

    def play_from_here(self, button):
        if self.controller.player.status == self.controller.player.PauseStatus:
            self.controller.update_status("set", self.value)
        elif self.controller.player.status != self.controller.player.PlayingStatus:
            self.controller.update_status("start", self.value)
        self.controller.update_status("set", self.value)
        return True

    def use_current_position(self, button):
        v=self.controller.player.current_position_value
        if self.callback and not self.callback(v):
            return True
        self.value=v
        self.update_display()
        return True

    def update_snapshot(self, button):
        # FIXME: to implement
        print "Not implemented yet."
        pass

    # Static values used in numericTime
    _hour = r'(?P<hour>\d+)'
    _minute = r'(?P<minute>\d+)'
    _second = r'(?P<second>\d+(\.\d+))'
    _time = _hour + r':' + _minute + r'(:' + _second + r')?'
    _timeRE = re.compile(_time, re.I)

    def numericTime(self, s):
        """Converts a time string into a long value.

        This function is inspired from the numdate.py example script from the
        egenix mxDateTime package.

        If the input string s is a valid time expression of the
        form hh:mm:ss.sss or hh:mm:ss or hh:mm, return
        the corresponding value in milliseconds (float), else None
        """

        if s is None:
            return None
        dt = None
        match = TimeAdjustment._timeRE.search(s)
        if match is not None:
            hh = int(match.group('hour'))
            mm = int(match.group('minute'))
            second = match.group('second')
            if second:
                ss = float(second)
            else:
                ss = 0.0
            dt=int(1000 * (ss + (60 * mm) + (3600 * hh)))
        return dt

    def convert_entered_value(self, *p):
        t=self.entry.get_text()
        v=self.numericTime(t)
        if v is not None and v != self.value:
            v=self.check_bound_value(v)
            if self.callback and not self.callback(v):
                return False
            self.value = v
            if self.sync_video:
                self.controller.move_position(self.value, relative=False)
            self.update_display()
        return False

    def check_bound_value(self, value):
        if value < 0:
            value = 0
        elif (self.controller.cached_duration > 0
              and value > self.controller.cached_duration):
            value = self.controller.cached_duration
        return value

    def update(self):
        self.update_display()

    def update_display(self):
        """Updates the value displayed in the entry according to the current value."""
        self.entry.set_text(helper.format_time(self.value))
        self.image.value=self.value

    def update_value_cb(self, widget, increment):
        if not self.editable:
            return True
        v=self.check_bound_value(self.value + increment)
        if self.callback and not self.callback(v):
            return True
        self.value=v
        if self.sync_video:
            self.controller.move_position(self.value, relative=False)
        self.update_display()
        return True

    def get_widget(self):
        return self.widget

    def get_value(self):
        return self.value

class FrameSelector(object):
    """Frame selector interface.
    
    Given a timestamp, it displays a series of snapshots around
    the timestamp and allows to select the most appropriate
    one.
    """
    def __init__(self, controller, timestamp=0, callback=None):
        self.controller = controller
        self.timestamp = timestamp
        self.selected_value = timestamp
        self.callback = callback
        # Number of displayed timestamps
        self.count = 8
        self.frame_length = 1000 / 25
        # Reference to the HBox holding TimestampRepresentation widgets.
        # It is initialized in build_widget()
        self.container = None
        self.widget = self.build_widget()
        
    def update_offset(self, offset):
        """Update the timestamps to go forward/backward.
        """
        if offset < 0:
            ref=self.container.get_children()[0]
            start = max(ref.value + offset * self.frame_length, 0)
        else:
            ref=self.container.get_children()[offset]
            start = ref.value
        self.update_timestamp(start + self.count / 2 * self.frame_length)
        return True

    def set_timestamp(self, timestamp):
        """Set the reference timestamp.

        It is the timestamp displayed in the label, and corresponds
        most of the time to the original timestamp (before adjustment).
        """
        self.timestamp = timestamp
        self.selected_value = timestamp
        self.update_timestamp(timestamp)
        
    def update_timestamp(self, timestamp):
        """Set the center timestamp.
        """
        t = max(timestamp - self.count / 2 * self.frame_length, 0)
        for c in self.container.get_children():
            c.value = t
            if t < self.timestamp:
                c.bgcolor = '#666666'
            else:
                c.bgcolor = 'black'
            if t == timestamp:
                c.grab_focus()
            t += self.frame_length
        return True

    def refresh_snapshots(self):
        """Update non-initialized snapshots.
        """
        ic=self.controller.package.imagecache
        for c in self.container.get_children():
            if not ic.is_initialized(c.value):
                self.controller.update_snapshot(c.value)
        return True

    def handle_scroll_event(self, widget, event):
        if event.direction == gtk.gdk.SCROLL_UP:
            offset=-1
        else:
            offset=+1
        self.update_offset(offset)
        return True

    def handle_key_press(self, widget, event):
        if event.keyval == gtk.keysyms.Page_Down:
            self.update_offset(-self.count / 2)
            return True
        elif event.keyval == gtk.keysyms.Page_Up:
            self.update_offset(+self.count / 2)
            return True
        return False

    def get_value(self, title=None):
        if title is None:
            title = _("Select the appropriate snapshot")
        d = gtk.Dialog(title=title,
                       parent=None,
                       flags=gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                       buttons=( gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                 gtk.STOCK_OK, gtk.RESPONSE_OK,
                                 ))

        def callback(v):
            d.response(gtk.RESPONSE_OK)
            return True
        self.callback = callback

        d.vbox.add(self.widget)
        d.show_all()
        dialog.center_on_mouse(d)

        res = d.run()
        timestamp = self.timestamp
        if res == gtk.RESPONSE_OK:
            timestamp = self.selected_value
        d.destroy()
        return timestamp
    
    def select_time(self, button=None):
        """General callback.

        It updates self.selected_value then calls self.callback if defined.
        """
        if button is not None:
            self.selected_value = button.value
        if self.callback is not None:
            self.callback(self.selected_value)
        return True
        
    def build_widget(self):
        vb=gtk.VBox()

        buttons = gtk.HBox()

        b=gtk.Button(stock=gtk.STOCK_REFRESH)
        b.set_tooltip_text(_("Refresh missing snapshots"))
        b.connect("clicked", lambda b: self.refresh_snapshots())
        buttons.pack_start(b, expand=True)

        vb.pack_start(buttons, expand=False)

        hb=gtk.HBox()

        for i in xrange(-self.count / 2, self.count / 2):
            r=TimestampRepresentation(0, self.controller, width=100, visible_label=True, epsilon=30)
            r.connect("clicked", self.select_time)
            hb.pack_start(r, expand=False)

        hb.connect('scroll-event', self.handle_scroll_event)
        hb.connect('key-press-event', self.handle_key_press)
        vb.add(hb)

        self.container = hb
        self.update_timestamp(self.timestamp)
        return vb
