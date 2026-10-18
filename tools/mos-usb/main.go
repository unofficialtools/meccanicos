// mos-usb: makes a MeccanicOS USB stick on Linux, Windows or macOS.
//
// It downloads the latest MeccanicOS ISO (checked against SHA256SUMS), waits
// for a USB drive to be plugged in, and puts the ISO on it: with Ventoy when
// the computer can run Ventoy (Linux, Windows), so the stick keeps room for
// other ISOs and files; written directly otherwise (macOS). Before erasing a
// drive it shows a big red warning naming it, and goes on only if the user
// types YES. A drive that already has Ventoy is not erased.
//
// The downloads are done as the user; only then does it ask for administrator
// rights, and the part run as administrator writes nothing in the download
// folder (it checks the downloads again and runs Ventoy from a private copy).
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
	elevatedFlag   = "--elevated" // this process was started by elevate
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

// ventoyRuns: Ventoy can be installed, and ISOs copied onto a Ventoy drive.
const ventoyRuns = runtime.GOOS != "darwin"

func run() error {
	title("MeccanicOS USB maker")
	handedOver := elevatedRun() // first: on Windows it also reads the arguments
	admin := isAdmin()
	if handedOver && !admin {
		return fmt.Errorf("administrator rights were not given")
	}
	cache, err := cacheDir()
	if err != nil {
		return err
	}
	download := func() (ISO, error) {
		iso, err := fetchISO(cache)
		if err == nil && ventoyRuns {
			if err := downloadVentoy(cache); err != nil {
				warn("Could not download Ventoy (%v).", err)
			}
		}
		return iso, err
	}
	if !admin {
		// Downloading needs no special rights, so it is done first, as you.
		// The part run as administrator writes nothing in the download
		// folder: it checks the downloads again, keeps the ISO open, and
		// runs Ventoy from a private copy.
		if _, err := download(); err != nil {
			return err
		}
		return elevate()
	}
	var iso ISO
	if handedOver {
		iso, err = checkISO(cache)
	} else {
		iso, err = download() // started as administrator: nothing was downloaded yet
	}
	if err != nil {
		return err
	}
	if !ventoyRuns {
		note("Ventoy is not available on macOS: the ISO is written directly to the USB drive.")
	}

	// Ventoy is unpacked only for a drive that needs it installed: adding the
	// ISO to a drive that has Ventoy already does not.
	var ventoyDir string
	var ventoyErr error
	ventoyTried, ventoyCleanup := false, func() {}
	defer func() { ventoyCleanup() }()
	ventoy := func() (string, error) {
		if !ventoyTried {
			ventoyTried = true
			if ventoyDir, ventoyCleanup, ventoyErr = prepareVentoy(cache); ventoyErr != nil {
				ventoyCleanup = func() {}
			}
		}
		return ventoyDir, ventoyErr
	}

	need := iso.Size + 64<<20 // Ventoy's own partition and some room
	for {
		d, err := waitForDisk(need)
		if err != nil {
			return err
		}
		usedVentoy := ventoyRuns && d.Ventoy
		if usedVentoy {
			step("Ventoy is already on %s: adding the ISO, nothing else on the drive is erased.", d)
			if err := copyToVentoy(iso, d); err != nil {
				return err
			}
		} else {
			dir := ""
			if ventoyRuns {
				if dir, err = ventoy(); err != nil {
					warn("Could not get Ventoy (%v).", err)
					note("MeccanicOS can still be written directly to the drive: it starts the same way,")
					note("but the drive then holds only MeccanicOS, with no room for other ISOs or files.")
				}
			}
			if !confirmErase(d) {
				note("Cancelled: nothing was written to %s.", d.Name())
				note("To use another drive, insert it now; or close this window.")
				continue // wait for another drive
			}
			// The drive's name may have gone to another drive since the YES.
			if now, ok := find(d.ID); !ok || !d.same(now) {
				warn("%s is not the drive you said YES to any more (it was removed, or another drive took its place): nothing was written.", d.Name())
				note("To go on, unplug the drive you want to use and plug it in again; or close this window.")
				continue
			}
			if dir != "" {
				usedVentoy = true
				err = installVentoy(dir, d)
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
		if err := finish(d); err != nil {
			printBootGuide(usedVentoy)
			return fmt.Errorf("MeccanicOS is on the USB drive and was checked, but the drive could not be disconnected safely (%v). "+
				"Do not pull it out yet: eject it first (in the file manager, or the Finder on a Mac)", err)
		}
		done("Done. The USB drive is ready: you can remove it now.")
		printBootGuide(usedVentoy)
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
