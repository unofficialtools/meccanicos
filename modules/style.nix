# The MeccanicOS look, in one place: graphite surfaces, off-white text and
# one accent, the logo's amber. Amber is only for what is current or needs
# you: the selection, focus, the active workspace, progress and alerts.
# Imported by the modules that draw something (branding, keyboard); the
# terminal tools use the same colours from the 256-colour palette
# (scripts/lib/mos_tui.py, the prompt in shell.nix: 214 amber, 236 graphite).
{
  # Surfaces, darkest first
  ink = "#121417"; # behind everything: wallpaper, boot screens
  base = "#1a1d21"; # the panel, the command center
  raised = "#24282d"; # a hovered or chosen row, input fields
  line = "#3a4048"; # thin borders and inset lines
  # Text
  text = "#e8e6e1"; # off-white
  dim = "#8b929a"; # notes, labels, inactive workspaces
  # The accent
  amber = "#f8a800";
  amberDim = "#8a5f0a"; # amber on graphite, for large areas
  # Only for what is wrong now (the top bar's CPU when too hot).
  red = "#ff5f5f";
  # The logo's second colour. On the desktop only in the logo; in the
  # terminal, the prompt's and the mos-* tools' bars (256-colour 23); mc,
  # Jed and yazi are graphite and amber, like the desktop.
  teal = "#288080";

  # Type: a monospace for labels and readouts (the panel, the command
  # center's header, notification titles), Cantarell for reading.
  mono = "JetBrainsMono Nerd Font";
  sans = "Cantarell";

  # The icon theme: branding/icons.py's icons, then Kora (branding.nix).
  iconTheme = "MeccanicOS";
}
