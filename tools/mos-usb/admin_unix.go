//go:build linux || darwin

package main

import (
	"fmt"
	"os"
	"os/exec"
	"syscall"
)

// ensureAdmin starts the program again with sudo when it is not root (writing
// a whole drive needs it). The download folder stays the user's.
func ensureAdmin() error {
	if os.Geteuid() == 0 {
		return nil
	}
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
	args := []string{"sudo", "--preserve-env=MOS_USB_CACHE,MOS_USB_RELEASE,HTTPS_PROXY,https_proxy,HTTP_PROXY,http_proxy", exe}
	args = append(args, os.Args[1:]...)
	return syscall.Exec(sudo, args, env)
}

func pauseAtEnd() bool { return false }
