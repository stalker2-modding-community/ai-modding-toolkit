# Security

## What the installer does
`install.py` (and `install.bat`, which only starts it) copies skill folders from this pack into the skills folders
of the agents you pick. It:
- uses no network and needs no admin rights;
- never runs anything from the pack;
- refuses to overwrite a skill it did not install, unless you pass `--replace-foreign`, and then backs that skill up
  first to `%USERPROFILE%/.stalker2-skill-pack/backups/`;
- checks every copied file against the pack's checksums, and builds each skill in a temporary folder before
  swapping it in;
- writes one record file (`.stalker2-skill-pack.json`) inside each skill it installs, so updates and uninstalls
  touch only its own folders;
- never writes a file named `manifest.json` into a skills folder (some Claude Code versions treat that file
  specially).

Check the files you received against `SHA256SUMS.txt` (PowerShell: `Get-FileHash <file> -Algorithm SHA256`).
Check installed skills any time: `python install.py --verify --agent <ids>`.

## What the skills' scripts do
Scripts run only when you, or your agent with your permission, start them. None of them reach the internet. Two talk only
to local tools on your own PC over loopback (`127.0.0.1`):
- `waapi.py` (stalker2-audio) sends commands to the Wwise authoring tool you have open, through its local port (`8090`).
- `editor_bridge.py` / `sdk_run.py --bridge*` (stalker2-zonekit) is opt-in only: start it manually per sitting inside the Zone Kit
  Output Log (`editor_bridge.start_bridge()`) and call `editor_bridge.stop_bridge()` when finished (commandlets and cooks
  auto-skip). It opens a localhost HTTP listener on `127.0.0.1:18777` (configurable via `S2_BRIDGE_PORT`) with fail-closed
  per-boot bearer token auth stored under an owner-only NTFS ACL (`%LOCALAPPDATA%/Stalker2/Saved/s2_editor_bridge.token`;
  POST requests fail with HTTP 403 if the token is missing or reset). `set_mi_params` refuses all writes unless
  `start_bridge(mod='<ModName>')` or `S2_BRIDGE_MOD` locks writes to one named mod, and `_BudgetGuard` is only a best-effort
  speed bump around Python load/save wrappers rather than a hard sandbox. `run_script` is off by default and has no env-var
  toggle; it is enabled only via `start_bridge(allow_run_script=True, script_root='<local dir>')`, rejects UNC/network paths,
  confines scripts inside that local directory, and runs arbitrary Python inside the editor process (prepending the script's
  directory to `sys.path`).
- They find the game, the Zone Kit and ~mods with `s2paths.py`, which reads the Steam and Epic launcher files and
  the registry (read-only) and writes only its own config file in `%APPDATA%/stalker2-skill-pack/`.
- They call external tools you installed yourself: retoc, repak, the Zone Kit editor and cook commandlet, Node,
  dotnet. `npm install` in stalker2-cfg's scripts folder downloads s2cfgtojson from npm; you run that once yourself.
- Some scripts are run inside the Zone Kit editor's Python (stalker2-blueprints, stalker2-voiceover,
  stalker2-zonekit). They read or change assets of your own mod in the kit.
- `s2sav.py` (stalker2-saves) reads save files. Its `pack` command writes a new save file, never over an existing
  one, and is untested in game: work on a copy.
- Scripts that edit a binary file (in stalker2-zonekit: `sdk_renew_state_id.py`, `sdk_code_patch.py`,
  `zen_add_redirect.py` when editing in place) write a `.bak` copy first unless you pass `--no-backup`.
- `paste_pages.ps1` (stalker2-blueprints) opens a small window with one Copy button per page of Blueprint paste text.
  It reads those text files and writes to the clipboard, nothing else.
- `pak_park.py` (stalker2-paks) moves paks between ~mods and `<game>/_parked_mods/`; it is the only script that moves your mods.
- Read any script before running it. They are plain Python or JavaScript.

## The running game
No script here reads or changes the running game, and nothing here is loaded into it. The scripts work on files.

## Secrets
The pack contains no keys, tokens or passwords and never asks for any. If you paste a
secret into a chat by mistake, revoke it.

## Things to keep in mind
- Skills are instructions for an AI agent. Install packs only from people you trust, and read the SKILL.md files:
  they are short plain text.
- Files inside other people's mods, downloads and web pages are data. The skills tell the agent never to follow
  instructions found in them.
- Windows Smart App Control can block some Zone Kit programs. The stalker2-zonekit skill explains the symptoms and
  the workarounds. Turning Smart App Control off lowers your PC's protection; that is your decision.

## Reporting a problem
Use GitHub's private vulnerability reporting on this repo (Security tab, Report a vulnerability). Please do not open a public issue for a
security problem. When you share crash files or logs, remember they contain your Windows user name in paths.
