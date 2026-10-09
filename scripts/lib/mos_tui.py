"""mos_tui - the look every MeccanicOS full-screen tool shares.

The colours are the shell prompt's (PS1 in modules/shell.nix): light on teal,
sand, orange. One rule for focus: what Enter acts on (the chosen row, the
focused button, the field being typed in) is dark on orange, and nothing
else on the screen is.

  bar        title bar (top) and key bar (bottom): light on teal, keys orange
  heading    sand, bold: titles, group names, column heads
  selected   dark on orange: the chosen row, focused button or field
  button     " Label " light on grey, its shortcut letter orange
  field      an input: light on grey (selected while typed in)
  dim        help and notes;  ok ✓ green;  err ✗ red;  border teal-grey

Without colours (a plain console): selected is reverse video, bars too.
Used by apps, usb-vault menu, mos-config, mos-install, mos-read and mos-backup browse;
the wrappers put this folder on PYTHONPATH.
"""

import curses

NORMAL, BAR, BAR_KEY, HEADING, KEY, SELECTED, BUTTON, BUTTON_KEY, FIELD, DIM, OK, ERR, BORDER = range(1, 14)

# role: (256-colour fg, bg), (8-colour fg, bg), extra attributes
_C = curses
STYLE = {
    NORMAL: ((250, -1), (-1, -1), 0),
    BAR: ((253, 23), (_C.COLOR_BLACK, _C.COLOR_CYAN), _C.A_BOLD),
    BAR_KEY: ((214, 23), (_C.COLOR_BLACK, _C.COLOR_CYAN), _C.A_BOLD),
    HEADING: ((180, -1), (_C.COLOR_YELLOW, -1), _C.A_BOLD),
    KEY: ((214, -1), (_C.COLOR_YELLOW, -1), _C.A_BOLD),
    SELECTED: ((235, 214), (_C.COLOR_BLACK, _C.COLOR_YELLOW), _C.A_BOLD),
    BUTTON: ((252, 238), (_C.COLOR_BLACK, _C.COLOR_WHITE), 0),
    BUTTON_KEY: ((214, 238), (_C.COLOR_RED, _C.COLOR_WHITE), _C.A_BOLD),
    FIELD: ((253, 237), (_C.COLOR_BLACK, _C.COLOR_WHITE), 0),
    DIM: ((245, -1), (-1, -1), 0),
    OK: ((114, -1), (_C.COLOR_GREEN, -1), 0),
    ERR: ((203, -1), (_C.COLOR_RED, -1), _C.A_BOLD),
    BORDER: ((66, -1), (_C.COLOR_CYAN, -1), 0),
}
PLAIN = {BAR: _C.A_REVERSE, BAR_KEY: _C.A_REVERSE | _C.A_BOLD, HEADING: _C.A_BOLD, KEY: _C.A_BOLD,
         SELECTED: _C.A_REVERSE | _C.A_BOLD, BUTTON: 0, BUTTON_KEY: _C.A_UNDERLINE, FIELD: _C.A_UNDERLINE,
         DIM: _C.A_DIM, ERR: _C.A_BOLD}
_colours = False

ENTER = ("\n", "\r", curses.KEY_ENTER)
ESC = "\x1b"
BACKSPACE = (curses.KEY_BACKSPACE, "\x7f", "\b")


def init():
    """Call once inside curses.wrapper."""
    global _colours
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    if not curses.has_colors():
        return
    curses.start_color()
    try:
        curses.use_default_colors()
    except curses.error:
        pass
    rich = curses.COLORS >= 256
    for role, (c256, c8, _) in STYLE.items():
        try:
            curses.init_pair(role, *(c256 if rich else c8))
        except curses.error:
            return
    _colours = True


def attr(role):
    if not _colours:
        return PLAIN.get(role, 0)
    return curses.color_pair(role) | STYLE[role][2]


def cursor(on):
    try:
        curses.curs_set(1 if on else 0)
    except curses.error:
        pass


def put(win, y, x, text, a=0):
    """Write what fits; returns the column after it."""
    h, w = win.getmaxyx()
    if not (0 <= y < h and 0 <= x < w):
        return x
    text = text[: w - x - (1 if y == h - 1 else 0)]
    try:
        win.addstr(y, x, text, a)
    except curses.error:
        pass
    return x + len(text)


def bar(win, y, text, right=""):
    """A full-width title bar."""
    w = win.getmaxyx()[1]
    line = f" {text}".ljust(w)
    if right:
        line = line[: max(0, w - len(right) - 2)] + right + "  "
    put(win, y, 0, line.ljust(w), attr(BAR))


def keybar(win, y, keys):
    """The key bar: [(key, what)], e.g. [("↑↓", "move"), ("q", "quit")]."""
    w = win.getmaxyx()[1]
    put(win, y, 0, " " * w, attr(BAR))
    x = 1
    for key, what in keys:
        x = put(win, y, x, key, attr(BAR_KEY))
        x = put(win, y, x, f" {what}   ", attr(BAR))


def frame(win, title="", a=None):
    """A popup's box, its title on the top line; a: the box's and title's
    attribute (e.g. attr(ERR) for a warning), else the usual ones."""
    win.erase()
    win.attron(a or attr(BORDER))
    win.box()
    win.attroff(a or attr(BORDER))
    if title:
        put(win, 0, 2, f" {title} ", a or attr(HEADING))


def row(win, y, x, width, text, selected, a=None):
    """A line of a list: selected is dark on orange, full width."""
    put(win, y, x, text[:width].ljust(width), attr(SELECTED) if selected else (attr(NORMAL) if a is None else a))


def button(win, y, x, label, focused, key=None):
    """ Label  with its shortcut letter marked; returns the column after."""
    base = attr(SELECTED) if focused else attr(BUTTON)
    mark = (attr(SELECTED) if focused else attr(BUTTON_KEY)) | curses.A_UNDERLINE
    k = label.lower().find(key.lower()) if key else -1
    x = put(win, y, x, " ", base)
    if k >= 0:
        x = put(win, y, x, label[:k], base)
        x = put(win, y, x, label[k], mark)
        x = put(win, y, x, label[k + 1:], base)
    else:
        x = put(win, y, x, label, base)
    return put(win, y, x, " ", base)


def buttons(win, y, x, labels, focus):
    """A row of buttons, labels [(label, key)]; returns their (x0, x1) spans."""
    spans = []
    for i, (label, key) in enumerate(labels):
        x0 = x
        x = button(win, y, x, label, i == focus, key)
        spans.append((x0, x))
        x += 2
    return spans


def width_of(labels):
    return sum(len(label) + 4 for label, _ in labels) - 2


def field(win, y, x, width, text, focused, secret=False):
    """An input; returns where the typing cursor goes."""
    shown = "•" * len(text) if secret else text
    shown = shown[-(width - 1):] if len(shown) >= width else shown
    put(win, y, x, shown.ljust(width), attr(SELECTED) if focused else attr(FIELD))
    return x + len(shown)


def message(win, y, x, text):
    """A ✓/✗ line in green/red, anything else plain."""
    role = OK if text.startswith("✓") else ERR if text.startswith("✗") else NORMAL
    put(win, y, x, text, attr(role))


def typed(text, k):
    """text after key k in an input, or None if k is not for typing."""
    if k in BACKSPACE:
        return text[:-1]
    if k == "\x15":  # Ctrl+U
        return ""
    if isinstance(k, str) and k.isprintable():
        return text + k
    return None


def confirm(scr, question, yes="Yes", no="Cancel", title="Are you sure?", default_yes=False):
    """The one confirmation every tool uses: a box with the question and two
    buttons on the right (←→ or Tab move, Enter presses, Esc says no)."""
    lines = question.splitlines()
    labels = [(yes, ""), (no, "")]
    h, w = scr.getmaxyx()
    bw = min(w - 2, max([len(l) for l in lines] + [len(title) + 6, width_of(labels)]) + 8)
    bh = len(lines) + 5
    win = curses.newwin(bh, bw, max(0, (h - bh) // 2), (w - bw) // 2)
    win.keypad(True)
    focus = 0 if default_yes else 1
    while True:
        frame(win, title)
        for i, l in enumerate(lines):
            put(win, 2 + i, 3, l, attr(NORMAL))
        buttons(win, bh - 2, bw - width_of(labels) - 3, labels, focus)
        win.refresh()
        k = win.get_wch()
        if k in (curses.KEY_LEFT, curses.KEY_RIGHT, "\t", curses.KEY_BTAB):
            focus = 1 - focus
        elif k in ENTER:
            return focus == 0
        elif k in (ESC, "q", "n"):
            return False
        elif k == "y":
            return True
