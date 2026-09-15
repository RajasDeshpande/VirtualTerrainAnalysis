"""Offline GLB visual QA in Blender, independent of the web material toggles."""
import bpy
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]
for mode,filename in [('imagery','terrain-imagery.glb'),('slope','terrain.glb')]:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(ROOT/'webxr/assets'/filename))
    scene=bpy.context.scene
    terrain=next(o for o in scene.objects if o.type=='MESH')
    points=[terrain.matrix_world @ v.co for v in terrain.data.vertices]
    width=max(p.x for p in points)-min(p.x for p in points)
    # Imported glTF is converted back to Blender Z-up.
    center=Vector((0,0,(max(p.z for p in points)+min(p.z for p in points))/2))
    bpy.ops.object.camera_add(location=(width*.55,-width*.8,width*1.1))
    camera=bpy.context.object;camera.rotation_euler=(center-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.type='ORTHO';camera.data.ortho_scale=width*1.55;camera.data.clip_end=20000;scene.camera=camera
    for mat in terrain.data.materials:
        if not mat or not mat.use_nodes:continue
        nodes=mat.node_tree.nodes;output=next(n for n in nodes if n.type=='OUTPUT_MATERIAL')
        emission=nodes.new('ShaderNodeEmission')
        textures=[n for n in nodes if n.type=='TEX_IMAGE']
        if textures:mat.node_tree.links.new(textures[0].outputs['Color'],emission.inputs['Color'])
        else:
            bsdf=next(n for n in nodes if n.type=='BSDF_PRINCIPLED')
            emission.inputs['Color'].default_value=bsdf.inputs['Base Color'].default_value
        mat.node_tree.links.new(emission.outputs[0],output.inputs['Surface'])
    scene.render.engine='BLENDER_EEVEE';scene.render.resolution_x=1100;scene.render.resolution_y=850;scene.render.resolution_percentage=100
    scene.world=bpy.data.worlds.new('PreviewBackground');scene.world.color=(.015,.025,.04)
    scene.view_settings.view_transform='Standard';scene.view_settings.look='None'
    scene.render.filepath=str(ROOT/f'logs/{mode}-preview.png')
    bpy.ops.render.render(write_still=True)
