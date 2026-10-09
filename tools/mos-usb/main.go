// mos-usb: makes a MeccanicOS USB stick on Linux, Windows or macOS.
//
// It downloads the latest MeccanicOS ISO (checked against SHA256SUMS), waits
// for a USB drive to be plugged in, and puts the ISO on it: with Ventoy when
// the computer can run Ventoy (Linux, Windows), so the stick keeps room for
// other ISOs and files; written directly otherwise (macOS). Before erasing a
// drive it shows a big red warning naming it, and goes on only if the user
// types YES. A drive that already has Ventoy is not erased.
//
// Environment, for testing: MOS_USB_RELEASE (where SHA256SUMS and the parts
// are; default the "latest" GitHub release), MOS_USB_CACHE (download folder).
package main

import (
	"errors"
	"fmt"
	"os"
	"runtime"
	"time"
)

const (
	defaultRelease = "https://github.com/unofficialtools/meccanicos/releases/download/latest"
)

func main() {
	err := run()
	if err != nil {
		fail("%v", err)
	}
	if pauseAtEnd() {
		fmt.Println("\nPress Enter to close this window.")
		stdin.ReadString('\n')
	}
	if err != nil {
		os.Exit(1)
	}
}

func run() error {
	title("MeccanicOS USB maker")
	if err := ensureAdmin(); err != nil {
		return err
	}
	cache, err := cacheDir()
	if err != nil {
		return err
	}

	iso, err := fetchISO(cache)
	if err != nil {
		return err
	}

	ventoy := ""
	if runtime.GOOS == "darwin" {
		note("Ventoy is not available on macOS: falling back to writing the ISO directly to the USB drive.")
	} else if ventoy, err = fetchVentoy(cache); err != nil {
		warn("Could not get Ventoy (%v): falling back to writing the ISO directly to the USB drive.", err)
		ventoy = ""
	}

	need := iso.Size + 64<<20 // Ventoy's own partition and some room
	for {
		d, err := waitForDisk(need)
		if err != nil {
			return err
		}
		if ventoy != "" && d.Ventoy {
			step("Ventoy is already on %s: adding the ISO, nothing else on the drive is erased.", d)
			if err := copyToVentoy(iso, d); err != nil {
				return err
			}
		} else {
			if !confirmErase(d) {
				note("Cancelled: nothing was written to %s.", d.Name())
				note("To use another drive, insert it now; or close this window.")
				continue // wait for another drive
			}
			if _, ok := find(d.ID); !ok {
				return fmt.Errorf("%s was removed: nothing was written", d.Name())
			}
			if ventoy != "" {
				err = installVentoy(ventoy, d)
				if err == nil {
					err = copyToVentoy(iso, d)
				}
			} else {
				err = writeRaw(iso, d)
			}
			if err != nil {
				return err
			}
		}
		finish(d)
		done("Done. The USB drive is ready: you can remove it now.")
		printBootGuide(ventoy != "")
		return nil
	}
}

// waitForDisk returns the first USB drive plugged in after the call; drives
// already plugged in are left alone (unless unplugged and plugged in again).
func waitForDisk(need int64) (Disk, error) {
	ignore := map[string]bool{}
	disks, err := listUSB()
	if err != nil {
		return Disk{}, err
	}
	for _, d := range disks {
		ignore[d.ID] = true
	}
	if len(disks) > 0 {
		note("USB drives already connected are left alone: %s.", diskNames(disks))
	}
	step("Insert the USB drive to use for MeccanicOS (at least %s; everything on it may be erased).", human(need))
	if len(disks) > 0 {
		fmt.Println("  If it is already plugged in, unplug it and plug it in again.")
	}
	for {
		time.Sleep(time.Second)
		disks, err := listUSB()
		if err != nil {
			return Disk{}, err
		}
		present := map[string]bool{}
		for _, d := range disks {
			present[d.ID] = true
		}
		for id := range ignore {
			if !present[id] {
				delete(ignore, id) // unplugged: plugging it in again counts
			}
		}
		for _, d := range disks {
			if ignore[d.ID] {
				continue
			}
			time.Sleep(2 * time.Second) // let the system read its partitions
			if d2, ok := find(d.ID); ok {
				d = d2
			}
			if d.Size < need {
				warn("%s is too small (%s). Remove it and insert a drive of at least %s.", d, human(d.Size), human(need))
				ignore[d.ID] = true
				continue
			}
			step("Found %s.", d)
			return d, nil
		}
	}
}

func find(id string) (Disk, bool) {
	disks, err := listUSB()
	if err != nil {
		return Disk{}, false
	}
	for _, d := range disks {
		if d.ID == id {
			return d, true
		}
	}
	return Disk{}, false
}

var errUnsupported = errors.New("not supported on " + runtime.GOOS)
