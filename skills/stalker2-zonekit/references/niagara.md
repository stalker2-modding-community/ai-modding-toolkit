# Niagara systems in the Zone Kit

## Contents
- Before editing a GSC system: check it compiles in the kit
- Reading module constants offline
- Reading links, dynamic inputs and text: copy them as text
- Row naming quirks in the stack
- Editing an expression
- CPU and GPU scripts
- World positions are tile relative
- User parameter defaults offline
- Verifying a saved system offline
- What does not work
- Checking a system still has its sound

## Before editing a GSC system: check it compiles in the kit
Some GSC Niagara systems reference module scripts the kit does not ship. A checked-out copy then cooks with no error, the System
script fails, and the cooked system renders NOTHING in game (a tell: the cooked system is far smaller than the vanilla one).
Before editing any system, open it in the kit and search the editor log for `Skipping non mounted imported package` and
`Unknown Function Call`. Any hit: that system cannot be rebuilt from the kit as is.

## Reading module constants offline
Constants typed into a module (a Lifetime, a Spawn Count, a colour) can be read from the saved file with the kit closed.
Every NiagaraScript export keeps them in `RapidIterationParameters`: a list of names with byte offsets
(`SortedParameterOffsets`) and the packed values (`ParameterData`). A system's user parameters are in `ExposedParameters`.
- `python scripts/niagara_constants.py <system or emitter .uasset> [filter]` reads the uncooked asset directly and prints
  one line per value, `Constants.<Emitter>.<Module>.<Input> [type] = value`, grouped by script. About 60 ms a system.
- Checked on two kit-mod systems (1,429 and 292 values): identical, line for line, to a second reader that works from a
  uasset-dump JSON.
- A constant appears once per script that uses it (spawn, update, GPU compute).
- Uncooked assets only (file version UE5 1012 or newer). It reads; it does not write.
- It shows constants only. What an input is LINKED to, dynamic inputs and expression text are not in these stores: use the
  clipboard route below. uasset-dump itself does not decode the stores, and headless Python cannot read them.

## Reading links, dynamic inputs and text: copy them as text
The editor clipboard shows everything a module holds:
1. The user selects a module in an emitter's stack, Ctrl+C, and pastes it into a text file. Several modules can go one after
   another into the same file.
2. `python scripts/niagara_clipboard.py <pasted.txt>` prints each module with its inputs: local values decoded (floats, vectors,
   colours, ints, enums, bools), linked parameters (`-> User.Something`) and dynamic inputs nested under their input.
- The clipboard is T3D text: a first pass of nested `Begin Object` shells, then a second pass that fills each object with
  InputName, InputType, ValueMode (Local / Linked / Dynamic), the linked name and `Local(n)` raw bytes. Local bytes are the value's
  little-endian memory: float 4 bytes, Vector2f 8, Vector3f 12, Vector4f / LinearColor / Quat4f 16, int32 and enums 4, bool 0 or
  0xFFFFFFFF.
- The text is GSC's content: keep it local, never ship it.

## Row naming quirks in the stack
- Set modules show as "Set (PARTICLES) ...": find one by its rows, not by its title or position.
- Dynamic Material Parameter rows show parameter names borrowed from OTHER materials, for example "DepthFade (Multiple
  Aliases...)" was Param 1 and "Param1-0 (Parameter not used...)" was Param 2. Never read a slot's meaning from the shown name.
- In steps for the user, name a module by a row it shows ("the module whose first row is Lifetime"), never "the 8th module".
- "Add Vector To Position" is a DYNAMIC INPUT on Set Parameters > Particles.Position, not a module.

## Editing an expression
To replace an expression in a module input: click into the expression box, Ctrl+A, paste the new text, click outside the box.
Then Apply, Compile, Save (from the system window's toolbar).
- NEVER Ctrl+Z in the Niagara editor: it leaves stale data behind.
- `Cannot use variable ... hasn't been encountered yet` (it hits the first compile after opening a saved system): Ctrl+S, Asset
  Actions > Reload, reopen the system, Compile.
- `no member named X in FParamMap0_User` (cause unknown): the kit put the variable into the text but did not register it. It
  hit the LAST variable first seen at the end of an expression, twice, and it is not a cap on the number of variables. The cure
  that worked: move that term away from the end and END the expression with `+ 0.0 * User.<a parameter another expression
  already uses>`. To diagnose, have the user press Ctrl+S in the failed state: the asset then holds the generated HLSL.

## CPU and GPU scripts
- Emitter and system scripts (Spawn Rate, a Set Parameters in Emitter Update) compile for the CPU vector VM, which has NO
  `smoothstep` and no `step`: write `t*t*(3-2*t)` or a `saturate` ramp. An offline FXC compile does not catch this. Particle
  scripts of a GPU emitter run on the GPU.
- Never compute one hash on both the CPU and the GPU: a CPU `sin` and a GPU `sin` differ in the last bits, and
  `frac(sin(x) * 43758)` turns that into another number. Compute it on one side only.

## World positions are tile relative
Niagara positions are relative to the large-world tile. The game's tile is 50800 cm, so
world position = `Particles.Position + Engine.Owner.LWCTile * 50800`. Any expression that needs the absolute world position
must add that term.

## User parameter defaults offline
The float defaults of a system's user parameters can be byte patched in the uncooked `.uasset`, kit closed. They sit in both of
the asset's ParameterData stores, in case-insensitive alphabetical order of the parameter names: patch both stores and read
both back.

## Verifying a saved system offline
The saved .uasset holds every expression as plain text. Search it: the new text must appear once and the old text zero times.
Do this before the user closes the kit.

## What does not work
- Headless editor Python has no edit access to Niagara: Custom HLSL nodes are not exposed (their text cannot be read),
  `emitter_handles` is not exposed, and NiagaraSystem has no compile or save methods.
- An offline patch of Niagara expression TEXT is untested (user parameter defaults are the tested exception, above). It would
  likely need the graph's change id renewed so the cook recompiles, the way a material needs a new StateId. Prove it with a
  loud change before relying on it.

## Checking a system still has its sound
After a kit save, confirm a Niagara system kept its Wwise event: a working cook lists the event path as text. Run
`python scripts/niagara_sound_refs.py <file or folder>` on the system's cooked files ("events: NONE" means no event reached
that file). In a legacy extract, an export of class
NiagaraDataInterfaceWwiseEvent has SerialSize 10 with an event and 6 with none. To read a lone mod, copy its trio with the game's
`global.utoc` / `.ucas` into one folder and run `retoc to-legacy`; imports then show as `/Engine/UnknownPackage`, so judge imports
from the raw chunk text instead. Compare with a control cooked by the same kit version.
