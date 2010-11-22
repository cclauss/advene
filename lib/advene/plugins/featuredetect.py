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
name="Feature detection importer"

from gettext import gettext as _

import os

try:
    import cv
except ImportError:
    cv = None

import advene.core.config as config
from advene.util.importer import GenericImporter

def register(controller=None):
    if cv:
        controller.register_importer(FeatureDetectImporter)
    return True

class FeatureDetectImporter(GenericImporter):
    name = _("Feature detection (face...)")

    def __init__(self, *p, **kw):
        super(FeatureDetectImporter, self).__init__(*p, **kw)

        self.threshold = 10
        self.scale = 2
        classifiers = [ n.replace('.xml', '') for n in os.listdir(config.data.advenefile('haars')) ]
        self.classifier = classifiers[0]
        
        self.optionparser.add_option("-t", "--threshold",
                                     action="store", type="int", dest="threshold", default=self.threshold,
                                     help=_("Sensitivity level."))
        self.optionparser.add_option("-s", "--scale",
                                     action="store", type="int", dest="scale", default=self.scale,
                                     help=_("Scale. Original image size will be divided by this factor, in order to speed up detection."))
        self.optionparser.add_option("-c", "--classifier",
                                     action="store", type="choice", dest="classifier", choices=classifiers, default=self.classifier,
                                     help=_("Classifier"))

    def can_handle(fname):
        """Return a score between 0 and 100.

        100 is for the best match (specific extension), 0 is for no match at all.
        """
        ext = os.path.splitext(fname)[1]
        if ext in config.data.video_extensions:
            return 80
        return 0
    can_handle=staticmethod(can_handle)

    def process_file(self, filename):
        at = self.ensure_new_type('feature', title=_("Feature %s") % self.classifier)
        at.mimetype = 'image/svg+xml'
        at.setMetaData(config.data.namespace_prefix['dc'], "description", _("Detected %s") % self.classifier)

        self.progress(0, _("Detection started"))
        video = cv.CreateFileCapture(filename)

        if not video:
            raise "Cannot read video file:"
        self.convert(self.iterator(video))
        return self.package

    def iterator(self, video):
        def svg_rect(x, y , w, h):
            return

        # Take the first frame to get width/height
        pos = cv.GetCaptureProperty(video, cv.CV_CAP_PROP_POS_MSEC)
        frame = cv.QueryFrame(video)
        width, height = cv.GetSize(frame)
        scaled_width, scaled_height = int(width / self.scale), int(height / self.scale)
        print width, height, scaled_width, scaled_height

        # create storage for grayscale version
        largegrayscale = cv.CreateImage( (width, height), 8, 1)
        grayscale = cv.CreateImage( (scaled_width, scaled_height), 8, 1)
        # create storage
        storage = cv.CreateMemStorage(128)
        cascade = cv.Load(config.data.advenefile( ('haars', self.classifier + '.xml') ))
        count = 0

        x = y = w = h = 0
        svg_template = r"""<svg xmlns='http://www.w3.org/2000/svg' version='1' viewBox="0 0 %(scaled_width)d %(scaled_height)d" x='0' y='0' width='%(scaled_width)d' height='%(scaled_height)d'><rect style="fill:none;stroke:green;stroke-width:4;" width="%(w)d" height="%(h)s" x="%(x)s" y="%(y)s"></rect></svg>"""
        start_pos = None

        while frame :
            cv.CvtColor(frame, largegrayscale, cv.CV_RGB2GRAY)
            cv.Resize(largegrayscale, grayscale, cv.CV_INTER_LINEAR)

            # equalize histogram
            cv.EqualizeHist(grayscale, grayscale)

            # detect objects
            faces = cv.HaarDetectObjects(image=grayscale,
                                         cascade=cascade,
                                         storage=storage,
                                         scale_factor=1.2,
                                         min_neighbors=2,
                                         flags=cv.CV_HAAR_DO_CANNY_PRUNING)

            # We start a new annotation if the threshold is reached,
            # but we do not end if if we get below the threshold.
            if faces and faces[0][1] > self.threshold and start_pos is None:
                x, y, w, h = faces[0][0]
                start_pos = pos
                count += 1
            # FIXME: if faces and start_pos is not None:
            # check that the rectangle is not too much different from the previous one, else create a new annotation
            elif not faces and start_pos is not None:
                yield {
                    'begin': start_pos,
                    'end': pos,
                    'content': svg_template % locals(),
                    }
                start_pos = None
            if not self.progress(cv.GetCaptureProperty(video,
                                                       cv.CV_CAP_PROP_POS_AVI_RATIO),
                                 "Detected %d feature(s)" % count):
                break
            pos = cv.GetCaptureProperty(video, cv.CV_CAP_PROP_POS_MSEC)
            frame = cv.QueryFrame(video)

        # Last frame
        if start_pos is not None:
            yield {
                'begin': start_pos,
                'end': pos,
                'content': svg_template % locals(),
                }
