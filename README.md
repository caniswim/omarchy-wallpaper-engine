# Wallpaper Engine Workshop for Omarchy

Search the Steam Workshop, sign in with Steam's mobile QR approval, download wallpapers and apply them from **Omarchy → Style → Wallpaper Engine**. The native Quickshell gallery follows your Omarchy colors and supports English and Brazilian Portuguese.

A Wallpaper Engine **Steam license** is required for protected content and shared scene assets. You do **not** need to install or run the official Windows Wallpaper Engine application. This integration uses [tapline](https://github.com/UnhingedSoftware/tapline) to talk to Steam and [linux-wallpaperengine](https://github.com/Almamu/linux-wallpaperengine) to render Scene and Video projects. Some scenes use effects the Linux renderer does not implement; Web and Application projects are not supported.

## Install

Requirements: Omarchy with the native Quickshell shell, Python 3, `qrencode`, `tapline`, and `linux-wallpaperengine`. On Arch/Omarchy, the renderer package is `linux-wallpaperengine-git` from AUR; `qrencode` is in the official repositories.

The tested tapline revision is `f54136611519bef50cf31336e0c28a78eb175657`. Its `app download` command incorrectly starts anonymously even with a saved login. Apply the included compatibility patch before building this revision:

```bash
git clone https://github.com/UnhingedSoftware/tapline.git
cd tapline
git checkout f54136611519bef50cf31336e0c28a78eb175657
git apply /path/to/omarchy-wallpaper-engine/deps/tapline-owned-apps.patch
cargo build --release -p tapline-cli
install -Dm755 target/release/tapline ~/.local/bin/tapline
```

The patch changes only `Session::anonymous_shared(...)` to `Session::automatic_shared(None, ...)` for app downloads. Newer tapline versions may already include the fix; inspect that call before applying it. tapline stores its own login tokens with restricted file permissions; this plugin never reads them.

Install the Omarchy plugin after dependencies are available:

```bash
omarchy plugin add https://github.com/caniswim/omarchy-wallpaper-engine.git --enable
```

For development, put this repository in the user plugin directory with its manifest ID, enable that plugin, and run `./install.sh --no-deps`. The installer links `omarchy-we` into `~/.local/bin`, adds the Style menu item, installs a theme hook and adds a Hyprland login command. It never changes `/usr/share/omarchy`. Keep the repository in place: the CLI symlink points into it. Back up your user config before installing.

## Use

1. Open **Style → Wallpaper Engine**.
2. Choose **Steam sign-in**, scan the QR with the Steam mobile app, and approve. The QR expires after five minutes; press Cancel and retry if needed.
3. Choose **Scene assets** once. Only Wallpaper Engine's `assets` folder is downloaded; no Windows application, executables or web runtime are needed. Videos do not require these shared assets.
4. Search Workshop, select a tile and choose **Download / update**.
5. Choose **Apply**. **Library** shows downloaded content; **Stop live wallpaper** restores the previous background and disables login/theme restoration until another wallpaper is applied.

Searches and thumbnails load only when you ask to search. There is no background polling of Steam. You can close the gallery while an operation finishes; use **Cancel** to stop it. Downloads have a one-hour timeout; Steam errors appear in the gallery. Partial downloads stay hidden and can be resumed by retrying the same item. Shared assets also download into staging: only a successful Steam completion with nonempty baseline model, material and shader files replaces the current assets. Empty managed folders cannot shadow a valid Steam installation.

Downloaded wallpapers appear in `~/.local/share/omarchy-we/workshop`, shared assets in `~/.local/share/omarchy-we/engine/assets`, thumbnails in `~/.cache/omarchy-we/previews`, and renderer diagnostics in `~/.local/state/omarchy-we/renderer.log`. Standard XDG data/state/cache locations are honored. Existing Steam Workshop libraries, including paths in Steam's `libraryfolders.vdf`, are also discovered.

### Put wallpapers on another disk

Create `~/.config/omarchy-we/settings.json` with an absolute library path and a required mount point:

```json
{
  "library": "/run/media/you/Games/SteamLibrary/steamapps/workshop/content/431960",
  "required_mount": "/run/media/you/Games"
}
```

The library must be inside that mount. The plugin refuses to use an unavailable disk, so it cannot silently fill the system disk underneath an unmounted path. Mount and repair the disk through your system tools first. Shared engine assets remain in the user's data directory. Settings take effect on the next command or gallery reload.

To select a custom renderer build, add `"renderer": "/absolute/path/to/linux-wallpaperengine"` to the same settings file. `OMARCHY_WE_RENDERER` overrides that setting. An unavailable explicit renderer reports an error instead of silently choosing a different build from `PATH`; `omarchy-we doctor` reports the selected executable as `renderer_path`.

### CLI

```bash
omarchy-we browse                    # native gallery (menu/omatrix are aliases)
omarchy-we browse "nature"           # open gallery and search immediately
omarchy-we search "ocean" --page 1 --json
omarchy-we login                     # terminal QR approval
omarchy-we account                   # current tapline account (network request)
omarchy-we assets                    # selective shared assets download
omarchy-we download 1975950854        # verify app, download and add to library
omarchy-we list
omarchy-we set 1975950854             # ID, list index or unambiguous title
omarchy-we next                      # also prev/random
omarchy-we stop
omarchy-we doctor                    # local dependency/assets/current status
omarchy-we logout                    # forget all saved tapline logins
```

`OMARCHY_WE_FPS` defaults to `30` (1–240), `OMARCHY_WE_SCALING` defaults to `fill` (`fill`, `fit`, `stretch`, `default`), and `OMARCHY_WE_ASSETS` optionally points to another assets directory. `OMARCHY_WE_WORKSHOP` adds a local library to discovery. `omarchy-we launch` restores only an explicitly saved selection; an empty library never auto-starts a wallpaper.

The compatible JSON IPC commands are `ipc version`, `ipc entries`, `ipc current`, `ipc set ID`, `ipc stop`, `ipc kill`, and `ipc picker`. New direct commands accept `--json`; `login --json` emits newline-delimited QR/completion events. Errors are on stderr with nonzero status. `entries` returns `id/title/type/preview/current/installed`; `preview` is always a local path or null. The original `DialPicker.qml` remains as source reference; all menu aliases now open the searchable gallery.

## Desktop integration and boundaries

One renderer process draws the same wallpaper on every active monitor. Audio is muted. The plugin remembers its PID and Linux process start time, so stopping it cannot kill unrelated linux-wallpaperengine sessions. Startup errors go to the renderer log and do not make the Omarchy background transparent.

While live content plays, Omarchy's background points to the bundled transparent PNG. `owe refresh` lets Omarchy's own video daemon release its previous layer. Stopping restores the previous image/video. A theme change updates that saved background and reapplies the live wallpaper. Choosing another static background covers the live renderer; use **Stop live wallpaper** to release its GPU usage. Renderer compatibility varies by scene; a successful download does not guarantee every effect renders correctly.

Workshop metadata is bounded, titles render as `Text.PlainText`, subprocesses receive argument arrays, and downloaded code is never executed. Search verifies the Wallpaper Engine app ID; downloads verify it separately because tapline's current download CLI does not enforce its APPID argument. Thumbnails are cached from an allowlist of Steam HTTPS hosts with validated redirects, timeouts, size limits and raster signatures. Paths from `project.json` cannot point outside their wallpaper directory. Failed or incomplete downloads do not replace an existing library item.

## Verification and removal

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile bin/omarchy-we
bash -n install.sh uninstall.sh hooks/50-wallpaper-engine
omarchy plugin validate .
```

Tests use a fake tapline executable to assert actual CLI contracts and cover wrong-app rejection, hostile arguments/text, scene asset selection, partial installation visibility, mount guards, preview isolation, process timeouts and stop persistence. Real Steam authentication and renderer compatibility require a signed-in account and an active Hyprland desktop.

Run `./uninstall.sh` **before** removing the plugin with `omarchy plugin remove io.github.dkgamer02ai.wallpaper-engine`. It stops live rendering and removes the CLI link, hook, autostart and menu entry. Wallpapers, shared assets, thumbnail cache, settings, tapline account tokens and installed packages are retained. Run `omarchy-we logout` before uninstalling if you also want to forget tapline logins.

Based on the original [dkgamer02ai/omarchy-wallpaper-engine](https://github.com/dkgamer02ai/omarchy-wallpaper-engine), with native Workshop integration. MIT licensed; Steam content retains its respective licenses.
