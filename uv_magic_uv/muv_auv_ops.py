# <pep8-80 compliant>

# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

__author__ = "Nutti <nutti.metro@gmail.com>, imdjs"
__status__ = "production"
__version__ = "4.5"
__date__ = "19 Nov 2017"

import math
from math import atan2, tan, sin, cos

import bpy
import bmesh
from mathutils import Vector
from bpy.props import EnumProperty


class MUV_AUVCircle(bpy.types.Operator):

    bl_idname = "uv.muv_auv_circle"
    bl_label = "Circle"
    bl_description = "Align UV coordinates to Circle"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def __get_circle(self, v):
        alpha = atan2((v[0].y - v[1].y), (v[0].x - v[1].x)) + math.pi / 2
        beta = atan2((v[1].y - v[2].y), (v[1].x - v[2].x)) + math.pi / 2
        ex = (v[0].x + v[1].x) / 2.0
        ey = (v[0].y + v[1].y) / 2.0
        fx = (v[1].x + v[2].x) / 2.0
        fy = (v[1].y + v[2].y) / 2.0
        cx = (ey - fy - ex * tan(alpha) + fx * tan(beta)) / (tan(beta) - tan(alpha))
        cy = ey - (ex - cx) * tan(alpha)
        center = Vector((cx, cy))

        r = v[0] - center
        radian = r.length

        return center, radian

    def __calc_new_uvs(self, uvs, center, radius):
        base = uvs[0]
        theta = atan2(base.y - center.y, base.x - center.x)
        new_uvs = []
        for i, uv in enumerate(uvs):
            angle = theta + i * 2 * math.pi / len(uvs)
            new_uvs.append(Vector((center.x + radius * sin(angle),
                                   center.y + radius * cos(angle))))

        return new_uvs

    def execute(self, context):
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        uv_layer = bm.loops.layers.uv.verify()

        sel_faces = [f for f in bm.faces if f.select]

        for f in sel_faces:
            uvs = [l[uv_layer].uv.copy() for l in f.loops]
            c, r = self.__get_circle(uvs[0:3])
            new_uvs = self.__calc_new_uvs(uvs, c, r)
            for l, uv in zip(f.loops, new_uvs):
                l[uv_layer].uv = uv

        bmesh.update_edit_mesh(obj.data)

        return {'FINISHED'}


class MUV_AUVSmooth(bpy.types.Operator):

    bl_idname = "uv.muv_auv_smooth"
    bl_label = "Smooth"
    bl_description = "Smooth UV coordinates"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        uv_layer = bm.loops.layers.uv.verify()

        sel_faces = [f for f in bm.faces if f.select]

        # get candidate loops
        cand_loops = []
        for f in sel_faces:
            for l in f.loops:
                if l[uv_layer].select:
                    cand_loops.append(l)

        # find first loop
        ordered_loops = []
        for l in cand_loops:
            if not l.link_loop_prev in cand_loops:
                ordered_loops.append(l)
                break
        else:
            self.report({'WARNING'}, "Selected UVs are looped")
            return {'CANCELLED'}

        # order loops
        next = ordered_loops[0].link_loop_next
        while True:
            if not next[uv_layer].select:
                break
            if next in ordered_loops:
                self.report({'WARNING'}, "Selected UVs are looped")
                return {'CANCELLED'}
            ordered_loops.append(next)
            next = next.link_loop_next

        if len(ordered_loops) != len(cand_loops):
            self.report({'WARNING'}, "Isolated UVs are found (Expected {0} but {1})".format(len(ordered_loops), len(cand_loops)))
            return {'CANCELLED'}

        # calculate path length
        accm_length = [0.0]
        full_length = 0
        orig_uvs = [ordered_loops[0][uv_layer].uv.copy()]
        for l1, l2 in zip(ordered_loops[:-1], ordered_loops[1:]):
            diff = l2[uv_layer].uv - l1[uv_layer].uv
            full_length = full_length + diff.length
            accm_length.append(full_length)
            orig_uvs.append(l2[uv_layer].uv.copy())

        # calculate target UV (exclude first/end loop)
        for i, l in enumerate(ordered_loops[1:-1]):
            target_length = full_length * (i+1) / (len(ordered_loops) - 1)
            for j in range(len(accm_length[:-1])):
                # get line segment to be placed
                if (accm_length[j] <= target_length) and (accm_length[j+1] > target_length):
                    tgt_seg_len = target_length - accm_length[j]
                    seg_len = accm_length[j+1] - accm_length[j]
                    uv1 = orig_uvs[j]
                    uv2 = orig_uvs[j+1]
                    target_uv = uv1 + (uv2 - uv1) * tgt_seg_len / seg_len
                    break
            else:
                self.report({'ERROR'}, "Failed to get target UV")
                return {'CANCELLED'}

            l[uv_layer].uv = target_uv

        bmesh.update_edit_mesh(obj.data)

        return {'FINISHED'}


class MUV_AUVStraighten(bpy.types.Operator):

    bl_idname = "uv.muv_auv_straighten"
    bl_label = "Straighten"
    bl_description = "Straighten UV coordinates"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        uv_layer = bm.loops.layers.uv.verify()

        sel_faces = [f for f in bm.faces if f.select]

        # get candidate loops
        cand_loops = []
        for f in sel_faces:
            for l in f.loops:
                if l[uv_layer].select:
                    cand_loops.append(l)

        # find first loop
        ordered_loops = []
        for l in cand_loops:
            if not l.link_loop_prev in cand_loops:
                ordered_loops.append(l)
                break
        else:
            self.report({'WARNING'}, "Selected UVs are looped")
            return {'CANCELLED'}

        # order loops
        next_ = ordered_loops[0].link_loop_next
        while True:
            if not next_[uv_layer].select:
                break
            if next_ in ordered_loops:
                self.report({'WARNING'}, "Selected UVs are looped")
                return {'CANCELLED'}
            ordered_loops.append(next_)
            next_ = next_.link_loop_next

        if len(ordered_loops) != len(cand_loops):
            self.report({'WARNING'}, "Isolated UVs are found (Expected {0} but {1})".format(len(ordered_loops), len(cand_loops)))
            return {'CANCELLED'}

        if len(ordered_loops) < 3:
            self.report({'WARNING'}, "More than 3 UVs must be selected")
            return {'CANCELLED'}

        # align
        first_uv = ordered_loops[0][uv_layer].uv.copy()
        last_uv = ordered_loops[-1][uv_layer].uv.copy()
        for i, l in enumerate(ordered_loops):
            diff = last_uv - first_uv
            l[uv_layer].uv = first_uv + diff * i / (len(ordered_loops) - 1)

        bmesh.update_edit_mesh(obj.data)

        return {'FINISHED'}


class MUV_AUVAxis(bpy.types.Operator):

    bl_idname = "uv.muv_auv_axis"
    bl_label = "XY-Axis"
    bl_description = "Align UV to XY-axis"
    bl_options = {'REGISTER', 'UNDO'}

    align = EnumProperty(
        name="Align",
        description="Align to ...",
        items=[
            ('LEFT_TOP', "Left/Top", "Align to Left or Top"),
            ('MIDDLE', "Middle", "Align to middle"),
            ('RIGHT_BOTTOM', "Right/Bottom", "Align to Right or Bottom")
        ],
        default='MIDDLE'
    )

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        uv_layer = bm.loops.layers.uv.verify()

        sel_faces = [f for f in bm.faces if f.select]

        # get candidate loops
        cand_loops = []
        for f in sel_faces:
            for l in f.loops:
                if l[uv_layer].select:
                    cand_loops.append(l)

        # find first loop
        ordered_loops = []
        for l in cand_loops:
            if not l.link_loop_prev in cand_loops:
                ordered_loops.append(l)
                break
        else:
            self.report({'WARNING'}, "Selected UVs are looped")
            return {'CANCELLED'}

        # order loops
        next_ = ordered_loops[0].link_loop_next
        while True:
            if not next_[uv_layer].select:
                break
            if next_ in ordered_loops:
                self.report({'WARNING'}, "Selected UVs are looped")
                return {'CANCELLED'}
            ordered_loops.append(next_)
            next_ = next_.link_loop_next

        if len(ordered_loops) != len(cand_loops):
            self.report({'WARNING'}, "Isolated UVs are found (Expected {0} but {1})".format(len(ordered_loops), len(cand_loops)))
            return {'CANCELLED'}

        if len(ordered_loops) < 3:
            self.report({'WARNING'}, "More than 3 UVs must be selected")
            return {'CANCELLED'}

        # get height and width
        uv_max = Vector((0.0, 0.0))
        uv_min = Vector((0.0, 0.0))
        for l in ordered_loops:
            uv = l[uv_layer].uv
            uv_max.x = max(uv.x, uv_max.x)
            uv_max.y = max(uv.y, uv_max.y)
            uv_min.x = min(uv.x, uv_min.x)
            uv_min.y = min(uv.y, uv_min.y)
        width = uv_max.x - uv_min.x
        height = uv_max.y - uv_min.y

        # align along to horizontal line
        if width > height:
            for i, l in enumerate(ordered_loops):
                if self.align == 'LEFT_TOP':
                    l[uv_layer].uv.x = uv_min.x
                elif self.align == 'MIDDLE':
                    l[uv_layer].uv.x = uv_min.x + width * 0.5
                elif self.align == 'RIGHT_BOTTOM':
                    l[uv_layer].uv.x = uv_min.x + width
                l[uv_layer].uv.y = uv_min.y + i / (len(ordered_loops) - 1)
        # align along to vertical line
        else:
            for i, l in enumerate(ordered_loops):
                if self.align == 'LEFT_TOP':
                    l[uv_layer].uv.y = uv_min.y + height
                elif self.align == 'MIDDLE':
                    l[uv_layer].uv.y = uv_min.y + height * 0.5
                elif self.align == 'RIGHT_BOTTOM':
                    l[uv_layer].uv.y = uv_min.y
                l[uv_layer].uv.x = uv_min.x + i / (len(ordered_loops) - 1)

        bmesh.update_edit_mesh(obj.data)

        return {'FINISHED'}

