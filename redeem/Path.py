""" 
Path.py - A single movement from one point to another 
All coordinates  in this file is in meters.

Author: Elias Bakken
email: elias(dot)bakken(at)gmail(dot)com
Website: http://www.thing-printer.com
License: GNU GPL v3: http://www.gnu.org/copyleft/gpl.html

 Redeem is free software: you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.
 
 Redeem is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU General Public License for more details.
 
 You should have received a copy of the GNU General Public License
 along with Redeem.  If not, see <http://www.gnu.org/licenses/>.
"""

import numpy as np
import logging

class Path:
    
    printer = None

    # Different types of paths
    ABSOLUTE = 0
    RELATIVE = 1
    G92 = 2
    G2 = 3
    G3 = 4

    # Numpy array type used throughout    
    DTYPE = np.float64

    # http://www.manufacturinget.org/2011/12/cnc-g-code-g17-g18-and-g19/
    X_Y_ARC_PLANE = 0
    X_Z_ARC_PLANE = 1
    Y_Z_ARC_PLANE = 2

    # max length of any segment in an arc
    ARC_SEGMENT_LENGTH = 0.1 / 1000
    
    def __init__(self, axes, speed, accel, cancelable=False, use_bed_matrix=True, use_backlash_compensation=True, enable_soft_endstops=True):
        """ The axes of evil, the feed rate in m/s and ABS or REL """
        self.axes = axes
        self.speed = speed
        self.accel = accel
        self.cancelable = int(cancelable)
        self.use_bed_matrix = int(use_bed_matrix)
        self.use_backlash_compensation = int(use_backlash_compensation)
        self.enable_soft_endstops = enable_soft_endstops
        self.next = None
        self.prev = None
        self.speeds = None
        self.start_pos = None
        self.end_pos = None
        self.ideal_end_post = None

    def is_G92(self):
        """ Special path, only set the global position on this """
        return self.movement == Path.G92

    def set_homing_feedrate(self):
        """ The feed rate is set to the lowest axis in the set """
        self.speeds = np.minimum(self.speeds,
                                 self.home_speed[np.argmax(self.vec)])
        self.speed = np.linalg.norm(self.speeds[:3])

    def unlink(self):
        """ unlink this from the chain. """
        self.next = None
        self.prev = None

    @staticmethod
    def backlash_reset():
        #TODO: This needs further attention
        return

    def needs_splitting(self):
        """ Return true if this is a arc movement"""
        return self.movement == Path.G2 or self.movement == Path.G3

    def get_segments(self):
        """ Returns split segments for delta or arcs """
        if self.movement == Path.G2 or self.movement == Path.G3:
            return self.get_arc_segments()

    def _get_point_on_plane(self, point):
        """ Returns the two dimensions that are relevant for the active arc plane """
        if self.printer.arc_plane == Path.X_Y_ARC_PLANE:
            return point[0], point[1]
        if self.printer.arc_plane == Path.X_Z_ARC_PLANE:
            return point[0], point[2]
        # if Path.Y_Z_ARC_PLANE
        return point[1], point[2]

    def _get_axes_point(self, point):
        """ Identifies the point as dimensions along the active arc plane"""
        if self.printer.arc_plane == Path.X_Y_ARC_PLANE:
            return {'X': point[0], 'Y': point[1]}
        if self.printer.arc_plane == Path.X_Z_ARC_PLANE:
            return {'X': point[0], 'Z': point[1]}
        # ifPath.Y_Z_ARC_PLANE
        return {'Y': point[0], 'Z': point[1]}

    def _get_offset_on_plane(self):
        """ Returns the two offset dimensions that are relevant for the active arc plane """
        if self.printer.arc_plane == Path.X_Y_ARC_PLANE:
            return self.I, self.J
        if self.printer.arc_plane == Path.X_Z_ARC_PLANE:
            return self.I, self.K
        # Path.Y_Z_ARC_PLANE
        return self.J, self.K

    def get_arc_segments(self):
        """Returns paths that approximate an arc"""
        #  reference : http://www.manufacturinget.org/2011/12/cnc-g-code-g02-and-g03/

        # isolate dimensions relevant for the active plane (eg X,Y for XY plane)
        start0, start1 = self._get_point_on_plane(self.prev.ideal_end_pos)
        end0, end1 = self._get_point_on_plane(self.ideal_end_pos)
        offset0, offset1 = self._get_offset_on_plane()

        radius = np.sqrt(offset0 ** 2 + offset1 ** 2)

        # calculate the arc center
        circle0, circle1 = start0 + offset0, start1 + offset1

        # arctan2 defined with center of circle at 0,0. adjust other dimensions to match
        origin1 = (start1-circle1, end1-circle1)
        origin0 = (start0-circle0, end0-circle0)

        # determine the start and end angle (in radians)
        start_theta, end_theta = np.arctan2(origin1, origin0)

        # clockwise angles are always increasing, adjust for +/- pi modulus
        if start_theta <= end_theta and self.movement is Path.G2:
            start_theta = np.pi + abs(-np.pi - start_theta)

        # counter-clockwise anges are always decreasing, adjust for +/- modulus
        if start_theta >= end_theta and self.movement is Path.G3:
            start_theta = -np.pi - abs(np.pi - start_theta)

        # determine the length of the arc in order to determine how many segments to split into
        arc_length = radius * abs(end_theta - start_theta)
        num_segments = int(arc_length / self.ARC_SEGMENT_LENGTH)

        # create equally spaced angles (in radians) from start to end
        arc_thetas = np.linspace(start_theta + 2 * np.pi, end_theta + 2 * np.pi, num_segments)

        arc_0 = circle0 + radius * np.cos(arc_thetas)
        arc_1 = circle1 + radius * np.sin(arc_thetas)

        path_segments = []

        # for each coordinate along the arc, create a segment
        for index, segment in enumerate(zip(arc_0, arc_1)):
            segment_end = self._get_axes_point(segment)
            path = AbsolutePath(segment_end, self.speed, self.accel, self.cancelable, self.use_bed_matrix, False)
            # these paths don't get added to the path planner directly, need to set printer manually (?)
            path.printer = self.printer
            if index is not 0:
                path.set_prev(path_segments[-1])
            else:
                path.set_prev(self.prev)

            path_segments.append(path)

        return path_segments

    def __str__(self):
        """ The vector representation of this path segment """
        return "Path from " + str(self.start_pos[:4]) + " to " + str(self.end_pos[:4])

class AbsolutePath(Path):
    """ A path segment with absolute movement """
    def __init__(self, axes, speed, accel, cancelable=False, use_bed_matrix=True, use_backlash_compensation=True, enable_soft_endstops=True):
        Path.__init__(self, axes, speed, accel, cancelable, use_bed_matrix, use_backlash_compensation, enable_soft_endstops)
        self.movement = Path.ABSOLUTE

    def set_prev(self, prev):
        """ Set the previous path element """
        self.prev = prev
        prev.next = self
        self.start_pos = prev.end_pos

        # Make the start, end and path vectors. 
        self.ideal_end_pos = np.copy(prev.ideal_end_pos)
        for index, axis in enumerate(self.printer.AXES):
            if axis in self.axes:
                self.ideal_end_pos[index] = self.axes[axis]
    
        # Store the ideal end pos, so the target 
        # coordinates are pushed forward
        self.end_pos = np.copy(self.ideal_end_pos)
        if self.use_bed_matrix:
            self.end_pos[:3] = self.end_pos[:3].dot(self.printer.matrix_bed_comp)

        #logging.debug("Abs before: "+str(self.ideal_end_pos[:3])+" after: "+str(self.end_pos[:3]))
        
class RelativePath(Path):
    """ 
    A path segment with Relative movement 
    This is an approximate relative movement, i.e. we will move according to:
      (where we actually are) -> (somewhere close to = (where we think we are + our passed in vector))
      but it should be pretty close!
    """
    def __init__(self, axes, speed, accel, cancelable=False, use_bed_matrix=True, use_backlash_compensation=True, enable_soft_endstops=True):
        Path.__init__(self, axes, speed, accel, cancelable, use_bed_matrix, use_backlash_compensation, enable_soft_endstops)
        self.movement = Path.RELATIVE

    def set_prev(self, prev):
        """ Link to previous segment """
        self.prev = prev
        prev.next = self
        self.start_pos = prev.end_pos

        # Generate the vector
        vec = np.zeros(self.printer.MAX_AXES, dtype=Path.DTYPE)
        for index, axis in enumerate(self.printer.AXES):
            if axis in self.axes:
                vec[index] = self.axes[axis]

        # Calculate the ideal end position. 
        # In an ideal world, this is where we want to go. 
        self.ideal_end_pos = np.copy(prev.ideal_end_pos) + vec
        
        self.end_pos = self.start_pos + vec
        

class G92Path(Path):
    """ A reset axes path segment. No movement occurs, only global position
    setting """
    def __init__(self, axes, cancelable=False, use_bed_matrix=False):
        Path.__init__(self, axes, 0, 0, cancelable, use_bed_matrix)
        self.movement = Path.G92


    def set_prev(self, prev):
        """ Set the previous segment """
        self.prev = prev
        if prev is not None:
            self.start_pos      = prev.end_pos
            self.end_pos        = np.copy(self.start_pos) 
            self.ideal_end_pos  = np.copy(prev.ideal_end_pos)
            prev.next = self
        else:
            self.start_pos      = np.zeros(self.printer.MAX_AXES, dtype=Path.DTYPE)
            self.end_pos        = np.zeros(self.printer.MAX_AXES, dtype=Path.DTYPE)
            self.ideal_end_pos  = np.zeros(self.printer.MAX_AXES, dtype=Path.DTYPE)

        # Update the ideal pos based on G92 values
        for index, axis in enumerate(self.printer.AXES):
            if axis in self.axes:
                self.ideal_end_pos[index] = self.axes[axis]
                self.end_pos[index] = self.axes[axis]

        # Update the matrix compensated pos
        if self.use_bed_matrix:
            matrix_pos = np.copy(self.ideal_end_pos)
            matrix_pos[:3] = matrix_pos[:3].dot(self.printer.matrix_bed_comp)
            for index, axis in enumerate(self.printer.AXES):
                if axis in self.axes:
                    self.end_pos[index] = matrix_pos[index]
        #logging.debug("G92 before: "+str(self.ideal_end_pos[:3])+" after: "+str(self.end_pos[:3]))

