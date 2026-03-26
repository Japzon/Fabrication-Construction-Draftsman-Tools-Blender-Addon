# --------------------------------------------------------------------------------
# Copyright (c) 2026 Greenlex Systems Services Incorporated. All rights reserved.
#
# A C K N O W L E D G M E N T (GPL COMPLIANT)
# This add-on is protected under the GNU General Public License (GPL) to ensure 
# fair use and free distribution. The original architecture, source code, and 
# design logic are the intellectual property of Greenlex Systems Services Incorporated. 
#
# No party is authorized to claim authorship or ownership of this original work.
# --------------------------------------------------------------------------------



import math
from operator import itemgetter
from typing import List, Tuple, Set, Dict

# --- Versioning and Naming ---
# Using a tuple for the version allows for easy comparison and access.
ADDON_VERSION: Tuple[int, int, int] = (7, 45, 0)

# --- Naming Conventions ---
# Consistent prefixes for addon-created objects, modifiers, and constraints
# are crucial for robustly identifying and managing them. This avoids fragile
# name matching and makes the code more readable and maintainable.
MOD_PREFIX: str = "URDF_"
WIDGET_PREFIX: str = f"{MOD_PREFIX}Widget_v{ADDON_VERSION[0]}{ADDON_VERSION[1]}"
CUTTER_PREFIX: str = f"{MOD_PREFIX}Cutter_"
BOOL_PREFIX: str = f"{MOD_PREFIX}Bool_"
NATIVE_SPRING_MOD_NAME: str = f"{MOD_PREFIX}NativeSpring"
NATIVE_DAMPER_MOD_NAME: str = f"{MOD_PREFIX}NativeDamper"
NATIVE_SLINKY_MOD_NAME: str = f"{MOD_PREFIX}NativeSlinky"
IK_CONSTRAINT_NAME: str = f"{MOD_PREFIX}IK"
WIDGETS_COLLECTION_NAME: str = "URDF_Widgets"
MECHANICAL_PARTS_COLLECTION_NAME: str = "Mechanical_Parts"

# --- Numerical Constants ---
# Using named constants for "magic numbers" improves readability and makes
# future adjustments easier and safer.
GEAR_BEVEL_TAPER_FACTOR: float = math.cos(math.radians(20)) # Default taper for bevel gears
GIZMO_ROTATION_OFFSET: float = -90.0 # Degrees
WELD_THRESHOLD: float = 0.0001
MIN_BONE_LENGTH: float = 0.01
MIN_GIZMO_SCALE: float = 0.001
DEFAULT_IK_CHAIN_LENGTH: int = 255

# --- UI Panel Management ---
# A list of scene properties used to control the visibility of the addon's panels.
# This is used for the "Auto-Collapse Other Panels" feature.
URDF_PANEL_PROPS: List[str] = [
    "urdf_show_panel_parts",
    "urdf_show_panel_electronics",
    "urdf_show_panel_parametric",
    "urdf_show_panel_materials",
    "urdf_show_panel_lighting",
    "urdf_show_panel_dimensions", 
    "urdf_show_panel_ai_factory",
    "urdf_show_panel_kinematics",
    "urdf_show_panel_inertial",
    "urdf_show_panel_collision",
    "urdf_show_panel_transmission",
    "urdf_show_panel_export",
    "urdf_show_panel_assets",
    "urdf_show_panel_architectural",
]

# --- Mechanical Part Categories and Types ---
# These lists define the available parametric parts in the addon.
# Each tuple represents an item in an EnumProperty: (identifier, UI name, UI description).
# They are used to populate the UI dropdowns and for logic dispatching in the
# `regenerate_mech_mesh` function.
GEAR_TYPES: List[Tuple[str, str, str]] = sorted([
    ('SPUR', "Spur", "A standard straight-toothed gear."),
    ('HELICAL', "Helical", "A gear with angled teeth for smoother, quieter operation."),
    ('HERRINGBONE', "Herringbone", "Two helical gears side-by-side, neutralizing axial thrust."),
    ('DOUBLE_HERRING', "Double Herringbone", "A herringbone gear with a central groove."),
    ('BEVEL', "Bevel", "A cone-shaped gear for transmitting power between intersecting shafts."),
    ('WORM', "Worm", "A gear that meshes with a worm screw."),
    ('INTERNAL', "Internal (Ring)", "A gear with teeth on the inside of a cylinder.")
], key=itemgetter(1))
RACK_TYPES: List[Tuple[str, str, str]] = sorted([
    ('RACK_SPUR', "Rack (Spur)", "A straight gear rack with straight teeth."),
    ('RACK_HELICAL', "Rack (Helical)", "A gear rack with angled teeth."),
    ('RACK_HERRINGBONE', "Rack (Herringbone)", "A herringbone gear rack."),
    ('RACK_DOUBLE', "Rack (Double)", "A double herringbone gear rack."),
    ('RACK_BEVEL', "Rack (Bevel)", "A gear rack with beveled teeth."),
    ('RACK_WORM', "Rack (Worm)", "A gear rack that meshes with a worm screw.")
], key=itemgetter(1))
FASTENER_TYPES: List[Tuple[str, str, str]] = sorted([
    ('BOLT', "Bolt & Nut", "A threaded fastener with a matching nut."),
    ('SCREW', "Screw", "A threaded fastener designed to be screwed into a material."),
    ('RIVET', "Rivet", "A permanent mechanical fastener.")
], key=itemgetter(1))
SPRING_TYPES: List[Tuple[str, str, str]] = sorted([ 
    ('SPRING', "Spring (Standard)", "A helical spring that can be compressed or stretched."),
    ('DAMPER', "Damper Setup", "A hydraulic or pneumatic damper."),
    ('SPRING_SLINKY', "Slinky (Curved)", "A physics-based curvy spring.")
], key=itemgetter(1))
CHAIN_TYPES: List[Tuple[str, str, str]] = sorted([
    ('ROLLER', "Roller Chain", "A chain made of rollers and plates."),
    ('BELT', "Belt", "A flexible belt, such as a timing belt.")
], key=itemgetter(1))
WHEEL_TYPES: List[Tuple[str, str, str]] = sorted([
    ('WHEEL_STANDARD', "Standard", "A standard wheel with a tire"),
    ('WHEEL_MECANUM', "Mecanum", "A wheel with angled rollers for holonomic movement"),
    ('WHEEL_OMNI', "Omni", "A wheel with perpendicular rollers for holonomic movement"),
    ('WHEEL_CASTER', "Caster (Sphere)", "A spherical caster wheel"),
    ('WHEEL_OFFROAD', "Off-road", "A heavy-duty wheel with treads"),
], key=itemgetter(1))
PULLEY_TYPES: List[Tuple[str, str, str]] = sorted([
    ('PULLEY_FLAT', "Flat Pulley", "A flat pulley with flanges for flat belts."),
    ('PULLEY_V', "V-Belt Pulley", "A pulley with a V-shaped groove."),
    ('PULLEY_TIMING', "Timing Pulley", "A toothed pulley for timing belts."),
    ('PULLEY_UGROOVE', "U-Groove Pulley", "A pulley with a rounded groove for cables/ropes.")
], key=itemgetter(1))
WHEEL_TREAD_PATTERNS: List[Tuple[str, str, str]] = [
    ('NONE', "None", "A smooth tire surface"),
    ('BLOCKS', "Blocks", "Standard blocky treads"),
    ('GROOVES', "Grooves", "Simple circumferential grooves on all treads"),
    ('LINES', "Lines", "Fine circumferential lines"),
    ('V_SHAPE', "V-Shape", "Directional V-shaped tread pattern"),
    ('W_SHAPE', "W-Shape", "Directional W-shaped tread pattern")
]
WHEEL_SIDE_PATTERNS: List[Tuple[str, str, str]] = [
    ('NONE', "None", "Flat rim surface"),
    ('SPOKES', "Spokes", "Radial spokes pattern"),
    ('DISH', "Dish", "Concave dish shape"),
    ('RINGS', "Rings", "Concentric rings")
]
ROPE_TYPES: List[Tuple[str, str, str]] = sorted([
    ('ROPE_STEEL', "Steel Cable", "A twisted steel cable."),
    ('ROPE_SYNTHETIC', "Synthetic Rope", "A braided synthetic rope."),
    ('ROPE_TUBE', "Hose / Tube", "A flexible hollow tube.")
], key=itemgetter(1))

# --- AI Editor Note: New two-level category system for electronics ---
ELECTRONICS_CATEGORIES: List[Tuple[str, str, str]] = sorted([
    ('MOTOR', "Motor", "Generate an electric motor"),
    ('SENSOR', "Sensor", "Generate a sensor component"),
    ('PCB', "PCB", "Generate a printed circuit board or microcontroller"),
    ('IC', "IC", "Generate integrated circuits and components"),
    ('CAMERA', "Camera", "Generate a camera component")
], key=itemgetter(1))

MOTOR_TYPES: List[Tuple[str, str, str]] = sorted([
    ('MOTOR_DC_ROUND', "DC Motor (Round)", "Standard cylindrical DC motor"),
    ('MOTOR_DC_FLAT', "DC Motor (Flat)", "Flat-sided DC motor (e.g. 130 size)"),
    ('MOTOR_STEPPER_NEMA', "Stepper (NEMA)", "Square NEMA-style stepper motor"),
    ('MOTOR_SERVO_STD', "Servo (Standard)", "Standard hobby servo motor"),
    ('MOTOR_SERVO_MICRO', "Servo (Micro)", "Micro hobby servo motor"),
    ('MOTOR_BLDC_OUTRUNNER', "BLDC (Outrunner)", "Brushless DC outrunner motor"),
    ('MOTOR_PANCAKE', "Pancake Motor", "Flat, high-torque motor")
], key=itemgetter(1))
SENSOR_TYPES: List[Tuple[str, str, str]] = sorted([
    ('SENSOR_LIDAR', "Lidar", "A lidar sensor puck"),
    ('SENSOR_IMU', "IMU", "An inertial measurement unit"),
    ('SENSOR_ULTRASONIC', "Ultrasonic", "An ultrasonic distance sensor"),
    ('SENSOR_GPS', "GPS", "A GPS unit with antenna"),
    ('SENSOR_FORCE_TORQUE', "Force/Torque", "A 6-axis force/torque sensor"),
    ('SENSOR_CONTACT', "Contact/Bumper", "A contact or bumper sensor"),
    ('SENSOR_RADAR', "Radar", "A radar sensor box"), # Keep existing
    ('SENSOR_THERMAL', "Thermal", "A thermal sensor unit") # Keep existing
], key=itemgetter(1))
PCB_TYPES: List[Tuple[str, str, str]] = sorted([
    ('PCB_BOARD', "PCB Board", "A standard printed circuit board"),
    ('PCB_BREADBOARD', "Breadboard", "A prototyping breadboard"),
    ('PCB_RPI', "Raspberry Pi", "A standard Raspberry Pi sized board"),
    ('PCB_ARDUINO', "Arduino Uno", "A standard Arduino Uno sized board")
], key=itemgetter(1))
IC_TYPES: List[Tuple[str, str, str]] = sorted([
    ('IC_RESISTOR', "Resistor", "A standard axial resistor"),
    ('IC_DIODE', "Diode", "A standard diode"),
    ('IC_CAPACITOR', "Capacitor", "A cylindrical capacitor"),
    ('IC_LED', "LED", "A standard LED"),
    ('IC_REGULATOR', "Regulator", "A voltage regulator"),
    ('IC_MICROCHIP', "Microchip", "A DIP or QFP microchip")
], key=itemgetter(1))
CAMERA_TYPES: List[Tuple[str, str, str]] = sorted([
    ('CAMERA_DEFAULT', "Camera", "A standard camera sensor")
], key=itemgetter(1))
ALL_ELECTRONICS_TYPES = MOTOR_TYPES + SENSOR_TYPES + PCB_TYPES + IC_TYPES + CAMERA_TYPES

BASIC_SHAPE_TYPES: List[Tuple[str, str, str]] = sorted([
    ('SHAPE_PLANE', "Plane", "A standard 2D plane"),
    ('SHAPE_CUBE', "Cube", "A standard cube"),
    ('SHAPE_CIRCLE', "Circle", "A standard circle"),
    ('SHAPE_UVSPHERE', "UV Sphere", "A standard UV sphere"),
    ('SHAPE_ICOSPHERE', "Ico Sphere", "A standard Icosphere"),
    ('SHAPE_CYLINDER', "Cylinder", "A standard cylinder"),
    ('SHAPE_CONE', "Cone", "A standard cone"),
    ('SHAPE_TORUS', "Torus", "A standard torus")
], key=itemgetter(1))

ARCHITECTURAL_TYPES: List[Tuple[str, str, str]] = sorted([
    ('WALL', "Wall", "A vertical structural wall."),
    ('WINDOW', "Window", "A window with frame and glass."),
    ('DOOR', "Door", "A door with frame."),
    ('COLUMN', "Column", "A vertical support column."),
    ('BEAM', "Beam", "A horizontal support beam."),
    ('STAIRS', "Stairs", "A set of structural stairs.")
], key=itemgetter(1))

# --- Visual Gizmo Styles ---
GIZMO_STYLES: List[Tuple[str, str, str]] = [
    ('DEFAULT', "Default (Flat)", "Standard flat 2D gizmos"),
    ('MODERN_3D', "Modern 3D", "Volumetric 3D shapes for better depth perception"),
    ('LILY_2D', "Lily 2D", "Stylized 2D shapes for high contrast visibility"),
]

BASIC_JOINT_TYPES: List[Tuple[str, str, str]] = sorted([
    ('JOINT_REVOLUTE', "Revolute Joint", "A hinge-like joint that rotates around a single axis (Z-aligned)"),
    ('JOINT_CONTINUOUS', "Continuous Joint", "A joint that rotates continuously around a single axis (Z-aligned)"),
    ('JOINT_PRISMATIC', "Prismatic (Ball Screw)", "A sliding joint driven by a ball screw (Z-aligned)"),
    ('JOINT_PRISMATIC_WHEELS', "Prismatic (Wheels)", "A sliding carriage on a rack/rail with wheels"),
    ('JOINT_PRISMATIC_WHEELS_ROT', "Prismatic (Wheels, Rotated)", "A sliding carriage with rotated orientation and supporting frame"),
    ('JOINT_SPHERICAL', "Spherical Joint", "A ball-and-socket joint with 3 degrees of freedom")
], key=itemgetter(1))

# --- AI Editor Note: Define sorted category lists for UI consistency ---
MECH_CATEGORIES_RAW = [
    ('GEAR', "Gears", "Generate gears"),
    ('RACK', "Racks", "Generate gear racks"),
    ('FASTENER', "Fasteners", "Generate fasteners"),
    ('SPRING', "Springs", "Generate springs"),
    ('CHAIN', "Chains & Belts", "Generate chains and belts"),
    ('WHEEL', "Wheels", "Generate robotic wheels"),
    ('PULLEY', "Pulleys", "Generate pulleys"),
    ('ROPE', "Ropes & Cables", "Generate ropes and cables"),
    ('BASIC_JOINT', "Basic Joints", "Generate kinematic joint templates"),
    ('BASIC_SHAPE', "Basic Shapes", "Generate parametric primitive shapes"),
    ('ARCHITECTURAL', "Architectural", "Generate architectural elements"),
]
MECH_CATEGORIES_SORTED = sorted(MECH_CATEGORIES_RAW, key=itemgetter(1))
ALL_CATEGORIES_SORTED = sorted(MECH_CATEGORIES_RAW + [('ELECTRONICS', "Electronics", "Generate electronic components")], key=itemgetter(1))

# --- Kinematic Bone Alignment Enums ---
BONE_MODES: List[Tuple[str, str, str]] = [
    ('SINGLE', "Joint Editor", "Use the global joint tool to edit all selected bones at once"),
    ('INDIVIDUAL', "Bone Editor", "Edit each selected bone's URDF properties individually")
]

BONE_AXES: List[Tuple[str, str, str]] = [
    ('AUTO', "Auto (Z-Align)", "Automatically align bone to local Z axis"),
    ('X', "Local X", "Align bone along local X axis"),
    ('Y', "Local Y", "Align bone along local Y axis"),
    ('Z', "Local Z", "Align bone along local Z axis")
]

