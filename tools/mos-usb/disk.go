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

func (d Disk) String() string {
	model := d.Model
	if model == "" {
		model = "USB drive"
	}
	return fmt.Sprintf("%s (%s, %s)", d.Path, model, human(d.Size))
}
