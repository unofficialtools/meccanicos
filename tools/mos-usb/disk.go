package main

import "fmt"

// Disk is a whole USB drive.
type Disk struct {
	ID     string // stable while plugged in: sdb, disk4, 2
	Path   string // what to open: /dev/sdb, /dev/disk4, \\.\PhysicalDrive2
	Model  string
	Serial string // the drive's serial number, where the system reports one
	Size   int64
	Ventoy bool     // Ventoy is installed on it
	Parts  []string // its partitions (Linux)
}

// Name is how the drive is always called, so nobody needs to know what
// /dev/sdb means: USB DRIVE (/dev/sdb), USB DRIVE (Disk 2) on Windows.
func (d Disk) Name() string { return "USB DRIVE (" + deviceName(d) + ")" }

func (d Disk) String() string {
	if d.Model == "" {
		return fmt.Sprintf("%s, %s", d.Name(), human(d.Size))
	}
	return fmt.Sprintf("%s: %s, %s", d.Name(), d.Model, human(d.Size))
}

// same: o is the drive d was when the user said YES to erasing it, not
// another drive given its name since (/dev/sdb, Disk 2: the system reuses
// them when a drive is unplugged). The serial number decides where the system
// reports one; the size and model must match too. A drive without a serial
// number (macOS reports none) is told apart by size and model only: an
// identical drive put in its place looks the same.
func (d Disk) same(o Disk) bool {
	return d.ID == o.ID && d.Serial == o.Serial && d.Size == o.Size && d.Model == o.Model
}
