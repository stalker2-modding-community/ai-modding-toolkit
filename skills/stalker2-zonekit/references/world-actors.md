# Placing actors in the open world

## Contents
- Two routes
- Place an actor in WorldMap_WP
- Where the save goes
- Blueprints that need placing
- A personal stash spawned from cfg does not work

Tested on game build 26123434 (Steam) with the matching Zone Kit, unless marked otherwise.

## Two routes
| Route | Suits | How |
|---|---|---|
| cfg spawn actor (`SpawnActorPrototypes`) | What the game spawns from a prototype: contextual-action spots, lairs and their trigger volumes, NPCs, items, ordinary loot containers | A new root struct in a SpawnActorPrototypes cfg. For existing saves: `SpawnOnStart = true` plus a `NodePrototypeAppliedMods` entry; bumping its `NodePrototypeModVersion` makes the game delete and respawn the actor from the patched prototype (GSC guide "How To Mod Placeholders"). |
| Placed actor (Zone Kit editor) | Blueprints the game places straight into its levels: the personal stash, beds, other interactive objects that run their own logic | Steps below; needs the kit's cook. |

## Place an actor in WorldMap_WP
GSC's guide: "How To Add New Actors" in the game's guides on mod.io (PDF `https://cdn.stalker2.com/guides/How_to_add_new_actors.pdf`).
1. Select the mod in the main toolbar's mod selector. The actors you add are saved into the selected mod.
2. Content Browser, All, open the level WorldMap_WP.
3. Window → World Partition → World Partition Editor. Select the area, right-click, Load Region From Selection.
4. Drag the blueprint from the Content Browser into the viewport (or Quick Add → Place Actors). Type Location and Rotation in the Details panel.
5. Save with the Save icon in the top-left corner of the main window (it saves the current level).
6. Cook the mod with the kit's cook: the actors ship in the mod's pak.

In-game player positions are the capsule, about 92 units above the floor when standing; for an object's Z use the floor (a vanilla contextual-action spot nearby has the floor's Z).

## Where the save goes
- One file per actor (World Partition external actors), inside the mod:
  `Mods/<Mod>/Content/__ExternalActors__/ContentBundle/<bundle GUID>/_Stalker_2/maps/_Stalker2_WorldMap/WorldMap_WP/<a>/<b>/<c>/<hash>.uasset`.
  The content bundle is the mod's own, so GSC's level is not modified.
- The Content Browser does not list `__ExternalActors__`. The actors show in the Outliner while WorldMap_WP is open. Outside
  the editor, a file's strings name its class (`BP_..._C`), which identifies the actor.
- Do not check out or save GSC's levels or their external actors (GSC: it may crash the editor).

## Blueprints that need placing
| Object | Blueprint |
|---|---|
| Personal stash, shared with the hub stashes | `/Game/GameLite/Blueprints/Interactable/ItemContainers/BP_PlayerStash` |
| Personal stash that a quest can switch off | `.../ItemContainers/BP_PlayerStash_WithDeactivationReciever`: registers itself on BeginPlay, unregisters on a signal. DLC1 places one in its main hub and hides it with a quest `SendSignal` node aimed at the actor's signal receiver. |
| Bed on the floor | `/Game/_STALKER2/GameDesign/InteractiveObjects/Bed/BP_Bed_OnGround`: a mattress with its own mesh, fine on any flat floor |
| Bed on a bed frame | `.../Bed/BP_Bed_OnBed`: only the mattress; the hubs set it on a separate bed-frame mesh |
| (base class) | `/Game/GameLite/Blueprints/Interactable/Beds/BP_Bed`: abstract, error-cube mesh; do not place |

Saving both into a mod's content bundle is tested (above). How a placed stash and bed behave in game, including whether that
stash shares its inventory with the hub stashes, is untested.

A blueprint's asset path: run `retoc manifest` on each `pakchunk*.utoc` in an empty folder and search the `packagename`
entries (stalker2-paks).

## A personal stash spawned from cfg does not work
An ItemContainer spawn actor with `SpawnedPrototypeSID = PlayerStash`, tried three ways in game:
- the vanilla `PlayerStash` container prototype has no `Blueprint`: it spawns the generic container with the default backpack mesh;
- `Blueprint = BP_PlayerStash` on that prototype: the blue chest shows but cannot be opened;
- `Blueprint = BP_PlayerStash_WithDeactivationReciever`: the frame rate in that room fell to about 12 fps; removing the actor
  restored it.
Place the stash in the editor instead.
