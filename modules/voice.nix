# Offline text-to-speech: Piper with the en_US "Amy" voice (medium quality).
#
#   say "Hello there"               speak through the speakers
#   echo "Hello" | say               ...or from a pipe
#   piper -m "$PIPER_VOICE" -f out.wav <<< "Hello"   save to a WAV file
#   mos-read                       read the clipboard aloud in a small TUI
#                                    (command bar: "Read Clipboard Aloud")
{ pkgs, ... }:
let
  inherit (import ./not-root.nix) notRoot;
  # Speech only: nixpkgs' default also bundles voice *training* (PyTorch,
  # ~1.5 GB), an HTTP server and alignment tools.
  piper = pkgs.piper-tts.override {
    withTrain = false;
    withHTTP = false;
    withAlignment = false;
  };

  # Pinned to the v1.0.0 release of rhasspy/piper-voices (~63 MB).
  voiceBase = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/amy/medium";
  amy = pkgs.runCommand "piper-voice-en_US-amy-medium" { } ''
    mkdir -p $out/share/piper/voices
    ln -s ${
      pkgs.fetchurl {
        url = "${voiceBase}/en_US-amy-medium.onnx";
        hash = "sha256-s6bke1e4x/vmoM4lGBYaUPWanN2KUINcAssCvdYgbBg=";
      }
    } $out/share/piper/voices/en_US-amy-medium.onnx
    ln -s ${
      pkgs.fetchurl {
        url = "${voiceBase}/en_US-amy-medium.onnx.json";
        hash = "sha256-laI+tNQpCdON9zu5rH9F9Zfb/N4tG/lSb96vVGaXfXc=";
      }
    } $out/share/piper/voices/en_US-amy-medium.onnx.json
  '';
  voice = "${amy}/share/piper/voices/en_US-amy-medium.onnx";

  # One voice at a time: say and mos-read take this lock while they speak,
  # so a second one waits instead of talking over the first.
  speechLock = "\${XDG_RUNTIME_DIR:-/tmp}/mos-speech.lock";
  say = pkgs.writeShellScriptBin "say" ''
    ${notRoot "say"}
    # say "text"  or  echo text | say   (Amy speaks at 22050 Hz, 16-bit mono)
    # A bit faster than Piper's pace: SAY_LENGTH_SCALE=1 for the original.
    # Speaking right after another line (the tutorial): say --to FILE "text"
    # makes the audio ahead of time, say --play FILE speaks it once it's there.
    synth() {
      # Words Piper says wrong, spelled as they sound (as in mos-read).
      printf '%s\n' "$1" | ${pkgs.gnused}/bin/sed -E 's/\b[Nn]ixpkgs\b/nix packages/g; s/\bMeccanicOS\b/Meccanic O S/g' |
        ${piper}/bin/piper -m "''${PIPER_VOICE:-${voice}}" --length-scale "''${SAY_LENGTH_SCALE:-0.8}" --output-raw 2>/dev/null
    }
    play() {
      exec 9>"${speechLock}"
      ${pkgs.util-linux}/bin/flock 9
      ${pkgs.pipewire}/bin/pw-play --raw --rate 22050 --channels 1 --format s16 -
    }
    case ''${1:-} in
      -h | --help)
        echo "say - speak text aloud (Amy, offline)"
        echo
        echo "  say TEXT...           speak TEXT"
        echo "  echo TEXT | say       speak what comes in"
        echo "  say --to FILE TEXT    make the audio into FILE (to speak later)"
        echo "  say --play FILE       speak FILE once it exists"
        echo "SAY_LENGTH_SCALE=1 for Piper's own (slower) pace."
        exit 0 ;;
      --to | --play)
        [ "$#" -ge 2 ] || { echo "say: $1 needs a FILE (say --help)" >&2; exit 2; } ;;
    esac
    case ''${1:-} in
      --to)
        out=$2
        shift 2
        synth "$*" >"$out.part" && mv "$out.part" "$out"
        exit ;;
      --play)
        for _ in $(seq 600); do [ -e "$2" ] && break; sleep 0.1; done
        play <"$2"
        exit ;;
    esac
    if [ "$#" -gt 0 ]; then text="$*"; else text=$(cat); fi
    synth "$text" | play
  '';

  # Clipboard reader TUI (scripts/mos-read.py): pause, skip, speed, stop.
  pythonWithPiper = pkgs.python3.withPackages (ps: [ (ps.toPythonModule piper) ]);
  mos-read = pkgs.writeShellScriptBin "mos-read" ''
    ${notRoot "mos-read"}
    export MECCANICOS_PYLIB=${../scripts/lib}
    export MECCANICOS_READ_VOICE=${voice}
    export MECCANICOS_READ_PWPLAY=${pkgs.pipewire}/bin/pw-play
    export MECCANICOS_READ_XCLIP=${pkgs.xclip}/bin/xclip
    export MECCANICOS_SPEECH_LOCK="${speechLock}"
    exec ${pythonWithPiper}/bin/python3 ${../scripts/mos-read.py} "$@"
  '';
  readLauncher = pkgs.makeDesktopItem {
    name = "mos-read";
    desktopName = "Read Clipboard Aloud (Piper)";
    comment = "Read the copied text aloud (offline voice); Space pauses, q stops";
    exec = "xfce4-terminal --class mos-read --title \"Read from clipboard\" --geometry 84x22 -x mos-read";
    icon = "audio-volume-high";
    keywords = [
      "speak"
      "say"
      "tts"
      "voice"
      "read aloud"
    ];
    categories = [
      "Utility"
      "Accessibility"
    ];
  };
in
{
  environment.systemPackages = [
    piper
    amy
    say
    mos-read
    readLauncher
  ];
  environment.sessionVariables.PIPER_VOICE = voice;
}
