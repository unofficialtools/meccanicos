package main

import (
	"fmt"
	"runtime"
	"strings"
)

// bootGuide is shown when the drive is ready: how to start MeccanicOS from
// it, here or on another computer, and the firmware settings that get in
// the way. Kept in step with the README ("Boot it").
func bootGuide(ventoy bool) string {
	var b strings.Builder
	p := func(s string) { b.WriteString(s + "\n") }

	p("HOW TO START MECCANICOS FROM THE USB DRIVE")
	p("")
	p("It is safe: starting from the USB drive changes nothing on the computer.")
	p("Its own disk is not touched unless you choose to install MeccanicOS.")
	p("To go back, shut down, remove the drive and start the computer as usual.")
	p("")
	switch runtime.GOOS {
	case "windows":
		p("On this computer (Windows): plug the drive in, then hold Shift while you")
		p("click Restart (Start > Power). Choose \"Use a device\" and pick the USB drive.")
	case "darwin":
		p("On this Mac: only Macs with an Intel processor can start MeccanicOS")
		p("(Apple menu > About This Mac). Shut down, plug the drive in, turn the Mac")
		p("on holding the Option (Alt) key, and choose \"EFI Boot\". Macs with the T2")
		p("chip first need: Startup Security Utility > Allow booting from external media.")
	default:
		p("On this computer: plug the drive in, restart, and use the boot menu key below.")
	}
	p("")
	p("On any PC: plug the drive in, turn it on and tap the boot menu key at once:")
	p("  Dell, Lenovo, Acer, Toshiba: F12    HP: F9 (or Esc)    ASUS: F8 or Esc")
	p("  MSI: F11    Gigabyte: F12    Microsoft Surface: hold Volume Down while")
	p("  pressing Power    Intel Mac: hold Option")
	p("Pick the entry with \"USB\" or the drive's name in it (if it is listed twice,")
	p("pick the one that starts with \"UEFI\").")
	if ventoy {
		p("Ventoy's menu then lists the ISOs on the drive: choose MeccanicOS, then")
		p("\"Boot in normal mode\".")
	}
	p("")
	p("IF IT DOES NOT START: firmware (BIOS) settings. Open them with the setup key,")
	p("usually Del, F2 or F10 right after power-on (Windows: Shift+Restart >")
	p("Troubleshoot > Advanced options > UEFI Firmware Settings).")
	p("  - Secure Boot: MeccanicOS is not signed for it. If the drive is skipped, or")
	p("    you see \"Verification failed\" or \"Security violation\", turn Secure Boot")
	p("    off. You can turn it on again later for Windows.")
	p("  - BitLocker: changing firmware settings can make Windows ask for its")
	p("    BitLocker recovery key at the next start. Have it at hand first")
	p("    (aka.ms/myrecoverykey, on your Microsoft account).")
	p("  - Fast Boot: if the boot menu key does nothing, turn off Fast Boot in the")
	p("    firmware (or use Shift+Restart from Windows, which always works).")
	p("  - USB boot: make sure \"USB boot\" is enabled; without a boot menu key, put")
	p("    the USB drive first in the boot order.")
	p("  - Old PCs (before about 2012): enable \"Legacy\" or \"CSM\" boot if the drive")
	p("    is not listed; newer PCs should use UEFI.")
	p("  - Installing (not just trying): if the installer sees no disk, the disk may")
	p("    be in \"RAID\" or \"Intel RST\" mode; it needs \"AHCI\" (ask before changing")
	p("    it on a computer that also runs Windows).")
	p("")
	p("More help: https://meccanicos.com and the manual,")
	p("https://github.com/unofficialtools/meccanicos#readme")
	return b.String()
}

func printBootGuide(ventoy bool) {
	fmt.Println()
	fmt.Print(bootGuide(ventoy))
}
