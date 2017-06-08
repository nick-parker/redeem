"""
GCode G30
Single Z probe

Author: Elias Bakken
email: elias(dot)bakken(at)gmail dot com
Website: http://www.thing-printer.com
License: CC BY-SA: http://creativecommons.org/licenses/by-sa/2.0/
"""

from GCodeCommand import GCodeCommand
import logging
import json
try:
    from Gcode import Gcode
    from Path import G92Path
    from Alarm import Alarm
except ImportError:
    from redeem.Gcode import Gcode
    from redeem.Path import G92Path
    from redeem.Alarm import Alarm

class G30(GCodeCommand):

    def execute(self, g):
        if g.has_letter("P"): # Load point
            index = int(g.get_value_by_letter("P"))
            point = self.printer.probe_points[index]
        else:
            # If no probe point is specified, use current pos
            # this value is in metres
            # need to convert to millimetres as we are using 
            #this value for a G0 call
            point = self.printer.path_planner.get_current_pos(mm=True, ideal=True)
            logging.debug("G30: current position (mm) :  X{} Y{} Z{}".format(point["X"], point["Y"], point["Z"]))
            
        if g.has_letter("X"): # Override X
            point["X"] = float(g.get_value_by_letter("X"))
        if g.has_letter("Y"): # Override Y
            point["Y"] = float(g.get_value_by_letter("Y"))
        if g.has_letter("Z"): # Override Z
            point["Z"] = float(g.get_value_by_letter("Z"))        

        # Get probe length, if present, else use value from config. 
        if g.has_letter("D"):
            probe_length = float(g.get_value_by_letter("D")) / 1000.
        else:
            probe_length = self.printer.config.getfloat('Probe', 'length')

        # Get probe speed, if present, else use value from config. 
        if g.has_letter("F"):
            probe_speed = float(g.get_value_by_letter("F")) / 60000.0
        else:
            probe_speed = self.printer.config.getfloat('Probe', 'speed')
        
        # Get acceleration, if present, else use value from config.
        if g.has_letter("A"):
            probe_accel = float(g.get_value_by_letter("A"))
        else:
            probe_accel = self.printer.config.getfloat('Probe', 'accel')
        
        use_bed_matrix = bool(g.get_int_by_letter("B", 0))

        # Find the Probe offset
        # values in config file are in metres, need to convert to millimetres
        offset_x = self.printer.config.getfloat('Probe', 'offset_x')*1000
        offset_y = self.printer.config.getfloat('Probe', 'offset_y')*1000
        
        logging.debug("G30: probing from point (mm) : X{} Y{} Z{}".format(point["X"]+offset_x, point["Y"]+offset_y, point["Z"]))

        # Move to the position
        G0 = Gcode({"message": "G0 X{} Y{} Z{}".format(point["X"]+offset_x, point["Y"]+offset_y, point["Z"]), "parent": g})
        self.printer.processor.execute(G0)
        self.printer.path_planner.wait_until_done()
        bed_dist = self.printer.path_planner.probe(probe_length, probe_speed, probe_accel)*1000.0 # convert to mm
        logging.debug("Bed dist: "+str(bed_dist)+" mm")
        
        self.printer.send_message(
            g.prot,
            "Found Z probe distance {0:.2f} mm at (X, Y) = ({1:.2f}, {2:.2f})".format(
                    bed_dist, point["X"], point["Y"]))


        Alarm.action_command("bed_probe_point", json.dumps([point["X"], point["Y"], bed_dist]))

        # Must have S to save the probe bed distance
        # this is required for calculation of the bed compensation matrix
        # NOTE: the use of S in G30 means "save".
        if g.has_letter("S"):
            if not g.has_letter("P"):
                logging.warning("G30: S-parameter was set, but no index (P) was set.")
            else:
                self.printer.probe_heights[index] = bed_dist
        
    def get_description(self):
        return "Probe the bed at current point"

    def get_long_description(self):
        return ("Probe the bed at the current position, or if specified, a point "
                "previously set by M557. X, Y, and Z starting probe positions can be overridden, "
                "D = sets the probe length, or taken from config if nothing is specified. \n"
                "F = sets the probe speed. If not present, it's taken from the config. \n"
                "A = sets the probe acceleration. If not present, it's taken from the config. \n"
                "B = determines if the bed marix is used or not. (0 or 1)\n"
                "P = the point at which to probe, previously set by M557. \n"
                "S = save the probed point distance\n"
                "P and S save the probed bed distance to a list that corresponds with point P")
   
    def is_buffered(self):
        return True

    def get_test_gcodes(self):
        return ["G30", "G30 P0", "G30 P1 X10 Y10"]

class G30_1(GCodeCommand):
    
    def execute(self, g):
        # Catch most letters to tell user use may have been in error.
        if g.has_letter("P"):
            self.printer.send_message(
                g.prot,
                "Warning: P not supported for G30.1, proceeding as if none existed.")
        if g.has_letter("X"): # Override X
            self.printer.send_message(
                 g.prot,
                 "Warning: X not supported for G30.1, proceeding as if none existed.")  
        if g.has_letter("Y"): # Override Y
            self.printer.send_message(
                g.prot,
                "Warning: Y not supported for G30.1, proceeding as if none existed.")
        if g.has_letter("Z"): # Override Z
            Z_new = float(g.get_value_by_letter("Z"))
        else:
            Z_new= 0
           
        # Usable letters listed here          
        # Get probe length, if present, else use value from config. 
        if g.has_letter("D"):
            probe_length = float(g.get_value_by_letter("D")) / 1000.
        else:
            probe_length = self.printer.config.getfloat('Probe', 'length')
  
        # Get probe speed. If not preset, use printers curent speed. 
        if g.has_letter("F"):
            probe_speed = float(g.get_value_by_letter("F")) / 60000.0
        else:
            probe_speed = self.printer.config.getfloat('Probe', 'speed')
        
        # Get acceleration. If not present, use value from config.        
        if g.has_letter("A"):
            probe_accel = float(g.get_value_by_letter("A"))
        else:
            probe_accel = self.printer.config.getfloat('Probe', 'accel')
        # what does use_bed_matrix do?
        
        point = self.printer.path_planner.get_current_pos(mm=True, ideal=True)
        logging.debug("G30.1: current position (mm) :  X{} Y{} Z{}".format(point["X"], point["Y"], point["Z"]))  
        logging.debug("G30.1: will set bed to Z{}".format(Z_new))
        
        # Find the Probe offset
        # values in config file are in metres, need to convert to millimetres
        offset_x = self.printer.config.getfloat('Probe', 'offset_x')*1000
        offset_y = self.printer.config.getfloat('Probe', 'offset_y')*1000
          
        logging.debug("G30.1: probing from point (mm) : X{} Y{} Z{}".format(point["X"]+offset_x, point["Y"]+offset_y, point["Z"]))

        # Move to the position
        G0 = Gcode({"message": "G0 X{} Y{} Z{}".format(point["X"]+offset_x, point["Y"]+offset_y, point["Z"]), "parent": g})
        self.printer.processor.execute(G0)
        self.printer.path_planner.wait_until_done()
        bed_dist = self.printer.path_planner.probe(probe_length, probe_speed, probe_accel)*1000.0 # convert to mm
        
        #calculated required offset to make bed euqal to Z0 or user's specified Z.
        #should be correct, assuming probe starts at Z(5), requested Z(0)  probe Z(-0.3), adjusted global Z should be 5.3 
        # assuming probe starts at Z(5), requested Z(-0.2), probe Z(-0.3), adjusted global Z should be 5.1
    
        Z_adjusted = point["Z"] - bed_dist + Z_new
        logging.debug("Bed dist: "+str(bed_dist)+" mm")
        logging.debug("Old Z{}, New Z{}.".format(point["Z"], Z_adjusted))

        self.printer.send_message(g.prot,"Offseting Z by {} to Z{}".format(bed_dist, Z_adjusted))
        # wiley's advice on bypassing sending via G92
        pos = {}
        pos["Z"] = Z_adjusted/1000.0
        path = G92Path(pos,self.printer.feed_rate)
        self.printer.path_planner.add_path(path)
        
        # not sure if next part is necessary
        Alarm.action_command("bed_probe_point", json.dumps([point["X"], point["Y"], bed_dist]))
  

    def get_description(self):
        return "Probes the bed at the current point, sets Z0."

    def get_long_description(self):
        return ("Probe the bed at the current position."
                "B, P, X, Y, S inputs are ignored. \n"
                "Z = sets the requested Z height at bed level, if not present, set to 0. \n"
                "D = sets the probe length, or taken from config if nothing is specified. \n"
                "F = sets the probe speed. If not present, it's taken from the config. \n"
                "A = sets the probe acceleration. If not present, it's taken from the config. \n")

    def is_buffered(self):
        return True
    # What should be put here?
    def get_test_gcodes(self):
        return ["G30.1", "G30.1 P0", "G30.1 P1 X10 Y10 Z10"]
  
 