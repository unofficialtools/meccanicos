package main

import (
	"fmt"
	"os"
	"os/exec"
	"strings"
	"time"
)

func isAdmin() bool { return exec.Command("net", "session").Run() == nil }

// elevate starts the program again as administrator (Windows asks the user
// to allow it), told where the downloads are; the new window does the rest.
func elevate() error {
	exe, err := os.Executable()
	if err != nil {
		return err
	}
	cache, err := cacheDir()
	if err != nil {
		return err
	}
	step("Writing a USB drive needs administrator rights: allow it in the window Windows shows.")
	note("MeccanicOS USB maker continues in a new window.")
	quote := func(s string) string { return "'" + strings.ReplaceAll(s, "'", "''") + "'" }
	args := []string{elevatedFlag, "--cache=" + cache}
	if r := os.Getenv("MOS_USB_RELEASE"); r != "" {
		args = append(args, "--release="+r)
	}
	// Start-Process joins these with spaces and no quotes: one with a space
	// (C:\Users\Mario Rossi\...) goes in double quotes, or it becomes two.
	// (A Windows path holds no double quote, and this one ends in no \.)
	quoted := make([]string, len(args))
	for i, a := range args {
		if strings.ContainsAny(a, " \t") {
			a = `"` + a + `"`
		}
		quoted[i] = quote(a)
	}
	if out, err := ps(fmt.Sprintf("Start-Process -FilePath %s -Verb RunAs -ArgumentList %s",
		quote(exe), strings.Join(quoted, ","))); err != nil {
		return fmt.Errorf("could not get administrator rights: %s", out)
	}
	time.Sleep(3 * time.Second)
	os.Exit(0)
	return nil
}

// pauseAtEnd: a double-clicked program's window closes when it ends; keep
// it open until the user has read the result.
func pauseAtEnd() bool { return true }

// elevatedRun: this is the window started by elevate. It also takes the
// download folder and release from its arguments (the environment is not
// passed on by RunAs).
func elevatedRun() bool {
	found := false
	for _, a := range os.Args[1:] {
		switch {
		case a == elevatedFlag:
			found = true
		case strings.HasPrefix(a, "--cache="):
			os.Setenv("MOS_USB_CACHE", strings.TrimPrefix(a, "--cache="))
		case strings.HasPrefix(a, "--release="):
			os.Setenv("MOS_USB_RELEASE", strings.TrimPrefix(a, "--release="))
		}
	}
	return found
}
