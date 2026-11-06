"""将局部接触阴影烘焙到模型，保持公司现有配色。"""
import bpy


def bake_contact_occlusion(root):
    scene=bpy.context.scene
    scene.render.engine='CYCLES';scene.cycles.samples=16
    material=bpy.data.materials.new('TemporaryAOBake');material.use_nodes=True
    nodes=material.node_tree.nodes;nodes.clear()
    output=nodes.new('ShaderNodeOutputMaterial')
    emission=nodes.new('ShaderNodeEmission')
    ao=nodes.new('ShaderNodeAmbientOcclusion');ao.samples=16
    ao.inputs['Distance'].default_value=.38
    material.node_tree.links.new(ao.outputs['AO'],emission.inputs['Color'])
    material.node_tree.links.new(emission.outputs['Emission'],output.inputs['Surface'])
    objects=[o for o in root.children_recursive if o.type=='MESH' and not o.name.startswith('MotorCanopy_guard_frame')]
    originals={}
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        originals[obj.name]=list(obj.data.materials)
        obj.data.materials.clear();obj.data.materials.append(material)
        if 'ContactAO' in obj.data.color_attributes:obj.data.color_attributes.remove(obj.data.color_attributes['ContactAO'])
        color=obj.data.color_attributes.new(name='ContactAO',type='BYTE_COLOR',domain='CORNER')
        obj.data.color_attributes.active_color_index=list(obj.data.color_attributes).index(color)
        obj.data.color_attributes.render_color_index=obj.data.color_attributes.active_color_index
        obj.select_set(True)
    bpy.context.view_layer.objects.active=objects[0]
    try:
        bpy.ops.object.bake(type='EMIT',target='VERTEX_COLORS',use_clear=True)
        for obj in objects:
            for pixel in obj.data.color_attributes['ContactAO'].data:
                value=max(0,min(1,sum(pixel.color[:3])/3))
                shade=.45+.55*value
                pixel.color=(shade,shade,shade,1)
    finally:
        for obj in objects:
            obj.data.materials.clear()
            for original in originals[obj.name]:obj.data.materials.append(original)
        bpy.data.materials.remove(material)
    return {'method':'local ambient occlusion, baked grayscale vertex colors','distance':.38,
            'palette':'unchanged company base colors','objects':len(objects)}
