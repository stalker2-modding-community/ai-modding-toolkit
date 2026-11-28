# Blueprint and kit facts proven while building S2MM

All tested in game or in the kit while building S2MM 1.0.0 (Steam build 26123434, Zone Kit 2.1.0), unless marked. General
paste tooling: stalker2-blueprints.

## Contents
- Paste defaults that vanish
- Action nodes that look pure
- Instanced structs and the game save hook
- Input
- Menus and widgets
- Editing assets without a paste
- Headless kit runs
- Checking a paste

## Paste defaults that vanish
- **A typed `0` or `false` on a pin is dropped on paste, and the function's declared default wins.** `Add_IntInt(k, 0)`
  came back as `k + 1` (B defaults to 1); `ParseIntoArray(CullEmptyStrings = false)` came back true. Seen as a garbled
  value split and three-number rows off by one. Use `Max(k, k)` for an int literal (0 included) and feed a false from
  `Not_PreBool(true)`. Custom event parameters have no declared default, so a typed 0 there is harmless.
- **A class pin default survives only if that asset is loaded at paste time.** Open (or Ctrl+P) every asset a pin default
  names before pasting, or feed the pin from a class variable whose default is set headless. A game widget class on a
  Create Widget pin came through empty even when loaded: have the user pick it in the node's Class dropdown.
- **A call to another Blueprint's custom event pastes only once that event exists** (its graph pasted and compiled). Paste
  callee first.

## Action nodes that look pure
Written as pure nodes these paste, compile with "was pruned because its Exec pin is not connected" (or are dropped) and
read 0: `WidgetLayoutLibrary.GetMousePositionOnViewport`, `KismetSystemLibrary.GetConsoleVariableFloatValue`,
`BlueprintInstancedStructLibrary.MakeInstancedStruct`, `GetInstancedStructValue`. Rule seen: static library functions that
are not const are action nodes; const member functions (IsInputKeyDown, GetChildAt, GetChildIndex, IsHovered) are pure.
Other type traps: an EditableTextBox needs `EditableTextBox.SetText` (TextBlock's will not connect); `IsHovered` and
`IsInViewport` live on `Widget`.

## Instanced structs and the game save hook
- A `ModWorldSubsystem` can keep data in the game save: `ShouldSaveData` (true), `OnSaveDataRequested` >
  `SetDataForSave(InstancedStruct)`, and `OnSaveDataLoaded(SaveData)`.
- Wrap a string in an engine struct that always exists (S2MM uses `DirectoryPath.Path`), so a save still loads after the mod
  is removed (tested: saves made with S2MM load without it).
- Paste format, read from a node placed by hand: class `/Script/BlueprintGraph.K2Node_InstancedStruct` with
  `FunctionReference=(MemberParent=<BlueprintInstancedStructLibrary class>,MemberName="MakeInstancedStruct")`, pins
  `execute`, `then`, `Value` (wildcard), `ReturnValue`. The Get form adds `bWantsEnumToExecExpansion=True` and has pins
  `Valid`, `NotValid`, `execute`, `InstancedStruct` (by ref), `Value`. As `K2Node_CallFunction` both are refused.
- To check what really went into a save: game saves are Oodle-compressed (a uint32 raw size, then the stream); the kit
  ships an Oodle runtime DLL in its AutomationTool folder.
- Unknown node format in general: ask the user to place the node, select it, Ctrl+C, and read the clipboard.

## Input
- Key events (`K2Node_InputKey`, InputAction) on a spawned mod actor did not fire at all in one test, and any mod that binds
  an AnyKey event with consume on swallows them for actors below it. Poll `PlayerController.WasInputKeyJustPressed(Key)`
  (pure) on Tick: it works beside such mods and while a menu is open in GameAndUI mode.
- A gamepad Back button inside a menu: give the menu its own Input Mapping Context with one Input Action and read it while
  the menu is open; the game's Esc handling stays as it is.
- Script consoles: a UE4SS console enabler (if the user has one) gives the real engine console and takes `~` first. Let
  the user choose the key.

## Menus and widgets
- Adding an entry to the Esc menu: the buttons are data (`View/MenuButtonModel/PauseRootButtonData`), not layout, and no
  Blueprint can reach the game's menu widgets (a widget search returned nothing and made menus lag). S2MM overrides that
  data asset: an entry after Options with a `GotoViewAction` whose `destination_widget` is a `MenuSubViewBase` page.
  `MenuButtonData` fields are template-only for Python: `export_text()` an entry, edit the text, `import_text()`. This
  override clashes with any other mod that replaces the same asset.
- A game menu page is sized to its content: a page with a bare Overlay root got height 0. Use a fixed root (SizeBox
  1920 x 1080), as the game's own pages do, or draw on the viewport.
- An Image with DrawAs RoundedBox and an outline keeps drawing the outline at SetRenderOpacity(0): hide it with visibility.
- Kit T3D exports turn UTF-16 (BOM ff fe) when a graph holds a non-ASCII character; such a string is UTF-16 inside the
  .uasset too, so a byte grep for it finds nothing.

## Editing assets without a paste
- A designer widget is reachable headless as
  `unreal.find_object(None, '/<Mod>/UI/WBP_X.WBP_X:WidgetTree.<WidgetName>')`: set properties, compile, save.
- A graph's literal string sits twice in the saved .uasset (pin default and compiled copy). Swapping it for text of the SAME
  byte length, then headless load, compile and save, works. Different lengths break the file: paste instead. Back up first.
- A change with no added or removed asset re-packs without the GUI: `RunUAT GSCCookMod -PluginPath=<mod uplugin>
  -PackageClassifierOutputDir=<SavedMods/PackageClassifier/<Mod>>` (about 3 minutes; classifier lists from one GUI
  Package). Compare the new containers with the last tested ones file by file (`retoc unpack`): only the changed assets and
  the per-cook Wwise anchor should differ.

## Headless kit runs
- `BlueprintEditorLibrary.add_member_variable` does not refuse an existing name: it adds `Name_0`. Read the variable list
  from a T3D export first.
- Python cannot add an implemented interface (`implemented_interfaces` is not settable). Duplicate an asset that already
  implements it, or add it in Class Settings. `remove_graph` and `remove_unused_variables` exist, but removing the event
  graph leaves the Blueprint with none to paste into.
- A headless run does not mount a mod whose `.uplugin` has `ExplicitlyLoaded` + `Mod` (the GUI form): swap in the plain form
  for the run, restore it after.
- The `-script=` path is read with backslash escapes: a folder or file starting with t, r, n, b, f, a, v or x after a
  backslash breaks it ("could not load Python file"). Use forward slashes or other names.
- `Blueprint.status` is protected in Python; read compile errors from the editor log.

## Checking a paste
After each kit session: export every pasted Blueprint as T3D, compare node kinds and counts with the paste, list class pins
with no DefaultObject and no link, and read the `DefaultValue` of every typed pin you depend on (that check would have caught
the dropped 0). Hand pastes over with a copy window that reads the clipboard back and compares it with the file before it
shows "copied": a plain SetText can fail silently and the user pastes the previous round.
