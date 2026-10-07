package main

import (
	"os/exec"
	"testing"
)

// listUSB only reads (lsblk): safe to run anywhere; it must never list the
// disk the system runs from.
func TestListUSB(t *testing.T) {
	if _, err := exec.LookPath("lsblk"); err != nil {
		t.Skip("no lsblk")
	}
	disks, err := listUSB()
	if err != nil {
		t.Fatal(err)
	}
	for _, d := range disks {
		t.Logf("USB drive: %s ventoy=%v parts=%v", d, d.Ventoy, d.Parts)
		if d.Path == "" || d.Size == 0 {
			t.Errorf("incomplete: %+v", d)
		}
	}
}
