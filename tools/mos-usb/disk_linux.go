package main

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"syscall"
	"time"
)

type lsblkDev struct {
	Name        string          `json:"name"`
	Path        string          `json:"path"`
	Size        json.RawMessage `json:"size"`
	Tran        *string         `json:"tran"`
	RM          json.RawMessage `json:"rm"`
	Model       *string         `json:"model"`
	Type        string          `json:"type"`
	Label       *string         `json:"label"`
	Mountpoints []*string       `json:"mountpoints"`
	Children    []lsblkDev      `json:"children"`
}

// Mount points that mean "this disk runs the computer": never touched.
var systemMounts = map[string]bool{"/": true, "/boot": true, "/boot/efi": true, "/efi": true,
	"/home": true, "/nix": true, "/nix/store": true, "/usr": true, "/var": true, "[SWAP]": true}

func listUSB() ([]Disk, error) {
	out, err := exec.Command("lsblk", "-J", "-b", "-o", "NAME,PATH,SIZE,TRAN,RM,MODEL,TYPE,LABEL,MOUNTPOINTS").Output()
	if err != nil {
		return nil, fmt.Errorf("lsblk: %w", err)
	}
	var data struct {
		Devices []lsblkDev `json:"blockdevices"`
	}
	if err := json.Unmarshal(out, &data); err != nil {
		return nil, fmt.Errorf("lsblk: %w", err)
	}
	var disks []Disk
	for _, d := range data.Devices {
		removable := strings.Trim(string(d.RM), `"`)
		if d.Type != "disk" || !(deref(d.Tran) == "usb" || removable == "true" || removable == "1") {
			continue
		}
		size, _ := strconv.ParseInt(strings.Trim(string(d.Size), `"`), 10, 64)
		if size == 0 || holdsSystem(d) {
			continue
		}
		disk := Disk{ID: d.Name, Path: d.Path, Model: strings.TrimSpace(deref(d.Model)), Size: size}
		for _, c := range d.Children {
			disk.Parts = append(disk.Parts, c.Path)
			if deref(c.Label) == "VTOYEFI" {
				disk.Ventoy = true
			}
		}
		disks = append(disks, disk)
	}
	return disks, nil
}

func holdsSystem(d lsblkDev) bool {
	for _, m := range d.Mountpoints {
		if m != nil && systemMounts[*m] {
			return true
		}
	}
	for _, c := range d.Children {
		if holdsSystem(c) {
			return true
		}
	}
	return false
}

func deref(s *string) string {
	if s == nil {
		return ""
	}
	return *s
}

// mounts lists where the drive's partitions are mounted.
func mounts(d Disk) map[string]string {
	out, err := exec.Command("lsblk", "-J", "-o", "PATH,MOUNTPOINTS", d.Path).Output()
	res := map[string]string{}
	if err != nil {
		return res
	}
	var data struct {
		Devices []lsblkDev `json:"blockdevices"`
	}
	json.Unmarshal(out, &data)
	var walk func(lsblkDev)
	walk = func(x lsblkDev) {
		for _, m := range x.Mountpoints {
			if m != nil && *m != "" {
				res[x.Path] = *m
			}
		}
		for _, c := range x.Children {
			walk(c)
		}
	}
	for _, x := range data.Devices {
		walk(x)
	}
	return res
}

func unmountAll(d Disk) error {
	for dev, mp := range mounts(d) {
		if out, err := exec.Command("umount", mp).CombinedOutput(); err != nil {
			return fmt.Errorf("could not unmount %s (%s): %s", dev, mp, strings.TrimSpace(string(out)))
		}
	}
	return nil
}

func openRaw(d Disk) (*os.File, error) {
	if err := unmountAll(d); err != nil {
		return nil, err
	}
	// O_EXCL: refused if anything still has the drive mounted.
	return os.OpenFile(d.Path, os.O_WRONLY|syscall.O_EXCL, 0)
}

func openRawRead(d Disk) (*os.File, error) { return os.Open(d.Path) }

const blkflsbuf = 0x1261 // BLKFLSBUF: drop the cached copy, so the check reads the drive

func flushDisk(f *os.File) error {
	if err := f.Sync(); err != nil {
		return err
	}
	syscall.Syscall(syscall.SYS_IOCTL, f.Fd(), blkflsbuf, 0)
	return nil
}

func ventoyInstall(dir string, d Disk) error {
	if err := unmountAll(d); err != nil {
		return err
	}
	cmd := exec.Command("sh", "Ventoy2Disk.sh", "-i", "-g", d.Path)
	cmd.Dir = dir
	cmd.Stdin = strings.NewReader("y\ny\ny\n") // Ventoy asks twice; we told the user already
	out, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("%v\n%s", err, tail(string(out), 15))
	}
	exec.Command("partprobe", d.Path).Run()
	exec.Command("udevadm", "settle").Run()
	for i := 0; i < 15; i++ {
		if d2, ok := find(d.ID); ok && d2.Ventoy {
			return nil
		}
		time.Sleep(time.Second)
	}
	return fmt.Errorf("Ventoy did not install:\n%s", tail(string(out), 15))
}

// dataMount mounts Ventoy's first partition (where ISOs go); release unmounts
// it again if this program mounted it.
func dataMount(d Disk) (string, func(), error) {
	d2, ok := find(d.ID)
	if !ok || len(d2.Parts) == 0 {
		return "", nil, fmt.Errorf("the drive or its partition is gone")
	}
	part := d2.Parts[0]
	if mp, ok := mounts(d2)[part]; ok {
		return mp, func() { exec.Command("sync").Run() }, nil
	}
	dir, err := os.MkdirTemp("", "mos-usb-")
	if err != nil {
		return "", nil, err
	}
	if out, err := exec.Command("mount", part, dir).CombinedOutput(); err != nil {
		os.Remove(dir)
		return "", nil, fmt.Errorf("mount %s: %s", part, strings.TrimSpace(string(out)))
	}
	return dir, func() {
		exec.Command("sync").Run()
		exec.Command("umount", dir).Run()
		os.Remove(dir)
	}, nil
}

func finish(d Disk) {
	exec.Command("sync").Run()
	unmountAll(d)
	// Switch the drive off where udisks is around; pulling it out is safe either way now.
	exec.Command("udisksctl", "power-off", "-b", d.Path, "--no-user-interaction").Run()
}

func tail(s string, n int) string {
	lines := strings.Split(strings.TrimSpace(s), "\n")
	if len(lines) > n {
		lines = lines[len(lines)-n:]
	}
	return strings.Join(lines, "\n")
}

// freeSpace is how many bytes can still be written in the folder dir.
func freeSpace(dir string) (int64, error) {
	var st syscall.Statfs_t
	if err := syscall.Statfs(dir, &st); err != nil {
		return 0, err
	}
	return int64(st.Bavail) * int64(st.Bsize), nil
}

func deviceName(d Disk) string { return d.Path }
