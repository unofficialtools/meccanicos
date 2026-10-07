# AI chat, shipped without any model: Ollama and the aichat client.
# The Ollama service is installed but not started at boot. One command sets
# everything up (needs network once):
#
#   mos-ai-setup                  # local: downloads qwen3:4b, configures aichat
#   mos-ai-setup claude           # or claude / chatgpt / grok with an API key
#   mos-ai-setup status           # what is set up, where questions go, the models
#   mos-ai-setup remove MODEL     # delete a downloaded model
#
# Then "AI Chat" in the command bar (or `mos-ai`) starts a chat, and
# "?question" in the command bar asks one question. Both start Ollama when
# needed (polkit lets the desktop user start it without a password).
{
  config,
  lib,
  pkgs,
  distro,
  ...
}:
let
  inherit (import ./not-root.nix) notRoot;
  defaultModel = "qwen3:4b"; # ~2.5 GB; smaller: qwen3:1.7b
  modelsDir = config.services.ollama.models; # /var/lib/ollama/models (the service's own)

  # Start Ollama if it isn't running, and wait until it answers.
  startOllama = ''
    if ! ollama list >/dev/null 2>&1; then
      systemctl start ollama.service || { echo "Could not start Ollama." >&2; exit 1; }
      for _ in $(seq 50); do
        ollama list >/dev/null 2>&1 && break
        sleep 0.2
      done
    fi
  '';

  # mos-ai-setup [local|claude|chatgpt|grok] [MODEL]
  # Writes ~/.config/aichat/config.yaml with every AI set up so far (API keys
  # are kept in ~/.config/meccanicos/ai, readable only by you); the last one set up
  # is the default. In a chat, `.model` switches between them.
  # mos-ai-setup status: that, where questions go, and the downloaded models
  # (never the keys); mos-ai-setup remove MODEL deletes one, after asking.
  mos-ai-setup = pkgs.writeShellApplication {
    name = "mos-ai-setup";
    runtimeInputs = [
      pkgs.ollama
      pkgs.systemd
      pkgs.coreutils # also du, df, numfmt (status)
      pkgs.gnugrep
      pkgs.gnused
      pkgs.gawk
    ];
    text = notRoot "mos-ai-setup" + ''
      dir="''${XDG_CONFIG_HOME:-$HOME/.config}/meccanicos/ai"
      conf="''${XDG_CONFIG_HOME:-$HOME/.config}/aichat/config.yaml"

      aichat_name() { case $1 in local) echo ollama ;; *) echo "$1" ;; esac; }

      # Ollama answers only while its service runs (started on demand, as mos-ai does).
      # ollama_down puts it back as it was: looking must not leave it running.
      started=0
      ollama_up() {
        ollama list >/dev/null 2>&1 && return 0
        systemctl start --no-ask-password ollama.service 2>/dev/null || return 1
        started=1
        for _ in $(seq 50); do
          ollama list >/dev/null 2>&1 && return 0
          sleep 0.2
        done
        return 1
      }

      ollama_down() {
        if [ "$started" = 1 ]; then systemctl stop --no-ask-password ollama.service 2>/dev/null || true; fi
      }

      status() {
        local p m where key envkey default=""
        if [ -e "$conf" ] && grep -q '^# Written by mos-ai-setup' "$conf"; then
          default=$(sed -n 's/^model: *//p' "$conf" | head -n1)
        elif [ -e "$conf" ]; then
          echo "AI Chat uses your own $conf (model: $(sed -n 's/^model: *//p' "$conf" | head -n1))."
        fi
        echo "Set up (the default is what AI Chat and ?question use; .model in a chat switches):"
        found=0
        for p in local claude chatgpt grok; do
          [ -s "$dir/$p.model" ] || continue
          found=1
          m=$(cat "$dir/$p.model")
          case $p in
            local)   where="stays on this computer (Ollama, offline)"; envkey="" ;;
            claude)  where="sent to Anthropic's servers (Claude)"; envkey=ANTHROPIC_API_KEY ;;
            chatgpt) where="sent to OpenAI's servers (ChatGPT)"; envkey=OPENAI_API_KEY ;;
            grok)    where="sent to xAI's servers (Grok)"; envkey=XAI_API_KEY ;;
          esac
          key=""
          if [ -n "$envkey" ]; then
            # Never the key itself: only whether there is one.
            if [ -s "$dir/$p.key" ]; then key="; API key set"; else key="; no API key"; fi
          fi
          if [ "$default" = "$(aichat_name "$p"):$m" ]; then p="$p (default)"; fi
          printf '  %-17s %-18s %s%s\n' "$p" "$m" "$where" "$key"
        done
        [ "$found" = 1 ] || echo "  nothing yet: mos-ai-setup (local, private) or mos-ai-setup claude|chatgpt|grok"

        echo
        echo "Downloaded models (Ollama, in ${modelsDir}):"
        if ollama_up; then
          list=$(ollama list 2>/dev/null | tail -n +2 || true)
          if [ -n "$list" ]; then
            printf '%s\n' "$list" | awk '{printf "  %-30s %s %s\n", $1, $3, $4}'
          else
            echo "  none (mos-ai-setup downloads ${defaultModel})"
          fi
        else
          echo "  (Ollama is not running and could not be started here; mos-ai starts it)"
          list=""
        fi
        ollama_down
        # The folder belongs to the service: du as you, else with sudo (no password asked).
        used=$(du -sb ${modelsDir} 2>/dev/null || sudo -n du -sb ${modelsDir} 2>/dev/null || true)
        used=''${used%%[[:space:]]*}
        if [ -n "$used" ]; then
          echo "  disk used: $(numfmt --to=iec-i --suffix=B --format=%.1f "$used")"
        fi
        if [ "$(df --output=fstype /var/lib 2>/dev/null | tail -n1)" = tmpfs ]; then
          echo "  This is the live USB: that folder is in memory (it uses RAM), and the models"
          echo "  are gone when the computer restarts, persistent home or not: download again"
          echo "  after a restart (mos-ai-setup), or install ${distro.name} to keep them."
        else
          echo "  Kept on disk: they stay after a restart."
        fi
        echo
        echo "Change: mos-ai-setup [local|claude|chatgpt|grok] [MODEL]; delete a model: mos-ai-setup remove MODEL"
      }

      remove() {
        local m=$1 have
        trap ollama_down EXIT
        ollama_up || { echo "Could not start Ollama." >&2; exit 1; }
        [[ $m == *:* ]] || m="$m:latest"
        have=$(ollama list 2>/dev/null | awk -v m="$m" 'NR > 1 && $1 == m {print $3 " " $4}' || true)
        if [ -z "$have" ]; then
          echo "mos-ai-setup: no model $1 here (mos-ai-setup status lists them)" >&2
          exit 1
        fi
        read -r -p "Delete $m ($have)? It can be downloaded again later. [y/N] " ans || ans=""
        case $ans in
          y | Y | yes) ;;
          *) echo "Kept."; exit 0 ;;
        esac
        ollama rm "$m"
        if [ "$(cat "$dir/local.model" 2>/dev/null || true)" = "$m" ] || [ "$(cat "$dir/local.model" 2>/dev/null || true):latest" = "$m" ]; then
          rm -f "$dir/local.model"
          echo "It was the local AI: run mos-ai-setup again to download one (or use claude|chatgpt|grok)."
        fi
      }

      provider=''${1:-local}
      case $provider in
        status)
          status
          exit 0 ;;
        remove | rm)
          [ $# -eq 2 ] || { echo "Usage: mos-ai-setup remove MODEL (mos-ai-setup status lists them)" >&2; exit 2; }
          remove "$2"
          exit 0 ;;
        local)   model=''${2:-${defaultModel}} ;;
        claude)  model=''${2:-claude-opus-5-5};  envkey=ANTHROPIC_API_KEY; site=https://console.anthropic.com/settings/keys ;;
        chatgpt) model=''${2:-gpt-5};            envkey=OPENAI_API_KEY;    site=https://platform.openai.com/api-keys ;;
        grok)    model=''${2:-grok-4};           envkey=XAI_API_KEY;       site=https://console.x.ai ;;
        -h|--help|help)
          echo "mos-ai-setup - set up an AI for AI Chat (mos-ai)"
          echo
          echo "Usage: mos-ai-setup [local|claude|chatgpt|grok] [MODEL]"
          echo "  local    (default) download ${defaultModel} for Ollama: free, offline, private"
          echo "  claude   Anthropic's Claude (API key, paid; default model claude-opus-5-5)"
          echo "  chatgpt  OpenAI's ChatGPT (API key, paid; default model gpt-5)"
          echo "  grok     xAI's Grok (API key, paid; default model grok-4)"
          echo
          echo "  mos-ai-setup status        what is set up, where your questions go, the downloaded models"
          echo "  mos-ai-setup remove MODEL  delete a downloaded model (asks first)"
          exit 0 ;;
        *)
          echo "mos-ai-setup: unknown AI '$provider' (mos-ai-setup --help)" >&2
          exit 2 ;;
      esac

      mkdir -p "$dir" "$(dirname "$conf")"
      chmod 700 "$dir"

      if [ "$provider" = local ]; then
        ${startOllama}
        echo "Downloading $model (a few GB; only the first time)..."
        ollama pull "$model"
      else
        key=''${!envkey:-}
        if [ -z "$key" ] && [ -s "$dir/$provider.key" ]; then
          key=$(cat "$dir/$provider.key")
          echo "Using your saved $provider API key."
        fi
        if [ -z "$key" ]; then
          echo "Paste your $provider API key (from $site); it won't be shown:"
          read -rs key
          echo
        fi
        [ -n "$key" ] || { echo "No key given." >&2; exit 1; }
        (umask 077; printf '%s\n' "$key" >"$dir/$provider.key")
      fi
      echo "$model" >"$dir/$provider.model"

      # Keep a config.yaml that you wrote yourself.
      if [ -e "$conf" ] && ! grep -q '^# Written by mos-ai-setup' "$conf"; then
        mv "$conf" "$conf.bak"
        echo "Your old $conf is now $conf.bak"
      fi
      {
        echo "# Written by mos-ai-setup; run it again to change. Switch in a chat with .model"
        echo "model: $(aichat_name "$provider"):$model"
        echo "clients:"
        for p in local claude chatgpt grok; do
          [ -s "$dir/$p.model" ] || continue
          m=$(cat "$dir/$p.model")
          k=$(cat "$dir/$p.key" 2>/dev/null || true)
          case $p in
            local)   printf '  - type: openai-compatible\n    name: ollama\n    api_base: http://localhost:11434/v1\n' ;;
            claude)  printf '  - type: claude\n    name: claude\n    api_key: %s\n' "$k" ;;
            chatgpt) printf '  - type: openai\n    name: chatgpt\n    api_key: %s\n' "$k" ;;
            grok)    printf '  - type: openai-compatible\n    name: grok\n    api_base: https://api.x.ai/v1\n    api_key: %s\n' "$k" ;;
          esac
          printf '    models:\n      - name: %s\n' "$m"
          # Anthropic's API needs max_tokens on every request.
          [ "$p" = claude ] && printf '        max_output_tokens: 16000\n        require_max_tokens: true\n'
        done
      } >"$conf.new"
      chmod 600 "$conf.new"
      mv "$conf.new" "$conf"
      echo "Ready ($provider, $model): \"AI Chat\" in the command bar (Super+Space), or type ?question there."
    '';
  };

  # Chat (no arguments) or answer one question (arguments).
  mos-ai = pkgs.writeShellApplication {
    name = "mos-ai";
    runtimeInputs = [
      pkgs.ollama
      pkgs.systemd
      pkgs.coreutils
      pkgs.aichat
    ];
    text = notRoot "mos-ai" + ''
      conf="''${XDG_CONFIG_HOME:-$HOME/.config}/aichat/config.yaml"
      if [ ! -e "$conf" ]; then
        echo "No AI set up yet. Run once (needs network): mos-ai-setup"
        echo "(or mos-ai-setup claude|chatgpt|grok to use one of those with an API key)"
        exit 1
      fi
      # Ollama only matters when a local model is configured.
      if grep -q 'name: ollama' "$conf"; then
        ${startOllama}
      fi
      exec aichat "$@"
    '';
  };

  chatLauncher = pkgs.makeDesktopItem {
    name = "mos-ai";
    desktopName = "AI Chat (aichat)";
    comment = "Chat with the local AI (Ollama, offline); set up with mos-ai-setup";
    icon = "user-available";
    exec = "xfce4-terminal --class mos-ai --title \"AI Chat\" --hold -x mos-ai";
    categories = [ "Utility" ];
  };
in
{
  services.ollama.enable = true; # loadModels = [ ] by default: nothing is downloaded
  systemd.services.ollama.wantedBy = lib.mkForce [ ]; # don't start at boot

  # The person at the computer may start Ollama (mos-ai, the command bar).
  security.polkit.extraConfig = ''
    polkit.addRule(function(action, subject) {
      if (action.id == "org.freedesktop.systemd1.manage-units" &&
          action.lookup("unit") == "ollama.service" &&
          action.lookup("verb") == "start" &&
          subject.local && subject.active) {
        return polkit.Result.YES;
      }
    });
  '';

  environment.systemPackages = [
    pkgs.aichat
    mos-ai-setup
    mos-ai
    chatLauncher
  ];
}
