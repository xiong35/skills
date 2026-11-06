"""依据照片建立本台三轴设备的几何结构，不作为通用零件套件。"""
import math
from types import SimpleNamespace

import bpy
from mathutils import Vector


def rounded_rectangle(width, depth, radius, segments=6):
    result=[]
    for cx,cy,start in [(width/2-radius,depth/2-radius,0),(-width/2+radius,depth/2-radius,math.pi/2),
                         (-width/2+radius,-depth/2+radius,math.pi),(width/2-radius,-depth/2+radius,3*math.pi/2)]:
        for i in range(segments+1):
            a=start+i*math.pi/(2*segments)
            result.append((cx+radius*math.cos(a),cy+radius*math.sin(a)))
    return result


def cast_loft(h,name,x,y,layers,parent,mat='housing'):
    """圆角矩形铸造截面：下壳收窄，上壳向内倾斜。"""
    verts=[]
    for z,width,depth,radius in layers:
        verts.extend((x+px,y+py,z) for px,py in rounded_rectangle(width,depth,radius))
    n=len(rounded_rectangle(*layers[0][1:]))
    faces=[tuple(range(n-1,-1,-1))]
    for k in range(len(layers)-1):
        for i in range(n):
            j=(i+1)%n
            faces.append((k*n+i,k*n+j,(k+1)*n+j,(k+1)*n+i))
    faces.append(tuple(range((len(layers)-1)*n,len(layers)*n)))
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],faces);mesh.update()
    # 长箱体侧壁保持平面，仅将铸造转角圆滑处理；
    # 整体平滑放样会让壳体看起来鼓胀。
    for k,p in enumerate(list(mesh.polygons)[1:-1]):
        side=k % n
        level=layers[k//n][0]
        p.use_smooth=level>=2.16 if side in [6,20] else level>=1.90 if side in [13,27] else True
    obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj)
    return h.finish(obj,name,mat,parent,.012)


def yz_web(h,name,x,yz,thickness,parent,taper=False):
    # 照片中的筋板从箱壁向外伸出，支撑轴承座。
    n=len(yz)
    ymin=min(y for y,z in yz);span=max(y for y,z in yz)-ymin
    verts=[(x+side*thickness/2*(1-.45*(y-ymin)/span if taper and span else 1),y,z)
           for side in [-1,1] for y,z in yz]
    faces=[tuple(range(n-1,-1,-1)),tuple(range(n,2*n))]
    faces += [(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],faces);mesh.update()
    obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj)
    return h.finish(obj,name,'housing',parent,.008)


def mounting_stud(h,name,x,y,z,parent,radius=.10):
    h.cylinder(name+'_Washer',(x,y,z),radius*1.35,.025,'steel',parent,axis='Z',vertices=32)
    h.cylinder(name+'_Nut',(x,y,z+.070),radius,.13,'steel',parent,axis='Z',vertices=6)
    h.cylinder(name+'_Thread',(x,y,z+.15),radius*.50,.065,'steel',parent,axis='Z',vertices=16)


def perforated_fan_cover(h,motor,m):
    x,y,z=m['x'],m['y'],m['z'];r=m['radius'];rear=y+m['length']/2
    h.ring('MotorFanCowlLip',x,rear+.16,z,r*1.105,r*.99,.29,motor,'motor')
    h.ring('MotorFanGrilleRim',x,rear+.32,z,r*1.04,r*.84,.055,motor,'motor')
    # 按方形孔阵列生成风罩开孔。
    radius=r*.84;pitch=.024;bar=.006
    count=math.floor(radius/pitch)
    for i in range(-count,count+1):
        d=i*pitch;span=2*math.sqrt(max(0,radius*radius-(abs(d)+bar/2)**2))
        if span<bar:continue
        h.box(f'FanGrilleVertical_{i}',(x+d,rear+.345,z),(bar,.018,span),'motor',motor,0)
        h.box(f'FanGrilleHorizontal_{i}',(x,rear+.344,z+d),(span,.018,bar),'motor',motor,0)
    h.cylinder('DarkFanInterior',(x,rear+.08,z),r*.94,.025,'recess',motor)


def cover_with_bolts(h,name,position,radius,parent,through_shaft=False):
    x,y,z=position
    h.ring(name+'_MachinedEdge',x,y,z,radius,radius*.94,.075,parent,'housing')
    disc=h.cylinder(name+'_Plate',(x,y-.012,z),radius*.963,.060,'housing',parent,vertices=64)
    if through_shaft:
        cutter=h.cylinder('CoverBoreCutter',(x,y,z),.17,.40,'steel',parent)
        for mod in list(cutter.modifiers):cutter.modifiers.remove(mod)
        mod=disc.modifiers.new('ShaftBore','BOOLEAN');mod.operation='DIFFERENCE';mod.object=cutter
        bpy.context.view_layer.objects.active=disc;bpy.ops.object.modifier_apply(modifier=mod.name)
        bpy.data.objects.remove(cutter,do_unlink=True)
    n=10 if radius>.5 else 8
    for i in range(n):
        a=math.tau*i/n+math.pi/n
        px=x+radius*.86*math.cos(a);pz=z+radius*.86*math.sin(a)
        h.cylinder(name+f'_BoltWasher_{i}',(px,y+.024,pz),radius*.092,.012,'steel',parent,vertices=20)
        h.cylinder(name+f'_Bolt_{i}',(px,y+.0475,pz),radius*.072,.035,'steel',parent,vertices=6)


def motor_canopy(h,motor,m,spec):
    """两端敞开的薄板拱罩，与电机尾端风扇格栅分开。"""
    canopy=h.group('MotorCanopy',motor,partKey='motor')
    radius=spec['radius'];thickness=spec['thickness'];steps=96
    start,end=map(math.radians,spec.get('angleRangeDeg',[-7,187]))
    vertices=[]
    for py in spec['yRange']:
        for rr in [radius,radius-thickness]:
            for i in range(steps+1):
                angle=start+(end-start)*i/steps
                vertices.append((m['x']+rr*math.cos(angle),py,m['z']+rr*math.sin(angle)))
    n=steps+1;faces=[]
    for i in range(steps):
        j=i+1
        faces.extend([(i,j,2*n+j,2*n+i),(n+i,3*n+i,3*n+j,n+j),
                      (i,n+i,n+j,j),(2*n+i,2*n+j,3*n+j,3*n+i)])
    faces.extend([(0,2*n,3*n,n),(steps,n+steps,3*n+steps,2*n+steps)])
    mesh=bpy.data.meshes.new('MotorCanopySheet');mesh.from_pydata(vertices,[],faces);mesh.update()
    for polygon in mesh.polygons:
        polygon.use_smooth=polygon.index<steps*4 and polygon.index%4<2
    obj=bpy.data.objects.new('MotorCanopySheet',mesh);bpy.context.collection.objects.link(obj)
    h.finish(obj,obj.name,'motor',canopy,0)
    for side in [-1,1]:
        for py in spec['supportYs']:
            h.box(f'CanopyLeg_{side}_{py}',(m['x']+side*(radius-.045),py,.31),(.025,.14,.58),'guard_frame',canopy,.004)
            h.box(f'CanopyFoldedFoot_{side}_{py}',(m['x']+side*(radius-.025),py,.036),(.15,.18,.026),'guard_frame',canopy,.004)
            fixing_x=m['x']+side*(radius-.045)
            h.cylinder(f'CanopyFixingWasher_{side}_{py}',(fixing_x,py,.055),.040,.012,'steel',canopy,axis='Z',vertices=24)
            h.cylinder(f'CanopyFixingNut_{side}_{py}',(fixing_x,py,.081),.028,.040,'steel',canopy,axis='Z',vertices=6)
            h.cylinder(f'CanopyFixingStem_{side}_{py}',(fixing_x,py,.109),.014,.025,'steel',canopy,axis='Z',vertices=12)
    # 侧板从拱形切点连续延伸到平台。
    edge_z=m['z']+radius*math.sin(start)
    for side in [-1,1]:
        edge_x=m['x']+side*radius*math.cos(start)
        h.box(f'CanopySkirt_{side}',(edge_x,sum(spec['yRange'])/2,(edge_z+.025)/2),
              (thickness,spec['yRange'][1]-spec['yRange'][0],edge_z-.025),'guard_frame',canopy,.002)
    # 护板独立使用项目的防护材质，电机报警时
    # 不改变其独立防护罩的颜色。
    obj.data.materials[0]=h.MATERIALS['guard_frame']
    return canopy


def motor_side_flange(h,gearbox,g,spec):
    """短端 -X 方向圆盖与三个背面端盖垂直。"""
    flange=h.group('GearboxMotorSideFlange',gearbox,partKey='gearbox',axis='X')
    px=g['x']-g['length']/2;py=g['y'];pz=spec['z'];rr=spec['radius'];lid=rr*spec['coverRadiusRatio']
    neck=spec['neckLength'];end=px-neck
    h.cylinder('SideFlangeCastNeck',(px-neck/2,py,pz),rr*.64,neck,'housing',flange,axis='X',vertices=64)
    h.cylinder('SideFlangeRoot',(px-.025,py,pz),rr*.94,.13,'housing',flange,axis='X',vertices=64)
    rim=h.ring('SideFlangeRim',0,0,0,rr,rr*.82,.09,flange,'housing')
    rim.rotation_euler.z=-math.pi/2;rim.location=(end+.035,py,pz)
    h.cylinder('SideFlangeCover',(end-.065,py,pz),lid,.09,'housing',flange,axis='X',vertices=64)
    h.cylinder('SideFlangeCenterBoss',(end-.13,py,pz),rr*.11,.045,'housing',flange,axis='X',vertices=32)
    h.cylinder('SideFlangeCenterNut',(end-.16,py,pz),rr*.075,.035,'steel',flange,axis='X',vertices=6)
    for i in range(8):
        angle=math.tau*i/8
        yy=py+lid*.84*math.cos(angle);zz=pz+lid*.84*math.sin(angle)
        h.cylinder(f'SideFlangeBolt_{i}',(end-.13,yy,zz),.034,.045,'steel',flange,axis='X',vertices=6)
    # 宽三角轴向筋板在伸出的铸造筒座周围形成凹槽。
    for i in range(4):
        angle=math.pi*i/2;radial=Vector((0,math.cos(angle),math.sin(angle)))
        tangent=Vector((0,-math.sin(angle),math.cos(angle)))
        profile=[(px-.03,rr*.66),(end+.04,rr*.93),(end+.04,rr*.65)]
        verts=[tuple(Vector((xx,py,pz))+radial*radius+tangent*side*(.065 if xx>px-neck/2 else .035))
               for side in [-1,1] for xx,radius in profile]
        faces=[(2,1,0),(3,4,5),(0,1,4,3),(1,2,5,4),(2,0,3,5)]
        mesh=bpy.data.meshes.new(f'SideFlangeCastWeb_{i}');mesh.from_pydata(verts,[],faces);mesh.update()
        obj=bpy.data.objects.new(mesh.name,mesh);bpy.context.collection.objects.link(obj)
        h.finish(obj,obj.name,'housing',flange,.007)
    return flange


def circular_housing(h,pump,entry,oy,oz,spec):
    """按用户标注，在 +X 尾轴端建立带筋圆形壳体。"""
    body=h.group('RearCircularHousing',pump,partKey='pump',axis='X')
    radius=spec['radius'];depth=spec['depth'];center=entry+depth/2+.10
    face=center+depth/2+.045
    wall=h.ring('CircularHousingWall',0,0,0,radius*.965,radius*.91,depth,body,'pump')
    wall.rotation_euler.z=-math.pi/2;wall.location=(center,oy,oz)
    rim=h.ring('CircularHousingOuterLip',0,0,0,radius,radius*.91,.15,body,'pump')
    rim.rotation_euler.z=-math.pi/2;rim.location=(face,oy,oz)
    back_rim=h.ring('CircularHousingRearLip',0,0,0,radius*.985,radius*.93,.055,body,'pump')
    back_rim.rotation_euler.z=-math.pi/2;back_rim.location=(center-depth/2-.015,oy,oz)
    h.cylinder('CircularHousingRecessedWeb',(face-.18,oy,oz),radius*.925,.040,'pump',body,axis='X',vertices=96)
    h.cylinder('CircularHousingHub',(face-.035,oy,oz),spec['hubRadius'],.29,'pump',body,axis='X',vertices=64)
    for i in range(spec['ribCount']):
        angle=math.tau*i/spec['ribCount']+.13
        # 实体背板上布置径向铸造筋板，不额外开出轮辐孔。
        radial=Vector((math.cos(angle),math.sin(angle)));tangent=Vector((-radial.y,radial.x))
        near=radial*(spec['hubRadius']*.88);far=radial*(radius*.925)
        outline=[near+tangent*.075,far+tangent*.050,far-tangent*.050,near-tangent*.075]
        vertices=[(xx,oy+p.x,oz+p.y) for xx in [face-.16,face+.02] for p in outline]
        faces=[(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
        mesh=bpy.data.meshes.new(f'CircularHousingRadialRib_{i}');mesh.from_pydata(vertices,[],faces);mesh.update()
        obj=bpy.data.objects.new(mesh.name,mesh);bpy.context.collection.objects.link(obj)
        h.finish(obj,obj.name,'pump',body,.008)
    # 照片中朝向联轴器的 -X 一侧为敞口盘形结构。
    # 保留凹入的背板作为盘底，将筋板向开口方向延伸。
    inlet=center-depth/2-.015
    floor=face-.20
    h.cylinder('InletRaisedHub',((inlet+floor)/2,oy,oz),spec['hubRadius']*1.12,
               floor-inlet+.10,'pump',body,axis='X',vertices=64)
    for i in range(spec['ribCount']):
        angle=math.tau*i/spec['ribCount']+.13
        radial=Vector((math.cos(angle),math.sin(angle)))
        tangent=Vector((-radial.y,radial.x))
        near=radial*(spec['hubRadius']*.96);far=radial*(radius*.935)
        outline=[near+tangent*.055,far+tangent*.035,far-tangent*.035,near-tangent*.055]
        vertices=[(xx,oy+p.x,oz+p.y) for xx in [inlet+.015,floor+.015] for p in outline]
        faces=[(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
        mesh=bpy.data.meshes.new(f'InletDishRib_{i}');mesh.from_pydata(vertices,[],faces);mesh.update()
        obj=bpy.data.objects.new(mesh.name,mesh);bpy.context.collection.objects.link(obj)
        h.finish(obj,obj.name,'pump',body,.006)
    return center,face


def build_equipment(cfg,api):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    api['ROOT']=None
    root=api['group']('MachineRoot',typeKey=cfg['typeKey'],modelVersion=cfg['version'])
    root.parent=None;api['ROOT']=root
    h=SimpleNamespace(**api)
    h.make_materials()
    m,g=cfg['motor'],cfg['gearbox']
    motor=h.group('Motor',partKey='motor');gearbox=h.group('Gearbox',partKey='gearbox')
    base=h.group('BaseFrame',partKey='base');points=[]
    x,y,z,r,length=m['x'],m['y'],m['z'],m['radius'],m['length']

    # 电机主体大于小带轮，尾端采用圆形开孔风罩。
    h.cylinder('MotorMainBarrel',(x,y,z),r*.94,length,'motor',motor,vertices=64)
    for i in range(36):
        a=math.tau*i/36
        fin=h.box(f'MotorCoolingFin_{i}',(x+(r+.009)*math.cos(a),y-.05,z+(r+.009)*math.sin(a)),
                  (.030,length*.74,.060),'motor',motor,.003)
        fin.rotation_euler.y=-a
    for side in [-1,1]:
        h.cylinder(f'MotorEndBell_{side}',(x,y+side*length/2,z),r*.98,.12,'motor',motor,vertices=64)
        h.cylinder(f'MotorBearingBoss_{side}',(x,y+side*(length/2+.07),z),r*.40,.15,'motor',motor)
    perforated_fan_cover(h,motor,m)
    for sx in [x-.35,x+.35]:
        for sy in [y-length*.31,y+length*.31]:
            h.box(f'MotorFoot_{sx}_{sy}',(sx,sy,.065),(.24,.33,.13),'motor',motor,.018)
            mounting_stud(h,f'MotorBolt_{sx}_{sy}',sx,sy,.14,motor,.05)
    h.box('MotorSideTerminalBox',(x+r*.80,y+.14,z+.20),(.27,.43,.31),'motor',motor,.025)
    h.box('MotorTerminalLid',(x+r*.80+.025,y+.14,z+.36),(.32,.47,.045),'motor',motor,.008)
    motor_canopy(h,motor,m,cfg['motorCanopy'])
    for key,label,side in [('motor_de','电机输出端',-1),('motor_nde','电机非输出端',1)]:
        h.sensor(points,key,label,motor,(x,y+side*(length/2+.10),z),'motor','photo-proportional',
                 '依据电机两端轴承关系建立的比例节点，非实测安装坐标。')

    gx,gy=g['x'],g['y'];front=gy-g['depth']/2;back=gy+g['depth']/2
    left=gx-g['length']/2;right=gx+g['length']/2
    def case_layers(rows):return [(z,w+g['length']-3.36,d,r) for z,w,d,r in rows]
    # 上壳体较宽且向内倾斜，下壳体逐渐收窄。
    # X/Z 方向侧壁按实物采用直壁与局部圆角。
    cast_loft(h,'GearboxLowerCasting',gx,gy,case_layers([(.18,3.16,1.37,.15),(.32,3.24,1.43,.16),
              (.91,3.32,1.64,.19),(1.13,3.36,1.70,.18)]),gearbox)
    cast_loft(h,'GearboxUpperCasting',gx,gy,case_layers([(1.14,3.36,1.70,.18),(1.98,3.36,1.70,.12),
              (2.08,3.34,1.70,.12),(2.16,3.30,1.70,.12),
              (2.22,3.24,1.68,.12),(2.27,3.16,1.64,.12),(2.30,3.09,1.60,.12),
              (2.32,2.96,1.57,.18)]),gearbox)
    h.box('CaseSplitJoint',(gx,gy,1.14),(g['length']+.12,1.85,.095),'housing',gearbox,.015)
    h.box('RoofCoverRim',(gx,gy,2.3275),(g['length']-.52,1.07,.035),'housing',gearbox,.010)
    h.box('RoofInspectionPlate',(gx,gy,2.349),(g['length']-.81,.89,.020),'housing',gearbox,.006)
    for px in [left+.55,gx,right-.55]:
        for py in [gy-.38,gy+.38]:h.cylinder(f'RoofScrew_{px}_{py}',(px,py,2.370),.025,.018,'steel',gearbox,axis='Z',vertices=6)
    h.cylinder('OilFiller',(gx+.26,gy+.20,2.415),.045,.075,'housing',gearbox,axis='Z',vertices=12)

    # 每个轴承座均建立向外凸出的铸造座体。
    for i,(sx,sz,rr) in enumerate(zip(g['shaftXs'],g['shaftZs'],g['coverRadii'])):
        bearing=h.group(f'GearboxBearingSaddle_{i+1}',gearbox,partKey='gearbox')
        h.cylinder(f'RearBearingBoss_{i+1}',(sx,back+.11,sz),rr+.075,.26,'housing',bearing,vertices=64)
        h.box(f'RearBearingLowerSupport_{i+1}',(sx,back+.09,sz-rr*.54),(rr*1.64,.26,rr*.90),'housing',bearing,.025)
        cover=h.group(f'GearboxCover_{i+1}',gearbox,partKey='gearbox')
        cover_with_bolts(h,f'RearEndCover_{i+1}',(sx,back+.275,sz),rr,cover)
        # 筋板位于 Y/Z 平面，向外支撑圆形凸台。
        for dx in [-rr*.40,rr*.40]:
            yz_web(h,f'BearingTopWeb_{i+1}_{dx}',sx+dx,[(back+.045,2.24),(back+.30,sz+rr+.035),
                   (back+.045,sz+rr*.78)],.090,gearbox,taper=True)
        for dx in [-rr*.55,rr*.55]:
            yz_web(h,f'LowerCaseWeb_{i}_{dx}',sx+dx,[(back-.02,.26),(back+.19,.48),
                   (back+.18,sz-rr*.64),(back-.05,sz-.12)],.065,gearbox)
        for side in [-1,1]:
            key=f'gearbox_shaft_{i+1}_{"a" if side<0 else "b"}'
            sy=front-.15 if side<0 else back+.30
            h.sensor(points,key,f'减速机轴{i+1}{"A" if side<0 else "B"}端',gearbox,((left-.20,front-.275,1.14) if key=='gearbox_shaft_2_a' else (sx,sy,sz)),'gearbox',
                     'front-auxiliary-seat-photo' if key=='gearbox_shaft_2_a' else ('rear-cover-photo' if side>0 else 'opposite-end-inferred'),
                     '05按照片移至大带轮左侧圆座；05与06配对及中间轴命名待核准，不能视为已确认共轴。' if i==1 else '前后成对归属同一轴；位置按照片比例估计，背侧使用同构封闭圆盖。')

    # 相邻座体共用一个实体铸造横台。
    # 重叠横台在烘焙和导出后会产生错误的黑色缝隙。
    ear_xs=[g['shaftXs'][0]-g['coverRadii'][0]-.055]
    ear_xs += [(g['shaftXs'][i]+g['coverRadii'][i]+g['shaftXs'][i+1]-g['coverRadii'][i+1])/2
               for i in range(len(g['shaftXs'])-1)]
    ear_xs += [g['shaftXs'][-1]+g['coverRadii'][-1]+.055]
    for i,ex in enumerate(ear_xs):
        h.box(f'BearingSharedEar_{i}',(ex,back+.02,1.16),(.28,.30,.18),'housing',gearbox,.018)
        mounting_stud(h,f'BearingCaseBolt_{i}',ex,back+.02,1.2625,gearbox,.060)

    # 圆座旁的分箱横台由竖向立柱承托。
    front_seat=g['shaftXs'][2]
    table_start=front_seat+cfg['frontCastShoulders']['outputRadius']-.008
    table_end=table_start+.62;post_x=(table_start+table_end)/2
    h.box('FrontLateralSplitTable',(post_x,front+.045,1.16),
          (table_end-table_start,.38,.30),'housing',gearbox,.025)
    for px in [table_start+.13,table_end-.13]:
        mounting_stud(h,f'FrontTableBolt_{px}',px,front+.045,1.3225,gearbox,.060)
    h.cylinder('FrontSaddlePost',(post_x,front+.045,.65),.18,.80,'housing',gearbox,axis='Z',vertices=48)
    h.box('FrontSaddleFoot',(post_x,front+.045,.15),(.55,.48,.25),'housing',gearbox,.015)
    h.box('FrontSaddleFootPlate',(post_x,front+.045,-.02),(.65,.58,.09),'base',base,.008)
    # 大带轮左侧的小轴承座按照片保留三个紧固件。
    aux_x=left-.20
    h.cylinder('FrontAuxiliaryRoundSeat',(aux_x,front-.13,1.14),.32,.28,'housing',gearbox,vertices=64)
    h.box('FrontAuxiliarySplitTable',(aux_x,front-.19,1.38),(.82,.40,.15),'housing',gearbox,.025)
    for index,dx in enumerate([-.27,0,.27]):
        mounting_stud(h,f'FrontAuxiliaryBolt_{index}',aux_x+dx,front-.22,1.4675,gearbox,.047)
    h.box('FrontAuxiliaryLowerSeat',(aux_x,front-.02,.83),(.43,.32,.42),'housing',gearbox,.025)
    h.cylinder('FrontInputSaddle',(g['shaftXs'][0],front-.12,g['shaftZs'][0]),g['coverRadii'][0]+.06,.25,'housing',gearbox)
    shoulders=h.group('FrontCastShoulders',gearbox,partKey='gearbox')
    for name,sx,sz,rr in [('Input',g['shaftXs'][0],g['shaftZs'][0],cfg['frontCastShoulders']['inputRadius']),
                          ('Output',g['shaftXs'][2],g['shaftZs'][2],cfg['frontCastShoulders']['outputRadius'])]:
        # 圆形铸造肩台部分被带轮和横台遮挡，属于
        # 箱体体积结构，不额外复制三个带螺栓的背面端盖。
        h.cylinder(f'Front{name}CastShoulder',(sx,front-.035,sz),rr,.20,'housing',shoulders,vertices=96)
    # 外露的输出轴座包含铸造筋板和周边小紧固件。
    sx=g['shaftXs'][2];sz=g['shaftZs'][2];rr=cfg['frontCastShoulders']['outputRadius']
    for dx in [-.22,.22]:
        yz_web(h,f'FrontSaddleWeb_{dx}',sx+dx,[(front+.04,2.16),(front-.22,sz+rr*.90),(front+.04,sz+.35)],.075,shoulders)
    for angle in [-1.25,-.65,.60,1.15]:
        h.cylinder(f'FrontSaddleFastener_{angle}',(sx+rr*.87*math.cos(angle),front-.15,sz+rr*.87*math.sin(angle)),.029,.035,'steel',shoulders,vertices=6)
    motor_side_flange(h,gearbox,g,cfg['motorSideFlange'])
    # 宽铸造耳台与箱体两端连成一体。
    for side,px in [(-1,left+.18),(1,right-.18)]:
        outline=[(px-side*.36,1.80),(px+side*.19,1.80),(px+side*.19,2.22),
                 (px+side*.12,2.34),(px-side*.06,2.40),(px-side*.36,2.32)]
        lug=h.extruded_profile(f'CastShoulderEye_{side}',outline,.18,'housing',gearbox)
        lug.location.y=front-.055
        bpy.context.view_layer.objects.active=lug
        for modifier in list(lug.modifiers):bpy.ops.object.modifier_apply(modifier=modifier.name)
        cutter=h.cylinder('LiftingEyeBore',(px,front-.055,2.26),.070,.50,'steel',gearbox,vertices=32)
        for modifier in list(cutter.modifiers):cutter.modifiers.remove(modifier)
        mod=lug.modifiers.new('EyeBore','BOOLEAN');mod.operation='DIFFERENCE';mod.object=cutter
        bpy.context.view_layer.objects.active=lug;bpy.ops.object.modifier_apply(modifier=mod.name)
        bpy.data.objects.remove(cutter,do_unlink=True)
    # 厚圆角侧耳保留可见紧固件，下方为连续侧壁。
    for px,table_width in [(left,.60),(right-.06,.50)]:
        h.box(f'RearSplitEndTable_{px}',(px,back-.02,1.16),(table_width,.40,.30),'housing',gearbox,.055)
        h.box(f'RearSplitEndWall_{px}',(px,back-.01,.65),(.48,.40,.77),'housing',gearbox,.025)
        for index,(dx,dy) in enumerate([(-.14,.09),(.14,.09),(0,-.09)]):
            mounting_stud(h,f'RearEndTableBolt_{px}_{index}',px+dx,back-.02+dy,1.3225,gearbox,.060)
    for px in [left+.18,right-.18]:
        for py in [front-.10,back+.17]:
            h.box(f'CastFoot_{px}_{py}',(px,py,.15),(.59,.57,.25),'housing',gearbox,.015)
            h.box(f'CastFootSole_{px}_{py}',(px,py,.035),(.65,.63,.045),'housing',gearbox,.006)
            yz_web(h,f'FootHaunch_{px}_{py}',px,[(py,.27),(gy,.65),(gy,.27)],.22,gearbox)
            mounting_stud(h,f'MainFoundationBolt_{px}_{py}',px,py,.2875,gearbox,.103)

    # 按实物背面照片建立中间基础座。
    px=g['shaftXs'][1];py=back+.17
    h.box('CentreRearFoot',(px,py,.15),(.49,.57,.25),'housing',gearbox,.015)
    h.box('CentreRearFootSole',(px,py,.035),(.55,.63,.045),'housing',gearbox,.006)
    yz_web(h,'CentreRearFootWeb',px,[(py,.27),(gy,.65),(gy,.27)],.16,gearbox)
    mounting_stud(h,'CentreRearFoundationBolt',px,py,.2875,gearbox,.103)

    # 仅保留所给背面照片中清晰可见的调节螺栓。
    foot_x=left+.18;foot_y=back+.17
    h.cylinder('VisibleFootAdjusterStem',(foot_x-.37,foot_y,.13),.047,.32,'steel',gearbox,axis='X',vertices=20)
    h.cylinder('VisibleFootAdjusterWasher',(foot_x-.30,foot_y,.13),.11,.020,'steel',gearbox,axis='X',vertices=32)
    h.cylinder('VisibleFootAdjusterNut',(foot_x-.35,foot_y,.13),.095,.080,'steel',gearbox,axis='X',vertices=6)
    h.cylinder('VisibleFootAdjusterLocknut',(foot_x-.44,foot_y,.13),.090,.075,'steel',gearbox,axis='X',vertices=6)

    wheel_y=cfg['wheelY'];input_x,input_z=g['shaftXs'][0],g['shaftZs'][0]
    h.pulley('PulleyMotor',x,wheel_y,z,m['pulleyRadius'])
    h.pulley('PulleyGearbox',input_x,wheel_y,input_z,g['pulleyRadius'])
    h.cylinder('MotorDriveShaft',(x,(wheel_y+y-length/2)/2,z),.09,abs(wheel_y-y+length/2)+.25,'steel',motor)
    h.cylinder('InputDriveShaft',(input_x,(wheel_y+front)/2,input_z),.15,abs(wheel_y-front)+.20,'steel',gearbox)
    h.belt((x,z),(input_x,input_z),m['pulleyRadius'],g['pulleyRadius'],wheel_y,cfg['beltCount'])
    guard=h.build_guard(cfg,(x,z),(input_x,input_z))
    # 默认涂装相同，但报警控制的材质所有权保持独立。
    for part in guard.children_recursive:
        if part.type=='MESH':
            for index,mat in enumerate(part.data.materials):
                if mat.name=='housing':part.data.materials[index]=h.MATERIALS['guard_frame']

    connection=cfg['outputConnection'];output=connection['shaftIndex']
    if connection['axis']!='X' or connection['direction']!=1:raise ValueError('Tail output must follow the confirmed +X end face')
    oy=g['y'];oz=g['shaftZs'][output];surface=right;entry=surface+connection['shaftLength']
    coupling=h.group('OutputCoupling',gearbox,axis='X',direction=1)
    h.cylinder('TailOutputBearingNeck',(surface+.035,oy,oz),.38,.24,'housing',gearbox,axis='X',vertices=64)
    h.cylinder('OutputShaft',((surface+entry)/2,oy,oz),.19,entry-surface+.08,'steel',coupling,axis='X')
    h.cylinder('CouplingSleeve',(surface+.39,oy,oz),.33,.37,'steel',coupling,axis='X')
    for distance in [.22,.37]:
        h.cylinder(f'OutputFlange_{distance}',(surface+distance,oy,oz),.41,.10,'steel',coupling,axis='X')
    h.cylinder('CouplingJointBand',(surface+.295,oy,oz),.375,.055,'recess',coupling,axis='X',vertices=64)
    for i in range(8):
        angle=math.tau*i/8
        h.cylinder(f'OutputFlangeBolt_{i}',(surface+.435,oy+.34*math.cos(angle),oz+.34*math.sin(angle)),.027,.035,'steel',coupling,axis='X',vertices=6)
    pump=h.group('PumpHousing',partKey='pump')
    for px in [entry-.15,entry-.04]:h.cylinder(f'MatingFlange_{px}',(px,oy,oz),.41,.085,'steel',pump,axis='X')
    h.cylinder('HousingEntryCollar',(entry+.08,oy,oz),.40,.18,'pump',pump,axis='X')
    for i in range(8):
        angle=math.tau*i/8
        h.cylinder(f'ConnectionBolt_{i}',(entry-.18,oy+.34*math.cos(angle),oz+.34*math.sin(angle)),.027,.035,'steel',pump,axis='X',vertices=6)
    housing_center,housing_face=circular_housing(h,pump,entry,oy,oz,cfg['rearHousing'])
    h.sensor(points,'pump_housing','泵头壳体',pump,(housing_face-.155,oy+.68,oz+.64),'pump','location-unconfirmed',
             '按实拍补建大圆形壳体后的表面示意节点；传感器实际安装位置仍待现场核对。')

    # 采用开敞钢梁支架和局部安装板。
    base_left,base_right=cfg['base']['left'],cfg['base']['right'];mid=(base_left+base_right)/2;width=base_right-base_left
    for py in [-1.22,1.22]:
        h.box(f'LongitudinalWeb_{py}',(mid,py,-.29),(width-.14,.09,.43),'base',base,.005)
        for pz in [-.07,-.51]:h.box(f'LongitudinalFlange_{py}_{pz}',(mid,py,pz),(width-.10,.34,.055),'base',base,.006)
        for px in [.68,2.80,left+.18,right-.18]:h.box(f'BeamStiffener_{px}_{py}',(px,py,-.30),(.065,.32,.38),'base',base,.005)
        for px in [.24,left+.18,cfg['base']['right']-.27]:h.box(f'FoundationFoot_{px}_{py}',(px,py,-.575),(.49,.54,.075),'base',base,.010)
    for px in [.26,left+.18,cfg['base']['right']-.32]:
        h.box(f'CrossBeamWeb_{px}',(px,0,-.30),(.09,2.48,.35),'base',base,.005)
        for pz in [-.09,-.48]:h.box(f'CrossBeamFlange_{px}_{pz}',(px,0,pz),(.30,2.54,.045),'base',base,.005)
    h.box('MotorMountingPlate',(.89,0,-.020),(1.82,2.62,.09),'base',base,.008)
    h.box('GearboxMountingPlate',(gx,0,-.020),(g['length']+.36,2.72,.09),'base',base,.008)
    h.box('ContinuousDeck',((left+.89+.91)/2,0,-.020),(left-(.89+.91)+.05,2.62,.09),'base',base,.005)
    # 网罩通过下横梁固定在前侧钢梁上，与照片一致。
    h.box('GuardLowerMountRail',(3.54,-1.21,.005),(6.95,.20,.07),'base',base,.008)
    bpy.context.view_layer.update()
    return points
