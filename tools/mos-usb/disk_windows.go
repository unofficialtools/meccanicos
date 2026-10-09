package main

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"time"
	"unsafe"
)

// ps runs a PowerShell script and returns its output.
func ps(script string) (string, error) {
	out, err := exec.Command("powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
		"-Command", "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; "+script).CombinedOutput()
	return strings.TrimSpace(string(out)), err
}

// listUSB: disks on the USB bus that do not hold Windows. Ventoy's second
// partition is labelled VTOYEFI.
func listUSB() ([]Disk, error) {
	out, err := ps(`@(Get-Disk | Where-Object { $_.BusType -eq 'USB' -and -not $_.IsBoot -and -not $_.IsSystem } | ForEach-Object {
  $labels = @(Get-Partition -DiskNumber $_.Number -ErrorAction SilentlyContinue | Get-Volume -ErrorAction SilentlyContinue | ForEach-Object { $_.FileSystemLabel })
  [pscustomobject]@{ Number = $_.Number; Model = $_.FriendlyName; Size = [int64]$_.Size; Labels = ($labels -join ',') }
}) | ConvertTo-Json -Compress`)
	if err != nil {
		return nil, fmt.Errorf("listing disks: %v: %s", err, out)
	}
	out = strings.TrimSpace(out)
	if out == "" {
		return nil, nil
	}
	if !strings.HasPrefix(out, "[") {
		out = "[" + out + "]"
	}
	var rows []struct {
		Number int
		Model  string
		Size   int64
		Labels string
	}
	if err := json.Unmarshal([]byte(out), &rows); err != nil {
		return nil, fmt.Errorf("listing disks: %w", err)
	}
	var disks []Disk
	for _, r := range rows {
		disks = append(disks, Disk{
			ID:     strconv.Itoa(r.Number),
			Path:   fmt.Sprintf(`\\.\PhysicalDrive%d`, r.Number),
			Model:  strings.TrimSpace(r.Model),
			Size:   r.Size,
			Ventoy: strings.Contains(r.Labels, "VTOYEFI"),
		})
	}
	return disks, nil
}

func openRaw(d Disk) (*os.File, error) {
	// Remove its partitions first, so Windows lets go of its volumes.
	ps(fmt.Sprintf(`Clear-Disk -Number %s -RemoveData -RemoveOEM -Confirm:$false`, d.ID))
	ps(fmt.Sprintf(`Update-Disk -Number %s`, d.ID))
	return os.OpenFile(d.Path, os.O_RDWR, 0)
}

func openRawRead(d Disk) (*os.File, error) { return os.Open(d.Path) }

func flushDisk(f *os.File) error { return f.Sync() }

func ventoyInstall(dir string, d Disk) error {
	done := filepath.Join(dir, "cli_done.txt")
	os.Remove(done)
	cmd := exec.Command(filepath.Join(dir, "Ventoy2Disk.exe"), "VTOYCLI", "/I", "/PhyDrive:"+d.ID, "/GPT", "/NOUSBCheck")
	cmd.Dir = dir
	if err := cmd.Run(); err != nil {
		return err
	}
	// Ventoy writes 0 to cli_done.txt on success; the details are in cli_log.txt.
	for i := 0; i < 30; i++ {
		if b, err := os.ReadFile(done); err == nil {
			if strings.TrimSpace(string(b)) == "0" {
				time.Sleep(3 * time.Second) // let Windows see the new partitions
				return nil
			}
			break
		}
		time.Sleep(time.Second)
	}
	log, _ := os.ReadFile(filepath.Join(dir, "cli_log.txt"))
	return fmt.Errorf("Ventoy did not install:\n%s", tailLines(string(log), 15))
}

// dataMount gives Ventoy's first partition (where ISOs go) a drive letter.
func dataMount(d Disk) (string, func(), error) {
	var letter string
	var err error
	for i := 0; i < 20; i++ {
		letter, err = ps(fmt.Sprintf(`$p = Get-Partition -DiskNumber %[1]s -PartitionNumber 1
if (-not $p.DriveLetter -or $p.DriveLetter -eq [char]0) {
  Add-PartitionAccessPath -DiskNumber %[1]s -PartitionNumber 1 -AssignDriveLetter | Out-Null
  $p = Get-Partition -DiskNumber %[1]s -PartitionNumber 1
}
$p.DriveLetter`, d.ID))
		if err == nil && len(letter) == 1 {
			if _, serr := os.Stat(letter + `:\`); serr == nil {
				return letter + `:\`, func() { ps("Write-VolumeCache -DriveLetter " + letter) }, nil
			}
		}
		time.Sleep(time.Second)
	}
	return "", nil, fmt.Errorf("no drive letter for the Ventoy partition: %v %s", err, letter)
}

func finish(Disk) {}

func tailLines(s string, n int) string {
	lines := strings.Split(strings.TrimSpace(s), "\n")
	if len(lines) > n {
		lines = lines[len(lines)-n:]
	}
	return strings.Join(lines, "\n")
}

// freeSpace is how many bytes can still be written in the folder dir.
func freeSpace(dir string) (int64, error) {
	path, err := syscall.UTF16PtrFromString(dir)
	if err != nil {
		return 0, err
	}
	var free uint64
	proc := syscall.NewLazyDLL("kernel32.dll").NewProc("GetDiskFreeSpaceExW")
	if r, _, err := proc.Call(uintptr(unsafe.Pointer(path)), uintptr(unsafe.Pointer(&free)), 0, 0); r == 0 {
		return 0, err
	}
	return int64(free), nil
}

// deviceName is the drive as Windows' Disk Management numbers it.
func deviceName(d Disk) string { return "Disk " + d.ID }

// Colors in the console: on since Windows 10, but only when asked for.
func init() {
	h, err := syscall.GetStdHandle(syscall.STD_OUTPUT_HANDLE)
	var mode uint32
	if err != nil || syscall.GetConsoleMode(h, &mode) != nil {
		colors = false
		return
	}
	const enableVirtualTerminalProcessing = 0x0004
	set := syscall.NewLazyDLL("kernel32.dll").NewProc("SetConsoleMode")
	if r, _, _ := set.Call(uintptr(h), uintptr(mode|enableVirtualTerminalProcessing)); r == 0 {
		colors = false
	}
}
