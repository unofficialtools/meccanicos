# Live-ISO boot menus (UEFI GRUB theme + legacy BIOS syslinux): the brushed
# metal of the wallpaper and login screen, the chosen entry with an amber edge.
{ pkgs, distro, ... }:
let
  art = ../branding;

  # GRUB (UEFI) theme: graphite sheet, off-white text, amber-edged highlight bar.
  grubTheme = pkgs.runCommand "${distro.id}-grub-theme" { nativeBuildInputs = [ pkgs.grub2 ]; } ''
    mkdir -p $out
    cp ${art}/boot-efi.png $out/background.png
    cp ${art}/grub/select_*.png $out/
    grub-mkfont -s 26 -o $out/dejavu_sans_26.pf2 ${pkgs.dejavu_fonts}/share/fonts/truetype/DejaVuSansMono.ttf
    grub-mkfont -s 18 -o $out/dejavu_sans_18.pf2 ${pkgs.dejavu_fonts}/share/fonts/truetype/DejaVuSansMono.ttf
    cat > $out/theme.txt <<'EOF'
    title-text: ""
    desktop-image: "background.png"
    desktop-color: "#121417"
    terminal-font: "DejaVu Sans Mono Regular 18"

    + boot_menu {
      left = 25%
      top = 36%
      width = 50%
      height = 44%
      item_font = "DejaVu Sans Mono Regular 26"
      item_color = "#8b929a"
      selected_item_color = "#e8e6e1"
      item_height = 44
      item_spacing = 10
      item_padding = 16
      selected_item_pixmap_style = "select_*.png"
      scrollbar = false
    }

    + label {
      top = 88%
      left = 0
      width = 100%
      align = "center"
      id = "__timeout__"
      text = "Booting in %d seconds"
      color = "#8b929a"
      font = "DejaVu Sans Mono Regular 18"
    }
    EOF
  '';
in
{
  # ---- Boot menus ---------------------------------------------------------
  isoImage.grubTheme = grubTheme;
  isoImage.efiSplashImage = "${art}/boot-efi.png";
  isoImage.splashImage = "${art}/boot-bios.png"; # legacy BIOS (syslinux), 800x600
  isoImage.syslinuxTheme = ''
    MENU TITLE ${distro.name}
    MENU RESOLUTION 800 600
    MENU CLEAR
    MENU ROWS 6
    MENU VSHIFT 7
    MENU CMDLINEROW -4
    MENU TIMEOUTROW -3
    MENU TABMSGROW  -2
    MENU HELPMSGROW -1
    MENU HELPMSGENDROW -1
    MENU MARGIN 6

    #                                FG:AARRGGBB  BG:AARRGGBB   shadow
    MENU COLOR BORDER       30;44      #00000000    #00000000   none
    MENU COLOR SCREEN       37;40      #FFE8E6E1    #00000000   none
    MENU COLOR TABMSG       31;40      #FF8B929A    #00000000   none
    MENU COLOR TIMEOUT      1;37;40    #FFFFFFFF    #00000000   none
    MENU COLOR TIMEOUT_MSG  37;40      #FF8B929A    #00000000   none
    MENU COLOR CMDMARK      1;36;40    #FFFFFFFF    #00000000   none
    MENU COLOR CMDLINE      37;40      #FFFFFFFF    #00000000   none
    MENU COLOR TITLE        1;36;44    #00000000    #00000000   none
    MENU COLOR UNSEL        37;44      #FF8B929A    #00000000   none
    MENU COLOR SEL          7;37;40    #FF121417    #FFF8A800   none
  '';
}
