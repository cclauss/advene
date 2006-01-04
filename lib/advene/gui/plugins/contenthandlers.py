import advene.core.config as config

import gtk
import os

from advene.gui.edit.elements import ContentHandler
from advene.gui.edit.shapewidget import ShapeDrawer, Rectangle
import advene.gui.util

import advene.model.tal.global_methods as global_methods

name="Default content handlers"

def register(controller=None):
    for c in ZoneContentHandler, RuleSetContentHandler, SimpleQueryContentHandler:
	controller.register_content_handler(c)

class ZoneContentHandler (ContentHandler):
    """Create a zone edit form for the given element."""
    def can_handle(mimetype):
	res=0
	if mimetype == 'application/x-advene-zone':
	    res=80
	return res
    can_handle=staticmethod(can_handle)

    def __init__ (self, element, controller=None, annotation=None, **kw):
        self.element = element
        self.controller=controller
        self.annotation=annotation
        self.editable = True
        self.fname=None
        self.view = None
        self.shape = None
        self.tooltips=gtk.Tooltips()

    def set_editable (self, boolean):
        self.editable = boolean

    def callback(self, l):
        if self.shape is None:
            r = Rectangle()
            r.name = "Selection"
            r.color = "green"
            r.set_bounds(l)
            self.view.add_object(r)
            self.shape=r
        else:
            self.shape.set_bounds(l)
            self.view.plot()
        return
        
    def update_element (self):
        """Update the element fields according to the values in the view."""
        if not self.editable:
            return False
        if self.shape is None:
            return True

        shape=self.shape
        text="""shape=rect\nname=%s\nx=%d\ny=%d\nwidth=%d\nheight=%d""" % (
            shape.name,
            shape.x * 100 / self.view.canvaswidth,
            shape.y * 100 / self.view.canvasheight,
            shape.width * 100 / self.view.canvaswidth,
            shape.height * 100 / self.view.canvasheight)

	self.element.data = text
        return True

    def get_view (self):
        """Generate a view widget for editing zone attributes."""
        vbox=gtk.VBox()
        
        # FIXME: use correct position from annotation bound
        i=advene.gui.util.image_from_position(self.controller, self.annotation.fragment.begin)
        self.view = ShapeDrawer(callback=self.callback, background=i)

        if self.element.data:
            d=global_methods.parsed( self.element, None )
            if isinstance(d, dict):
                try:
                    x = int(d['x']) * self.view.canvaswidth / 100
                    y = int(d['y']) * self.view.canvasheight / 100
                    width = int(d['width']) * self.view.canvaswidth / 100
                    height = int(d['height']) * self.view.canvasheight / 100
                    self.callback( ( (x, y),
                                     (x+width, y+height) ) )
                    self.shape.name = d['name']
                except KeyError:
                    self.callback( ( (0, 0),
                                     (99, 99) ) )
                    self.shape.name = self.element.data

        vbox.add(self.view.widget)

        return vbox


class RuleSetContentHandler (ContentHandler):
    """Create a RuleSet edit form for the given element (a view, presumably).
    """
    def can_handle(mimetype):
	res=0
	if mimetype == 'application/x-advene-ruleset':
	    res=80
	return res
    can_handle=staticmethod(can_handle)

    def __init__ (self, element, controller=None, **kw):
        self.element = element
        self.controller=controller
        self.editable = True
        self.view = None

    def set_editable (self, boolean):
        self.editable = boolean

    def check_validity(self):
        iv=self.edit.invalid_items()
        if iv:
	    advene.gui.util.message_dialog(
                _("The following items seem to be\ninvalid TALES expressions:\n\n%s") %
                "\n".join(iv),
		icon=gtk.MESSAGE_ERROR)
            return False
        else:
            return True


    def update_element (self):
        """Update the element fields according to the values in the view."""
        if not self.editable:
            return False
        if not self.edit.update_value():
            return False
	self.element.data = self.edit.model.xml_repr()
        return True

    def get_view (self):
        """Generate a view widget to edit the ruleset."""
        rs=advene.rules.elements.RuleSet()
        rs.from_dom(catalog=self.controller.event_handler.catalog,
                    domelement=self.element.model)

        self.edit=advene.gui.edit.rules.EditRuleSet(rs,
                                                    catalog=self.controller.event_handler.catalog,
                                                    editable=self.editable,
                                                    controller=self.controller)
        self.view = self.edit.get_packed_widget()

        scroll_win = gtk.ScrolledWindow ()
        scroll_win.set_policy (gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroll_win.add_with_viewport(self.view)

        return scroll_win

class SimpleQueryContentHandler (ContentHandler):
    """Create a Query edit form for the given element (a view, presumably).
    """
    def can_handle(mimetype):
	res=0
	if mimetype == 'application/x-advene-simplequery':
	    res=80
	return res
    can_handle=staticmethod(can_handle)

    def __init__ (self, element, controller=None, editable=True, **kw):
        self.element = element
        self.controller=controller
        self.editable = editable
        self.view = None

    def check_validity(self):
        iv=self.edit.invalid_items()
        if iv:
	    advene.gui.util.message_dialog(
                _("The following items seem to be\ninvalid TALES expressions:\n\n%s") %
                "\n".join(iv),
		icon=gtk.MESSAGE_ERROR)
            return False
        else:
            return True

    def set_editable (self, boo):
        self.editable = boo

    def update_element (self):
        """Update the element fields according to the values in the view."""
        if not self.editable:
            return False
        if not self.edit.update_value():
            return False
	self.element.data = self.edit.model.xml_repr()
	# Just to be sure:
        self.element.mimetype = 'application/x-advene-simplequery'
        return True

    def get_view (self):
        """Generate a view widget to edit the ruleset."""
        q=advene.rules.elements.Query()
        q.from_dom(domelement=self.element.model)

        self.edit=advene.gui.edit.rules.EditQuery(q,
                                                  controller=self.controller,
                                                  editable=self.editable)
        self.view = self.edit.get_widget()

        scroll_win = gtk.ScrolledWindow ()
        scroll_win.set_policy (gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroll_win.add_with_viewport(self.view)

        return scroll_win
