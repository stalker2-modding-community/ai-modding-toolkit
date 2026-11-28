"""Shared builders for the paste generators (graph text only; see bpgen.py for the node writer)."""
from bpgen import (link, chain, call, var_get, var_set, event, branch, cast, self_node, create_widget, spawn_actor, obj, cls,
                   struct, BOOL, foreach, array_fn, get_item, sequence, message, iface_event, switch_enum, custom_event2)

# ---- paths
MGR = '/S2MM/Core/BP_S2MM_Manager.BP_S2MM_Manager_C'
SELF = '/S2MM/Core/BP_S2MM_Self.BP_S2MM_Self_C'
SG = '/S2MM/Core/SG_S2MM_Settings.SG_S2MM_Settings_C'
MENU = '/S2MM/UI/WBP_S2MM_Menu.WBP_S2MM_Menu_C'
ROW = '/S2MM/UI/WBP_S2MM_Row.WBP_S2MM_Row_C'
MODBTN = '/S2MM/UI/WBP_S2MM_ModButton.WBP_S2MM_ModButton_C'
IFACE = '/S2MM/API/BPI_S2MM_Provider.BPI_S2MM_Provider_C'
PBTN = '/S2MM/UI/WBP_S2MM_PauseButton.WBP_S2MM_PauseButton_C'
SUBV = '/S2MM/UI/WBP_S2MM_SubView.WBP_S2MM_SubView_C'
TAB = '/S2MM/UI/WBP_S2MM_Tab.WBP_S2MM_Tab_C'
GUI = '/Game/GameLite/FPS_Game/UIRemaster/'
PROOT = GUI + 'View/MenuSubView/W_PauseMenuSubViewRoot.W_PauseMenuSubViewRoot_C'
MROOT = GUI + 'View/MenuSubView/W_MainMenuSubViewRoot.W_MainMenuSubViewRoot_C'
SOFTCUR = GUI + 'CommonWidgets/W_SoftwareCursor.W_SoftwareCursor_C'
PUSHBTN = GUI + 'CommonWidgets/MenuButtons/W_PushOptionButton.W_PushOptionButton_C'
SBL = '/Script/UMG.SlateBlueprintLibrary'
GEO = dict(cat='struct', subobj="\"/Script/CoreUObject.ScriptStruct'/Script/SlateCore.Geometry'\"")
SUBSYS = '/Script/Stalker2.ModWorldSubsystem'
ACTOR = '/Script/Engine.Actor'
PC = '/Script/Engine.PlayerController'
CTRL = '/Script/Engine.Controller'
GS = '/Script/Engine.GameplayStatics'
KML = '/Script/Engine.KismetMathLibrary'
KSL = '/Script/Engine.KismetSystemLibrary'
KStr = '/Script/Engine.KismetStringLibrary'
KTL = '/Script/Engine.KismetTextLibrary'
WBL = '/Script/UMG.WidgetBlueprintLibrary'
W = '/Script/UMG.Widget'
UW = '/Script/UMG.UserWidget'
TB = '/Script/UMG.TextBlock'
PW = '/Script/UMG.PanelWidget'
VIS = "\"/Script/CoreUObject.Enum'/Script/UMG.ESlateVisibility'\""
OBJ = '/Script/CoreUObject.Object'

S = dict(cat='string')
I = dict(cat='int')
R = dict(cat='real', sub='double')
T = dict(cat='text')
SA = dict(cat='string', container='Array')
IA = dict(cat='int', container='Array')
RA = dict(cat='real', sub='double', container='Array')
AA = dict(cat='object', subobj=cls(ACTOR), container='Array')
KEY = dict(cat='struct', subobj=struct('/Script/InputCore.Key'))
KEYA = dict(cat='struct', subobj=struct('/Script/InputCore.Key'), container='Array')
V2 = dict(cat='struct', subobj=struct('/Script/CoreUObject.Vector2D'))
XF = dict(cat='struct', subobj=struct('/Script/CoreUObject.Transform'))
VEC = dict(cat='struct', subobj=struct('/Script/CoreUObject.Vector'))
ROT = dict(cat='struct', subobj=struct('/Script/CoreUObject.Rotator'))


def ty_of(cat):
    return {'string': S, 'int': I, 'real': R}[cat]


def pc0(g, x, y):
    n = call(g, x, y, GS, 'GetPlayerController', pure=True)
    n.pin('PlayerIndex', cat='int', default='0')
    n.ret = n.pin('ReturnValue', out=True, **obj(PC))
    return n


def pure(g, x, y, parent, fname, ins, out_ty, target=None, target_src=None):
    n = call(g, x, y, parent, fname, pure=True, target=target)
    if target_src is not None:
        link(target_src, n.target)
    for name, src, ty, default in ins:
        p = n.pin(name, default=default, **ty)
        if src is not None:
            link(src, p)
    return n.pin('ReturnValue', out=True, **out_ty)


def gv(g, x, y, name, ty, parent=None, target_src=None):
    n = var_get(g, x, y, name, ty, parent=parent)
    if parent and target_src is not None:
        link(target_src, n.target)
    return n.val


def sv(g, x, y, name, ty, src=None, default=None, parent=None, target_src=None):
    n = var_set(g, x, y, name, ty, parent=parent, default=default)
    if src is not None:
        link(src, n.val)
    if parent and target_src is not None:
        link(target_src, n.target)
    return n


def item(g, x, y, arr_pin, idx_pin, ty):
    n = get_item(g, x, y, ty['cat'], ty.get('subobj'))
    if ty.get('sub'):
        n.out.sub = ty['sub']
        n.arr.sub = ty['sub']
    link(arr_pin, n.arr)
    link(idx_pin, n.idx)
    return n.out


def lit_int(g, x, y, value):
    """an int from a node (pasted literal defaults on int pins are fine, but this keeps -1 safe)"""
    return pure(g, x, y, KML, 'Subtract_IntInt', [('A', None, I, '0'), ('B', None, I, str(-int(value)))], I) if value < 0 else None


def concat(g, x, y, parts):
    cur = None
    k = 0
    for p in parts:
        if cur is None:
            if isinstance(p, str):
                n = call(g, x, y, KStr, 'Concat_StrStr', pure=True)
                n.pin('A', cat='string', default=p)
                n.pin('B', cat='string', default='')
                cur = n.pin('ReturnValue', out=True, **S)
            else:
                cur = p
            continue
        k += 1
        n = call(g, x + 170 * k, y + (k % 2) * 50, KStr, 'Concat_StrStr', pure=True)
        link(cur, n.pin('A', cat='string'))
        b = n.pin('B', cat='string', default=p if isinstance(p, str) else None)
        if not isinstance(p, str):
            link(p, b)
        cur = n.pin('ReturnValue', out=True, **S)
    return cur


def eqs(g, x, y, a, b):
    """string equality; b may be a literal"""
    return pure(g, x, y, KStr, 'EqualEqual_StrStr', [('A', a, S, None), ('B', None if isinstance(b, str) else b, S, b if isinstance(b, str) else None)], BOOL)


def nes(g, x, y, a, b):
    return pure(g, x, y, KStr, 'NotEqual_StrStr', [('A', a, S, None), ('B', None if isinstance(b, str) else b, S, b if isinstance(b, str) else None)], BOOL)


def AND(g, x, y, a, b):
    return pure(g, x, y, KML, 'BooleanAND', [('A', a, BOOL, None), ('B', b, BOOL, None)], BOOL)


def OR(g, x, y, a, b):
    return pure(g, x, y, KML, 'BooleanOR', [('A', a, BOOL, None), ('B', b, BOOL, None)], BOOL)


def NOT(g, x, y, a):
    return pure(g, x, y, KML, 'Not_PreBool', [('A', a, BOOL, None)], BOOL)


def ge_int(g, x, y, a, b_lit):
    return pure(g, x, y, KML, 'GreaterEqual_IntInt', [('A', a, I, None), ('B', None, I, str(b_lit))], BOOL)


def to_text(g, x, y, s):
    if isinstance(s, str):      # a literal
        return pure(g, x, y, KTL, 'Conv_StringToText', [('InString', None, S, s)], T)
    return pure(g, x, y, KTL, 'Conv_StringToText', [('InString', s, S, None)], T)


def set_text(g, x, y, tb_pin, s_pin):
    n = call(g, x, y, TB, 'SetText', target=TB)
    link(tb_pin, n.target)
    link(to_text(g, x - 200, y + 120, s_pin), n.pin('InText', **T))
    return n


def set_vis(g, x, y, w_pin, vis):
    n = call(g, x, y, W, 'SetVisibility', target=W)
    link(w_pin, n.target)
    n.pin('InVisibility', cat='byte', subobj=VIS, default=vis)
    return n


def is_valid(g, x, y, src):
    return pure(g, x, y, KSL, 'IsValid', [('Object', src, dict(cat='object', subobj=cls(OBJ)), None)], BOOL)


def parse(g, x, y, src, delim='|'):
    """src: a string pin, or a literal string"""
    lit = src if isinstance(src, str) else None
    return pure(g, x, y, KStr, 'ParseIntoArray', [('SourceString', None if lit is not None else src, S, lit), ('Delimiter', None, S, delim),
                                                  ('CullEmptyStrings', None, BOOL, 'true')], SA)


def fmt(g, x, y, type_pin, opts_pin, val_pin):
    """display string: toggle -> ON/OFF, choice -> option name, else the value itself"""
    on = pure(g, x, y + 120, KML, 'SelectString', [('A', None, S, 'ON'), ('B', None, S, 'OFF'), ('bPickA', eqs(g, x - 200, y + 160, val_pin, '1'), BOOL, None)], S)
    arr = parse(g, x - 400, y + 300, opts_pin)
    ln = array_fn(g, x - 400, y + 420, 'Array_Length', 'string', pure=True)
    link(arr, ln.arr)
    top = pure(g, x - 250, y + 420, KML, 'Max', [('A', pure(g, x - 330, y + 470, KML, 'Subtract_IntInt', [('A', ln.ret, I, None), ('B', None, I, '1')], I), I, None), ('B', None, I, '0')], I)
    ix = pure(g, x - 150, y + 360, KML, 'Clamp', [('Value', pure(g, x - 300, y + 360, KStr, 'Conv_StringToInt', [('InString', val_pin, S, None)], I), I, None),
                                                  ('Min', None, I, '0'), ('Max', top, I, None)], I)
    ch = item(g, x, y + 300, arr, ix, S)
    inner = pure(g, x + 200, y + 220, KML, 'SelectString', [('A', ch, S, None), ('B', val_pin, S, None), ('bPickA', eqs(g, x, y + 220, type_pin, 'choice'), BOOL, None)], S)
    return pure(g, x + 400, y + 100, KML, 'SelectString', [('A', on, S, None), ('B', inner, S, None), ('bPickA', eqs(g, x + 200, y + 60, type_pin, 'toggle'), BOOL, None)], S)


def mgr_call(g, x, y, fname, mgr_pin, args):
    """call a manager custom event from another Blueprint: args = [(pin, src_pin_or_None, ty, default)]"""
    n = call(g, x, y, MGR, fname, target=MGR)
    link(mgr_pin, n.target)
    for name, src, ty, default in args:
        p = n.pin(name, default=default, **ty)
        if src is not None:
            link(src, p)
    return n


def add_mod(g, x, y, mgr_pin, self_pin, mod, name, author, group):
    return mgr_call(g, x, y, 'S2MM_AddMod', mgr_pin, [('Provider', self_pin, obj(ACTOR), None), ('ModID', None, S, mod),
                                                     ('Name', None, S, name), ('Author', None, S, author), ('Group', None, S, group)])


def add_setting(g, x, y, mgr_pin, self_pin, mod, sid, typ, label, desc, default, mn='0', mx='0', step='0', opts=''):
    """literal arguments (strings) or pins"""
    def a(name, v, ty):
        return (name, None if isinstance(v, str) else v, ty, v if isinstance(v, str) else None)
    return mgr_call(g, x, y, 'S2MM_AddSetting', mgr_pin, [('Provider', self_pin, obj(ACTOR), None), a('ModID', mod, S), a('SettingID', sid, S),
                                                         a('Type', typ, S), a('Label', label, S), a('Desc', desc, S), a('Default', default, S),
                                                         a('Min', mn, R), a('Max', mx, R), a('Step', step, R), a('Options', opts, S)])


def get_manager(g, x, y):
    """exec: GetActorOfClass(BP_S2MM_Manager) -> cast; returns (first, last, as_pin)"""
    ga = call(g, x, y, GS, 'GetActorOfClass')
    ga.pin('ActorClass', cat='class', subobj=cls(ACTOR), defobj=MGR)
    gr = ga.pin('ReturnValue', out=True, **obj(ACTOR))
    c = cast(g, x + 300, y, MGR, 'BP S2MM Manager')
    link(gr, c.obj)
    link(ga.exec_out, c.exec_in)
    return ga, c, c.as_


def spawn_keep(g, x, y, var_name, cls_path, exec_in):
    """Branch(IsValid(var)) -> false: spawn cls at origin, store in var"""
    b = branch(g, x, y)
    link(exec_in, b.exec_in)
    link(is_valid(g, x - 200, y + 160, gv(g, x - 400, y + 160, var_name, obj(cls_path))), b.cond)
    sp = spawn_actor(g, x + 300, y, cls_path)
    mt = call(g, x, y + 260, KML, 'MakeTransform', pure=True)
    mt.pin('Location', **VEC, default='0,0,0')
    mt.pin('Rotation', **ROT, default='0,0,0')
    mt.pin('Scale', **VEC, default='1.000000,1.000000,1.000000')
    link(mt.pin('ReturnValue', out=True, **XF), sp.xf)
    link(b.f, sp.exec_in)
    s = sv(g, x + 750, y, var_name, obj(cls_path), src=sp.ret)
    link(sp.exec_out, s.exec_in)
    return s


def just_key(g, x, y, key_pin):
    wk = call(g, x, y, PC, 'WasInputKeyJustPressed', pure=True, target=PC)
    link(pc0(g, x - 250, y).ret, wk.target)
    link(key_pin, wk.pin('Key', **KEY))
    return wk.pin('ReturnValue', out=True, cat='bool')


def eq_int(g, x, y, a, b_lit):
    return pure(g, x, y, KML, 'EqualEqual_IntInt', [('A', a, I, None), ('B', None, I, str(b_lit))], BOOL)


def paused(g, x, y):
    return pure(g, x, y, GS, 'IsGamePaused', [], BOOL)


def sel_int(g, x, y, a, b, pick):
    """a / b: pins or int literals"""
    return pure(g, x, y, KML, 'SelectInt', [('A', None if isinstance(a, int) else a, I, str(a) if isinstance(a, int) else None),
                                            ('B', None if isinstance(b, int) else b, I, str(b) if isinstance(b, int) else None),
                                            ('bPickA', pick, BOOL, None)], I)


def sel_f(g, x, y, a, b, pick):
    return pure(g, x, y, KML, 'SelectFloat', [('A', None if isinstance(a, (int, float)) else a, R, '%f' % a if isinstance(a, (int, float)) else None),
                                              ('B', None if isinstance(b, (int, float)) else b, R, '%f' % b if isinstance(b, (int, float)) else None),
                                              ('bPickA', pick, BOOL, None)], R)


def input_ui(g, x, y, focus_pin):
    """SetInputMode_GameAndUIEx(PC 0, focus = focus_pin or nothing)"""
    im = call(g, x, y, WBL, 'SetInputMode_GameAndUIEx')
    link(pc0(g, x - 200, y + 180).ret, im.pin('PlayerController', **obj(PC)))
    p = im.pin('InWidgetToFocus', **obj(W))
    if focus_pin is not None:
        link(focus_pin, p)
    im.pin('InMouseLockMode', cat='byte', subobj="\"/Script/CoreUObject.Enum'/Script/Engine.EMouseLockMode'\"", default='DoNotLock')
    im.pin('bHideCursorDuringCapture', cat='bool', default='false')
    im.pin('bFlushInput', cat='bool', default='false')
    return im


def cursor(g, x, y, on):
    return sv(g, x, y, 'bShowMouseCursor', BOOL, default='true' if on else 'false', parent=PC, target_src=pc0(g, x - 200, y + 180).ret)
