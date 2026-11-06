"""依据所给 Word 和照片编写的设备展示模型源文件。

尺寸使用照片比例建模单位，不是工程实测尺寸。
blender -b --python build_model.py -- --config parameters.json --out DIR [--render]
"""
from pathlib import Path
import argparse
import json
import math
import struct
import sys

import bpy
import bmesh
from mathutils import Vector

MATERIALS = {}
ROOT = None

def material(name, color, metallic=0.55, roughness=0.38):
    mat = bpy.data.materials.new(name)
    if not mat.node_tree:
        mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Metallic'].default_value = metallic
    bsdf.inputs['Roughness'].default_value = roughness
    mat.diffuse_color = (*color, 1)
    MATERIALS[name] = mat
    return mat

def group(name, parent=None, location=(0, 0, 0), **metadata):
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    obj.parent = parent or ROOT
    obj.location = location
    for key, value in metadata.items():
        obj[key] = value
    return obj

def finish(obj, name, mat, parent, bevel=0):
    obj.name = name
    obj.parent = parent
    obj.data.materials.append(MATERIALS[mat])
    if bevel:
        modifier = obj.modifiers.new('ManufacturingEdge', 'BEVEL')
        modifier.width = bevel
        modifier.segments = 2
    return obj

def box(name, pos, size, mat='housing', parent=None, bevel=0.035):
    bpy.ops.mesh.primitive_cube_add(size=1, location=pos)
    obj = bpy.context.object
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return finish(obj, name, mat, parent or ROOT, bevel)

def cylinder(name, pos, radius, depth, mat='steel', parent=None, axis='Y', vertices=48):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=pos)
    obj = bpy.context.object
    if axis == 'Y':
        obj.rotation_euler.x = math.pi / 2
    elif axis == 'X':
        obj.rotation_euler.y = math.pi / 2
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    for face in obj.data.polygons:
        face.use_smooth = len(face.vertices) == 4
    return finish(obj, name, mat, parent or ROOT, 0.009 if vertices > 12 else 0)

def rod(name, start, end, radius, mat='steel', parent=None):
    delta = Vector(end) - Vector(start)
    obj = cylinder(name, (Vector(start) + Vector(end)) / 2, radius, delta.length, mat, parent, axis='Z', vertices=16)
    obj.rotation_euler = delta.to_track_quat('Z', 'Y').to_euler()
    return obj

def bolts(prefix, x, y, z, radius, count, parent):
    for i in range(count):
        angle = math.tau * i / count
        cylinder(f'{prefix}_{i:02}', (x + radius * math.cos(angle), y, z + radius * math.sin(angle)), 0.027, 0.035, 'steel', parent, vertices=6)

def ring(name, x, y, z, outer, inner, width, parent, mat='wheel'):
    count = 64
    vertices, faces = [], []
    for offset in [-width / 2, width / 2]:
        for radius in [outer, inner]:
            vertices.extend((x + radius * math.cos(math.tau*i/count), y+offset, z + radius * math.sin(math.tau*i/count)) for i in range(count))
    for i in range(count):
        j = (i+1) % count
        faces.extend([(i,j,2*count+j,2*count+i), (count+i,3*count+i,3*count+j,count+j),
                      (i,count+i,count+j,j), (2*count+i,2*count+j,3*count+j,3*count+i)])
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    for polygon in mesh.polygons:
        polygon.use_smooth = polygon.index % 4 < 2
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return finish(obj, name, mat, parent)

def pulley(name, x, y, z, radius):
    pivot = group(name, location=(x, y, z), motionKey=name, rotationAxis=[0.0, 0.0, -1.0])
    # 原图中两个带轮均为五个圆形减重孔。
    disc = cylinder(name+'_FiveHoleDisc', (0,0,0), radius*.91, .14, 'wheel', pivot, vertices=96)
    for modifier in list(disc.modifiers):
        bpy.context.view_layer.objects.active=disc
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    for i in range(5):
        angle = math.tau*i/5 + math.pi/2
        cutter=cylinder('HoleCutter', (radius*.55*math.cos(angle),0,radius*.55*math.sin(angle)), radius*.212, .5, 'steel', pivot, vertices=40)
        for modifier in list(cutter.modifiers):cutter.modifiers.remove(modifier)
        modifier=disc.modifiers.new('LighteningHole','BOOLEAN')
        modifier.operation='DIFFERENCE';modifier.solver='EXACT';modifier.object=cutter
        bpy.context.view_layer.objects.active=disc
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        bpy.data.objects.remove(cutter,do_unlink=True)
    ring(name+'_Rim', 0, 0, 0, radius, radius*.88, .23, pivot)
    for i in [-1,0,1]:
        ring(name+f'_Groove_{i}',0,i*.068,0,radius+.006,radius-.015,.012,pivot,'steel')
    cylinder(name+'_Hub', (0,0,0), radius*.235, .26, 'wheel', pivot)
    cylinder(name+'_ShaftEndCap', (0,-.16,0), radius*.115, .055, 'steel', pivot, vertices=32)
    cylinder(name+'_RetainingNut', (0,-.194,0), radius*.060, .018, 'steel', pivot, vertices=6)
    bolts(name+'_HubBolt',0,-.145,0,radius*.18,5,pivot)
    return pivot

def extruded_profile(name, outline, depth, mat, parent, smooth_sides=False):
    """将封闭的 X/Z 截面沿 Y 方向挤出，生成铸造壳体或筋板。"""
    n=len(outline)
    verts=[(x,y,z) for y in [-depth/2,depth/2] for x,z in outline]
    faces=[tuple(range(n-1,-1,-1)),tuple(range(n,2*n))]
    faces += [(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],faces);mesh.update()
    if smooth_sides:
        for face in list(mesh.polygons)[2:]:face.use_smooth=True
    obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj)
    return finish(obj,name,mat,parent,.025)

def belt_path(c1, c2, r1, r2):
    delta = Vector(c2)-Vector(c1)
    heading = math.atan2(delta.y, delta.x)
    alpha = math.acos((r1-r2)/delta.length)
    top, bottom = heading+alpha, heading-alpha
    def point(center, radius, angle):
        return Vector(center)+Vector((math.cos(angle), math.sin(angle)))*radius
    path = [point(c1,r1,top),point(c2,r2,top)]
    path += [point(c2,r2,top+(bottom-top)*i/64) for i in range(1,65)]
    path += [point(c1,r1,bottom)]
    path += [point(c1,r1,bottom+(top-math.tau-bottom)*i/48) for i in range(1,48)]
    return path

def belt(c1, c2, r1, r2, y, count):
    # 皮带内表面贴合带轮轮缘，外表面按皮带厚度向外偏移。
    thickness=0.015
    path = belt_path(c1,c2,r1+thickness,r2+thickness)
    vertices, faces, uvs = [], [], []
    total = sum((path[(i+1)%len(path)]-p).length for i,p in enumerate(path))
    for k in range(count):
        offset = (k-(count-1)/2)*0.068
        travelled = 0
        for i,p in enumerate(path):
            q = path[(i+1)%len(path)]
            normal = Vector((-(q-p).y,(q-p).x)).normalized()*0.014
            base = len(vertices)
            vertices += [(p.x,y+offset-0.018,p.y),(p.x,y+offset+0.018,p.y),
                         (q.x,y+offset+0.018,q.y),(q.x,y+offset-0.018,q.y)]
            faces.append((base,base+3,base+2,base+1))
            step=(q-p).length
            uvs += [(travelled/total*18,0),((travelled+step)/total*18,0),((travelled+step)/total*18,1),(travelled/total*18,1)]
            travelled += step
    mesh = bpy.data.meshes.new('DriveBeltGeometry')
    mesh.from_pydata(vertices,[],faces)
    mesh.update()
    layer=mesh.uv_layers.new(name='BeltTravel')
    for i,uv in enumerate(uvs):layer.data[i].uv=uv
    obj=bpy.data.objects.new('DriveBelt',mesh)
    bpy.context.collection.objects.link(obj)
    finish(obj,'DriveBelt','belt',ROOT)
    obj['motionKey']='belt'
    solid=obj.modifiers.new('BeltThickness','SOLIDIFY');solid.thickness=thickness;solid.offset=-1
    return obj

def make_materials():
    def linear(hex_color):
        values=[((hex_color >> shift)&255)/255 for shift in (16,8,0)]
        return tuple(v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values)
    # 沿用公司现有组件的基础配色和材质参数。
    for name in ['housing','motor','base','guard_frame','pump']:
        material(name,linear(0x18fefe),.7,.4)
    material('steel',linear(0xc9c8ca),.7,.5)
    material('wheel',linear(0xc9c8ca),.7,.5)
    material('guard_mesh',linear(0x77858c),.6,.6)
    material('recess',linear(0x131a21),.05,.88)
    mat=material('belt',linear(0x151a1e),0,.85)
    image=bpy.data.images.new('BeltMotionMarks',width=64,height=16)
    image.pixels=[c for yy in range(16) for xx in range(64)
                  for c in ((.06,.06,.06,1) if (xx+yy*2)%64<5 else (.005,.005,.005,1))]
    image.pack()
    texture=mat.node_tree.nodes.new('ShaderNodeTexImage');texture.image=image;texture.extension='REPEAT'
    bsdf=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    mat.node_tree.links.new(texture.outputs['Color'],bsdf.inputs['Base Color'])

def guard_frame(outer, inner, y, depth, parent):
    n=len(outer)
    verts=[]
    for sy in [y-depth/2,y+depth/2]:
        for path in [outer,inner]:verts += [(p.x,sy,p.y) for p in path]
    faces=[]
    for i in range(n):
        j=(i+1)%n
        faces += [(i,j,n+j,n+i),(2*n+i,3*n+i,3*n+j,2*n+j),
                  (i,2*n+i,2*n+j,j),(n+i,n+j,3*n+j,3*n+i)]
    mesh=bpy.data.meshes.new('SlopingGuardFrame');mesh.from_pydata(verts,[],faces);mesh.update()
    obj=bpy.data.objects.new('SlopingGuardFrame',mesh);bpy.context.collection.objects.link(obj)
    return finish(obj,obj.name,'housing',parent,.008)

def clipped_mesh_line(outline, slope, offset):
    intersections=[]
    for i,p in enumerate(outline):
        q=outline[(i+1)%len(outline)]
        dp=p.x+slope*p.y-offset;dq=q.x+slope*q.y-offset
        if abs(dp)<1e-8:intersections.append(p.copy())
        if dp*dq<0:intersections.append(p+(q-p)*(dp/(dp-dq)))
    if len(intersections)<2:return None
    intersections.sort(key=lambda p:p.x)
    a,b=intersections[0],intersections[-1]
    return (a,b) if (a-b).length>.04 else None

def build_guard(cfg, c1, c2):
    spec=cfg['guard'];y=spec['y'];depth=spec['depth']
    guard=group('BeltGuard',partKey='guard')
    frame=group('BeltGuardFrame',guard)
    mesh_group=group('BeltGuardMesh',guard)
    outer=belt_path(c1,c2,spec['smallRadius'],spec['largeRadius'])
    inner=belt_path(c1,c2,spec['smallRadius']-spec['frameWidth'],spec['largeRadius']-spec['frameWidth'])
    guard_frame(outer,inner,y,depth,frame)
    # 金属网使用不透明的四边线材几何，避免透明混合与排序问题。
    # 按两个不同半径圆形成的外轮廓裁切斜线。
    for slope in [-1,1]:
        values=[p.x+slope*p.y for p in inner]
        for k in range(math.floor(min(values)/spec['meshPitch']),math.ceil(max(values)/spec['meshPitch'])+1):
            segment=clipped_mesh_line(inner,slope,k*spec['meshPitch'])
            if not segment:continue
            a,b=segment
            start=Vector((a.x,y-depth/2+.018,a.y));end=Vector((b.x,y-depth/2+.018,b.y))
            delta=end-start
            obj=cylinder(f'GuardWire_{slope}_{k}',(start+end)/2,spec['wireRadius'],delta.length,'guard_mesh',mesh_group,axis='Z',vertices=4)
            obj.rotation_euler=delta.to_track_quat('Z','Y').to_euler()
    # 保留一根竖向立柱，对应参考图中的中间支架。
    rail_x=spec['railX'];crossings=clipped_mesh_line(outer,0,rail_x)
    if crossings:
        # 竖向裁切线的 x 恒定，因此按高度显式排序。
        low,high=sorted(crossings,key=lambda p:p.y)
        box('GuardCentralUpright',(rail_x,y,(low.y+high.y)/2),(.18,depth+.018,high.y-low.y),'housing',frame,.009)
    for i,(px,pz) in enumerate(spec['boltXZs']):
        cylinder(f'GuardFrameBolt_{i}',(px,y-depth/2-.018,pz),.029,.028,'housing',frame,vertices=12)
    return guard

def sensor(points,key,label,parent,pos,part,certainty,description):
    name='Anchor_'+key
    group(name,parent,location=pos,anchorId=key)
    points.append({'key':key,'label':label,'partKey':part,'anchor':name,
                   'localPosition':list(pos),'coordinateSystem':'Blender XYZ, proportional units',
                   'positionSource':certainty,'description':description})

def build(cfg):
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    from geometry import build_equipment
    return build_equipment(cfg,globals())

def report_glb(path):
    with path.open('rb') as f:
        magic,version,total=struct.unpack('<4sII',f.read(12))
        length,chunk=struct.unpack('<II',f.read(8))
        doc=json.loads(f.read(length))
    if magic!=b'glTF' or version!=2 or total!=path.stat().st_size:
        raise RuntimeError('Invalid GLB header')
    triangles=sum(doc['accessors'][p['indices']]['count']//3 for mesh in doc.get('meshes',[]) for p in mesh['primitives'] if 'indices' in p)
    return {'bytes':total,'triangles':triangles,'nodes':len(doc.get('nodes',[])),'meshes':len(doc.get('meshes',[])),
            'materials':len(doc.get('materials',[])),'anchors':sorted(n['extras']['anchorId'] for n in doc.get('nodes',[]) if 'anchorId' in n.get('extras',{})),
            'names':[n.get('name') for n in doc.get('nodes',[])],'extensions':doc.get('extensionsUsed',[])}

def merge_static_meshes():
    """在保留独立动画和报警部件的前提下合并网格，减少绘制调用。"""
    buckets={}
    for obj in list(ROOT.children_recursive):
        if obj.type=='MESH':
            key=(obj.parent.name, obj.data.materials[0].name)
            buckets.setdefault(key,[]).append(obj)
    for (parent,mat),objects in buckets.items():
        if len(objects)<2:continue
        bpy.ops.object.select_all(action='DESELECT')
        for obj in objects:obj.select_set(True)
        bpy.context.view_layer.objects.active=objects[0]
        # 合并前应用小倒角，保持边缘宽度一致。
        for obj in objects:
            bpy.context.view_layer.objects.active=obj
            for modifier in list(obj.modifiers):bpy.ops.object.modifier_apply(modifier=modifier.name)
        bpy.context.view_layer.objects.active=objects[0]
        bpy.ops.object.join()
        bpy.context.object.name=parent+'_'+mat+'_Mesh'
    for obj in list(ROOT.children_recursive):
        if obj.type!='MESH':continue
        bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
        for modifier in list(obj.modifiers):bpy.ops.object.modifier_apply(modifier=modifier.name)
        bm=bmesh.new();bm.from_mesh(obj.data)
        bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=0.000001)
        bmesh.ops.dissolve_degenerate(bm,edges=list(bm.edges),dist=0.000001)
        bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
        bm.to_mesh(obj.data);bm.free();obj.data.update()

def setup_render(out,draft=False):
    scene=bpy.context.scene
    scene.render.engine='CYCLES'
    scene.cycles.samples=16 if draft else 96
    scene.cycles.use_denoising=True
    scene.render.resolution_x=1000 if draft else 1600
    scene.render.resolution_y=700 if draft else 1000
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG'
    scene.render.film_transparent=True
    scene.view_settings.exposure=-.30
    scene.world=bpy.data.worlds.new('WorkshopStudio')
    scene.world.use_nodes=True
    scene.world.node_tree.nodes.get('Background').inputs[0].default_value=(.045,.065,.10,1)
    scene.world.node_tree.nodes.get('Background').inputs[1].default_value=.5
    material('floor',(.028,.045,.068),.12,.55)
    floor=box('RenderFloor',(4.3,0,-.72),(200,200,.08),'floor',bevel=0)
    floor.parent=None
    floor.hide_render=True
    for name,pos,power,size in [('Key',(1,-5,7),1300,6),('Fill',(8,-2,4),700,5),('Rim',(5,5,6),1000,5),('TailFill',(14,-3,5),850,4.5)]:
        data=bpy.data.lights.new(name,'AREA');data.energy=power;data.shape='DISK';data.size=size
        obj=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(obj);obj.location=pos
        obj.rotation_euler=(Vector((4.3,0,.9))-obj.location).to_track_quat('-Z','Y').to_euler()
    data=bpy.data.cameras.new('ReviewCamera');cam=bpy.data.objects.new('ReviewCamera',data);bpy.context.collection.objects.link(cam)
    scene.camera=cam;data.type='ORTHO';data.ortho_scale=10.2
    return cam

def front_camera(cfg):
    spec=cfg['reviewCamera']
    azimuth=math.radians(spec['frontAzimuthDeg'])
    elevation=math.radians(spec['frontElevationDeg'])
    direction=Vector((math.sin(azimuth)*math.cos(elevation),-math.cos(azimuth)*math.cos(elevation),math.sin(elevation)))
    target=Vector(spec['target'])
    return target+direction*18,target,spec['frontOrthoScale'],direction

def main():
    global ROOT
    args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);parser.add_argument('--out',required=True);parser.add_argument('--render',action='store_true')
    parser.add_argument('--draft',action='store_true');parser.add_argument('--clay',action='store_true')
    parser.add_argument('--shots',default='',help='Optional comma-separated review shot names')
    parser.add_argument('--samples',type=int,default=0,help='Optional Cycles samples for review renders')
    parser.add_argument('--bake-ao',action='store_true')
    args=parser.parse_args(args)
    cfg=json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
    g=cfg['gearbox']
    if len(g['shaftXs'])!=len(g['shaftZs']) or not g['shaftXs']:raise ValueError('Shaft coordinates inconsistent')
    out=Path(args.out).resolve();out.mkdir(parents=True,exist_ok=True)
    points=build(cfg)
    for point in points:
        naming=cfg.get('pointNames',{}).get(point['key'],{})
        point['label']=naming.get('label',point['label'])
        if naming.get('aliases'):point['aliases']=naming['aliases']
    merge_static_meshes()
    contact_shading=None
    if args.bake_ao:
        from shading import bake_contact_occlusion
        contact_shading=bake_contact_occlusion(ROOT)
    bpy.ops.object.select_all(action='DESELECT')
    for obj in [ROOT]+list(ROOT.children_recursive):obj.select_set(True)
    bpy.context.view_layer.objects.active=ROOT
    glb=out/(cfg['typeKey']+'.glb')
    bpy.ops.export_scene.gltf(filepath=str(glb),export_format='GLB',use_selection=True,export_yup=True,export_extras=True,export_animations=False,export_cameras=False,export_lights=False,
                              export_vertex_color='ACTIVE' if args.bake_ao else 'MATERIAL',export_all_vertex_colors=False)
    report=report_glb(glb)
    expected=sorted(p['key'] for p in points)
    if report['anchors']!=expected:raise RuntimeError('Export lost sensor anchors')
    if report['triangles']>100000:raise RuntimeError('Triangle budget exceeded')
    required=['Motor','Gearbox','DriveBelt','PulleyMotor','PulleyGearbox','BeltGuard','BeltGuardFrame','BeltGuardMesh']
    if not set(required)<=set(report['names']):raise RuntimeError('Export lost functional nodes')
    report.update({'ok':True,'blender':bpy.app.version_string,'typeKey':cfg['typeKey'],'expectedPoints':len(points),'dimensionSource':cfg['dimensionSource']})
    if contact_shading:report['contactShading']=contact_shading
    belt_loop=belt_path((cfg['motor']['x'],cfg['motor']['z']),
                        (g['shaftXs'][g['inputIndex']],g['shaftZs'][g['inputIndex']]),
                        cfg['motor']['pulleyRadius']+.015,g['pulleyRadius']+.015)
    belt_length=sum((belt_loop[(index+1)%len(belt_loop)]-point).length for index,point in enumerate(belt_loop))
    manifest={k:cfg[k] for k in ['schemaVersion','typeKey','label','version','dimensionSource','notes']}
    manifest.update({'asset':cfg['typeKey']+'.glb','points':points,'parts':{'motor':'Motor','gearbox':'Gearbox','guard':'BeltGuard',**({'pump':'PumpHousing'} if cfg.get('pumpHousing') else {})},
                     'motion':{'motorPivot':'PulleyMotor','drivenPivot':'PulleyGearbox','belt':'DriveBelt','axis':[0,0,-1],'radiusRatio':cfg['motor']['pulleyRadius']/cfg['gearbox']['pulleyRadius'],'radiansPerSecond':2.2,
                               'beltUvPerRadian':18*cfg['motor']['pulleyRadius']/belt_length},'running':cfg['running']})
    front_position,front_target,front_scale,front_direction=front_camera(cfg)
    manifest['view']={'defaultDirection':[front_direction.x,front_direction.z,-front_direction.y]}
    manifest['appearance']=cfg.get('appearance',{})
    (out/(cfg['typeKey']+'.manifest.json')).write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/(cfg['typeKey']+'.qa.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    sensors={'schemaVersion':1,'asset':cfg['typeKey']+'.glb','unit':'proportional display units, not measured metres or millimetres',
             'sensors':[{'id':p['key'],'name':p['anchor'],'label':p['label'],'owner':manifest['parts'][p['partKey']],
                         'localPositionBlender':p['localPosition'],
                         'positionGLTF':[p['localPosition'][0],p['localPosition'][2],-p['localPosition'][1]],
                         'positionSource':p['positionSource'],'description':p['description']} for p in points]}
    (out/'sensors.json').write_text(json.dumps(sensors,ensure_ascii=False,indent=2),encoding='utf-8')
    # 使用 Blender 实际回读导出的文件，验证节点名称与变换。
    original_anchors={p['key']:tuple(bpy.data.objects[p['anchor']].matrix_world.translation) for p in points}
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.gltf(filepath=str(glb))
    ROOT=next(o for o in bpy.data.objects if o.name=='MachineRoot')
    for key,pos in original_anchors.items():
        anchor=next((o for o in bpy.data.objects if o.get('anchorId')==key),None)
        if anchor is None or (anchor.matrix_world.translation-Vector(pos)).length>1e-4:raise RuntimeError('Anchor round-trip mismatch: '+key)
    cam=setup_render(out,args.draft)
    if args.samples:
        if args.samples<1:raise ValueError('Render samples must be positive')
        bpy.context.scene.cycles.samples=args.samples
    cam.data.ortho_scale=front_scale
    cam.location=front_position;cam.rotation_euler=(front_target-cam.location).to_track_quat('-Z','Y').to_euler()
    bpy.ops.wm.save_as_mainfile(filepath=str(out/(cfg['typeKey']+'.blend')))
    if args.render:
        if args.clay:
            clay=material('ReviewClay',(.28,.30,.32),0,.66)
            bpy.context.view_layer.material_override=clay
        shots=[('front',front_position,front_target,front_scale),
               ('rear',(-4.0,12,6.0),(4.3,0,1.02),10.2),
               ('gearbox-rear',(-1.5,12.5,5.3),(6.85,.3,1.26),5.8),
               ('gearbox-front',(6.8,-14,3.2),(6.8,-.1,1.20),6.25),
               ('rear-orthographic',(6.83,16,1.3),(6.83,.23,1.3),5.6),
               ('platform',(4.8,1.0,12),(4.8,0,.1),10.5),
               ('motor-rear',(-1.2,5.4,2.5),(.82,.3,.85),3.15),
               ('motor-front',(-.8,-5.8,2.2),(.82,.3,.85),3.20),
               ('gearbox-side',(1.0,8.0,3.0),(4.7,.23,1.22),4.4),
               ('circular-inlet',(3.7,7,3.5),(9.7,.23,1.08),4.5),
               ('circular-housing',(14,-6,3.6),(8.9,.23,1.08),5.50)]
        requested=set(filter(None,args.shots.split(',')))
        if requested and not requested<={shot[0] for shot in shots}:raise ValueError('Unknown review shot')
        for name,pos,aim,scale in shots:
            if requested and name not in requested:continue
            target=Vector(aim);cam.data.ortho_scale=scale
            cam.location=pos;cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler()
            bpy.context.scene.render.filepath=str(out/(cfg['typeKey']+'-'+name+'.png'))
            bpy.ops.render.render(write_still=True)
        floor=bpy.data.objects.get('RenderFloor');floor.hide_render=True
        scene=bpy.context.scene;scene.render.film_transparent=True;scene.render.resolution_x=640;scene.render.resolution_y=400
        bpy.context.view_layer.material_override=None
        cam.data.ortho_scale=front_scale
        cam.location=front_position;cam.rotation_euler=(front_target-cam.location).to_track_quat('-Z','Y').to_euler()
        scene.render.filepath=str(out/(cfg['typeKey']+'-overview.png'));bpy.ops.render.render(write_still=True)
    print('MODEL_RESULT '+json.dumps(report,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
