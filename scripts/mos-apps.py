#!/usr/bin/env python3
"""apps - find, try, install, update and remove apps (needs the internet).

  apps search WORDS     find apps in nixpkgs ("drawing", inkscape)
  apps try NAME         run it once without installing it
  apps install NAME...  install for you (no password, no restart)
  apps remove NAME...   uninstall
  apps update [NAME...] update your apps (all of them without a NAME)
  apps list             the apps you installed, then the ones that come with MeccanicOS
  apps undo             undo the last install, removal or update
  apps manage           all of the above in a full-screen window

For one folder only (a project's compilers, tools, ...):
  apps install --here NAME...   on PATH in a terminal in this folder (and the
                                folders inside it), nowhere else
  apps remove --here NAME...    apps list --here    apps update --here

--here writes them into the folder's .envrc (`use nix -p NAME...`, between
two "mos-apps" lines; the rest of the file is left alone), which direnv
loads in every terminal. Commit .envrc to give a project's users the same
tools (with direnv and Nix). Desktop apps started from the command bar don't
see them: for those, plain `apps install`.

Apps go into your own Nix profile (~/.nix-profile), from the same nixpkgs
as the system. The apps that come with MeccanicOS are updated with the system
(mos-update). Search uses search.nixos.org, or `nix search` if that is
unreachable.
"""

import curses
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import socket
import urllib.request

# The look shared by MeccanicOS TUIs: MECCANICOS_PYLIB from the Nix wrapper, else next to this file.
sys.path.insert(0, os.environ.get("MECCANICOS_PYLIB") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import mos_tui as ui  # noqa: E402

FLAKE = "nixpkgs"  # the system's pinned nixpkgs (nix registry)
# Public read-only credentials of the search.nixos.org web page.
SEARCH_URL = "https://search.nixos.org/backend"
SEARCH_AUTH = "Basic YVdWU0FMWHBadjpYOGdQSG56TDUyd0ZFZWt1eHNmUTljU2g="
# Package sets full of libraries and plugins rather than apps.
NOISE = re.compile(
    r"^(haskellPackages|haskell|python\d*Packages|perl\d*Packages|rPackages|"
    r"nodePackages\w*|ocamlPackages\w*|lua\w*Packages|emacsPackages|vimPlugins|"
    r"texlive\w*|coqPackages\w*|idrisPackages|elmPackages|beamPackages\w*|"
    r"chickenPackages\w*|akkuPackages|tclPackages|octavePackages|php\w*|"
    r"rubyPackages\w*|linuxKernel|linuxPackages\w*|gnomeExtensions|"
    r"vscode-extensions|home-assistant-custom\w*|terraform-providers|"
    r"androidenv|dotnetCorePackages|rocmPackages\w*|cudaPackages\w*|\w+Plugins)\."
)
# Unfree apps (Zoom, Steam, ...) are allowed, as on the system.
NIX_ENV = dict(os.environ, NIXPKGS_ALLOW_UNFREE="1")
NIX = ["nix", "--extra-experimental-features", "nix-command flakes"]
# APPS_PROFILE=/some/path: work on that profile instead of yours (testing).
PROFILE = ["--profile", os.environ["APPS_PROFILE"]] if os.environ.get("APPS_PROFILE") else []


def live_usb():
    try:
        with open("/etc/os-release") as f:
            return any(line.startswith("IMAGE_VERSION=") for line in f)
    except OSError:
        return False


def release():
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("VERSION_ID="):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return "unstable"


# ---- installed apps (your Nix profile) ---------------------------------------
def version_of(store_path):
    # /nix/store/<hash>-inkscape-1.4.2 -> 1.4.2
    parts = os.path.basename(store_path).split("-")[1:]
    for i, p in enumerate(parts):
        if p[:1].isdigit():
            return "-".join(parts[i:])
    return ""


def installed():
    """[{name, attr, version, missing}] from `nix profile list`."""
    try:
        out = subprocess.run(NIX + ["profile", "list", "--json"] + PROFILE, capture_output=True, text=True, check=True).stdout
        elements = json.loads(out).get("elements", {})
    except (subprocess.CalledProcessError, ValueError, OSError):
        return []
    if isinstance(elements, list):  # older Nix: a list without names
        elements = {e.get("attrPath", "?").split(".")[-1]: e for e in elements}
    apps = []
    for name, e in sorted(elements.items()):
        paths = e.get("storePaths") or [""]
        apps.append(
            {
                "name": name,
                "attr": (e.get("attrPath") or name).split(".", 2)[-1],
                "version": version_of(paths[0]),
                # A live USB forgets downloads at shutdown; the list in a
                # persistent home stays. Update downloads them again.
                "missing": not all(os.path.exists(p) for p in paths if p),
            }
        )
    return apps


# ---- search --------------------------------------------------------------------
SYSTEM_APPS = "/run/current-system/sw/share/applications"
SYSTEM_BIN = "/run/current-system/sw/bin"
WRAPPERS = {"env", "sh", "bash", "xfce4-terminal", "gtk-launch", "xdg-open"}


def package_of(path):
    """/nix/store/<hash>-inkscape-1.4.2/... -> ("inkscape", "1.4.2"), or None."""
    m = re.match(r"/nix/store/[a-z0-9]{32}-([^/]+)", path)
    if not m or m.group(1).endswith(".desktop") or m.group(1) == "system-path" or m.group(1).startswith("nixos-system-"):
        return None
    version = version_of(m.group(0))
    name = m.group(1)[: -len(version) - 1] if version else m.group(1)
    return name, version


def package_behind(path):
    """The package a file comes from, following its links one step at a time:
    MeccanicOS's small wrappers (no version) point on to the real package."""
    found = []
    for _ in range(12):
        pkg = package_of(path)
        if pkg:
            found.append(pkg)
            if pkg[1]:
                return pkg
        if not os.path.islink(path):
            break
        path = os.path.join(os.path.dirname(path), os.readlink(path))
    return found[0] if found else None


def system_apps():
    """[{name, version, apps, system}]: the packages behind the menu's visible
    entries, i.e. the apps that come with MeccanicOS (updated with the system).
    MeccanicOS renames entries by copying them, so the package is found from the
    program each one runs; its own launchers (mos-*) are not apps."""
    found = {}
    for f in sorted(glob.glob(os.path.join(SYSTEM_APPS, "*.desktop"))):
        try:
            with open(f, errors="replace") as fh:
                entry = fh.read().split("\n[", 1)[0]  # [Desktop Entry] only, not its actions
        except OSError:
            continue
        if re.search(r"^(NoDisplay|Hidden)=true", entry, re.M) or os.path.basename(f).startswith("mos-"):
            continue
        title = re.search(r"^Name=(.+)$", entry, re.M)
        exe = re.search(r"^Exec=(.+)$", entry, re.M)
        pkg = package_behind(f)
        if not pkg and exe:
            words = [w for w in exe.group(1).split() if "=" not in w and not w.startswith("%")]
            if " -x " in exe.group(1):  # a terminal launcher: the program it runs
                words = exe.group(1).split(" -x ", 1)[1].split()
            prog = next((w for w in words if os.path.basename(w) not in WRAPPERS and not w.startswith("-")), "")
            path = prog if prog.startswith("/") else os.path.join(SYSTEM_BIN, prog)
            pkg = package_behind(path) if prog else None
        if not pkg or pkg[0].startswith("mos-"):  # none, or one of MeccanicOS's launchers
            continue
        a = found.setdefault(pkg[0], {"name": pkg[0], "version": pkg[1], "apps": [], "system": True, "missing": False})
        if title:
            a["apps"].append(title.group(1))
    return sorted(found.values(), key=lambda a: a["name"].lower())


def search_web(words, size=60):
    req = urllib.request.Request(SEARCH_URL + "/_aliases", headers={"Authorization": SEARCH_AUTH})
    with urllib.request.urlopen(req, timeout=15) as r:
        aliases = json.load(r)
    rel = release()
    names = [a for v in aliases.values() for a in v.get("aliases", {}) if a.endswith(f"-nixos-{rel}")]
    if not names:
        names = [a for v in aliases.values() for a in v.get("aliases", {}) if a.endswith("-nixos-unstable")]
    index = max(names, key=lambda a: int(re.search(r"latest-(\d+)-", a).group(1)))
    query = {
        "size": size,
        "_source": ["package_attr_name", "package_pname", "package_pversion", "package_description", "package_programs", "package_mainProgram", "package_license_set"],
        "query": {
            "bool": {
                "filter": [{"term": {"type": "package"}}],
                "must": [
                    {
                        "multi_match": {
                            "query": words,
                            "type": "cross_fields",
                            "fields": ["package_attr_name^9", "package_pname^6", "package_programs^9", "package_description^1.3", "package_longDescription^1"],
                        }
                    }
                ],
                "should": [
                    {"term": {"package_attr_name": {"value": words.lower(), "boost": 50}}},
                    {"term": {"package_pname": {"value": words.lower(), "boost": 30}}},
                ],
            }
        },
    }
    req = urllib.request.Request(
        f"{SEARCH_URL}/{index}/_search",
        data=json.dumps(query).encode(),
        headers={"Authorization": SEARCH_AUTH, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        hits = json.load(r)["hits"]["hits"]
    found = []
    for h in hits:
        s = h["_source"]
        attr = s.get("package_attr_name", "")
        if NOISE.match(attr) or not (s.get("package_programs") or s.get("package_mainProgram")):
            continue
        found.append(
            {
                "attr": attr,
                "version": s.get("package_pversion") or "",
                "description": (s.get("package_description") or "").strip(),
                "program": s.get("package_mainProgram") or (s.get("package_programs") or [""])[0],
                "unfree": "unfree" in (s.get("package_license_set") or []),
            }
        )
    return found


def search_nix(words):
    # Evaluates all of nixpkgs: about a minute the first time, then cached.
    regex = ".*".join(re.escape(w) for w in words.split())
    out = subprocess.run(NIX + ["search", FLAKE, regex, "--json"], capture_output=True, text=True, env=NIX_ENV).stdout
    found = []
    for key, p in (json.loads(out or "{}")).items():
        attr = key.split(".", 2)[-1]
        if NOISE.match(attr):
            continue
        found.append({"attr": attr, "version": p.get("version", ""), "description": p.get("description", ""), "program": "", "unfree": False})
    return found


OFFLINE = "No internet connection: {} needs it. Connect (the network icon in the top bar) and try again."


def online(host="cache.nixos.org"):
    """Can we reach host? Quick: no network fails at once, a dead one in 3 s."""
    try:
        socket.create_connection((host, 443), timeout=3).close()
        return True
    except OSError:
        return False


def search(words, progress=lambda note: None):
    """(results, note); note is a problem worth showing, or ""."""
    if not online("search.nixos.org"):
        if not online():
            return [], OFFLINE.format("searching")
    else:
        progress(f"Searching search.nixos.org for “{words}”…")
        try:
            return search_web(words), ""
        except Exception:  # the site changed or is down
            pass
    progress("search.nixos.org did not answer: searching with nix search (a minute or more the first time)…")
    found = search_nix(words)
    return found, "" if found else "search.nixos.org did not answer and nix search found nothing."


# ---- actions (run in the terminal, showing Nix's progress) -------------------
def run(cmd):
    print("\033[38;5;245m$ " + " ".join(cmd) + "\033[0m", flush=True)
    return subprocess.run(cmd, env=NIX_ENV).returncode


def do_install(names):
    return run(NIX + ["profile", "add", "--impure"] + PROFILE + [f"{FLAKE}#{n}" for n in names])


def do_remove(names):
    return run(NIX + ["profile", "remove"] + PROFILE + list(names))


def do_update(names):
    return run(NIX + ["profile", "upgrade", "--impure"] + PROFILE + (list(names) or ["--all"]))


def do_undo():
    return run(NIX + ["profile", "rollback"] + PROFILE)


def do_try(name, program=""):
    """Download NAME into the store without installing it, then run it: a
    desktop app in its own window, a command-line tool in a shell where it is
    on PATH. Nothing is kept: Nix removes it when it cleans up."""
    print(f"Getting {name} (not installing it)...", flush=True)
    res = subprocess.run(NIX + ["build", "--impure", "--no-link", "--print-out-paths", f"{FLAKE}#{name}"], stdout=subprocess.PIPE, text=True, env=NIX_ENV)
    if res.returncode != 0:
        return res.returncode
    outs = res.stdout.split()
    bins = [os.path.join(o, "bin") for o in outs if os.path.isdir(os.path.join(o, "bin"))]
    gui = any(os.path.isdir(os.path.join(o, "share", "applications")) for o in outs)
    progs = sorted({p for b in bins for p in os.listdir(b)})
    if gui and progs:
        prog = program if program in progs else (name if name in progs else progs[0])
        exe = next(os.path.join(b, prog) for b in bins if os.path.exists(os.path.join(b, prog)))
        print(f"Starting {prog} in its own window.", flush=True)
        subprocess.Popen([exe], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return 0
    path = ":".join(bins + [os.environ.get("PATH", "")])
    print(f"\n\033[1;38;5;214m{name}\033[0m is ready to try in this shell: " + (", ".join(progs[:12]) or "(no commands)"))
    print("Type \033[38;5;214mexit\033[0m when you are done; nothing stays installed.\n", flush=True)
    return subprocess.run(["bash", "-i"], env=dict(os.environ, PATH=path)).returncode


# ---- apps for one folder (direnv) -------------------------------------------------
# direnv runs in every shell (shell.nix) with nix-direnv, which caches the
# folder's apps and keeps them from being cleaned up (in .direnv/).
BEGIN = "# mos-apps: this folder's apps (apps install --here, apps remove --here)"
END = "# end mos-apps"
NAME_RE = re.compile(r"[A-Za-z_][\w.+-]*")  # .envrc is run by bash: names only


def envrc(folder):
    return os.path.join(folder, ".envrc")


def here_split(folder):
    """(lines before, apps, lines after) of folder's .envrc."""
    try:
        with open(envrc(folder)) as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        return [], [], []
    try:
        b = next(i for i, l in enumerate(lines) if l.startswith("# mos-apps"))
        e = next(i for i in range(b, len(lines)) if lines[i].strip() == END)
    except StopIteration:
        return lines, [], []
    apps = []
    for line in lines[b + 1:e]:
        words = line.split()
        if words[:3] == ["use", "nix", "-p"]:
            apps += words[3:]
    return lines[:b], apps, lines[e + 1:]


def here_write(folder, apps):
    """Rewrite the block (none without apps); False if .envrc is now gone."""
    before, _, after = here_split(folder)
    block = [BEGIN, "use nix -p " + " ".join(apps), END] if apps else []
    while before and not before[-1].strip() and not block:  # the gap left by the block
        before.pop()
    if before and before[-1].strip() and block:
        block.insert(0, "")
    lines = before + block + after
    path = envrc(folder)
    if not any(l.strip() for l in lines):
        if os.path.exists(path):
            os.remove(path)
        return False
    with open(path + ".part", "w") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(path + ".part", path)
    subprocess.run(["direnv", "allow", folder])  # direnv loads no .envrc it wasn't told to
    return True


def here_names(names):
    for n in names:
        if not NAME_RE.fullmatch(n):
            usage_error(f"'{n}' is not an app name")
    if not shutil.which("direnv"):
        sys.exit("apps: direnv is not available, so --here can't work")
    return list(dict.fromkeys(names))


def here_install(names):
    folder = os.getcwd()
    have = here_split(folder)[1]
    new = [n for n in here_names(names) if n not in have]
    if not new:
        print(f"Already here: {', '.join(names)}.")
        return 0
    # Downloaded now: a wrong name fails here, and the first prompt in the folder is quick.
    print(f"Getting {', '.join(new)} for {folder}...", flush=True)
    code = run(NIX + ["build", "--impure", "--no-link"] + [f"{FLAKE}#{n}" for n in new])
    if code:
        return code
    here_write(folder, have + new)
    print(f"\n\033[1;38;5;214m{', '.join(have + new)}\033[0m: on PATH in a terminal in {folder}")
    print("and the folders inside it (this one too, from the next prompt); not elsewhere.")
    if os.path.exists(os.path.join(folder, ".git")):
        print("To share them, commit .envrc (and put .direnv/ in .gitignore).")
    return 0


def here_remove(names):
    folder = os.getcwd()
    have = here_split(folder)[1]
    names = here_names(names)
    gone = [n for n in names if n in have]
    for n in names:
        if n not in have:
            print(f"{n} is not one of this folder's apps.")
    if not gone:
        return 1
    left = [a for a in have if a not in gone]
    kept = here_write(folder, left)
    print(f"Removed {', '.join(gone)} from this folder." +
          (f" Still here: {', '.join(left)}." if left else "") +
          ("" if kept else " (.envrc had nothing else, so it is gone.)"))
    return 0


def here_list():
    folder = os.getcwd()
    apps = here_split(folder)[1]
    if not apps:
        print(f"No apps for this folder yet: apps install --here NAME (in {folder}).")
    for a in apps:
        print(a)
    return 0


def here_update():
    """nix-direnv rebuilds when .envrc is newer than its cache: from the
    system's current packages (they change with mos-upgrade/update)."""
    folder = os.getcwd()
    if not here_split(folder)[1]:
        print("No apps for this folder: nothing to update.")
        return 1
    os.utime(envrc(folder))
    subprocess.run(["direnv", "allow", folder])
    print("This folder's apps are brought up to date at the next prompt here.")
    return 0


# ---- full-screen manager -------------------------------------------------------
# The colours and keys of every MeccanicOS full-screen tool (scripts/lib/mos_tui.py).
C_NORMAL, C_CURSOR, C_TITLE, C_KEY, C_DIM, C_OK, C_ERR, C_BORDER = (
    ui.NORMAL, ui.SELECTED, ui.HEADING, ui.KEY, ui.DIM, ui.OK, ui.ERR, ui.BORDER)


class Manager:
    def __init__(self, scr):
        self.scr = scr
        self.tab = "installed"  # or "search"
        self.apps = installed()
        self.system = system_apps()  # MeccanicOS's own: listed, updated with the system
        self.results = []
        self.query = ""
        self.cursor = {"installed": 0, "search": 0}
        self.top = {"installed": 0, "search": 0}
        self.focus = 0  # focused button
        self.msg = ""
        self.err = False
        self.typing = False
        self.typing_at = (0, 0)
        self.busy = False  # a search is running
        self.online = online()
        self.hits = []  # clickable areas: (y, x0, x1, action)
        if not self.online:
            self.say(OFFLINE.format("finding and installing apps"), True)
        elif live_usb():
            self.msg = "Live USB: apps you install last until you shut down."

    # -- what's on screen ------------------------------------------------------
    def rows(self):
        return self.apps + self.system if self.tab == "installed" else self.results

    def buttons(self):
        if self.tab == "installed":
            return [("u", "Uninstall", self.uninstall), ("p", "Update", self.update_one), ("a", "Update all", self.update_all), ("o", "Undo", self.undo), ("s", "Search", self.go_search), ("q", "Quit", None)]
        return [("i", "Install", self.install), ("t", "Try it", self.try_it), ("n", "New search", self.new_search), ("b", "Back", self.go_installed), ("q", "Quit", None)]

    def add(self, y, x, text, attr=0, w=None):
        h, W = self.scr.getmaxyx()
        if y >= h or x >= W:
            return x
        text = text[: max(0, (w if w is not None else W - x) - 0)]
        text = text[: W - x - (1 if y == h - 1 else 0)]
        try:
            self.scr.addstr(y, x, text, attr)
        except curses.error:
            pass
        return x + len(text)

    def draw(self):
        s = self.scr
        s.erase()
        h, w = s.getmaxyx()
        self.hits = []
        cp = ui.attr
        # Title bar
        ui.bar(s, 0, "Apps Manager", "offline: search and installs need the internet" if not self.online else "")
        # Tabs: the one shown is teal, as the bars
        x = 1
        for key, label, tab in (("1", f" Installed ({len(self.apps) + len(self.system)}) ", "installed"), ("2", " Search ", "search")):
            attr = cp(ui.BAR) if self.tab == tab else cp(ui.BUTTON)
            x0 = x
            x = self.add(2, x, label, attr)
            self.hits.append((2, x0, x, ("tab", tab)))
            x += 1
        # Search box
        top_y = 4
        if self.tab == "search":
            self.add(top_y, 1, "Search: ", cp(C_KEY if self.typing else C_TITLE))
            at = ui.field(s, top_y, 9, max(10, w - 12), self.query, self.typing)
            if self.typing:
                self.typing_at = (top_y, at)
            self.hits.append((top_y, 9, w - 2, ("type",)))
            top_y += 2
        # Column header
        rows = self.rows()
        namew = max([len(r.get("name", r.get("attr", ""))) for r in rows] + [12])
        namew = min(namew, max(12, w // 3))
        verw = min(max([len(r["version"]) for r in rows] + [7]), 16)
        head = f"  {'App'.ljust(namew)}  {'Version'.ljust(verw)}  " + ("Status" if self.tab == "installed" else "What it is")
        self.add(top_y, 0, head, cp(C_TITLE))
        self.add(top_y + 1, 0, "─" * w, cp(C_BORDER))
        list_y = top_y + 2
        list_h = max(1, h - list_y - 4)
        cur = self.cursor[self.tab] = min(self.cursor[self.tab], max(0, len(rows) - 1))
        top = self.top[self.tab]
        if cur < top:
            top = cur
        elif cur >= top + list_h:
            top = cur - list_h + 1
        self.top[self.tab] = top
        mine = {a["attr"] for a in self.apps} | {a["name"] for a in self.apps} | {a["name"] for a in self.system}
        if not rows:
            empty = (
                "No apps installed yet. Press s to search for one."
                if self.tab == "installed"
                else ("Type what you are looking for (\"drawing\", inkscape) and press Enter." if not self.query else "Nothing found.")
            )
            self.add(list_y, 2, empty, cp(C_DIM))
        for i, r in enumerate(rows[top : top + list_h]):
            n = top + i
            y = list_y + i
            name = r.get("name", r.get("attr", ""))
            if self.tab == "installed" and r.get("system"):
                status, sattr = "comes with MeccanicOS: " + ", ".join(r["apps"]), cp(C_DIM)
            elif self.tab == "installed":
                status, sattr = ("downloaded again by Update" if r["missing"] else "installed"), (cp(C_ERR) if r["missing"] else cp(C_OK))
            else:
                status, sattr = r["description"], cp(C_NORMAL)
                if r["attr"] in mine or r["attr"].split(".")[-1] in mine:
                    status, sattr = "✓ installed  " + status, cp(C_OK)
                elif r["unfree"]:
                    status = "(not open source)  " + status
            line = f"  {name[:namew].ljust(namew)}  {r['version'][:verw].ljust(verw)}  "
            if n == cur:
                self.add(y, 0, (line + status).ljust(w), cp(C_CURSOR) if not self.typing else cp(ui.FIELD))
            else:
                x = self.add(y, 0, line, cp(C_NORMAL))
                self.add(y, x, status, sattr)
            self.hits.append((y, 0, w, ("row", n)))
        # Buttons
        by = h - 3
        self.add(by - 1, 0, "─" * w, cp(C_BORDER))
        labels = [(label, key) for key, label, _ in self.buttons()]
        focus = -1 if self.typing else self.focus
        for i, (x0, x1) in enumerate(ui.buttons(s, by, 1, labels, focus)):
            self.hits.append((by, x0, x1, ("button", i)))
        # Message + keys
        msg = ("✗ " if self.err and not self.msg.startswith("✗") else "") + self.msg
        ui.message(s, h - 2, 1, msg) if self.err or msg.startswith("✓") else self.add(h - 2, 1, msg, cp(C_KEY if self.busy else C_DIM))
        keys = [("Enter", "search"), ("Esc", "done typing")] if self.typing else \
            [("↑↓", "move"), ("←→", "button"), ("Enter", "press"), ("Tab", "switch list"), ("q", "quit")]
        ui.keybar(s, h - 1, keys)
        if self.typing:
            ui.cursor(True)
            s.move(*self.typing_at)
        else:
            ui.cursor(False)
        s.refresh()

    # -- actions ---------------------------------------------------------------
    def selected(self):
        rows = self.rows()
        return rows[self.cursor[self.tab]] if rows else None

    def shell(self, fn, *args, wait=True):
        """Leave the full screen to run a Nix command with its progress."""
        curses.def_prog_mode()
        curses.endwin()
        print()
        try:
            code = fn(*args)
        except KeyboardInterrupt:
            code = 130
        if wait:
            print("\n" + ("\033[38;5;114mDone.\033[0m" if code == 0 else f"\033[38;5;203mFailed (exit {code}).\033[0m") + " Press Enter to go back.", end="", flush=True)
            try:
                input()
            except (EOFError, KeyboardInterrupt):
                pass
        curses.reset_prog_mode()
        self.scr.clear()
        self.apps = installed()
        return code

    def say(self, msg, err=False):
        self.msg, self.err = msg, err

    def confirm(self, question):
        return ui.confirm(self.scr, question, yes="Yes", no="No")

    def mos_own(self, a):
        """True (and says why) for an app that comes with MeccanicOS."""
        if a and a.get("system"):
            self.say(f"{a['name']} comes with MeccanicOS: it is updated with the system (mos-upgrade), not here.")
            return True
        return False

    def uninstall(self):
        a = self.selected()
        if not a:
            return self.say("Nothing to uninstall.")
        if self.mos_own(a):
            return
        if self.confirm(f"Uninstall {a['name']}?"):
            code = self.shell(do_remove, [a["name"]])
            self.say(f"{a['name']} uninstalled." if code == 0 else f"Could not uninstall {a['name']}.", code != 0)

    def update_one(self):
        a = self.selected()
        if not a:
            return self.say("Nothing to update.")
        if self.mos_own(a):
            return
        if self.needs_internet("updating"):
            return
        code = self.shell(do_update, [a["name"]])
        self.say(f"{a['name']} is up to date." if code == 0 else f"Could not update {a['name']}.", code != 0)

    def update_all(self):
        if not self.apps:
            return self.say("No apps of yours to update. (MeccanicOS's own apps update with the system.)")
        if self.needs_internet("updating"):
            return
        code = self.shell(do_update, [])
        self.say("All your apps are up to date." if code == 0 else "Some apps could not be updated.", code != 0)

    def undo(self):
        if self.confirm("Undo the last install, removal or update?"):
            code = self.shell(do_undo)
            self.say("Undone." if code == 0 else "Nothing to undo.", code != 0)

    def install(self):
        r = self.selected()
        if not r:
            return self.say("Search for an app first.")
        if self.needs_internet("installing"):
            return
        code = self.shell(do_install, [r["attr"]])
        self.say(f"{r['attr']} installed: find it in the command bar (Super+Space)." if code == 0 else f"Could not install {r['attr']}.", code != 0)

    def try_it(self):
        r = self.selected()
        if not r:
            return self.say("Search for an app first.")
        if self.needs_internet("trying an app"):
            return
        code = self.shell(do_try, r["attr"], r.get("program", ""))
        self.say(f"Tried {r['attr']}; press i to install it." if code == 0 else f"Could not start {r['attr']}.", code != 0)

    def go_search(self):
        self.tab, self.focus, self.typing = "search", 0, not self.query

    def new_search(self):
        self.tab, self.typing = "search", True

    def go_installed(self):
        self.tab, self.focus, self.typing = "installed", 0, False

    def run_search(self):
        self.typing = False
        if not self.query.strip():
            return

        def progress(note):
            self.say(note)
            self.draw()

        self.busy = True
        progress(f"Searching for “{self.query}”…")
        try:
            self.results, note = search(self.query.strip(), progress)
        finally:
            self.busy = False
        self.online = not note.startswith("No internet")
        self.cursor["search"] = self.top["search"] = 0
        if note:
            self.say(note, True)
        else:
            self.say(f"✓ {len(self.results)} apps found. i installs, t tries without installing.")

    def needs_internet(self, what):
        """True (and says so) when offline."""
        self.online = online()
        if not self.online:
            self.say(OFFLINE.format(what), True)
        return not self.online

    def press(self, i):
        btns = self.buttons()
        if 0 <= i < len(btns):
            fn = btns[i][2]
            if fn is None:
                return False
            fn()
        return True

    # -- input -----------------------------------------------------------------
    def loop(self):
        curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
        self.scr.keypad(True)
        while True:
            self.focus = min(self.focus, len(self.buttons()) - 1)
            self.draw()
            k = self.scr.get_wch()
            if self.typing:
                if k in ("\n", "\r", curses.KEY_ENTER):
                    self.run_search()
                elif k == "\x1b":
                    self.typing = False
                elif k in (curses.KEY_BACKSPACE, "\x7f", "\b"):
                    self.query = self.query[:-1]
                elif k == curses.KEY_DOWN:
                    self.typing = False
                elif isinstance(k, str) and k.isprintable():
                    self.query += k
                continue
            n = len(self.rows())
            if k == curses.KEY_MOUSE:
                try:
                    _, mx, my, _, bstate = curses.getmouse()
                except curses.error:
                    continue
                if bstate & curses.BUTTON4_PRESSED:
                    self.cursor[self.tab] = max(0, self.cursor[self.tab] - 3)
                    continue
                if bstate & getattr(curses, "BUTTON5_PRESSED", 0x200000):
                    self.cursor[self.tab] = min(max(0, n - 1), self.cursor[self.tab] + 3)
                    continue
                for y, x0, x1, act in self.hits:
                    if my == y and x0 <= mx < x1:
                        if act[0] == "tab":
                            self.go_search() if act[1] == "search" else self.go_installed()
                        elif act[0] == "type":
                            self.typing = True
                        elif act[0] == "row":
                            self.cursor[self.tab] = act[1]
                        elif act[0] == "button":
                            self.focus = act[1]
                            if not self.press(act[1]):
                                return
                        break
                continue
            if k == curses.KEY_UP:
                self.cursor[self.tab] = max(0, self.cursor[self.tab] - 1)
                if self.tab == "search" and self.cursor["search"] == 0 and n == 0:
                    self.typing = True
            elif k == curses.KEY_DOWN:
                self.cursor[self.tab] = min(max(0, n - 1), self.cursor[self.tab] + 1)
            elif k == curses.KEY_PPAGE:
                self.cursor[self.tab] = max(0, self.cursor[self.tab] - 10)
            elif k == curses.KEY_NPAGE:
                self.cursor[self.tab] = min(max(0, n - 1), self.cursor[self.tab] + 10)
            elif k == curses.KEY_LEFT:
                self.focus = (self.focus - 1) % len(self.buttons())
            elif k == curses.KEY_RIGHT:
                self.focus = (self.focus + 1) % len(self.buttons())
            elif k in ("\t", curses.KEY_BTAB, "1", "2"):
                if k == "1":
                    self.go_installed()
                elif k == "2":
                    self.go_search()
                else:
                    self.go_search() if self.tab == "installed" else self.go_installed()
            elif k in ("\n", "\r", curses.KEY_ENTER):
                if not self.press(self.focus):
                    return
            elif k in ("q", "\x1b"):
                if self.tab == "search" and k == "\x1b":
                    self.go_installed()
                else:
                    return
            elif k == "/":
                self.new_search()
            elif k == curses.KEY_RESIZE:
                pass
            elif isinstance(k, str):
                for i, (key, _, _) in enumerate(self.buttons()):
                    if k.lower() == key:
                        self.focus = i
                        if not self.press(i):
                            return
                        break


def manage():
    if not sys.stdout.isatty():
        sys.exit("apps manage needs a terminal")
    os.environ.setdefault("ESCDELAY", "25")
    curses.wrapper(lambda scr: (ui.init(), Manager(scr).loop()))


# ---- command line ----------------------------------------------------------------
COMMANDS = ("manage", "list", "search", "install", "add", "remove", "uninstall", "update", "upgrade", "undo", "try")


def usage_error(problem):
    """Wrong usage: one line on stderr, exit code 2 (runtime failures exit 1)."""
    print(f"apps: {problem} (apps --help)", file=sys.stderr)
    sys.exit(2)


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    cmd, args = argv[0], argv[1:]
    if cmd not in COMMANDS:
        usage_error(f"unknown command '{cmd}'")
    here = "--here" in args
    args = [a for a in args if a != "--here"]
    if not shutil.which("nix"):
        sys.exit("apps: nix is not available")
    if here:
        if cmd in ("install", "add", "remove", "uninstall") and not args:
            usage_error(f"{cmd} --here needs a NAME")
        for n in args:  # a wrong name is a usage error, online or not
            if not NAME_RE.fullmatch(n):
                usage_error(f"'{n}' is not an app name")
        if cmd in ("install", "add", "update", "upgrade") and not online():
            sys.exit("apps: " + OFFLINE.format("getting apps"))
        if cmd in ("install", "add"):
            return here_install(args)
        if cmd in ("remove", "uninstall"):
            return here_remove(args)
        if cmd == "list":
            return here_list()
        if cmd in ("update", "upgrade"):
            return here_update()
        usage_error(f"{cmd} has no --here")
    if cmd == "manage":
        manage()
        return 0
    if cmd == "list":
        apps = installed()
        print("\033[1mYour apps\033[0m (apps install, apps remove, apps update):")
        if not apps:
            print("  none yet: apps search WORDS, then apps install NAME.")
        for a in apps:
            print(f"  {a['name']:<26} {a['version']:<16} {'(downloaded again by apps update)' if a['missing'] else ''}")
        print("\n\033[1mComes with MeccanicOS\033[0m (updated with the system: mos-upgrade):")
        for a in system_apps():
            print(f"  {a['name']:<26} {a['version']:<16} {', '.join(a['apps'])}")
        return 0
    if cmd == "search":
        if not args:
            usage_error("search needs WORDS")
        found, note = search(" ".join(args), lambda n: print(n, file=sys.stderr, flush=True))
        if note:
            print(note, file=sys.stderr)
            if note.startswith("No internet"):
                return 1
        for r in found[:30]:
            print(f"\033[1;38;5;214m{r['attr']}\033[0m {r['version']}" + ("  (not open source)" if r["unfree"] else ""))
            print(f"    {r['description']}")
        if not found:
            print("Nothing found.")
        return 0
    if cmd in ("install", "add"):
        if not args:
            usage_error("install needs a NAME")
        if not online():
            sys.exit("apps: " + OFFLINE.format("installing"))
        if live_usb():
            print("Live USB: apps you install last until you shut down.")
        return do_install(args)
    if cmd in ("remove", "uninstall"):
        if not args:
            usage_error("remove needs a NAME")
        return do_remove(args)
    if cmd in ("update", "upgrade"):
        if not online():
            sys.exit("apps: " + OFFLINE.format("updating"))
        return do_update(args)
    if cmd == "undo":
        return do_undo()
    if cmd == "try":
        if len(args) != 1:
            usage_error("try needs one NAME")
        if not online():
            sys.exit("apps: " + OFFLINE.format("trying an app"))
        return do_try(args[0])
    usage_error(f"unknown command '{cmd}'")


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]) or 0)
    except KeyboardInterrupt:  # Ctrl+C: curses.wrapper has restored the terminal
        sys.exit(130)
