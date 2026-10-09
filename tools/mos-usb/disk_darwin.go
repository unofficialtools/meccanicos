package main

import (
	"fmt"
	"os"
	"os/exec"
	"strings"
)

// listUSB: external physical disks (diskutil), USB or removable.
func listUSB() ([]Disk, error) {
	out, err := exec.Command("diskutil", "list", "-plist", "external", "physical").Output()
	if err != nil {
		return nil, fmt.Errorf("diskutil list: %w", err)
	}
	top, err := parsePlist(out)
	if err != nil {
		return nil, err
	}
	var disks []Disk
	whole, _ := top.(map[string]any)["WholeDisks"].([]any)
	for _, w := range whole {
		name, _ := w.(string)
		if name == "" {
			continue
		}
		info, err := exec.Command("diskutil", "info", "-plist", name).Output()
		if err != nil {
			continue
		}
		v, err := parsePlist(info)
		if err != nil {
			continue
		}
		m, _ := v.(map[string]any)
		internal, _ := m["Internal"].(bool)
		bus, _ := m["BusProtocol"].(string)
		removable, _ := m["RemovableMediaOrExternalDevice"].(bool)
		if internal || !(bus == "USB" || removable) {
			continue
		}
		size, _ := m["TotalSize"].(int64)
		if size == 0 {
			size, _ = m["Size"].(int64)
		}
		model, _ := m["MediaName"].(string)
		disks = append(disks, Disk{ID: name, Path: "/dev/" + name, Model: strings.TrimSpace(model), Size: size})
	}
	return disks, nil
}

func unmountDisk(d Disk) error {
	if out, err := exec.Command("diskutil", "unmountDisk", "force", d.Path).CombinedOutput(); err != nil {
		return fmt.Errorf("could not unmount %s: %s", d.Path, strings.TrimSpace(string(out)))
	}
	return nil
}

// The raw device (/dev/rdiskN) skips the cache: much faster, and the check
// reads what is really on the drive.
func rawPath(d Disk) string { return "/dev/r" + strings.TrimPrefix(d.Path, "/dev/") }

func openRaw(d Disk) (*os.File, error) {
	if err := unmountDisk(d); err != nil {
		return nil, err
	}
	return os.OpenFile(rawPath(d), os.O_WRONLY, 0)
}

func openRawRead(d Disk) (*os.File, error) { return os.Open(rawPath(d)) }

func flushDisk(f *os.File) error { return f.Sync() }

func ventoyInstall(string, Disk) error       { return errUnsupported }
func dataMount(Disk) (string, func(), error) { return "", nil, errUnsupported }
func finish(d Disk)                          { exec.Command("diskutil", "eject", d.Path).Run() }
func freeSpace(string) (int64, error)        { return 0, errUnsupported }
func deviceName(d Disk) string               { return d.Path }
