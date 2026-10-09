package main

import (
	"archive/tar"
	"archive/zip"
	"compress/gzip"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"runtime"
	"strings"
)

const ventoyAPI = "https://api.github.com/repos/ventoy/Ventoy/releases/latest"

// fetchVentoy downloads Ventoy's latest release for this system (checked
// against the release's sha256.txt) and unpacks it; it returns the folder
// holding Ventoy2Disk.
func fetchVentoy(cache string) (string, error) {
	suffix := map[string]string{"linux": "-linux.tar.gz", "windows": "-windows.zip"}[runtime.GOOS]
	if suffix == "" {
		return "", errUnsupported
	}
	step("Getting Ventoy (it makes the USB drive boot any ISO copied onto it).")
	resp, err := get(ventoyAPI, 0)
	if err != nil {
		return "", err
	}
	var rel struct {
		Tag    string `json:"tag_name"`
		Assets []struct {
			Name string `json:"name"`
			URL  string `json:"browser_download_url"`
		} `json:"assets"`
	}
	err = json.NewDecoder(resp.Body).Decode(&rel)
	resp.Body.Close()
	if err != nil {
		return "", err
	}
	var pkg, pkgURL, sumsURL string
	for _, a := range rel.Assets {
		switch {
		case strings.HasPrefix(a.Name, "ventoy-") && strings.HasSuffix(a.Name, suffix):
			pkg, pkgURL = a.Name, a.URL
		case a.Name == "sha256.txt":
			sumsURL = a.URL
		}
	}
	if pkg == "" || sumsURL == "" {
		return "", fmt.Errorf("no %s in Ventoy's release %s", suffix, rel.Tag)
	}
	sums, _, err := readSums(sumsURL)
	if err != nil {
		return "", err
	}
	if sums[pkg] == "" {
		return "", fmt.Errorf("%s is not in Ventoy's sha256.txt", pkg)
	}
	note("Ventoy %s", strings.TrimPrefix(rel.Tag, "v"))
	archive := filepath.Join(cache, pkg)
	if err := download(pkgURL, archive, sums[pkg], "Ventoy"); err != nil {
		return "", err
	}
	dest := filepath.Join(cache, strings.TrimSuffix(strings.TrimSuffix(pkg, ".zip"), ".tar.gz"))
	os.RemoveAll(dest)
	if strings.HasSuffix(pkg, ".zip") {
		err = unzip(archive, dest)
	} else {
		err = untar(archive, dest)
	}
	if err != nil {
		return "", fmt.Errorf("unpacking Ventoy: %w", err)
	}
	// The archive holds one folder, ventoy-VERSION/.
	matches, _ := filepath.Glob(filepath.Join(dest, "*", "Ventoy2Disk*"))
	if len(matches) == 0 {
		return "", fmt.Errorf("no Ventoy2Disk in %s", pkg)
	}
	return filepath.Dir(matches[0]), nil
}

func installVentoy(dir string, d Disk) error {
	step("Installing Ventoy on %s (about a minute).", d)
	if err := ventoyInstall(dir, d); err != nil {
		return fmt.Errorf("installing Ventoy: %w", err)
	}
	note("Ventoy is installed.")
	return nil
}

// copyToVentoy adds the ISO to the drive's Ventoy partition. Nothing already
// on the drive is deleted, older MeccanicOS ISOs included; only a file with
// this ISO's own name is replaced. If it does not fit, nothing is written.
func copyToVentoy(iso ISO, d Disk) error {
	mnt, release, err := dataMount(d)
	if err != nil {
		return fmt.Errorf("opening the Ventoy partition: %w", err)
	}
	defer release()
	dest := filepath.Join(mnt, iso.Name)
	need := iso.Size
	if fi, err := os.Stat(dest); err == nil {
		need -= fi.Size() // replaced: its space comes back
	}
	if free, err := freeSpace(mnt); err == nil && free < need {
		return fmt.Errorf("not enough room on the USB drive for %s: it needs %s, %s is free. "+
			"Nothing was changed: delete files you no longer need from the drive (older MeccanicOS ISOs, for example) and run mos-usb again",
			iso.Name, human(need), human(free))
	}
	step("Copying %s to the USB drive.", iso.Name)
	in, err := os.Open(iso.Path)
	if err != nil {
		return err
	}
	defer in.Close()
	out, err := os.Create(dest + ".part")
	if err != nil {
		return err
	}
	p := newProgress("Copying", iso.Size, 0)
	_, err = io.Copy(out, io.TeeReader(in, p))
	p.finish()
	if err == nil {
		note("Making sure everything is written (this can take a minute)...")
		err = out.Sync()
	}
	if cerr := out.Close(); err == nil {
		err = cerr
	}
	if err != nil {
		os.Remove(dest + ".part")
		return fmt.Errorf("copying the ISO: %w", err)
	}
	os.Remove(dest)
	if err := os.Rename(dest+".part", dest); err != nil {
		return err
	}
	step("Checking the copy.")
	sum, err := hashFile(dest, "Checking")
	if err != nil {
		return err
	}
	if sum != iso.Sum {
		return fmt.Errorf("the copy on the USB drive is damaged; the drive may be failing")
	}
	note("The copy is correct.")
	return nil
}

// writeRaw writes the ISO over the whole drive, then reads it back to check.
func writeRaw(iso ISO, d Disk) error {
	step("Writing MeccanicOS to %s.", d)
	in, err := os.Open(iso.Path)
	if err != nil {
		return err
	}
	defer in.Close()
	out, err := openRaw(d)
	if err != nil {
		return fmt.Errorf("opening %s: %w", d, err)
	}
	buf := make([]byte, 4<<20)
	p := newProgress("Writing", iso.Size, 0)
	for {
		n, rerr := io.ReadFull(in, buf)
		if n > 0 {
			chunk := buf[:n]
			if pad := n % 512; pad != 0 { // whole sectors only
				chunk = buf[:n+512-pad]
				clear(chunk[n:])
			}
			if _, err := out.Write(chunk); err != nil {
				out.Close()
				return fmt.Errorf("writing: %w", err)
			}
			p.add(int64(n))
		}
		if rerr == io.EOF || rerr == io.ErrUnexpectedEOF {
			break
		}
		if rerr != nil {
			out.Close()
			return rerr
		}
	}
	p.finish()
	note("Making sure everything is written (this can take a minute)...")
	if err := flushDisk(out); err != nil {
		out.Close()
		return err
	}
	out.Close()

	step("Checking what was written.")
	r, err := openRawRead(d)
	if err != nil {
		return err
	}
	defer r.Close()
	got, err := hashPrefix(r, iso.Size)
	if err != nil {
		return fmt.Errorf("reading back: %w", err)
	}
	if got != iso.Sum {
		return fmt.Errorf("what is on the USB drive does not match the ISO; the drive may be failing")
	}
	note("The USB drive is correct.")
	return nil
}

// hashPrefix is the SHA-256 of the first n bytes of r (the ISO's length of
// the drive: the rest of the drive is not the ISO's).
func hashPrefix(r io.Reader, n int64) (string, error) {
	h := sha256.New()
	p := newProgress("Checking", n, 0)
	_, err := io.CopyN(h, io.TeeReader(r, p), n)
	p.finish()
	return hex.EncodeToString(h.Sum(nil)), err
}

func untar(archive, dest string) error {
	f, err := os.Open(archive)
	if err != nil {
		return err
	}
	defer f.Close()
	gz, err := gzip.NewReader(f)
	if err != nil {
		return err
	}
	tr := tar.NewReader(gz)
	for {
		h, err := tr.Next()
		if err == io.EOF {
			return nil
		}
		if err != nil {
			return err
		}
		path, err := inside(dest, h.Name)
		if err != nil {
			return err
		}
		switch h.Typeflag {
		case tar.TypeDir:
			err = os.MkdirAll(path, 0o755)
		case tar.TypeReg:
			err = writeFile(path, tr, os.FileMode(h.Mode)&0o777)
		case tar.TypeSymlink:
			os.MkdirAll(filepath.Dir(path), 0o755)
			err = os.Symlink(h.Linkname, path)
		}
		if err != nil {
			return err
		}
	}
}

func unzip(archive, dest string) error {
	z, err := zip.OpenReader(archive)
	if err != nil {
		return err
	}
	defer z.Close()
	for _, zf := range z.File {
		path, err := inside(dest, zf.Name)
		if err != nil {
			return err
		}
		if zf.FileInfo().IsDir() {
			os.MkdirAll(path, 0o755)
			continue
		}
		rc, err := zf.Open()
		if err != nil {
			return err
		}
		err = writeFile(path, rc, 0o755)
		rc.Close()
		if err != nil {
			return err
		}
	}
	return nil
}

// inside joins name to dir, refusing names that climb out of it.
func inside(dir, name string) (string, error) {
	path := filepath.Join(dir, name)
	if path != dir && !strings.HasPrefix(path, dir+string(filepath.Separator)) {
		return "", fmt.Errorf("unsafe path in archive: %s", name)
	}
	return path, nil
}

func writeFile(path string, r io.Reader, mode os.FileMode) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	f, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, mode|0o200)
	if err != nil {
		return err
	}
	_, err = io.Copy(f, r)
	if cerr := f.Close(); err == nil {
		err = cerr
	}
	return err
}
