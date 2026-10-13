import React from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { C, MONO, SANS } from "../theme";

// One page, the top-level folders: what each is for, and a file in it.
const FOLDERS: [string, string, string][] = [
  ["/boot", "starting the computer: the kernel, the boot menu", "/boot/loader/loader.conf"],
  ["/dev", "devices as files: disks, USB sticks, the terminal", "/dev/nvme0n1, /dev/null"],
  ["/etc", "the system's settings, as text files", "/etc/hostname, /etc/os-release"],
  ["/home", "one folder per person: your files live here", "/home/student/notes.txt"],
  ["/nix", "MeccanicOS/NixOS: every program, each version apart", "/nix/store/…-bash-5.3/bin/bash"],
  ["/proc", "live view of running programs (not on the disk)", "/proc/cpuinfo, /proc/1234/status"],
  ["/root", "the administrator's own home", "/root/.bashrc"],
  ["/run", "runtime state, emptied at every start", "/run/current-system"],
  ["/sys", "the kernel's knobs and hardware details", "/sys/class/power_supply/BAT0"],
  ["/tmp", "scratch space, emptied at every start", "/tmp/download.part"],
  ["/usr, /bin", "programs on other Linuxes; tiny here", "/usr/bin/env, /bin/sh"],
  ["/var", "data that grows: logs, caches, databases", "/var/log/, /var/lib/"],
  ["/mnt, /media", "where extra disks get attached", "/run/media/student/USB"],
];

export const Folders: React.FC = () => {
  const f = useCurrentFrame();
  const { durationInFrames: D } = useVideoConfig();
  return (
    <div style={{ position: "absolute", left: 90, right: 90, top: 6, display: "grid", gridTemplateColumns: "1fr 1fr", columnGap: 40, rowGap: 9 }}>
      {FOLDERS.map(([dir, what, ex], i) => {
        const o = interpolate(f, [(i / FOLDERS.length) * D * 0.7, (i / FOLDERS.length) * D * 0.7 + 10], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
        return (
          <div key={dir} style={{ opacity: o, background: C.base, borderLeft: `5px solid ${dir === "/home" ? C.amber : C.line}`, padding: "7px 18px", height: 96, boxSizing: "border-box" }}>
            <div style={{ display: "flex", gap: 18, alignItems: "baseline" }}>
              <span style={{ fontFamily: MONO, fontSize: 28, color: C.amber, fontWeight: 700, minWidth: 215 }}>{dir}</span>
              <span style={{ fontFamily: SANS, fontSize: 25, color: C.text }}>{what}</span>
            </div>
            <div style={{ fontFamily: MONO, fontSize: 21, color: C.dim, marginTop: 6, marginLeft: 233 }}>{ex}</div>
          </div>
        );
      })}
    </div>
  );
};

// The last page: everything on one sheet.
const SHEET: [string, [string, string][]][] = [
  ["Move around", [["pwd", "where am I"], ["ls -la", "what's here"], ["cd DIR / cd .. / cd ~", "go"], ["yazi", "browse"]]],
  ["Files", [["mkdir, touch, cp, mv", "make, copy, move"], ["rm, rm -r", "delete (no undo!)"], ["trash, trash-restore", "delete, undo"], ["jed, open, codium", "edit, open"], ["print, print --pdf", "print, PDF"]]],
  ["Help", [["Tab, ↑, Ctrl+R", "complete, recall"], ["Ctrl+C", "stop"], ["tldr, --help, man", "how to use"]]],
  ["Plumbing", [["a | b", "a's output into b"], ["> file, >> file", "save, append"], ["grep, wc, sort, less", "filter, count"]]],
  ["Permissions", [["ls -l", "rwx: who may"], ["chmod +x", "make runnable"], ["sudo", "as administrator"]]],
  ["Environment", [["echo $PATH", "where programs are"], ["which", "which one runs"], ["~/.bashrc", "aliases, exports"]]],
  ["Processes", [["ps aux, pgrep, btop", "what runs"], ["kill PID, pkill", "stop it"], ["ps -o rss, free -h", "memory"]]],
  ["Network", [["ip -br addr", "my addresses"], ["ping, curl", "reach out"], ["sudo ss -tulpn", "ports, programs"]]],
  ["System", [["mos", "MeccanicOS commands"], ["mos-config, mos-doctor", "settings, fixes"], ["nix-shell -p gcc", "borrow a program"], ["mos-apps install", "keep a program"]]],
  ["Disks", [["lsblk, df -h", "disks, free space"], ["du -sh, ncdu", "what's big"], ["udisksctl", "mount, unmount"]]],
];

export const Sheet: React.FC = () => (
  <div style={{ position: "absolute", left: 70, right: 70, top: 0, display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 16 }}>
    {SHEET.map(([title, rows]) => (
      <div key={title} style={{ background: C.base, borderTop: `4px solid ${C.amber}`, padding: "10px 14px", height: 360, boxSizing: "border-box" }}>
        <div style={{ fontFamily: MONO, color: C.amber, fontSize: 24, fontWeight: 700, marginBottom: 8 }}>{title}</div>
        {rows.map(([cmd, what]) => (
          <div key={cmd} style={{ marginBottom: 10 }}>
            <div style={{ fontFamily: MONO, fontSize: 21, color: C.text }}>{cmd}</div>
            <div style={{ fontFamily: SANS, fontSize: 19, color: C.dim }}>{what}</div>
          </div>
        ))}
      </div>
    ))}
  </div>
);
