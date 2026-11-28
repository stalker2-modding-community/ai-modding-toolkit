"""Small Blueprint paste-text writer for S2MM (UE 5.5 clipboard text: K2Node objects + pins, links written on both ends).
Node and pin format follows a paste generator whose pastes worked in this kit. The editor rebuilds every node's pins from
the function on paste and keeps links by pin name."""
import uuid

NL = chr(13) + chr(10)


def gid():
    return uuid.uuid4().hex.upper()


def cls(path):
    return "\"/Script/CoreUObject.Class'%s'\"" % path


def struct(path):
    return "\"/Script/CoreUObject.ScriptStruct'%s'\"" % path


def enum(path):
    return "\"/Script/CoreUObject.Enum'%s'\"" % path


class Pin:
    def __init__(self, node, name, out=False, cat='exec', sub='', subobj=None, default=None, defobj=None, hidden=False,
                 deftext=None, container='None', ref=False):
        self.container, self.ref = container, ref
        self.node, self.name, self.out, self.cat, self.sub, self.subobj = node, name, out, cat, sub, subobj
        self.default, self.defobj, self.hidden, self.deftext, self.id, self.links = default, defobj, hidden, deftext, gid(), []

    def text(self):
        f = ['PinId=%s' % self.id, 'PinName="%s"' % self.name]
        if self.out:
            f.append('Direction="EGPD_Output"')
        f += ['PinType.PinCategory="%s"' % self.cat, 'PinType.PinSubCategory="%s"' % self.sub,
              'PinType.PinSubCategoryObject=%s' % (self.subobj or 'None'), 'PinType.PinSubCategoryMemberReference=()',
              'PinType.PinValueType=()', 'PinType.ContainerType=%s' % self.container,
              'PinType.bIsReference=%s' % ('True' if self.ref else 'False'), 'PinType.bIsConst=False',
              'PinType.bIsWeakPointer=False', 'PinType.bIsUObjectWrapper=False', 'PinType.bSerializeAsSinglePrecisionFloat=False']
        if self.default is not None:
            f.append('DefaultValue="%s"' % self.default)
        if self.defobj is not None:
            f.append('DefaultObject="%s"' % self.defobj)
        if self.deftext is not None:
            f.append('DefaultTextValue=INVTEXT("%s")' % self.deftext)
        if self.links:
            f.append('LinkedTo=(%s)' % ''.join('%s %s,' % (p.node.name, p.id) for p in self.links))
        f += ['PersistentGuid=00000000000000000000000000000000', 'bHidden=%s' % ('True' if self.hidden else 'False'),
              'bNotConnectable=False', 'bDefaultValueIsReadOnly=False', 'bDefaultValueIsIgnored=False', 'bAdvancedView=False',
              'bOrphanedPin=False']
        return '   CustomProperties Pin (%s,)' % ','.join(f)


class Graph:
    def __init__(self, prefix):
        self.nodes, self.boxes, self.prefix, self.count = [], [], prefix, {}

    def node(self, klass, x, y, props=(), comment=''):
        n = Node(self, klass, x, y, list(props), comment)
        self.nodes.append(n)
        return n

    def box(self, x, y, w, h, text):
        self.boxes.append((x, y, w, h, text))

    def text(self):
        names = [n.name for n in self.nodes]
        assert len(names) == len(set(names)), 'duplicate node names'
        out = []
        for i, (x, y, w, h, t) in enumerate(self.boxes):
            out += ['Begin Object Class=/Script/UnrealEd.EdGraphNode_Comment Name="%sBox_%d"' % (self.prefix, i),
                    '   NodePosX=%d' % x, '   NodePosY=%d' % y, '   NodeWidth=%d' % w, '   NodeHeight=%d' % h,
                    '   CommentColor=(R=0.250000,G=0.220000,B=0.150000,A=1.000000)',
                    '   NodeComment="%s"' % t, '   NodeGuid=%s' % gid(), 'End Object']
        for n in self.nodes:
            out.append(n.text())
        return NL.join(out) + NL

    def stats(self):
        links = sum(len(p.links) for n in self.nodes for p in n.pins) // 2
        return '%d nodes, %d links, %d boxes' % (len(self.nodes), links, len(self.boxes))


class Node:
    def __init__(self, graph, klass, x, y, props, comment):
        k = graph.count.get(klass, 0) + 1
        graph.count[klass] = k
        self.klass, self.x, self.y, self.props, self.pins, self.tail = klass, x, y, props, [], []
        self.name = '%s_%s%d' % (klass, graph.prefix, k)
        self.comment = comment

    def pin(self, *a, **k):
        p = Pin(self, *a, **k)
        self.pins.append(p)
        return p

    def __getitem__(self, name):
        for p in self.pins:
            if p.name == name:
                return p
        raise KeyError(name)

    def text(self):
        # K2 node classes live in different editor modules: a wrong module = the editor drops the node on paste, silently
        # (every K2Node_CreateWidget written under BlueprintGraph was gone after the paste)
        pkg = {'K2Node_CreateWidget': '/Script/UMGEditor'}.get(self.klass, '/Script/BlueprintGraph')
        out = ['Begin Object Class=%s.%s Name="%s"' % (pkg, self.klass, self.name)]
        out += ['   %s' % p for p in self.props]
        out += ['   NodePosX=%d' % self.x, '   NodePosY=%d' % self.y]
        if self.comment:
            out += ['   bCommentBubbleVisible=True', '   NodeComment="%s"' % self.comment]
        out += ['   NodeGuid=%s' % gid()]
        out += [p.text() for p in self.pins]
        out += ['   %s' % t for t in self.tail]
        out.append('End Object')
        return NL.join(out)


def link(a, b):
    a.links.append(b)
    b.links.append(a)


def chain(*nodes):
    for a, b in zip(nodes, nodes[1:]):
        link(a.exec_out, b.exec_in)


BOOL = dict(cat='bool')
STR = dict(cat='string')
INT = dict(cat='int')
TEXT = dict(cat='text')
NAME = dict(cat='name')


def obj(path):
    return dict(cat='object', subobj=cls(path))


# ------------------------------------------------------------------ node recipes
def call(g, x, y, parent, fname, pure=False, target=None, comment=''):
    """target = class path of the 'self' pin for member functions (None for static library calls)"""
    n = g.node('K2Node_CallFunction', x, y, (['bIsPureFunc=True'] if pure else []) +
               ['FunctionReference=(MemberParent=%s,MemberName="%s")' % (cls(parent), fname)], comment)
    n.exec_in = None if pure else n.pin('execute')
    n.exec_out = None if pure else n.pin('then', out=True)
    n.target = n.pin('self', **obj(target)) if target else None
    return n


def var_get(g, x, y, name, ty, parent=None, target=None):
    ref = ('VariableReference=(MemberParent=%s,MemberName="%s")' % (cls(parent), name)) if parent else \
          ('VariableReference=(MemberName="%s",bSelfContext=True)' % name)
    n = g.node('K2Node_VariableGet', x, y, [ref])
    n.target = n.pin('self', **obj(target or parent)) if parent else None
    n.val = n.pin(name, out=True, **ty)
    return n


def var_set(g, x, y, name, ty, parent=None, target=None, default=None):
    ref = ('VariableReference=(MemberParent=%s,MemberName="%s")' % (cls(parent), name)) if parent else \
          ('VariableReference=(MemberName="%s",bSelfContext=True)' % name)
    n = g.node('K2Node_VariableSet', x, y, [ref])
    n.exec_in, n.exec_out = n.pin('execute'), n.pin('then', out=True)
    n.target = n.pin('self', **obj(target or parent)) if parent else None
    n.val = n.pin(name, default=default, **ty)
    n.get = n.pin('Output_Get', out=True, **ty)
    return n


def event(g, x, y, parent, member, comment='', outs=()):
    n = g.node('K2Node_Event', x, y, ['EventReference=(MemberParent=%s,MemberName="%s")' % (cls(parent), member),
                                      'bOverrideFunction=True'], comment)
    n.pin('OutputDelegate', out=True, cat='delegate')
    n.exec_out = n.pin('then', out=True)
    for nm, ty in outs:
        setattr(n, nm, n.pin(nm, out=True, **ty))
    return n


def custom_event(g, x, y, fname, params=(), comment=''):
    """params = [(name, pinCategory)] simple types only"""
    n = g.node('K2Node_CustomEvent', x, y, ['CustomFunctionName="%s"' % fname], comment)
    n.pin('OutputDelegate', out=True, cat='delegate')
    n.exec_out = n.pin('then', out=True)
    n.params = {}
    for nm, cat in params:
        n.params[nm] = n.pin(nm, out=True, cat=cat)
        n.tail.append('CustomProperties UserDefinedPin (PinName="%s",PinType=(PinCategory="%s"),DesiredPinDirection=EGPD_Output)'
                      % (nm, cat))
    return n


def branch(g, x, y):
    n = g.node('K2Node_IfThenElse', x, y)
    n.exec_in = n.pin('execute')
    n.cond = n.pin('Condition', cat='bool', default='true')
    n.exec_out = n.t = n.pin('then', out=True)
    n.f = n.pin('else', out=True)
    return n


def cast(g, x, y, to_path, display):
    n = g.node('K2Node_DynamicCast', x, y, ['TargetType=%s' % cls(to_path)])
    n.exec_in, n.exec_out = n.pin('execute'), n.pin('then', out=True)
    n.fail = n.pin('CastFailed', out=True)
    n.obj = n.pin('Object', cat='object', subobj=cls('/Script/CoreUObject.Object'))
    n.as_ = n.pin('As' + display, out=True, **obj(to_path))
    n.ok = n.pin('bSuccess', out=True, cat='bool', hidden=True)
    return n


def self_node(g, x, y):
    n = g.node('K2Node_Self', x, y)
    n.val = n.pin('self', out=True, cat='object', sub='self')
    return n


def input_key(g, x, y, key, comment=''):
    n = g.node('K2Node_InputKey', x, y, ['InputKey=%s' % key], comment)
    n.pressed = n.pin('Pressed', out=True)
    n.released = n.pin('Released', out=True)
    n.key = n.pin('Key', out=True, cat='struct', subobj=struct('/Script/InputCore.Key'))
    return n


def create_widget(g, x, y, wclass):
    n = g.node('K2Node_CreateWidget', x, y)
    n.exec_in, n.exec_out = n.pin('execute'), n.pin('then', out=True)
    n.class_pin = n.pin('Class', cat='class', subobj=cls('/Script/UMG.UserWidget'), defobj=wclass)
    n.owner = n.pin('OwningPlayer', **obj('/Script/Engine.PlayerController'))
    n.ret = n.pin('ReturnValue', out=True, **obj(wclass))
    return n


def spawn_actor(g, x, y, aclass):
    n = g.node('K2Node_SpawnActorFromClass', x, y)
    n.exec_in, n.exec_out = n.pin('execute'), n.pin('then', out=True)
    n.class_pin = n.pin('Class', cat='class', subobj=cls('/Script/Engine.Actor'), defobj=aclass)
    n.ret = n.pin('ReturnValue', out=True, **obj(aclass))
    n.xf = n.pin('SpawnTransform', cat='struct', subobj=struct('/Script/CoreUObject.Transform'))
    n.pin('CollisionHandlingOverride', cat='byte', subobj=enum('/Script/Engine.ESpawnActorCollisionHandlingMethod'),
          default='AlwaysSpawn')
    return n


def bound_event(g, x, y, widget_bp_name, comp, delegate, owner_class, signature, outs=(), comment='', sig_in_class=False):
    """sig_in_class: the delegate type is declared inside the widget class (e.g. ComboBoxString:OnSelectionChangedEvent)"""
    parent = cls(owner_class) if sig_in_class else '"/Script/CoreUObject.Package\'/Script/UMG\'"'
    n = g.node('K2Node_ComponentBoundEvent', x, y, [
        'DelegatePropertyName="%s"' % delegate,
        'DelegateOwnerClass=%s' % cls(owner_class),
        'ComponentPropertyName="%s"' % comp,
        'EventReference=(MemberParent=%s,MemberName="%s")' % (parent, signature),
        'bInternalEvent=True',
        'CustomFunctionName="BndEvt__%s_%s_K2Node_ComponentBoundEvent_%d_%s"' % (widget_bp_name, comp, len(g.nodes), signature)],
        comment)
    n.pin('OutputDelegate', out=True, cat='delegate')
    n.exec_out = n.pin('then', out=True)
    for nm, ty in outs:
        setattr(n, nm, n.pin(nm, out=True, **ty))
    return n


# ------------------------------------------------------------------ recipes (arrays, loops, interfaces, switch)
KAL = '/Script/Engine.KismetArrayLibrary'
STDMAC = ("MacroGraphReference=(MacroGraph=\"/Script/Engine.EdGraph'/Engine/EditorBlueprintResources/StandardMacros.StandardMacros:%s'\","
          "GraphBlueprint=\"/Script/Engine.Blueprint'/Engine/EditorBlueprintResources/StandardMacros.StandardMacros'\",GraphGuid=%s)")
FOREACH_GUID = '99DBFD5540A796041F72A5A9DA655026'      # read from the kit's StandardMacros.uasset (Noah's recipe)


def wild(cat, subobj=None):
    return ('ResolvedWildcardType=(PinCategory="%s",PinSubCategory="",PinSubCategoryObject=%s,PinSubCategoryMemberReference=(),'
            'PinValueType=(),ContainerType=None,bIsReference=False,bIsConst=False,bIsWeakPointer=False,bIsUObjectWrapper=False,'
            'bSerializeAsSinglePrecisionFloat=False)' % (cat, subobj or 'None'))


def foreach(g, x, y, cat, subobj=None, comment=''):
    """ForEachLoop over an array of <cat> (string / int / object with subobj)"""
    n = g.node('K2Node_MacroInstance', x, y, [STDMAC % ('ForEachLoop', FOREACH_GUID), wild(cat, subobj)], comment)
    n.exec_in = n.pin('Exec')
    n.arr = n.pin('Array', cat=cat, subobj=subobj, container='Array', ref=True)
    n.body = n.pin('LoopBody', out=True)
    n.elem = n.pin('Array Element', out=True, cat=cat, subobj=subobj)
    n.index = n.pin('Array Index', out=True, cat='int')
    n.done = n.exec_out = n.pin('Completed', out=True)
    return n


def array_call(g, x, y, fname, cat, subobj=None, pure=False):
    """K2Node_CallArrayFunction: Array_Add (NewItem, ReturnValue), Array_Clear, Array_Length (pure, ReturnValue)"""
    n = g.node('K2Node_CallArrayFunction', x, y, (['bIsPureFunc=True'] if pure else []) +
               ['FunctionReference=(MemberParent=%s,MemberName="%s")' % (cls(KAL), fname)])
    n.exec_in = None if pure else n.pin('execute')
    n.exec_out = None if pure else n.pin('then', out=True)
    n.arr = n.pin('TargetArray', cat=cat, subobj=subobj, container='Array', ref=True)
    if fname == 'Array_Add':
        n.item = n.pin('NewItem', cat=cat, subobj=subobj)
        n.ret = n.pin('ReturnValue', out=True, cat='int')
    if fname == 'Array_Length':
        n.ret = n.pin('ReturnValue', out=True, cat='int')
    return n


def get_item(g, x, y, cat, subobj=None):
    """K2Node_GetArrayItem ('Get (a copy)'): Array, Dimension 1 (index) -> Output"""
    n = g.node('K2Node_GetArrayItem', x, y, ['bReturnByRefDesired=False'])
    n.arr = n.pin('Array', cat=cat, subobj=subobj, container='Array', ref=True)
    n.idx = n.pin('Dimension 1', cat='int')
    n.out = n.pin('Output', out=True, cat=cat, subobj=subobj)
    return n


def sequence(g, x, y, count):
    n = g.node('K2Node_ExecutionSequence', x, y)
    n.exec_in = n.pin('execute')
    n.outs = [n.pin('then_%d' % i, out=True) for i in range(count)]
    return n


def message(g, x, y, iface, fname, comment=''):
    """interface call on any object: K2Node_Message (Target = object)"""
    n = g.node('K2Node_Message', x, y, ['FunctionReference=(MemberParent=%s,MemberName="%s")' % (cls(iface), fname)], comment)
    n.exec_in, n.exec_out = n.pin('execute'), n.pin('then', out=True)
    n.target = n.pin('self', cat='object', subobj=cls('/Script/CoreUObject.Object'))
    return n


def iface_event(g, x, y, iface, fname, outs=(), comment=''):
    n = g.node('K2Node_Event', x, y, ['EventReference=(MemberParent=%s,MemberName="%s")' % (cls(iface), fname),
                                      'bOverrideFunction=True'], comment)
    n.pin('OutputDelegate', out=True, cat='delegate')
    n.exec_out = n.pin('then', out=True)
    n.p = {}
    for nm, ty in outs:
        n.p[nm] = n.pin(nm, out=True, **ty)
    return n


def switch_enum(g, x, y, enum_path, names):
    n = g.node('K2Node_SwitchEnum', x, y, ['Enum="/Script/Engine.UserDefinedEnum\'%s\'"' % enum_path] +
               ['EnumEntries(%d)="%s"' % (i, e) for i, e in enumerate(names)])
    n.exec_in = n.pin('execute')
    n.sel = n.pin('Selection', cat='byte', subobj="\"/Script/Engine.UserDefinedEnum'%s'\"" % enum_path)
    n.case = {e: n.pin(e, out=True) for e in names}
    return n


# ------------------------------------------------------------------ more recipes
def array_fn(g, x, y, fname, cat, subobj=None, pure=False, sub=''):
    """generic K2Node_CallArrayFunction with the right extra pins:
    Array_Find (ItemToFind -> ReturnValue int, pure), Array_Contains (ItemToFind -> ReturnValue bool, pure),
    Array_Set (Index, Item, bSizeToFit), Array_Add (NewItem -> ReturnValue), Array_Clear, Array_Length (pure)"""
    n = g.node('K2Node_CallArrayFunction', x, y, (['bIsPureFunc=True'] if pure else []) +
               ['FunctionReference=(MemberParent=%s,MemberName="%s")' % (cls(KAL), fname)])
    n.exec_in = None if pure else n.pin('execute')
    n.exec_out = None if pure else n.pin('then', out=True)
    n.arr = n.pin('TargetArray', cat=cat, sub=sub, subobj=subobj, container='Array', ref=True)
    if fname in ('Array_Find', 'Array_Contains'):
        n.item = n.pin('ItemToFind', cat=cat, sub=sub, subobj=subobj)
        n.ret = n.pin('ReturnValue', out=True, cat='int' if fname == 'Array_Find' else 'bool')
    elif fname == 'Array_Set':
        n.idx = n.pin('Index', cat='int')
        n.item = n.pin('Item', cat=cat, sub=sub, subobj=subobj)
        n.pin('bSizeToFit', cat='bool', default='false')
    elif fname == 'Array_Add':
        n.item = n.pin('NewItem', cat=cat, sub=sub, subobj=subobj)
        n.ret = n.pin('ReturnValue', out=True, cat='int')
    elif fname == 'Array_Length':
        n.ret = n.pin('ReturnValue', out=True, cat='int')
    return n


def custom_event2(g, x, y, fname, params=(), comment=''):
    """params = [(name, cat, sub, subobj_class_path_or_None)]"""
    n = g.node('K2Node_CustomEvent', x, y, ['CustomFunctionName="%s"' % fname], comment)
    n.pin('OutputDelegate', out=True, cat='delegate')
    n.exec_out = n.pin('then', out=True)
    n.params = {}
    for nm, cat, sub, sobj in params:
        is_struct = bool(sobj) and sobj.startswith('struct:')
        so = sobj[7:] if is_struct else sobj
        n.params[nm] = n.pin(nm, out=True, cat=cat, sub=sub, subobj=(struct(so) if is_struct else cls(so)) if sobj else None)
        extra = ''
        if sub:
            extra += ',PinSubCategory="%s"' % sub
        if sobj:
            extra += ",PinSubCategoryObject=\"/Script/CoreUObject.%s'%s'\"" % ('ScriptStruct' if is_struct else 'Class', so)
        n.tail.append('CustomProperties UserDefinedPin (PinName="%s",PinType=(PinCategory="%s"%s),DesiredPinDirection=EGPD_Output)'
                      % (nm, cat, extra))
    return n
