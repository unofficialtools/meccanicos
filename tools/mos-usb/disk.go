package main

import "fmt"

// Disk is a whole USB drive.
type Disk struct {
	ID     string // stable while plugged in: sdb, disk4, 2
	Path   string // what to open: /dev/sdb, /dev/disk4, \\.\PhysicalDrive2
	Model  string
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
