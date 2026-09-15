"""Blender: --background source.blend --python terrain_analysis.py.
Slopes use evaluated, world-space triangle geometry and explicit geographic up.
Do not infer up from mesh shape: a steep hillside need not have a flat base.
"""
import bpy, bmesh, math, json, os, csv
from pathlib import Path
from mathutils import Vector, Matrix

ROOT = Path(os.environ.get('TERRAIN_BUILD_ROOT', Path(__file__).resolve().parents[1]))
# EDITABLE CONFIGURATION: shared boundaries belong to the lower-slope class.
CLASSES = [(10, 'BLUE', '#187BFF'), (25, 'GREEN', '#32B85A'),
           (35, 'YELLOW', '#FFE234'), (45, 'ORANGE', '#FF8A24'),
           (90, 'RED', '#ED3349')]
UP_WORLD = None  # Override e.g. (0, 1, 0); otherwise require object metadata.
METRES_PER_UNIT = 1.0

def triangle_metrics(a, b, c, up):
    cross = (b-a).cross(c-a)
    length = cross.length
    if length < 1e-12:
        raise ValueError('Degenerate terrain triangle')
    cosine = max(0.0, min(1.0, abs(cross.dot(up)) / length))
    return math.degrees(math.acos(cosine)), length/2, abs(cross.dot(up))/2

def classify(slope):
    return next(i for i, (upper, _, _) in enumerate(CLASSES) if slope <= upper + 1e-8)

def linear_color(hex_color):
    s = [int(hex_color[i:i+2],16)/255 for i in (1,3,5)]
    return tuple(v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in s) + (1,)

def run():
    provenance_file=ROOT/'data/provenance.json'
    provenance=json.loads(provenance_file.read_text(encoding='utf-8')) if provenance_file.exists() else {}
    candidates = [o for o in bpy.context.scene.objects if o.type == 'MESH' and o.get('terrain_source')]
    if not candidates:
        candidates = [o for o in bpy.context.selected_objects if o.type == 'MESH']
    if len(candidates) != 1:
        raise ValueError('Select exactly one terrain mesh or tag it with terrain_source')
    obj = candidates[0]
    up_value = UP_WORLD or obj.get('analysis_up_world')
    if up_value is None:
        raise ValueError('Set UP_WORLD or analysis_up_world; geographic up cannot be inferred safely')
    up = Vector(up_value).normalized()
    assert up.length > .99
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = bpy.data.meshes.new_from_object(evaluated)
    bm = bmesh.new(); bm.from_mesh(mesh)
    bmesh.ops.triangulate(bm, faces=list(bm.faces)); bm.to_mesh(mesh); bm.free()
    world = [evaluated.matrix_world @ v.co * METRES_PER_UNIT for v in mesh.vertices]
    offset = float(obj.get('elevation_offset_m', 0))
    elevations = [p.dot(up) + offset for p in world]
    assert all(math.isfinite(z) for z in elevations)
    rows = [dict(name=name, color=color, upper_deg=upper, surface_area_m2=0,
                 horizontal_area_m2=0, triangles=0) for upper,name,color in CLASSES]
    slopes, total_area, weighted_slope, weighted_elevation = [], 0, 0, 0
    assignments = []
    for face in mesh.polygons:
        a,b,c = (world[i] for i in face.vertices)
        slope, area, horizontal = triangle_metrics(a,b,c,up)
        idx = classify(slope); assignments.append(idx); slopes.append(slope)
        row = rows[idx]; row['surface_area_m2'] += area
        row['horizontal_area_m2'] += horizontal; row['triangles'] += 1
        total_area += area; weighted_slope += slope * area
        weighted_elevation += (sum(elevations[i] for i in face.vertices)/3) * area
    total_horizontal = sum(r['horizontal_area_m2'] for r in rows)
    for r in rows:
        r['surface_percent'] = 100*r['surface_area_m2']/total_area
        r['horizontal_percent'] = 100*r['horizontal_area_m2']/total_horizontal
    stats = dict(min_elevation_m=min(elevations), max_elevation_m=max(elevations),
        elevation_range_m=max(elevations)-min(elevations),
        average_elevation_m=weighted_elevation/total_area,
        min_slope_deg=min(slopes), max_slope_deg=max(slopes),
        average_slope_deg=weighted_slope/total_area,
        averaging='Triangle surface-area weighted', surface_area_m2=total_area,
        horizontal_area_m2=total_horizontal, classes=rows,
        vertices=len(world), triangles=len(mesh.polygons),
        boundary_rule='[0,10], (10,25], (25,35], (35,45], (45,90]',
        up_world=list(up), source=obj.get('terrain_source','Selected terrain'),
        interpretation='Slope classes only; terrain traversability also depends on surface and obstacles.')
    stats['place_name']=obj.get('place_name',provenance.get('place_name','Selected terrain'))
    stats['quality']=provenance.get('quality',{})
    stats['imagery']=provenance.get('imagery',{'available':False})
    stats['crs']=provenance.get('crs',obj.get('crs','Unspecified'))
    stats['center_lon_lat']=provenance.get('center_lon_lat')
    stats['build_id']=os.environ.get('TERRAIN_BUILD_ID','manual')
    mesh.materials.clear()
    for _, name, color in CLASSES:
        mat = bpy.data.materials.new('Slope_' + name)
        mat.use_nodes = True
        mat.diffuse_color = linear_color(color)
        node = mat.node_tree.nodes.get('Principled BSDF')
        node.inputs['Base Color'].default_value = linear_color(color)
        node.inputs['Roughness'].default_value = 1
        mesh.materials.append(mat)
    for face, idx in zip(mesh.polygons, assignments):
        face.material_index = idx; face.use_smooth = False
    # Bake world transforms and map declared geographic up onto Blender +Z.
    rotation = up.rotation_difference(Vector((0,0,1)))
    points = [rotation @ p for p in world]
    center = Vector(((min(p.x for p in points)+max(p.x for p in points))/2,
                     (min(p.y for p in points)+max(p.y for p in points))/2,
                     min(p.z for p in points)))
    for v,p in zip(mesh.vertices, points): v.co = p-center
    if provenance.get('origin_easting_northing_m'):
        origin=provenance['origin_easting_northing_m']
        stats['export_origin_easting_northing_m']=[origin[0]+center.x,origin[1]+center.y]
        stats['export_elevation_offset_m']=min(elevations)
        # Real geographic UVs are generated before export. glTF converts V.
        if stats['imagery'].get('available'):
            x0,y0,x1,y1=stats['imagery']['extent_projected_m']
            uv=mesh.uv_layers.new(name='GeoreferencedImagery')
            for loop in mesh.loops:
                p=world[loop.vertex_index]
                uv.data[loop.index].uv=((p.x+origin[0]-x0)/(x1-x0),(p.y+origin[1]-y0)/(y1-y0))
        # Point/elevation CSV with projected coordinates is usable for data work.
        with (ROOT/'webxr/assets/elevation-samples.csv').open('w',newline='',encoding='utf-8') as f:
            writer=csv.writer(f);writer.writerow(['easting_m','northing_m','elevation_m','crs'])
            for p,z in zip(world,elevations):writer.writerow([round(p.x+origin[0],3),round(p.y+origin[1],3),round(z,3),stats['crs']])
        with (ROOT/'webxr/assets/slope-triangles.csv').open('w',newline='',encoding='utf-8') as f:
            writer=csv.writer(f);writer.writerow(['centroid_easting_m','centroid_northing_m','elevation_m','slope_degrees','class','surface_area_m2'])
            for face,slope,cls in zip(mesh.polygons,slopes,assignments):
                a,b,c=(world[i] for i in face.vertices);p=(a+b+c)/3
                writer.writerow([round(p.x+origin[0],3),round(p.y+origin[1],3),round(p.dot(up)+offset,3),round(slope,4),CLASSES[cls][1],round((b-a).cross(c-a).length/2,3)])
    obj.modifiers.clear(); obj.data = mesh; obj.matrix_world = Matrix.Identity(4)
    obj['analysis_up_world'] = [0.,0.,1.]
    obj['elevation_offset_m'] = min(elevations)
    obj['export_origin_shift_m'] = list(center)
    bpy.context.view_layer.update()
    stats['export_dimensions_m'] = list(obj.dimensions)
    (ROOT/'webxr/assets/terrain-stats.json').write_text(json.dumps(stats,indent=2),encoding='utf-8')
    bpy.ops.object.select_all(action='DESELECT'); obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.gltf(filepath=str(ROOT/'webxr/assets/terrain.glb'),
        export_format='GLB', use_selection=True, export_materials='EXPORT',
        export_yup=True, export_extras=True)
    if stats['imagery'].get('available'):
        imagery_mat=bpy.data.materials.new('Actual_aerial_imagery')
        imagery_mat.use_nodes=True
        image_node=imagery_mat.node_tree.nodes.new('ShaderNodeTexImage')
        image_node.image=bpy.data.images.load(str(ROOT/'webxr/assets/imagery.jpg'))
        image_node.image.pack()
        bsdf=imagery_mat.node_tree.nodes.get('Principled BSDF')
        imagery_mat.node_tree.links.new(image_node.outputs['Color'],bsdf.inputs['Base Color'])
        bsdf.inputs['Roughness'].default_value=1
        saved_materials=list(mesh.materials)
        mesh.materials.clear();mesh.materials.append(imagery_mat)
        for face in mesh.polygons:face.material_index=0
        bpy.ops.export_scene.gltf(filepath=str(ROOT/'webxr/assets/terrain-imagery.glb'),
            export_format='GLB',use_selection=True,export_materials='EXPORT',export_yup=True)
        mesh.materials.clear()
        for mat in saved_materials:mesh.materials.append(mat)
        for face,idx in zip(mesh.polygons,assignments):face.material_index=idx
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces.active.shading.type = 'SOLID'
                area.spaces.active.shading.color_type = 'MATERIAL'
                area.spaces.active.clip_end = 20000
                region = area.spaces.active.region_3d
                region.view_location = Vector((0,0,obj.dimensions.z/2))
                region.view_distance = max(obj.dimensions)*1.5
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'blender/terrain.blend'))
    print('ANALYSIS_VERIFIED', json.dumps(stats))

if __name__ == '__main__': run()
