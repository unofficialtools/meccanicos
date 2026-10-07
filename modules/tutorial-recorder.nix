# tutorial-recorder: films the tutorial video (nix run .#tutorial-video). Only
# in the recorder ISO, never shipped. On login it starts recording the screen
# and the sound, plays the tour (scripts/mos-tutorial.py: the ideas behind
# MeccanicOS and a demo it performs on the desktop), then saves the recording and
# its subtitle cues to the disk labelled MECCOSREC and turns the VM off.
{ pkgs, distro, ... }:
let
  # ~/Tutorial: the example picture and video (branding/samples.sh), a PDF
  # to open, and two text files.
  samples =
    pkgs.runCommand "${distro.id}-tutorial-samples" { nativeBuildInputs = [ pkgs.imagemagick ]; }
      ''
        mkdir -p $out
        cp ${../branding/samples/example.png} $out/picture.png
        cp ${../branding/samples/example.mp4} $out/video.mp4
        magick ${../branding/samples/example.png} -resize 1200x $out/welcome.pdf
        cat > $out/notes.txt <<'TXT'
        My notes
        ========

        Type something below this line, then save with Ctrl+X, Ctrl+S.

        TXT
        cat > $out/old-notes.txt <<'TXT'
        An old file to put in the trash, and get back.
        TXT
      '';
  mos-tour = pkgs.writeShellApplication {
    name = "mos-tour";
    runtimeInputs = with pkgs; [
      xdotool # which windows are open; the demo's keys
      wmctrl # keep the tour above other windows; close the demo's
      procps # pgrep
      util-linux # flock
      xclip # the text it copies to read aloud
    ];
    text = ''
      # --window: open the tour in its own window (one tour at a time).
      if [ "''${1:-}" = --window ]; then
        shift
        exec xfce4-terminal --disable-server --class mos-tutorial \
          --title ${pkgs.lib.escapeShellArg "Tutorial (${distro.name})"} \
          --geometry 78x24-0+32 -x mos-tour "$@"
      fi
      export MECCANICOS_NAME=${pkgs.lib.escapeShellArg distro.name}
      export MECCANICOS_TUTORIAL_SAMPLES=${samples}
      exec ${pkgs.python3}/bin/python3 ${../scripts/mos-tutorial.py} "$@"
    '';
  };
  # Runs in the desktop session: screen + sound -> /rec/raw.mkv, cues ->
  # /rec/cues.tsv, the recording's start time -> /rec/start; then power off.
  record = pkgs.writeShellApplication {
    name = "mos-tour-record";
    runtimeInputs = with pkgs; [
      ffmpeg-full # x11grab and pulse inputs
      pulseaudio # pactl: the sound output to record
      xrandr
      util-linux # flock
      coreutils
      xfconf # the terminal's font
      tmux # where the tour plays, out of sight
      systemd # journalctl: programs stopped for lack of memory
      gnugrep
      mos-tour
    ];
    text = ''
      trap 'sync; systemctl poweroff' EXIT
      # The output disk (the ISO's own fileSystems leave no room for it there).
      for _ in $(seq 30); do [ -e /dev/disk/by-label/MECCOSREC ] && break; sleep 1; done
      sudo mount -o uid="$(id -u)",gid="$(id -g)" /dev/disk/by-label/MECCOSREC /rec
      exec >/rec/record.log 2>&1
      sleep 15 # the desktop settles (panel, notifications)
      xrandr -s 1920x1080 || true
      # Terminals 50% larger than usual (VictorMono 11, shell.nix), easier to read on video.
      xfconf-query -c xfce4-terminal -p /font-name -n -t string -s "VictorMono Nerd Font 16.5"
      # A steady cursor: a blinking one would count as the screen changing,
      # and pauses would not be cut (scripts/mos-tutorial-encode.py).
      xfconf-query -c xfce4-terminal -p /misc-cursor-blinks -n -t bool -s false
      sleep 2
      sink=$(pactl get-default-sink)
      date +%s.%N >/rec/start
      ffmpeg -y -loglevel warning -thread_queue_size 1024 \
        -f x11grab -draw_mouse 1 -framerate 30 -video_size 1920x1080 -i "$DISPLAY" \
        -thread_queue_size 1024 -f pulse -i "$sink.monitor" \
        -c:v libx264 -preset ultrafast -crf 18 -pix_fmt yuv420p -c:a pcm_s16le /rec/raw.mkv &
      ff=$!
      sleep 2
      # Then the lowest priority, so the desktop draws first: otherwise the
      # encoder takes the CPU that software OpenGL needs, and the Video Player
      # shows only black. (Started at normal priority, so the recording begins
      # when /rec/start says; started niced, it began late and every cue with it.)
      # Every thread: on Linux the niceness is each thread's own.
      for t in /proc/"$ff"/task/*; do renice -n 19 -p "''${t##*/}" >/dev/null || true; done
      lock="$XDG_RUNTIME_DIR/mos-tutorial.lock"
      # The tour plays without a window (its words are the subtitles); its
      # previews open windows of their own.
      # Its errors go to tour.err (shown by ./start tutorial-video).
      tmux -L tour -f /dev/null new-session -d -x 100 -y 30 "mos-tour --record /rec/cues.tsv 2>/rec/tour.err"
      # The tour holds its lock while it plays (at most 40 minutes).
      for _ in $(seq 60); do [ -s /rec/cues.tsv ] && break; sleep 1; done
      timeout 2400 flock "$lock" true || echo "tour did not end in time"
      # Programs the kernel stopped for lack of memory, if any.
      journalctl -k -b --no-pager | grep -iE "out of memory|oom-kill" || true
      sleep 2
      kill -INT "$ff"
      wait "$ff" || true
      exec >/dev/null 2>&1 # let go of record.log, so /rec can be unmounted
      sync
      sudo umount /rec
    '';
  };
in
{
  environment.systemPackages = [ mos-tour ];
  # Where the output disk (a FAT image the host made; mtools reads it back) goes.
  systemd.tmpfiles.rules = [ "d /rec 0755 root root -" ];
  environment.etc."xdg/autostart/${distro.id}-tour-record.desktop".text = ''
    [Desktop Entry]
    Type=Application
    Name=Record the tutorial
    NoDisplay=true
    Exec=${record}/bin/mos-tour-record
  '';
}
