# 🏗️ Layouts & Systems Draftsman Toolkit (LSDT)

![Header Image](https://raw.githubusercontent.com/Japzon/Layouts-Systems-Draftsman-Toolkit-Addon/main/header.png)

An integrated toolkit for Blender designed to assist in architectural drafting, mechanical modeling, and robotics rigging. LSD provides a collection of scripted utilities that automate repetitive tasks like dimensioning, joint configuration, and part generation.

---

# ⚖️ LEGAL PROTECTION & LICENSE (GPL COMPLIANT)
Copyright (c) 2026 Greenlex Systems Services Incorporated. All rights reserved.

This toolkit is licensed under the **GNU General Public License (GPL)**. The hardware design logic and original architecture remain the intellectual property of **Greenlex Systems Services Incorporated**. 

---

## 🚀 Core Features & Usage

### 🤖 Robotics Joint Editor (Kinematics)
*   **How it works**: LSD utilizes Blender's native **Armature system**. By tagging bones in Pose Mode, the add-on attaches custom mechatronic properties and interactive 3D gizmos to the rig.
*   **Joint Configuration**: Easily define joints as Revolute, Prismatic, or Fixed. The editor provides real-time visual feedback for joint axes and motion limits.
*   **Physics Helpers**: Includes utilities to estimate **Center of Mass** and **Inertia Tensors** based on the volume and distribution of mesh objects parented to the bones.
*   **Rigging Tools**: Streamlined operators for aligning bone axes to geometry and managing parent-child bone relationships for multi-link robots.

### 📐 Procedural Drafting Dimensions
*   **How it works**: Dimension lines are generated as **parametric Empty rigs**. Each rig consists of a line, arrowheads, and a text label that measures the distance between two points.
*   **Interactive Adjustments**: Once generated, you can adjust the offset from the target, arrow scale, and font size directly from the N-panel.
*   **Vertex Snapping**: Place "Parametric Anchors" on mesh vertices to act as precise hooks for dimension lines, ensuring they follow the geometry if the underlying mesh is modified.

### ⚙️ Scripted Procedural Parts
*   **How it works**: LSD uses **BMesh scripting** to generate geometry on the fly. When you change a property (like gear teeth or wall height), the add-on recalculates and rebuilds the mesh data.
*   **Mechanical Presets**: Generate gears, racks, pulleys, and NEMA motors with accurate proportions. These parts can be "baked" into standard static meshes once the design is finalized.
*   **Architectural Presets**: Rapidly create walls, pillars, windows, and stairs using metric inputs. Features like door frames and window glass are generated as part of the modular mesh logic.
*   **Size Cage**: A global bounding-box system (Size Cage) helps ensure that generated parts fit within the maximum dimensional constraints of your project.

### 📦 Streamlined Asset Management
*   **Asset Browser Integration**: A simplified interface for Blender's native Asset Browser. It automates common tasks like marking objects as assets, assigning UUID-based catalogs, and organizing files into project directories.
*   **Import/Export**: Batch-import external models and automatically catalog them into your local or global libraries.

### 🧪 Generation Hub (Early Access)
*   **Template Hub**: A central panel to spawn complex assemblies using keyword-based templates. 
*   **Note**: The AI-driven prompt system is currently in early development and functions primarily through local keyword matching (e.g., "Rover", "Arm") to trigger pre-defined assembly scripts.

---

## 🛠 Installation & Access
1.  **Install**: In Blender, go to `Edit > Preferences > Add-ons > Install` and select the lsd_toolkit.zip.
2.  **Activate**: Enable `Layouts & Systems Draftsman Toolkit` in the list.
3.  **Usage**: All tools are located in the **3D Viewport Sidebar (N-Panel)** under the tab **Layouts & Systems Toolkit**.

---

**Author**: Greenlex Systems Services Incorporated  
**Support**: Documentation and issue tracking are handled via the [GitHub Repository](https://github.com/Japzon/Layouts-Systems-Draftsman-Toolkit-Addon).
