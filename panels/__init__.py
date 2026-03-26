# --------------------------------------------------------------------------------
# Copyright (c) 2026 Greenlex Systems Services Incorporated. All rights reserved.
#
# Licensed under the GNU General Public License (GPL).
# Original Architecture & Logic by Greenlex Systems Services Incorporated.
#
# No person or organization is authorized to misrepresent this work or claim 
# original authorship for themselves. Proper attribution is mandatory.
# --------------------------------------------------------------------------------




from . import ui_common
from . import ui_ai_factory
from . import ui_parts
from . import ui_materials
from . import ui_lighting
from . import ui_electronics
from . import ui_dimensions
from . import ui_architectural
from . import ui_vehicle
from . import ui_parametric
from . import ui_inertial
from . import ui_collision
from . import ui_transmission
from . import ui_kinematics
from . import ui_assets
from . import ui_export
from . import ui_preferences
from . import ui_main

modules = [
    ui_common,
    ui_ai_factory,
    ui_parts,
    ui_materials,
    ui_lighting,
    ui_electronics,
    ui_dimensions,
    ui_architectural,
    ui_vehicle,
    ui_parametric,
    ui_inertial,
    ui_collision,
    ui_transmission,
    ui_kinematics,
    ui_assets,
    ui_export,
    ui_preferences,
    ui_main,
]

def register():
    for mod in modules:
        mod.register()

def unregister():
    for mod in reversed(modules):
        mod.unregister()

