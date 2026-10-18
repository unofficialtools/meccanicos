//go:build linux || darwin

package main

import (
	"fmt"
	"os"
	"os/exec"
	"slices"
	"syscall"
)

func isAdmin() bool { return os.Geteuid() == 0 }

// elevatedRun: this process is the one elevate started.
func elevatedRun() bool { return slices.Contains(os.Args[1:], elevatedFlag) }

// elevate starts the program again with sudo (writing a whole drive needs
// it), told where the downloads are; it does not return when that works.
func elevate() error {
	sudo, err := exec.LookPath("sudo")
	if err != nil {
		return fmt.Errorf("writing a USB drive needs administrator rights: run this as root")
	}
	exe, err := os.Executable()
	if err != nil {
		return err
	}
	cache, err := cacheDir()
	if err != nil {
		return err
	}
	step("Writing a USB drive needs administrator rights: enter your password if asked.")
	env := append(os.Environ(), "MOS_USB_CACHE="+cache)
	args := []string{"sudo", "--preserve-env=MOS_USB_CACHE,MOS_USB_RELEASE,HTTPS_PROXY,https_proxy,HTTP_PROXY,http_proxy", exe, elevatedFlag}
	args = append(args, os.Args[1:]...)
	return syscall.Exec(sudo, args, env)
}

func pauseAtEnd() bool { return false }
