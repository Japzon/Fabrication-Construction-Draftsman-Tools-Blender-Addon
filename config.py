# --------------------------------------------------------------------------------
# Copyright (c) 2026 Greenlex Systems Services Incorporated. All rights reserved.
#
# Licensed under the GNU General Public License (GPL).
# Original Architecture & Logic by Greenlex Systems Services Incorporated.
#
# No person or organization is authorized to misrepresent this work or claim 
# original authorship for themselves. Proper attribution is mandatory.
# --------------------------------------------------------------------------------

import math
from operator import itemgetter
from typing import List, Tuple, Set, Dict

# --- Versioning and Naming ---
ADDON_VERSION: Tuple[int, int, int] = (0, 1, 0)

# --- Naming Conventions (Mandated LSD Prefix) ---
MOD_PREFIX: str = "LSD_"
WIDGET_PREFIX: str = f"{MOD_PREFIX}Widget_v{ADDON_VERSION[0]}{ADDON_VERSION[1]}"
CUTTER_PREFIX: str = f"{MOD_PREFIX}Cutter_"
BOOL_PREFIX: str = f"{MOD_PREFIX}Bool_"
NATIVE_SPRING_MOD_NAME: str = f"{MOD_PREFIX}NativeSpring"
NATIVE_DAMPER_MOD_NAME: str = f"{MOD_PREFIX}NativeDamper"
NATIVE_SLINKY_MOD_NAME: str = f"{MOD_PREFIX}NativeSlinky"
IK_CONSTRAINT_NAME: str = f"{MOD_PREFIX}IK"
WIDGETS_COLLECTION_NAME: str = f"{MOD_PREFIX}Widgets"
MECHANICAL_PARTS_COLLECTION_NAME: str = "Mechanical_Presets"
COLLISION_COLLECTION_NAME: str = "Physics_Collisions"

# --- Numerical Constants ---
GEAR_BEVEL_TAPER_FACTOR: float = math.cos(math.radians(20))
GIZMO_ROTATION_OFFSET: float = -90.0
WELD_THRESHOLD: float = 0.0001
MIN_BONE_LENGTH: float = 0.01
MIN_GIZMO_SCALE: float = 0.001
DEFAULT_IK_CHAIN_LENGTH: int = 255

# --- UI Panel Management (LSD Scoped) ---
LSD_PANEL_PROPS: List[str] = [
    "lsd_panel_enabled_parts", "lsd_show_panel_parts",
    "lsd_panel_enabled_electronics", "lsd_show_panel_electronics",
    "lsd_panel_enabled_procedural", "lsd_show_panel_procedural",
    "lsd_panel_enabled_materials", "lsd_show_panel_materials",
    "lsd_panel_enabled_lighting", "lsd_show_panel_lighting",
    "lsd_panel_enabled_dimensions", "lsd_show_panel_dimensions",
    "lsd_panel_enabled_ai_factory", "lsd_show_panel_ai_factory",
    "lsd_panel_enabled_kinematics", "lsd_show_panel_kinematics",
    "lsd_panel_enabled_physics", "lsd_show_panel_physics",
    "lsd_panel_enabled_transmission", "lsd_show_panel_transmission",
    "lsd_panel_enabled_export", "lsd_show_panel_export",
    "lsd_panel_enabled_assets", "lsd_show_panel_assets",
    "lsd_panel_enabled_camera", "lsd_show_panel_camera",
    "lsd_panel_enabled_architectural", "lsd_show_panel_architectural",
    "lsd_panel_enabled_vehicle", "lsd_show_panel_vehicle",
    "lsd_panel_enabled_preferences", "lsd_show_panel_preferences",
]

# --- Mechanical Part Categories and Types ---
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
    ('SENSOR_RADAR', "Radar", "A radar sensor box"),
    ('SENSOR_THERMAL', "Thermal", "A thermal sensor unit")
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

VEHICLE_TYPES: List[Tuple[str, str, str]] = sorted([
    ('CAR', "Car", "A standard passenger car."),
    ('TRUCK', "Truck", "A standard transport truck."),
    ('DRONE', "Drone (Quadcopter)", "A standard quadcopter drone."),
    ('TANK', "Tank", "A tracked heavy vehicle."),
    ('FORKLIFT', "Forklift", "A standard warehouse forklift.")
], key=itemgetter(1))

GIZMO_STYLES: List[Tuple[str, str, str]] = [
    ('DEFAULT', "Default (Flat)", "Standard flat 2D gizmos"),
]

BASIC_JOINT_TYPES: List[Tuple[str, str, str]] = sorted([
    ('JOINT_REVOLUTE', "Revolute Joint", "A hinge-like joint that rotates around a single axis (Z-aligned)"),
    ('JOINT_CONTINUOUS', "Continuous Joint", "A joint that rotates continuously around a single axis (Z-aligned)"),
    ('JOINT_PRISMATIC', "Prismatic (Ball Screw)", "A sliding joint driven by a ball screw (Z-aligned)"),
    ('JOINT_PRISMATIC_WHEELS', "Prismatic (Wheels)", "A sliding carriage on a rack/rail with wheels"),
    ('JOINT_PRISMATIC_WHEELS_ROT', "Prismatic (Wheels, Rotated)", "A sliding carriage with rotated orientation and supporting frame"),
    ('JOINT_SPHERICAL', "Spherical Joint", "A ball-and-socket joint with 3 degrees of freedom")
], key=itemgetter(1))

MECH_CATEGORIES_RAW = [
    ('NONE', "None/Tool", "No mechanical category (standard tool or helper)"),
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
]
MECH_CATEGORIES_SORTED = sorted(MECH_CATEGORIES_RAW, key=itemgetter(1))
ALL_CATEGORIES_SORTED = sorted(MECH_CATEGORIES_RAW + [
    ('ELECTRONICS', "Electronics", "Generate electronic components"),
    ('ARCHITECTURAL', "Architectural", "Generate architectural structural components"),
    ('VEHICLE', "Vehicle", "Generate vehicle assembly components")
], key=itemgetter(1))

BONE_MODES: List[Tuple[str, str, str]] = [
    ('SINGLE', "Group", "Use the global joint tool to edit all selected bones at once"),
    ('INDIVIDUAL', "Individual", "Edit each selected bone's LSD properties individually")
]

BONE_AXES: List[Tuple[str, str, str]] = [
    ('AUTO', "Auto (Z-Align)", "Automatically align bone to local Z axis"),
    ('X', "Local X", "Align bone along local X axis"),
    ('Y', "Local Y", "Align bone along local Y axis"),
    ('Z', "Local Z", "Align bone along local Z axis")
]

# --- Physics Element Data (Density in g/cm³) ---
# Values for gases and liquids represent their solid/frozen state density.
ELEMENT_DATA: Dict[str, Dict[str, float]] = {
    'METALS': {
        'Actinium': 10.07, 'Aluminium': 2.70, 'Americium': 13.67, 'Barium': 3.51, 
        'Berkelium': 14.78, 'Beryllium': 1.85, 'Bismuth': 9.78, 'Cadmium': 8.65, 
        'Calcium': 1.55, 'Californium': 15.1, 'Cerium': 6.69, 'Cesium': 1.88, 
        'Chromium': 7.19, 'Cobalt': 8.90, 'Copper': 8.96, 'Curium': 13.51, 
        'Dysprosium': 8.55, 'Einsteinium': 8.84, 'Erbium': 9.07, 'Europium': 5.24, 
        'Gadolinium': 7.90, 'Gallium': 5.91, 'Gold': 19.30, 'Hafnium': 13.31, 
        'Holmium': 8.80, 'Indium': 7.31, 'Iridium': 22.56, 'Iron': 7.87, 
        'Lanthanum': 6.15, 'Lead': 11.34, 'Lithium': 0.53, 'Lutetium': 9.84, 
        'Magnesium': 1.74, 'Manganese': 7.47, 'Mercury': 14.18, 'Molybdenum': 10.28, 
        'Neodymium': 7.01, 'Neptunium': 20.45, 'Nickel': 8.91, 'Niobium': 8.57, 
        'Osmium': 22.59, 'Palladium': 12.02, 'Platinum': 21.45, 'Plutonium': 19.84, 
        'Polonium': 9.20, 'Potassium': 0.86, 'Praseodymium': 6.64, 'Promethium': 7.26, 
        'Protactinium': 15.37, 'Radium': 5.00, 'Rhenium': 21.02, 'Rhodium': 12.45, 
        'Rubidium': 1.53, 'Ruthenium': 12.37, 'Samarium': 7.35, 'Scandium': 2.99, 
        'Silver': 10.49, 'Sodium': 0.97, 'Strontium': 2.64, 'Tantalum': 16.65, 
        'Technetium': 11.50, 'Terbium': 8.22, 'Thallium': 11.85, 'Thorium': 11.72, 
        'Thulium': 9.32, 'Tin': 7.29, 'Titanium': 4.51, 'Tungsten': 19.25, 
        'Uranium': 19.10, 'Vanadium': 6.11, 'Ytterbium': 6.97, 'Yttrium': 4.47, 
        'Zinc': 7.14, 'Zirconium': 6.52
    },
    'NONMETALS': {
        'Argon': 1.62, 'Bromine': 3.12, 'Carbon': 2.26, 'Chlorine': 2.03, 
        'Fluorine': 1.70, 'Helium': 0.19, 'Hydrogen': 0.09, 'Krypton': 2.82, 
        'Neon': 1.44, 'Nitrogen': 1.03, 'Oxygen': 1.43, 'Phosphorus': 1.82, 
        'Radon': 4.40, 'Selenium': 4.82, 'Sulfur': 2.07, 'Xenon': 3.64
    },
    'SEMIMETALS': {
        'Antimony': 6.69, 'Arsenic': 5.73, 'Astatine': 7.00, 'Boron': 2.46, 
        'Germanium': 5.32, 'Silicon': 2.33, 'Tellurium': 6.24
    }
}

