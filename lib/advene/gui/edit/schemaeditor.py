#
# This file is part of Advene.
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
# along with Foobar; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
#
"""SchemaEditor GUI classes and methods.

This module provides a schema editor form

"""

import advene.core.config as config
from gettext import gettext as _

import gtk
try:
    import goocanvas
    from goocanvas import Group
except ImportError:
    # Goocanvas is not available. Define some globals in order not to
    # fail the module loading, and use them as a guard in register()
    goocanvas=None
    Group=object
import cairo
from advene.model.schema import Schema, AnnotationType, RelationType
from advene.gui.views import AdhocView
from advene.gui.util import dialog, name2color, get_pixmap_button
from advene.gui.edit.create import CreateElementPopup
import advene.util.helper as helper
from math import sqrt
import advene.gui.popup


name="Schema editor view"

def register(controller):
    #print "Registering plugin SchemaEditor"
    if goocanvas is None:
        controller.log("Cannot register SchemaEditor: the goocanvas python module does not seem to be available.")
    else:
        controller.register_viewclass(SchemaEditor)

class SchemaEditor (AdhocView):
    view_name = _("Schema Editor")
    view_id = 'schemaeditor'
    tooltip=("Graphical editor of Advene schemas")
    def __init__ (self, controller=None, parameters=None, package=None):
        super(SchemaEditor, self).__init__(controller=controller)
        self.close_on_package_load = False
        self.contextual_actions = (
            (_("Refresh"), self.refresh),
            )
        self.listeSchemas = None
        self.controller=controller
        self.TE=None
        self.hboxEspaceSchema=None
        self.schemaArea = None
        self.canvas = None
        self.hboxButton = None
        self.rotButton = None
        self.exchButton = None
        self.canvasX = 1200
        self.canvasY = 1000
        self.swX = 0
        self.swY = 0
        self.sepV = None
        self.sepH = None
        self.openedschemas = {}
        self.dragging = False
        self.drag_x = 0
        self.drag_y = 0
        self.timer_motion_max=3
        self.timer_motion=self.timer_motion_max
        self.drag_coordinates=None
        self.dfont = 22

        if package is None and controller is not None:
            package=controller.package
        self.__package=package
        self.widget = self.build_widget()

    def build_widget(self):
        #HPaned containing schema area and Type explorer and Constraint explorer
        self.hboxEspaceSchema = gtk.HPaned()
        #   schema area
        self.schemaArea = self.createSchemaArea()
        self.openedschemas = []
        self.hboxEspaceSchema.pack1(self.schemaArea, resize=True)

        vbox=gtk.VBox()
        #   type explorer
        self.TE= TypeExplorer(self.controller, self.controller.package)

        # Store (schema, schema title, is_displayed?)
        store=gtk.ListStore( object, str, bool )

        self.listeSchemas = gtk.TreeView(store)

        renderer = gtk.CellRendererText()
        column = gtk.TreeViewColumn(_('Schema'), renderer, text=1)
        column.set_resizable(True)

        self.listeSchemas.append_column(column)
        renderer = gtk.CellRendererToggle()
        renderer.set_property('activatable', True)

        def toggled_schema(rend, path, model, col):
            schema=model[path][0]
            if schema in self.openedschemas:
                # Undisplay
                self.removeSchemaFromArea(schema)
                model[path][col]=False
            else:
                if len(self.openedschemas) >= 4:
                    self.log("Too many opened schemas")
                    return True
                self.openSchema(schema)
                model[path][col]=True
            return True
        renderer.connect('toggled', toggled_schema, store, 2)
        column = gtk.TreeViewColumn(_('Display'), renderer, active=2)
        self.listeSchemas.append_column(column)
        self.listeSchemas.show_all()
        self.update_list_schemas()
        vbox.pack_start(self.listeSchemas, expand=False)

        def popup_menu(widget, event):
            retval = False
            button = event.button
            x = int(event.x)
            y = int(event.y)

            if button == 3:
                if event.window is widget.get_bin_window():
                    model = widget.get_model()
                    t = widget.get_path_at_pos(x, y)
                    if t is not None:
                        path, col, cx, cy = t
                        schema=model[path][0]
                        widget.get_selection().select_path(path)

                        menu=gtk.Menu()

                        i=gtk.MenuItem(_("Delete"))
                        i.connect("activate", lambda e: self.delSchema(schema))
                        menu.append(i)

                        menu.show_all()
                        menu.popup(None, None, None, button, event.time)
                        retval = True
            return retval

        self.listeSchemas.connect('button-press-event', popup_menu)

        vbox.add(self.TE)
        self.hboxEspaceSchema.pack2(vbox)
        #self.hboxEspaceSchema.set_position(150)
        self.hboxEspaceSchema.show_all()

        return self.hboxEspaceSchema

    def createSchemaArea(self):
        #Constraint explorer
        hboxConExplorer = gtk.HBox()
        labelConExplorer = gtk.Label("Constraint Explorer")
        hboxConExplorer.pack_start(labelConExplorer, expand=False)

        bg_color = gtk.gdk.Color (55000, 55000, 65535, 0)
        hbox = gtk.HBox (False, 4)
        #Create the canvas
        canvas = goocanvas.Canvas()
        canvas.modify_base (gtk.STATE_NORMAL, bg_color)
        canvas.set_bounds (0, 0, self.canvasX, self.canvasY)
        scrolled_win = gtk.ScrolledWindow ()
        scrolled_win.add(canvas)

        def on_background_scroll(widget, event):
            zoom=event.state & gtk.gdk.CONTROL_MASK
            if zoom:
                # Control+scroll: zoom in/out
                a = self.zoom_adj
                incr = -a.step_increment
            elif event.state & gtk.gdk.SHIFT_MASK:
                # Horizontal scroll
                a = scrolled_win.get_hadjustment()
                incr = a.step_increment
            else:
                # Vertical scroll
                a = scrolled_win.get_vadjustment()
                incr = a.step_increment

            if event.direction == gtk.gdk.SCROLL_DOWN:
                val = a.value + incr
                if val > a.upper - a.page_size:
                    val = a.upper - a.page_size
                elif val < a.lower:
                    val = a.lower
                if val != a.value:
                    a.value = val
            elif event.direction == gtk.gdk.SCROLL_UP:
                val = a.value - incr
                if val < a.lower:
                    val = a.lower
                elif val > a.upper - a.page_size:
                    val = a.upper - a.page_size
                if val != a.value:
                    a.value = val

            return True
        canvas.connect('scroll-event', on_background_scroll)

        def on_background_motion(widget, event):
            if not event.state & gtk.gdk.BUTTON1_MASK:
                return False
            if self.dragging:
                return False
            if not self.drag_coordinates:
                self.drag_coordinates=(event.x_root, event.y_root)
                return False
            x, y = self.drag_coordinates
            wa = widget.get_allocation()
            a=scrolled_win.get_hadjustment()
            v=a.value + x - event.x_root
            if v > a.lower and v+wa.width < a.upper:
                a.value=v
            a=scrolled_win.get_vadjustment()
            v=a.value + y - event.y_root
            if v > a.lower and v+wa.height < a.upper:
                a.value=v

            self.drag_coordinates= (event.x_root, event.y_root)
            return False
        canvas.connect('motion-notify-event', on_background_motion)

        self.canvas = canvas

        #Zoom
        w = gtk.Label ("Zoom:")
        hbox.pack_start (w, False, False, 0)
        self.zoom_adj = gtk.Adjustment(1, 0.2, 2, 0.1, 0.5)
        self.zoom_adj.connect('value-changed', self.zoom_changed, canvas)
        w = gtk.SpinButton (self.zoom_adj, 0.0, 2)
        w.set_size_request (50, -1)
        hbox.pack_start (w, False, False, 0)
        w = gtk.Button('A+')
        w.connect('clicked', self.font_up_clicked, canvas)
        hbox.pack_start (w, False, False, 0)
        w = gtk.Button('A-')
        w.connect('clicked', self.font_down_clicked, canvas)
        hbox.pack_start (w, False, False, 0)

        rotButton=get_pixmap_button('rotate.png', self.rotateSchemaAreas)
        rotButton.set_no_show_all(True)
        exchButton=get_pixmap_button('exchange.png', self.exchangeSchemaAreas)
        exchButton.set_no_show_all(True)
        hbox.pack_start(rotButton, False, False, 4)
        hbox.pack_start(exchButton, False, False, 4)
        self.hboxButton = hbox

        canvas.connect('size-allocate', self.sw_resize, self.zoom_adj)

        #schemaArea
        schemaArea = gtk.VBox(False, 4)
        schemaArea.set_border_width(4)
        schemaArea.pack_start (hbox, False, False, 0)
        schemaArea.pack_start (gtk.VSeparator(), expand=False)
        schemaArea.pack_start(scrolled_win, True, True, 0)
        schemaArea.pack_start(gtk.HSeparator(), expand=False)
        schemaArea.pack_start(hboxConExplorer, expand=False)

        return schemaArea

    def font_up_clicked(self, w, canvas):
        root = canvas.get_root_item ()
        for i in range(0, root.get_n_children()):
            if hasattr(root.get_child(i), 'type') and root.get_child(i).text:
                fontsize = root.get_child(i).fontsize
                self.dfont = root.get_child(i).fontsize = fontsize+3
                root.get_child(i).text.props.font="Sans Bold %s" % str(self.dfont)
        for i in self.findSchemaTitles(canvas):
            i.props.font = "Sans Bold %s" % str(self.dfont)
        return

    def font_down_clicked(self, w, canvas):
        root = canvas.get_root_item ()
        for i in range(0, root.get_n_children()):
            if hasattr(root.get_child(i), 'type') and root.get_child(i).text:
                fontsize = root.get_child(i).fontsize
                self.dfont = root.get_child(i).fontsize = fontsize-3
                if fontsize >3:
                    root.get_child(i).text.props.font="Sans Bold %s" % str(self.dfont)
        for i in self.findSchemaTitles(canvas):
            i.props.font = "Sans Bold %s" % str(self.dfont)
        return

    def sw_resize(self, w, size, adj):
        #print adj.get_value()
        self.swX = size.width
        self.swY = size.height
        self.canvasX=size.width*4
        self.canvasY=size.height*4
        self.canvas.set_bounds(0, 0, self.canvasX, self.canvasY)
        self.setup_canvas()
        #print self.canvas.get_bounds()
        #print "%s %s" % (size.width, size.height)

###
#
# Functions to update the gui when an event occurs
#
###

    def update_model(self, package):
        self.update_list_schemas()
        self.openedschemas=[]
        self.setup_canvas()
        return True

    def update_schema(self, schema=None, event=None):
        self.update_list_schemas()
        if schema in self.openedschemas:
            self.setup_canvas()
        return True

    def update_relation(self, relation=None, event=None):
        if event == 'RelationCreate' or event == 'RelationDelete':
            rt = relation.getType()
            sc = rt.getSchema()
            if sc in self.openedschemas:
                rtg = self.findRelationTypeGroup(rt.getId(),self.canvas)
                rtg.update()
        return True

    def update_annotation (self, annotation=None, event=None):
        if event == 'AnnotationCreate' or event == 'AnnotationDelete':
            at = annotation.getType()
            sc = at.getSchema()
            if sc in self.openedschemas:
                atg = self.findAnnotationTypeGroup(at.getId(),self.canvas)
                atg.update()
        return True

    def update_annotationtype(self, annotationtype=None, event=None):
        schema = annotationtype.getSchema()
        if schema in self.openedschemas:
            if event == 'AnnotationTypeCreate':
                atg = self.findAnnotationTypeGroup(annotationtype.getId(),self.canvas)
                if atg is None:
                    self.addAnnotationTypeGroup(canvas=self.canvas, schema=schema, type=annotationtype)
            elif event == 'AnnotationTypeDelete':
                atg = self.findAnnotationTypeGroup(annotationtype.getId(),self.canvas)
                if atg is not None:
                    atg.remove_drawing_only()
                if self.TE is not None and self.TE.type == annotationtype:
                    self.TE.initWithType(None)
            elif event == 'AnnotationTypeEditEnd':
                atg = self.findAnnotationTypeGroup(annotationtype.getId(),self.canvas)
                if atg is not None:
                    atg.update()
                if self.TE is not None and self.TE.type == annotationtype:
                    self.TE.initWithType(annotationtype)
        return True

    def update_relationtype(self, relationtype=None, event=None):
        schema = relationtype.getSchema()
        if schema in self.openedschemas:
            if event == 'RelationTypeCreate':
                rtg = self.findRelationTypeGroup(relationtype.getId(),self.canvas)
                if rtg is None:
                    self.addRelationTypeGroup(canvas=self.canvas, schema=schema, type=relationtype)
            elif event == 'RelationTypeDelete':
                rtg = self.findRelationTypeGroup(relationtype.getId(),self.canvas)
                if rtg is not None:
                    rtg.remove_drawing_only()
                if self.TE is not None and self.TE.type == relationtype:
                    self.TE.initWithType(None)
            elif event == 'RelationTypeEditEnd':
                rtg = self.findRelationTypeGroup(relationtype.getId(),self.canvas)
                if rtg is not None:
                    rtg.update()
                if self.TE is not None and self.TE.type == relationtype:
                    self.TE.initWithType(relationtype)
        return True

    def refresh(self, *p):
        self.update_model(None)
        return True

    def update_list_schemas(self):
        store=self.listeSchemas.get_model()
        store.clear()
        for s in self.controller.package.schemas:
            store.append( [ s, self.controller.get_title(s), s in self.openedschemas ] )

##
#
#   Functions to create and delete elements
#
##

    def newSchema(self, w):
        cr = CreateElementPopup(type_=Schema,
                                    parent=self.controller.package,
                                    controller=self.controller)
        schema=cr.popup(modal=True)
        if schema:
            self.update_list_schemas()
            self.openSchema(schema)

    def delSchema(self, sc):
        tsc = sc.title
        if (sc is None):
            return False
        if dialog.message_dialog(label="Voulez-vous effacer le schema %s ?" % tsc, icon=gtk.MESSAGE_QUESTION, callback=None):
            if sc in self.openedschemas:
                self.removeSchemaFromArea(sc)
            self.controller.delete_element(sc)
            self.update_list_schemas()
            return True
        else:
            return False

    def openSchema(self, schema):
        if (schema is None):
            print "Error opening schema : None"
            return
        if len(self.openedschemas)>=4:
            print "too many schemas opened, 4 max."
            return
        if schema not in self.openedschemas:
            self.addSchemaToArea(schema)
        else:
            print "schema already opened"
        return

    def addSchemaToArea(self, schema):
        self.openedschemas.append(schema)
        self.setup_canvas()
        return

    def removeSchemaFromArea(self, schema):
        self.openedschemas.remove(schema)
        self.setup_canvas()
        return

    def rotateSchemaAreas(self, w):
        temp=self.openedschemas.pop()
        self.openedschemas.insert(0,temp)
        self.setup_canvas()

    def exchangeSchemaAreas(self, w):
        t1 =self.openedschemas[0]
        self.openedschemas[0]=self.openedschemas[1]
        self.openedschemas[1]=t1
        self.setup_canvas()
        #print "Exchanged %s and %s" % (self.openedschemas[0].title, self.openedschemas[1].title)

    def addTransformButtons(self, nb_schemas):
        if nb_schemas < 3:
            self.hboxButton.foreach(lambda w: w.hide())
            self.hboxButton.show_all()
        else:
            self.hboxButton.foreach(lambda w: w.show())

    def setup_canvas (self):
        root = self.canvas.get_root_item ()
        root.connect('button-press-event', self.on_background_button_press)
        root.connect('button-release-event', self.on_background_button_release)
        #deleting old drawing
        while root.get_n_children()>0:
            root.remove_child (0)

        size = len(self.openedschemas)
        self.sepV = None
        self.sepH = None
        # add buttons to rotate and change schemas place
        self.addTransformButtons(size)
        if size<=0:
            #print "No schema to draw"
            return
        if size>4:
            print "More than 4 schema, fixme!!!"
            return
        if size==1:
            schema = self.openedschemas[0]
            self.draw_schema_annots(self.canvas, schema, 20, 60, self.canvasX, self.canvasY)
        if size==2:
            # vertical separation between the 2 schemas
            self.draw_schema_annots(self.canvas, self.openedschemas[0], 20, 60, self.canvasX/2, self.canvasY)
            p = goocanvas.Points ([(self.canvasX/2, 0), (self.canvasX/2, self.canvasY)])
            self.sepV = goocanvas.Polyline (parent = root,
                                        close_path = False,
                                        points = p,
                                        stroke_color = "black",
                                        line_width = 6.0,
                                        start_arrow = False,
                                        end_arrow = False
                                        )
            self.draw_schema_annots(self.canvas, self.openedschemas[1], 20+self.canvasX/2, 60, self.canvasX, self.canvasY)
        if size==3:
            # 1+1/1
            self.draw_schema_annots(self.canvas, self.openedschemas[0], 20, 60, self.canvasX/2, self.canvasY/2)
            p = goocanvas.Points ([(self.canvasX/2, 0), (self.canvasX/2, self.canvasY/2)])
            self.sepV = goocanvas.Polyline (parent = root,
                                        close_path = False,
                                        points = p,
                                        stroke_color = "black",
                                        line_width = 6.0,
                                        start_arrow = False,
                                        end_arrow = False
                                        )
            self.draw_schema_annots(self.canvas, self.openedschemas[1], 20+self.canvasX/2, 60, self.canvasX, self.canvasY/2)
            p = goocanvas.Points ([(0, self.canvasY/2), (self.canvasX, self.canvasY/2)])
            self.sepH = goocanvas.Polyline (parent = root,
                                        close_path = False,
                                        points = p,
                                        stroke_color = "black",
                                        line_width = 6.0,
                                        start_arrow = False,
                                        end_arrow = False
                                        )
            self.draw_schema_annots(self.canvas, self.openedschemas[2], 20, 60+self.canvasY/2, self.canvasX, self.canvasY)
        if size==4:
            self.draw_schema_annots(self.canvas, self.openedschemas[0], 20, 60, self.canvasX/2, self.canvasY/2)
            p = goocanvas.Points ([(self.canvasX/2, 0), (self.canvasX/2, self.canvasY)])
            self.sepV = goocanvas.Polyline (parent = root,
                                        close_path = False,
                                        points = p,
                                        stroke_color = "black",
                                        line_width = 6.0,
                                        start_arrow = False,
                                        end_arrow = False
                                        )
            self.draw_schema_annots(self.canvas, self.openedschemas[1], 20+self.canvasX/2, 60, self.canvasX, self.canvasY/2)
            self.draw_schema_annots(self.canvas, self.openedschemas[3], 20, 60+self.canvasY/2, self.canvasX/2, self.canvasY)
            p = goocanvas.Points ([(0, self.canvasY/2), (self.canvasX, self.canvasY/2)])
            self.sepH = goocanvas.Polyline (parent = root,
                                        close_path = False,
                                        points = p,
                                        stroke_color = "black",
                                        line_width = 6.0,
                                        start_arrow = False,
                                        end_arrow = False
                                        )
            self.draw_schema_annots(self.canvas, self.openedschemas[2], 20+self.canvasX/2, 60+self.canvasY/2, self.canvasX, self.canvasY)
        self.draw_schemas_rels(self.canvas, self.openedschemas)


    def draw_schemas_rels(self, canvas, schemas):
        r=0
        for sc in schemas:
            relTypes = sc.getRelationTypes()
            for j in relTypes:
                self.addRelationTypeGroup(canvas, sc, j.getTitle(), j)
                r=r+1
        #print "%s RelationTypes drawn" % r

    def draw_schema_annots(self, canvas, schema, xoffset, yoffset, xmax, ymax):
        self.addSchemaTitle(canvas, schema, xoffset+(xmax-xoffset)/2, yoffset+(ymax-yoffset)/2)
        annotTypes = schema.getAnnotationTypes()
        a=0
        b=0
        an=0
        for i in annotTypes:
            x = xoffset+b*300
            y = yoffset+a*80
            self.addAnnotationTypeGroup(canvas, schema, i.getTitle(), i, x, y)
            an=an+1
            if x+600<xmax:
                b=b+1
            elif y+160<ymax:
                b=0
                a=a+1
        #print "%s AnnotationTypes drawn" % an
        return

    def addSchemaTitle(self, canvas, schema, xx, yy):
        color = self.controller.get_element_color(schema)
        goocanvas.Text (parent = canvas.get_root_item (),
                                        text = schema.title,
                                        x = xx,
                                        y = yy,
                                        fill_color = color,
                                        width = -1,
                                        anchor = gtk.ANCHOR_CENTER,
                                        font = "Sans Bold %s" % str(self.dfont))

    def findSchemaTitles(self, canvas, schema=None):
        res = []
        root = canvas.get_root_item ()
        for i in range(0, root.get_n_children()):
            if isinstance(root.get_child(i), goocanvas.Text):
                if schema is None or schema.title == root.get_child(i).props.text:
                    res.append(root.get_child(i))
        return res

###
#
#  Functions to add remove modify RelationTypesGroup and redraw them when moving AnnotationTypeGroup
#
###
    def addRelationTypeGroup(self, canvas, schema, name=" ", type=None, members=[]):
        if schema is None:
            return
        cvgroup = RelationTypeGroup(self.controller, canvas, schema, name, type, members, self.dfont)
        if cvgroup is not None:
            self.setup_rel_signals (cvgroup)
            #self.drawFocusOn(cvgroup)
            #self.TE.initWithType(cvgroup.type)
        return cvgroup

    def findRelationTypeGroup(self, typeId, canvas):
        #Find relationGroup from type id
        root = canvas.get_root_item ()
        for i in range(0, root.get_n_children()):
            if hasattr(root.get_child(i), 'type') and root.get_child(i).type.id== typeId:
                return root.get_child(i)
        return None

    def findAnnotationTypeGroup(self, typeId, canvas):
        root = canvas.get_root_item ()
        for i in range(0, root.get_n_children()):
            if hasattr(root.get_child(i), 'type') and root.get_child(i).type.id == typeId:
                return root.get_child(i)
        return None

    def rel_redraw(self, rtg):
        rtg.redraw()

    def removeRelationTypeGroup(self, group):
        group.remove()

###
#
#  Functions to add remove modify AnnotationTypesGroup
#
###

    def addAnnotationTypeGroup(self, canvas, schema, name=" ", type=None, rx =None, ry=None):
        if schema is None:
            return
        part = self.openedschemas.index(schema)
        if rx is None or ry is None:
            if part == 0:
                rx = 20
                ry = 60
            if part == 1:
                rx = self.sepV.get_bounds().x2 + 20
                ry = 60
            if (part == 2 and len(self.openedschemas)==3) or part == 3:
                rx = 20
                ry = self.sepH.get_bounds().y2 + 60
            if part == 2 and len(self.openedschemas)==4:
                rx = self.sepV.get_bounds().x2 + 20
                ry = self.sepH.get_bounds().y2 + 60
        cvgroup = AnnotationTypeGroup(self.controller, canvas, schema, name, type, rx, ry, self.dfont)
        if cvgroup is not None:
            self.setup_annot_signals(cvgroup, schema)
            self.drawFocusOn(cvgroup.rect)
            self.TE.initWithType(cvgroup.type)
            #self.widget.set_focus(self.TE.TName)
        return cvgroup


    def removeAnnotationTypeGroup(self, group, schema):
        group.remove()
        ### FIXME : delete relation types based on this annotation type in other schemas

    def create_view_based_on(self, model_obj):
        id_= model_obj.id+'_view'
        title_= model_obj.title+' view'
        if self.controller.package._idgenerator.exists(id_):
            #on remplace le contenu
            print 'pas encore fait'
        else:
            self.controller.package._idgenerator.add(id_)
            el=self.controller.package.createView(
                ident=id_,
                author=config.data.userid,
                date=self.controller.get_timestamp(),
                clazz=self.controller.package.viewableClass,
                content_mimetype='text/html',
                )
            el.title=title_
            # contenu a adapter
            el.content.data=u'<h1>test</h1>'
            if isinstance(model_obj, Schema):
                el.content.data=u'<h1>Schema %s</h1>\n' % model_obj.title
                el.content.data += u'<p>Containing the following Annotation Types:</p>\n<ul>\n'
                for at in model_obj.annotationTypes:
                    el.content.data += u'<li>%s (%s)</li>\n' % (at, len(at.annotations))
                el.content.data += u'</ul><p>And the following Relation Types:</p>\n<ul>\n'
                for rt in model_obj.relationTypes:
                    el.content.data += u'<li>%s (%s)</li>\n' % (rt, len(rt.relations))
                el.content.data += u'</ul>\n'
            # elif isinstance(model_obj, AnnotationType):
            # elif isinstance(model_obj, RelationType):
            self.controller.package.views.append(el)
            self.controller.notify('ViewCreate', view=el)

        print id_
###
#
#  Functions to handle notification signals
#
###

    def setup_rel_signals (self, item):
        #pour capter les events sur les relations du dessin
        #item.connect ("motion_notify_event", self.rel_on_motion_notify)
        item.connect ('button-press-event', self.rel_on_button_press)
        item.connect ('button-release-event', self.rel_on_button_release)


    def setup_annot_signals (self, item, schema):
        #pour capter les events sur les annotations du dessin
        item.connect ('motion-notify-event', self.annot_on_motion_notify)
        item.connect ('button-press-event', self.annot_on_button_press, schema)
        item.connect ('button-release-event', self.annot_on_button_release)


    def rel_on_button_press (self, item, target, event):
        self.TE.initWithType(item.type)
        self.drawFocusOn(item.line)
        if event.button == 1:
            if event.type == gtk.gdk._2BUTTON_PRESS:
                self.controller.gui.open_adhoc_view('generictable', elements=item.type.relations)
                canvas = item.get_canvas ()
                canvas.pointer_ungrab (item, event.time)
                self.dragging = False
                return True
            self.drag_x = event.x
            self.drag_y = event.y
            fleur = gtk.gdk.Cursor (gtk.gdk.FLEUR)
            canvas = item.get_canvas ()
            canvas.pointer_grab (item,
                                gtk.gdk.POINTER_MOTION_MASK | gtk.gdk.BUTTON_RELEASE_MASK,
                                fleur,
                                event.time)
            self.dragging = True
        elif event.button == 3:
            def menuRem(w, item):
                self.removeRelationTypeGroup(item)
                return True
            def menuView(w, item):
                self.create_view_based_on(item.type)

            m=advene.gui.popup.Menu(element=item.type, controller=self.controller)
            menu=m.menu

            itemM = gtk.MenuItem(_("Remove relation type"))
            itemM.connect('activate', menuRem, item )
            menu.insert(itemM, 1)
            itemM = gtk.MenuItem(_("Create HTML view"))
            itemM.connect('activate', menuView, item )
            menu.insert(itemM, 1)
            menu.show_all()
            m.popup()
        return True

    def rel_on_button_release (self, item, target, event):
        canvas = item.get_canvas ()
        canvas.pointer_ungrab (item, event.time)
        self.dragging = False

###
#
#  events on annotationTypeGroup
#
###

    def annot_on_motion_notify (self, item, target, event):
        if (self.dragging == True) and (event.state & gtk.gdk.BUTTON1_MASK):
            new_x = event.x
            new_y = event.y
            item.translate (new_x - self.drag_x, new_y - self.drag_y)
            # Hack not to redraw at every step
            self.timer_motion= self.timer_motion-1
            if self.timer_motion<=0:
                self.timer_motion=self.timer_motion_max
                for rtg in item.rels:
                    self.rel_redraw(rtg)
        return True

    def annot_on_button_press (self, item, target, event, schema):
        self.TE.initWithType(item.type)
        self.drawFocusOn(item.rect)
        if event.button == 1:
            if event.type == gtk.gdk._2BUTTON_PRESS:
                self.controller.gui.open_adhoc_view('table', elements=item.type.annotations)
                canvas = item.get_canvas ()
                canvas.pointer_ungrab (item, event.time)
                self.dragging = False
                return True
            self.drag_x = event.x
            self.drag_y = event.y
            self.orig_x = item.rect.get_bounds().x1
            self.orig_y = item.rect.get_bounds().y1
            self.timer_motion=self.timer_motion_max
            fleur = gtk.gdk.Cursor (gtk.gdk.FLEUR)
            canvas = item.get_canvas ()
            canvas.pointer_grab (item,
                                    gtk.gdk.POINTER_MOTION_MASK | gtk.gdk.BUTTON_RELEASE_MASK,
                                    fleur,
                                    event.time)
            self.dragging = True
        elif event.button == 3:
            def menuRem(w, item, schema):
                self.removeAnnotationTypeGroup(item, schema)
                return True
            def menuNew(w, item, schema, member2):
                mem = []
                mem.append(item.type)
                mem.append(member2)
                self.addRelationTypeGroup(item.get_canvas(), schema, members=mem)
                return True
            m=advene.gui.popup.Menu(element=item.type, controller=self.controller)
            menu=m.menu
            menu.insert(gtk.SeparatorMenuItem(), 1)
            itemM = gtk.MenuItem(_("Remove annotation type"))
            itemM.connect('activate', menuRem, item, schema )
            menu.insert(itemM, 2)
            itemM = gtk.MenuItem(_("Create relation type between this one and..."))
            ssmenu = gtk.Menu()
            itemM.set_submenu(ssmenu)
            for s in self.controller.package.getSchemas():
                sssmenu = gtk.Menu()
                itemSM = gtk.MenuItem(s.title)
                itemSM.set_submenu(sssmenu)
                for a in s.getAnnotationTypes():
                    itemSSM = gtk.MenuItem(a.title)
                    itemSSM.connect('activate', menuNew, item, schema, a )
                    sssmenu.append(itemSSM)
                ssmenu.append(itemSM)
            menu.insert(itemM, 3)
            menu.show_all()
            m.popup()
        return True

    def findGroupFromXY(self,x,y):
        root = self.canvas.get_root_item ()
        for i in range(0, root.get_n_children()):
            if hasattr(root.get_child(i), 'rect'):
                x1 = root.get_child(i).get_bounds().x1
                x2 = root.get_child(i).get_bounds().x2
                y1 = root.get_child(i).get_bounds().y1
                y2 = root.get_child(i).get_bounds().y2
                if x>x1 and x<x2 and y>y1 and y<y2:
                    return root.get_child(i)
        return None

    def annot_on_button_release (self, item, target, event):
        canvas = item.get_canvas ()
        canvas.pointer_ungrab (item, event.time)
        self.dragging = False
        if (event.state & gtk.gdk.CONTROL_MASK):
            dropObj = self.findGroupFromXY(item.get_bounds().x1,
                                            item.get_bounds().y1)
            x = item.rect.get_bounds().x1
            y = item.rect.get_bounds().y1
            item.translate (self.orig_x - x, self.orig_y - y)
            # HACK : to avoid to redraw relations before the item goes back to origin
            while item.get_bounds().x1 != self.orig_x and item.get_bounds().y1 != self.orig_y:
                pass
            if dropObj is not None and dropObj.type is not None:
                #print "creating relation between %s and %s" % (item.type, dropObj.type)
                self.addRelationTypeGroup(self.canvas, item.type.getSchema(), name="New Relation", type=None, members=[item.type,dropObj.type])

        # TODO
        # events drag & drop non implemantes pour goocanvas.group
        # drag-motion : on arrive dessus
        # drag-leave : on en part
        # drag-data-received quand on lache sur un objet
        # ...
        else:
            x = item.rect.get_bounds().x1
            y = item.rect.get_bounds().y1
            newsc = self.findSchemaFromXY(x, y)
            oldsc = item.type.getSchema()
            if oldsc != newsc:
                #if (dialog.message_dialog(label="Do you want to move %s to the %s schema ?" % (item.type.title, newsc.title), icon=gtk.MESSAGE_QUESTION, callback=None)):
                # gerer si des types de relation sont accroches
                #    print "todo"
                #    oldsc.annotationTypes.remove(item.type)
                #    newsc.annotationTypes.append(item.type)
                #    item.type.setSchema(newsc)
                #    self.controller.notify("SchemaEditEnd",schema=oldsc,comment="AnnotationType removed")
                #    self.controller.notify("SchemaEditEnd",schema=newsc,comment="AnnotationType added")
                #    self.controller.notify("AnnotationTypeEditEnd",annotationtype=item.type,comment="Schema changed")
                # notify
                # __parent apparemment en lecture seule,
                # si on ne peut pas, oblige de supprimer le type
                # et en creer un nouveau
                #else:
                item.translate (self.orig_x - x, self.orig_y - y)
                    # HACK : to avoid to redraw relations before the item goes back to origin
                while item.get_bounds().x1 != self.orig_x and item.get_bounds().y1 != self.orig_y:
                    pass
        # Relations redraw
        for rtg in item.rels:
            self.rel_redraw(rtg)

###
#
#  events on background
#
###

    def findSchemaFromXY(self, x, y):
        size=len(self.openedschemas)
        if size<=0 or size>4:
            return None
        if size==1:
            return self.openedschemas[0]
        if size==2:
            if x>self.sepV.get_bounds().x2:
                return self.openedschemas[1]
            return self.openedschemas[0]
        if size==3:
            if y>self.sepH.get_bounds().y2:
                return self.openedschemas[2]
            if x>self.sepV.get_bounds().x2:
                return self.openedschemas[1]
            return self.openedschemas[0]
        if size==4:
            #
            #       1  |  2
            #       ___|___
            #          |
            #       4  |  3
            #
            if x>self.sepV.get_bounds().x2 and y>self.sepH.get_bounds().y2:
                return self.openedschemas[2]
            if x>self.sepV.get_bounds().x2 and y<self.sepH.get_bounds().y1:
                return self.openedschemas[1]
            if x<self.sepV.get_bounds().x1 and y >self.sepH.get_bounds().y2:
                return self.openedschemas[3]
            return self.openedschemas[0]
        return None

    def on_background_button_release(self, item, widget, event):
        if event.button == 1:
            self.drag_coordinates=None
        return False

    def on_background_button_press (self, item, target, event):
        if event.button != 3:
            return False

        self.TE.initWithType(None)
        openedschema = True
        if len(self.openedschemas)<=0:
            openedschema=False
        canvas = item.get_canvas()
        self.drawFocusOn(canvas)
        schema = self.findSchemaFromXY(event.x, event.y)
        menu = gtk.Menu()
        itemM = gtk.MenuItem(_("New schema"))
        itemM.connect("activate", self.newSchema )
        menu.append(itemM)
        if openedschema:
            def newRel(w, canvas, schema):
                self.addRelationTypeGroup(canvas, schema)
                return True
            def newAnn(w, canvas, schema, x, y):
                self.addAnnotationTypeGroup(canvas, schema, rx=x, ry=y)
                return True
            def pick_color(w, schema):
                self.controller.gui.update_color(schema)
            def hide(w, schema):
                self.removeSchemaFromArea(schema)
            def menuView(w, schema):
                self.create_view_based_on(schema)
            itemM = gtk.MenuItem(_("Select a color"))
            itemM.connect('activate', pick_color, schema)
            menu.append(itemM)
            itemM = gtk.MenuItem(_("New annotation type"))
            itemM.connect('activate', newAnn, canvas, schema, event.x, event.y )
            menu.append(itemM)
            itemM = gtk.MenuItem(_("New relation type"))
            itemM.connect('activate', newRel, canvas, schema )
            menu.append(itemM)
            itemM = gtk.MenuItem(_("Hide this schema"))
            itemM.connect('activate', hide, schema )
            menu.append(itemM)
            itemM = gtk.MenuItem(_("Create HTML view"))
            itemM.connect('activate', menuView, schema )
            menu.append(itemM)
            itemM = gtk.MenuItem(_("Export drawing to pdf"))
            itemM.connect('activate', self.export_to_pdf, canvas)
            menu.append(itemM)
        #itemM = gtk.MenuItem(_("Move annotation type from Schema..."))
        #itemM.connect("activate", menuMove, canvas )
        #menu.append(itemM)
        menu.show_all()
        menu.popup(None, None, None, 0, gtk.get_current_event_time())
        return True

    def drawFocusOn(self, item):
        #print "focus on %s" % item
        canvas=None
        if isinstance(item, goocanvas.Canvas):
            canvas=item
        else:
            canvas = item.get_canvas()
            item.props.line_width = 4.0

        root = canvas.get_root_item()

        for i in range(root.get_n_children()):
            if hasattr(root.get_child(i), 'rect'):
                ite=root.get_child(i).rect
            elif hasattr(root.get_child(i), 'line'):
                ite=root.get_child(i).line
            else:
                ite=None
            if ite is not None and ite != item:
                ite.props.line_width = 2.0

    def zoom_changed (self, adj, canvas):
        canvas.set_scale (adj.get_value()/4)



    def export_to_pdf (self, w, canvas):

        nompdf = config.data.path['settings']
        for sc in self.openedschemas:
            nompdf += sc.id + '_'
        nompdf += u'.pdf'
        name=dialog.get_filename(title=_("Choose a filename to export the schema as PDF"),
                                 action=gtk.FILE_CHOOSER_ACTION_SAVE,
                                 button=gtk.STOCK_SAVE,
                                 default_file=nompdf,
                                 filter='any')
        if name is None:
            return
        surface = cairo.PDFSurface (name, self.canvasX, self.canvasY)
        cr = cairo.Context (surface)
        #cr.translate (20, 130)
        #if we want to export only 1/4 schema, we need to change X, Y and translate the frame to the middle of the screen
        canvas.render (cr, None, 1.0)
        cr.show_page ()
        dialog.message_dialog(u"%s exported" % name)

### Type Explorer class
class TypeExplorer (gtk.ScrolledWindow):
    def __init__ (self, controller=None, package=None):
        gtk.ScrolledWindow.__init__(self)
        self.controller=controller
        self.type=None
        if package is None and controller is not None:
            package=controller.package
        vbox=gtk.VBox()
        hboxNom = gtk.HBox()
        labelNom = gtk.Label("Title : ")
        entryNom = gtk.Entry()
        self.TName = entryNom
        hboxNom.pack_start(labelNom)
        hboxNom.pack_start(entryNom)
        hboxAddAtt = gtk.HBox()
        labelAddAtt = gtk.Label("Add attribute")
        boutonAddAtt = gtk.Button("Add")
        boutonAddAtt.connect('clicked', self.addAttributeSpace )
        hboxAddAtt.pack_start(labelAddAtt)
        hboxAddAtt.pack_start(boutonAddAtt)
        hboxMime = gtk.HBox()
        labelMime = gtk.Label("Mime Type : ")
        self.TMimeType = dialog.list_selector_widget(
            members=[ ('text/plain', _("Plain text content")),
                              ('application/x-advene-structured', _("Simple-structured content")),
                              ('application/x-advene-zone', _("Rectangular zone content")),
                              ('image/svg+xml', _("SVG graphics content")),
                              ])
        # a remplacer par la selection de type Mime
        hboxMime.pack_start(labelMime)
        hboxMime.pack_start(self.TMimeType)
        hboxColor = gtk.HBox()
        self.bcol = gtk.ColorButton()
        self.bcol.set_use_alpha(False)
        self.bcol.connect('color-set', self.colorChange)
        self.entryCol = gtk.Entry()
        self.entryCol.connect('changed', self.colorTextChange)
        hboxColor.pack_start(self.bcol)
        hboxColor.pack_start(self.entryCol)
        hboxDesc = gtk.HBox()
        labelDesc = gtk.Label("Description : ")
        entryDesc = gtk.Entry()
        self.TDesc = entryDesc
        hboxDesc. pack_start(labelDesc)
        hboxDesc. pack_start(entryDesc)
        hboxId = gtk.HBox()
        labelId1 = gtk.Label("Id :")
        labelId2 = gtk.Label("")
        self.TId = labelId2
        hboxId.pack_start(labelId1)
        hboxId.pack_start(labelId2)
        labelAtt = gtk.Label("Attributes : ")
        labelTypeExplorer = gtk.Label("Type Explorer")
        espaceAtt = gtk.VBox()
        self.TAttsSpace = espaceAtt
        self.TAtts = []
        espaceBoutons = gtk.HBox()
        self.boutonSave = gtk.Button("Save")
        self.boutonSave.connect('clicked', self.saveType)
        self.boutonCancel = gtk.Button("Cancel")
        self.boutonCancel.connect('clicked', self.cancelType )
        espaceBoutons.pack_end(self.boutonCancel, expand=False, fill=False)
        espaceBoutons.pack_end(self.boutonSave, expand=False, fill=False)
        vbox.pack_start(labelTypeExplorer, expand=False)
        vbox.pack_start(gtk.HSeparator(), expand=False)
        vbox.pack_start(hboxId, expand=False)
        vbox.pack_start(gtk.HSeparator(), expand=False)
        vbox.pack_start(hboxNom, expand=False)
        vbox.pack_start(gtk.HSeparator(), expand=False)
        vbox.pack_start(hboxMime, expand=False, fill=False)
        vbox.pack_start(gtk.HSeparator(), expand=False)
        vbox.pack_start(hboxColor, expand=False, fill=False)
        vbox.pack_start(gtk.HSeparator(), expand=False)
        #vbox.pack_start(hboxAddAtt, expand=False, fill=False)
        #vbox.pack_start(gtk.HSeparator(), expand=False)
        #vbox.pack_start(labelAtt, expand=False, fill=False)
        #vbox.pack_start(espaceAtt, expand=False, fill=False)
        #vbox.pack_start(gtk.HSeparator(), expand=False)
        vbox.pack_start(espaceBoutons, expand=False, fill=False)
        self.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.add_with_viewport(vbox)
        self.initWithType(None)


    def colorTextChange(self, w):
        col = self.entryCol.get_text()
        color=name2color(col)
        if color is not None:
            self.bcol.set_color(color)

    def colorChange(self, but):
        col=self.bcol.get_color()
        self.entryCol.set_text("#%04x%04x%04x" % (col.red, col.green, col.blue))

    def refresh(self, *p):
        return True

    def setTypeDesc(self, desc=""):
        if desc is None:
            return False
        self.TDesc.set_text(desc)
        return True

    def getTypeDesc(self):
        return self.TDesc.get_text()

    def setTypeColor(self, v):
        if v is None :
            v="#000000000000"
        try:
            gtk_color=name2color(v)
            self.bcol.set_color(gtk_color)
        except:
            print "exception in color change"
            pass
        col=self.bcol.get_color()
        self.entryCol.set_text("#%04x%04x%04x" % (col.red, col.green, col.blue))
        return True

    def getTypeColor(self):
        return self.bcol.get_color()

    def getTypeId(self):
        return self.TId.get_text()

    def setTypeId(self, name=""):
        if (name is None):
            return False
        self.TId.set_text(name)
        return True

    def getTypeName(self):
        return self.TName.get_text()

    def setTypeName(self, name=""):
        if (name is None):
            return False
        self.TName.set_text(name)
        return True

    def getMimeType(self):
        m = self.TMimeType.get_current_element()
        return m

    def setMimeType(self, mimetype):
        store, i = dialog.generate_list_model( elements = [ ('text/plain', _("Plain text content")),
                              ('application/x-advene-structured', _("Simple-structured content")),
                              ('application/x-advene-zone', _("Rectangular zone content")),
                              ('image/svg+xml', _("SVG graphics content")),
                              ],active_element=mimetype)
        self.TMimeType.set_model(store)
        if i is None:
            i = store.get_iter_first()
        if i is not None:
            self.TMimeType.set_active_iter(i)
        return True

    def addAttributeSpace(self, w, nom="New Attribute", type="None", con=""):
        #ajouter eventuellement un contenu directement avec x params
        #print "%s" % len(self.get_children()[0].get_children()[0].get_children())
        boxAtt = gtk.HBox()
        eNom = gtk.Entry()
        eNom.set_text(nom)
        eNom.set_size_request(100, 20)
        eType = gtk.combo_box_new_text()
        eType.append_text("None") # ajouter tous les types et focus sur le type type
        eContrainte = gtk.Entry() # liste + entry ? bouton + fenetre pour creer ?
        eContrainte.set_text(con)
        eContrainte.set_size_request(50, 20)
        bSuppr = gtk.Button("Remove")
        bSuppr.set_size_request(50, 20)
        boxAtt.pack_start(eNom)
        boxAtt.pack_start(eType)
        boxAtt.pack_start(eContrainte)
        boxAtt.pack_start(bSuppr)
        self.TAtts.append(boxAtt)
        self.TAttsSpace.pack_start(boxAtt)
        self.TAttsSpace.show_all()
        return True

    def initWithType(self, type):
        if type is None:
            # tout remettre a vide
            self.type=None
            self.setTypeName("")
            self.setTypeId("")
            self.setMimeType("")
            self.setTypeColor(None)
            self.setTypeDesc("")
            self.TName.set_sensitive(False)
            self.bcol.set_sensitive(False)
            self.entryCol.set_sensitive(False)
            self.TMimeType.set_sensitive(False)
            return True
        self.TName.set_sensitive(True)
        self.bcol.set_sensitive(True)
        self.entryCol.set_sensitive(True)
        self.TMimeType.set_sensitive(True)
        self.type = type
        self.setTypeName(self.type.title)
        self.setTypeId(self.type.id)
        self.setMimeType(self.type.mimetype)
        self.setTypeDesc("Non dipsonible actuellement")
        self.setTypeColor(self.controller.get_element_color(self.type))
        #boucle sur les attributs pour creer et remplir les lignes
        #if (self.type.mimetype=='application/x-advene-relaxNG'):
            # appel de la fonction qui parse l'arbre
            # pour chaque element attribut, appel de la fonction qui ajoute une case aux attributs.
        #    pass
        self.TName.grab_focus()
        return True

    def saveType(self, button):
        if self.type is None:
            return
        self.type.title=self.getTypeName()
        self.type.mimetype=self.getMimeType()
        col = self.getTypeColor()
        try:
            self.type.setMetaData(config.data.namespace, 'color', u"string:#%04x%04x%04x" % (col.red,col.green,col.blue))
        except:
            print "Error saving color for %s" % self.type

        if isinstance(self.type, AnnotationType):
            self.controller.notify('AnnotationTypeEditEnd', annotationtype=self.type)
        elif isinstance(self.type, RelationType):
            self.controller.notify('RelationTypeEditEnd', relationtype=self.type)
        #save attributes
        # send controller an event

    def cancelType(self, button):
        self.initWithType(self.type)

class AnnotationTypeGroup (Group):
    def __init__(self, controller=None, canvas=None, schema=None, name=" ", type=None, rx =0, ry=0, fontsize=22):
        Group.__init__(self, parent = canvas.get_root_item ())
        self.controller=controller
        self.schema=schema
        self.name=name
        self.type=type
        self.rect = None
        self.text = None
        self.color = "black"
        self.fontsize=fontsize
        self.rels=[] # rel groups
        if type is None:
            id_ = self.controller.package._idgenerator.get_id(AnnotationType)
            self.controller.package._idgenerator.add(id_)
            el=self.schema.createAnnotationType(
                    ident=id_)
            el.author=config.data.userid
            el.date=self.controller.get_timestamp()
            el.title=id_
            el.mimetype='text/plain'
            el.setMetaData(config.data.namespace, 'color', self.schema.rootPackage._color_palette.next())
            el.setMetaData(config.data.namespace, 'item_color', 'here/tag_color')
            self.schema.annotationTypes.append(el)
            self.controller.notify('AnnotationTypeCreate', annotationtype=el)
            if el is None:
                return None
            self.type=el
        self.name=self.type.title
        nbannot = len(self.type.getAnnotations())
        if (self.controller.get_element_color(self.type) is not None):
            self.color = self.controller.get_element_color(self.type)

        self.rect = self.newRect (rx,ry,self.color)
        self.text = self.newText (self.formattedName(),rx+5,ry+30)

    def formattedName(self):
        nbann = str(len(self.type.getAnnotations()))
        if len(self.name)+len(nbann)>17:
            e = 16-len(nbann)
            return self.name[0:e] + ".. ("+nbann+")"
        return self.name + " ("+nbann+")"

    def newRect(self, xx, yy, color):
        return goocanvas.Rect (parent = self,
                                    x = xx,
                                    y = yy,
                                    width = 280,
                                    height = 60,
                                    fill_color_rgba = 0x3cb37150,
                                    stroke_color = color,
                                    line_width = 2.0)

    def newText(self, txt, xx, yy):
        return goocanvas.Text (parent = self,
                                        text = txt,
                                        x = xx,
                                        y = yy,
                                        width = -1,
                                        anchor = gtk.ANCHOR_W,
                                        font = "Sans Bold %s" % str(self.fontsize))

    def remove(self):
        while (len(self.rels)>0):
            self.rels[0].remove()
        self.controller.delete_element(self.type)
        self.remove_drawing_only()

    def remove_drawing_only(self):
        for rel in self.rels:
            rel.remove_drawing_only()
        parent = self.get_parent()
        child_num = parent.find_child (self)
        parent.remove_child (child_num)

    def update(self):
        self.name=self.type.title
        self.color = "black"
        if (self.controller.get_element_color(self.type) is not None):
            self.color = self.controller.get_element_color(self.type)
            if self.rect is not None:
                self.rect.props.stroke_color = self.color
        if self.text is not None:
            self.text.props.text = self.formattedName()

class RelationTypeGroup (Group):
    def __init__(self, controller=None, canvas=None, schema=None, name=" ", type=None, members=[], fontsize=22):
        Group.__init__(self, parent = canvas.get_root_item ())
        self.controller=controller
        self.schema=schema
        self.name=name
        self.type=type
        self.line=None
        self.text=None
        self.fontsize=fontsize
        self.color = "black"
        self.members=members
        if self.type is None:
            cr=CreateElementPopup(type_=RelationType,
                                    parent=schema,
                                    controller=self.controller)
            rt=cr.popup(modal=True)
            if rt is None:
                return None
            self.type=rt
            if not self.members:
                self.controller.gui.edit_element(self.type)
            else:
                # FIXME if more than 2 members
                self.type.hackedMemberTypes=( '#' + self.members[0].id, '#' + self.members[1].id )
                #need to propagate edition event
        linked = self.type.getHackedMemberTypes()
        #print "%s %s %s %s %s" % (self.type, self.name, self.schema, self.members, linked)
        #print "%s" % self.members
        self.members=[]
        for i in linked:
            # Add annotations types to members
            typeA = self.getIdFromURI(i)
            typ = helper.get_id(self.controller.package.getAnnotationTypes(), typeA)
            #print "%s" % typ
            if typ is not None:
                self.members.append(typ)
                #print "%s %s %s %s" % (i, typeA, typ, self.members)
        #print "%s" % self.members
        self.name=self.type.title
        self.color = "black"
        if (self.controller.get_element_color(self.type) is not None):
            self.color = self.controller.get_element_color(self.type)
        temp=[]
        for i in self.members:
            gr = self.findAnnotationTypeGroup(i.id, canvas)
            #print "%s %s" % i.id, gr
            x=1
            y=1
            w=0
            h=0
            if gr is not None:
                x = gr.rect.get_bounds().x1
                y = gr.rect.get_bounds().y1
                w = gr.rect.props.width
                h = gr.rect.props.height
                if self not in gr.rels:
                    gr.rels.append(self)
            # 8 points of rect
            temp.append([[x+w/2,y],[x+w/2,y+h],[x,y+h/2],[x+w,y+h/2],[x,y],[x+w,y],[x+w,y+h],[x,y+h]])
        if len(temp)<2:
            self.line=None
            self.text=None
            return None
        # FIXME if more than 2 linked types
        it=0
        x1,y1,x2,y2,d = self.distMin(temp[it],temp[it+1])

        if d==0:
            # verify slot to attach the relation on annotation type before doing that
            p = goocanvas.Points ([(x1, y1), (x1,y1-40), (x1+30, y1-40), (x2+30, y2)])
        else:
            p = goocanvas.Points ([(x1, y1), (x2, y2)])
        #ligne
        self.line = self.newLine (p,self.color)
        if (d==0):
            self.text = self.newText (self.formattedName(),x1+15,y1-40)	
        else:
            self.text = self.newText (self.formattedName(),(x1+x2)/2, (y1+y2)/2)


    def formattedName(self):
        nbrel = str(len(self.type.getRelations()))
        #if len(self.name)+len(nbrel)>17:
        #    e = 16-len(nbrel)
        #    return self.name[0:e] + ".. ("+nbrel+")"
        return self.name + " ("+str(nbrel)+")"

    def newText(self, txt, xx, yy):
        return goocanvas.Text (parent = self,
                                        text = txt,
                                        x = xx,
                                        y = yy,
                                        width = -1,
                                        anchor = gtk.ANCHOR_CENTER,
                                        font = "Sans Bold %s" % str(self.fontsize))
    def newLine(self, p, color):
        return goocanvas.Polyline (parent = self,
                                        close_path = False,
                                        points = p,
                                        stroke_color = color,
                                        line_width = 3.0,
                                        start_arrow = False,
                                        end_arrow = True,
                                        arrow_tip_length =3.0,
                                        arrow_length = 4.0,
                                        arrow_width = 3.0
                                        )

    #FIXME : hack to find id from type's uri
    def getIdFromURI(self, uri):
        return uri[1:]

    def findAnnotationTypeGroup(self, typeId, canvas):
        root = canvas.get_root_item ()
        for i in range(0, root.get_n_children()):
            if hasattr(root.get_child(i), 'type') and root.get_child(i).type.id == typeId:
                return root.get_child(i)
        return None

    # function to calculate min distance between x points
    def distMin(self,l1,l2):
        d=-1
        xd1=xd2=yd1=yd2=0
        for i in range(len(l1)):
            x1 = l1[i][0]
            y1 = l1[i][1]
            for j in range(len(l2)):
                x2 = l2[j][0]
                y2 = l2[j][1]
                nd=sqrt((x2-x1)*(x2-x1)+(y2-y1)*(y2-y1))
                if ((d==-1) or (nd < d)):
                    d = nd
                    xd1 = x1
                    xd2 = x2
                    yd1 = y1
                    yd2 = y2
        return xd1,yd1,xd2,yd2,d

    def redraw(self):
        #print self.members
        temp=[]
        for i in self.members:
            gr = self.findAnnotationTypeGroup(i.id, self.get_canvas())
            x=1
            y=1
            w=0
            h=0
            if gr is not None:
                x = gr.rect.get_bounds().x1
                y = gr.rect.get_bounds().y1
                w = gr.rect.props.width
                h = gr.rect.props.height
                if self not in gr.rels:
                    gr.rels.append(self)
            # 8 points
            temp.append([[x+w/2,y],[x+w/2,y+h],[x,y+h/2],[x+w,y+h/2],[x,y],[x+w,y],[x+w,y+h],[x,y+h]])
        if len(temp)<2:
            self.line=None
            self.text=None
            return None
        x1,y1,x2,y2,d = self.distMin(temp[0],temp[1])
        nbrel = len(self.type.getRelations())
        if d==0:
            # modifier en fonction du slot
            p = goocanvas.Points ([(x1, y1), (x1,y1-40), (x1+30, y1-40), (x2+30, y2)])
            if self.text is None:
                self.text = self.newText (self.formattedName(),x1,y1)	
            self.text.translate(x1-130-self.text.get_bounds().x1, y1-60-self.text.get_bounds().y1)
        else:
            p = goocanvas.Points ([(x1, y1), (x2, y2)])
            if self.text is None:
                self.text = self.newText (self.formattedName(),(x1+x2)/2, (y1+y2)/2)
            self.text.translate((x1+x2)/2-self.text.get_bounds().x1, (y1+y2)/2-self.text.get_bounds().y1)
        if self.line  is None:
            self.line = self.newLine (p,self.color)
        self.line.props.points=p

    def remove(self):
        self.controller.delete_element(self.type)
        self.remove_drawing_only()

    def remove_drawing_only(self):
        for i in self.members:
            gr = self.findAnnotationTypeGroup(i.id, self.get_canvas())
            if gr is not None and self in gr.rels:
                gr.rels.remove(self)
            else:
                #Annotation group outside schema
                #we don't remove the link because it doesn't have one
                print "%s n'est pas dans ce schema ou a deja ete traite" % i.id
        parent = self.get_parent()
        child_num = parent.find_child (self)
        parent.remove_child(child_num)

    def update(self):
        linked = self.type.getHackedMemberTypes()
        self.members=[]
        for i in linked:
            # Add annotations types to members
            typeA = self.getIdFromURI(i)
            typ = helper.get_id(self.controller.package.getAnnotationTypes(), typeA)
            if typ is not None:
                self.members.append(typ)
        self.name=self.type.title
        self.color = "black"
        if (self.controller.get_element_color(self.type) is not None):
            self.color = self.controller.get_element_color(self.type)
            if self.line is not None:
                self.line.props.stroke_color = self.color
        if self.text is not None:
            nbrel = len(self.type.getRelations())
            self.text.props.text = self.formattedName()
        self.redraw()


