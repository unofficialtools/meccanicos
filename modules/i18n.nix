# Translations of the mos-* tools: i18n/ (languages.json and one file per
# language) in /etc/meccanicos/i18n, where scripts/lib/mos_i18n.py and
# mos_i18n.sh look for them. A fixed path: root tools (mos-install) and
# programs started without the session's environment find it too.
{ ... }:
{
  environment.etc."meccanicos/i18n".source = ../i18n;
}
