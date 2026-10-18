package main

import (
	"archive/tar"
	"archive/zip"
	"compress/gzip"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
	"strconv"
	"strings"
)

const ventoyAPI = "https://api.github.com/repos/ventoy/Ventoy/releases/latest"

// ventoyRelease finds Ventoy's latest release for this system: the package's
// name, address and SHA-256 (from the release's sha256.txt), and the version.
func ventoyRelease() (pkg, url, sum, version string, err error) {
	suffix := map[string]string{"linux": "-linux.tar.gz", "windows": "-windows.zip"}[runtime.GOOS]
	if suffix == "" {
		return "", "", "", "", errUnsupported
	}
	resp, err := get(ventoyAPI, 0)
	if err != nil {
		return "", "", "", "", err
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
		return "", "", "", "", err
	}
	var sumsURL string
	for _, a := range rel.Assets {
		switch {
		case strings.HasPrefix(a.Name, "ventoy-") && strings.HasSuffix(a.Name, suffix) && safeName(a.Name):
			pkg, url = a.Name, a.URL
		case a.Name == "sha256.txt":
			sumsURL = a.URL
		}
	}
	if pkg == "" || sumsURL == "" {
		return "", "", "", "", fmt.Errorf("no %s in Ventoy's release %s", suffix, rel.Tag)
	}
	sums, _, err := readSums(sumsURL)
	if err != nil {
		return "", "", "", "", fmt.Errorf("Ventoy's sha256.txt: %w", err)
	}
	if sums[pkg] == "" {
		return "", "", "", "", fmt.Errorf("%s is not in Ventoy's sha256.txt", pkg)
	}
	return pkg, url, sums[pkg], strings.TrimPrefix(rel.Tag, "v"), nil
}

// downloadVentoy downloads Ventoy's latest release for this system into the
// cache (checked against the release's sha256.txt). It is not unpacked
// there: prepareVentoy does that, in a folder of its own.
func downloadVentoy(cache string) error {
	step("Getting Ventoy (it makes the USB drive boot any ISO copied onto it).")
	pkg, url, sum, version, err := ventoyRelease()
	if err != nil {
		return err
	}
	note("Ventoy %s", version)
	return download(url, filepath.Join(cache, pkg), sum, "Ventoy")
}

// prepareVentoy runs as administrator. It copies the Ventoy package that
// downloadVentoy left in the cache (a folder of the user's) into a new folder
// that only the administrator can change, checking it again on the way, and
// unpacks it there: Ventoy then runs only from files nobody else could have
// changed. It returns the folder holding Ventoy2Disk, Ventoy's version, and
// cleanup, which deletes the private folder.
func prepareVentoy(cache string) (string, string, func(), error) {
	pkg, _, sum, version, err := ventoyRelease()
	if err != nil {
		return "", "", nil, err
	}
	priv, err := os.MkdirTemp(privateBase(), "mos-usb-ventoy-")
	if err != nil {
		return "", "", nil, err
	}
	cleanup := func() { os.RemoveAll(priv) }
	archive := filepath.Join(priv, pkg)
	if err := copyChecked(filepath.Join(cache, pkg), archive, sum); err != nil {
		cleanup()
		return "", "", nil, fmt.Errorf("Ventoy was not downloaded, or changed after it was checked: %w", err)
	}
	dest := filepath.Join(priv, "unpacked")
	if strings.HasSuffix(pkg, ".zip") {
		err = unzip(archive, dest)
	} else {
		err = untar(archive, dest)
	}
	if err != nil {
		cleanup()
		return "", "", nil, fmt.Errorf("unpacking Ventoy: %w", err)
	}
	// The archive holds one folder, ventoy-VERSION/.
	matches, _ := filepath.Glob(filepath.Join(dest, "*", "Ventoy2Disk*"))
	if len(matches) == 0 {
		cleanup()
		return "", "", nil, fmt.Errorf("no Ventoy2Disk in %s", pkg)
	}
	return filepath.Dir(matches[0]), version, cleanup, nil
}

// privateBase is where prepareVentoy makes its folder: a system folder in
// which other users can make folders of their own but not touch the
// administrator's (on Windows, the folder's permissions; elsewhere, the
// "sticky" /var/tmp or /tmp). The user's own temporary folder would not do.
func privateBase() string {
	if runtime.GOOS == "windows" {
		root := os.Getenv("SystemRoot")
		if root == "" {
			root = `C:\Windows`
		}
		return filepath.Join(root, "Temp")
	}
	if fi, err := os.Stat("/var/tmp"); err == nil && fi.IsDir() {
		return "/var/tmp" // /tmp may not allow running programs
	}
	return "/tmp"
}

// copyChecked copies the plain file src to the new file dest, which must
// match sum; else dest is removed.
func copyChecked(src, dest, sum string) error {
	in, err := openRegular(src)
	if err != nil {
		return err
	}
	defer in.Close()
	out, err := os.OpenFile(dest, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		return err
	}
	h := sha256.New()
	_, err = io.Copy(io.MultiWriter(out, h), in)
	if cerr := out.Close(); err == nil {
		err = cerr
	}
	if err == nil && hex.EncodeToString(h.Sum(nil)) != sum {
		err = fmt.Errorf("%s does not match Ventoy's sha256.txt", filepath.Base(src))
	}
	if err != nil {
		os.Remove(dest)
	}
	return err
}

func installVentoy(dir string, d Disk) error {
	step("Installing Ventoy on %s (about a minute).", d)
	if err := ventoyInstall(dir, d); err != nil {
		return fmt.Errorf("installing Ventoy: %w", err)
	}
	note("Ventoy is installed.")
	return nil
}

// updateVentoy replaces Ventoy on d with the one in dir. Only Ventoy's own
// partition and boot code are rewritten: the files on the drive stay.
func updateVentoy(dir string, d Disk) error {
	step("Updating Ventoy on %s (the files on it stay).", d)
	if err := ventoyUpdate(dir, d); err != nil {
		return fmt.Errorf("updating Ventoy (the files on the drive are still there; run mos-usb again to retry): %w", err)
	}
	note("Ventoy is updated.")
	return nil
}

// Ventoy's version is in its own partition (VTOYEFI, 32 MB at the end of the
// drive), as plain text: set VENTOY_VERSION="1.1.12".
var ventoyVersionRe = regexp.MustCompile(`VENTOY_VERSION="([0-9]+(?:\.[0-9]+)*)"`)

// ventoyTail is how much of the end of a drive holds Ventoy's partition.
const ventoyTail = 64 << 20

// ventoyVersionOn is the version of Ventoy on d, or "" if it cannot be told
// (a drive with space reserved after Ventoy's partitions, for example).
func ventoyVersionOn(d Disk) string {
	if d.Size < ventoyTail {
		return ""
	}
	f, err := openRawRead(d)
	if err != nil {
		return ""
	}
	defer f.Close()
	buf := make([]byte, ventoyTail)
	for off := 0; off < len(buf); off += 1 << 20 { // whole sectors at a time
		if _, err := f.ReadAt(buf[off:off+1<<20], d.Size-ventoyTail+int64(off)); err != nil {
			return ""
		}
	}
	m := ventoyVersionRe.FindSubmatch(buf)
	if m == nil {
		return ""
	}
	return string(m[1])
}

// olderVersion: version a (like 1.0.97) comes before b.
func olderVersion(a, b string) bool {
	as, bs := strings.Split(a, "."), strings.Split(b, ".")
	for i := range max(len(as), len(bs)) {
		var x, y int
		if i < len(as) {
			x, _ = strconv.Atoi(as[i])
		}
		if i < len(bs) {
			y, _ = strconv.Atoi(bs[i])
		}
		if x != y {
			return x < y
		}
	}
	return false
}

// copyToVentoy adds the ISO to the drive's Ventoy partition, and MeccanicOS-README.pdf
// next to it. Nothing already on the drive is deleted, older MeccanicOS ISOs
// included; only a file with this ISO's own name, and MeccanicOS-README.pdf, is replaced.
// If it does not fit, nothing is written.
func copyToVentoy(iso ISO, d Disk) (err error) {
	mnt, release, err := dataMount(d)
	if err != nil {
		return fmt.Errorf("opening the Ventoy partition: %w", err)
	}
	defer func() {
		if rerr := release(); err == nil && rerr != nil {
			err = fmt.Errorf("finishing writing to the USB drive: %w", rerr)
		}
	}()
	return copyISO(iso, mnt)
}

// copyISO copies the ISO into the folder mnt as NAME.part, checks the copy,
// and only then renames it to NAME: a copy of the ISO already there stays
// until the new one is complete and correct, and is kept if it is not.
func copyISO(iso ISO, mnt string) error {
	dest := filepath.Join(mnt, iso.Name)
	part := dest + ".part"
	// Room is needed for the whole new copy, next to the old one. A .part
	// left by an earlier try is overwritten: its space counts as free.
	free, err := freeSpace(mnt)
	if fi, lerr := os.Lstat(part); lerr == nil && fi.Mode().IsRegular() {
		free += fi.Size()
	}
	if err == nil && free < iso.Size {
		also := ""
		if _, err := os.Stat(dest); err == nil {
			also = " (the copy of this ISO already on it is replaced only once the new one is checked, so there must be room for both for a moment)"
		}
		return fmt.Errorf("not enough room on the USB drive for %s: it needs %s, %s is free%s. "+
			"Nothing was changed: delete files you no longer need from the drive (older MeccanicOS ISOs, for example) and run mos-usb again",
			iso.Name, human(iso.Size), human(free), also)
	}
	step("Copying %s to the USB drive.", iso.Name)
	in, err := iso.open()
	if err != nil {
		return err
	}
	defer in.Close()
	out, err := os.Create(part)
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
		os.Remove(part)
		return fmt.Errorf("copying the ISO: %w", err)
	}
	step("Checking the copy.")
	sum, err := hashFile(part, "Checking")
	if err != nil || sum != iso.Sum {
		os.Remove(part)
		return fmt.Errorf("the copy on the USB drive is damaged (nothing on the drive was replaced); the drive may be failing")
	}
	if err := os.Rename(part, dest); err != nil {
		os.Remove(part)
		return err
	}
	note("The copy is correct.")
	if iso.Readme != nil {
		// Optional: if it cannot be copied, the drive works without it.
		replaceFile(filepath.Join(mnt, "MeccanicOS-README.pdf"), iso.Readme)
	}
	return nil
}

// replaceFile writes a small file (MeccanicOS-README.pdf), replacing dest
// only once it is written in full.
func replaceFile(dest string, data []byte) error {
	if err := os.WriteFile(dest+".part", data, 0o644); err != nil {
		os.Remove(dest + ".part")
		return err
	}
	return os.Rename(dest+".part", dest)
}

// writeRaw writes the ISO over the whole drive, then reads it back to check.
func writeRaw(iso ISO, d Disk) error {
	step("Writing MeccanicOS to %s.", d)
	in, err := iso.open()
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

// maxUnpacked bounds what an archive may unpack to (Ventoy's: about 25 MB).
var maxUnpacked int64 = 1 << 30

// unpacker puts an archive's files in dest, and nowhere else: names that
// climb out of it are refused, and so are links pointing out of it (or
// through which a later file could be written anywhere: nothing is written
// through a link), devices and the like, and more than maxUnpacked bytes.
type unpacker struct {
	dest  string
	left  int64
	links []string
}

func newUnpacker(dest string) (*unpacker, error) {
	return &unpacker{dest: dest, left: maxUnpacked}, os.MkdirAll(dest, 0o755)
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
	u, err := newUnpacker(dest)
	if err != nil {
		return err
	}
	tr := tar.NewReader(gz)
	for {
		h, err := tr.Next()
		if err == io.EOF {
			return u.checkLinks()
		}
		if err != nil {
			return err
		}
		if h.Typeflag == tar.TypeXGlobalHeader {
			continue // details about the whole archive: nothing to unpack
		}
		path, err := u.target(h.Name)
		if err != nil {
			return err
		}
		switch h.Typeflag {
		case tar.TypeDir:
			err = os.MkdirAll(path, 0o755)
		case tar.TypeReg:
			err = u.writeFile(path, tr, os.FileMode(h.Mode)&0o777)
		case tar.TypeSymlink:
			err = u.symlink(path, h.Linkname)
		case tar.TypeLink:
			err = u.hardlink(path, h.Linkname)
		default:
			err = fmt.Errorf("unsupported kind of file in archive: %s", h.Name)
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
	u, err := newUnpacker(dest)
	if err != nil {
		return err
	}
	for _, zf := range z.File {
		path, err := u.target(zf.Name)
		if err != nil {
			return err
		}
		if zf.FileInfo().IsDir() {
			if err := os.MkdirAll(path, 0o755); err != nil {
				return err
			}
			continue
		}
		if !zf.Mode().IsRegular() {
			return fmt.Errorf("unsupported kind of file in archive: %s", zf.Name)
		}
		rc, err := zf.Open()
		if err != nil {
			return err
		}
		err = u.writeFile(path, rc, 0o755)
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
	if !within(dir, path) {
		return "", fmt.Errorf("unsafe path in archive: %s", name)
	}
	return path, nil
}

// within: path is dir or in it (both clean).
func within(dir, path string) bool {
	return path == dir || strings.HasPrefix(path, dir+string(filepath.Separator))
}

// target is where the archive's name goes: inside dest, and reached without
// going through a link (one unpacked earlier could point anywhere).
func (u *unpacker) target(name string) (string, error) {
	path, err := inside(u.dest, name)
	if err != nil {
		return "", err
	}
	rel, _ := filepath.Rel(u.dest, path)
	p := u.dest
	for _, c := range strings.Split(rel, string(filepath.Separator)) {
		if c == "." {
			break
		}
		p = filepath.Join(p, c)
		fi, err := os.Lstat(p)
		if errors.Is(err, fs.ErrNotExist) {
			break
		}
		if err != nil {
			return "", err
		}
		if fi.Mode()&fs.ModeSymlink != 0 {
			return "", fmt.Errorf("unsafe path in archive (through a link): %s", name)
		}
	}
	return path, nil
}

func (u *unpacker) writeFile(path string, r io.Reader, mode os.FileMode) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	f, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, mode|0o200)
	if err != nil {
		return err
	}
	n, err := io.Copy(f, io.LimitReader(r, u.left+1))
	u.left -= n
	if err == nil && u.left < 0 {
		err = fmt.Errorf("the archive unpacks to more than %s", human(maxUnpacked))
	}
	if cerr := f.Close(); err == nil {
		err = cerr
	}
	return err
}

// symlink makes a link to a relative target inside dest. Links through other
// links are checked once all is unpacked (checkLinks).
func (u *unpacker) symlink(path, target string) error {
	rel, _ := filepath.Rel(u.dest, path)
	bad := fmt.Errorf("unsafe link in archive: %s -> %s", rel, target)
	if target == "" || filepath.IsAbs(target) || filepath.VolumeName(target) != "" ||
		strings.HasPrefix(target, "/") || strings.HasPrefix(target, `\`) {
		return bad
	}
	if !within(u.dest, filepath.Join(filepath.Dir(path), target)) {
		return bad
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	u.links = append(u.links, path)
	return os.Symlink(target, path)
}

// hardlink links path to a plain file unpacked earlier.
func (u *unpacker) hardlink(path, name string) error {
	src, err := u.target(name)
	if err != nil {
		return err
	}
	if fi, err := os.Lstat(src); err != nil || !fi.Mode().IsRegular() {
		rel, _ := filepath.Rel(u.dest, path)
		return fmt.Errorf("unsafe link in archive: %s -> %s", rel, name)
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	return os.Link(src, path)
}

// checkLinks: every link, followed to the end (through other links too),
// leads to something inside dest.
func (u *unpacker) checkLinks() error {
	root, err := filepath.EvalSymlinks(u.dest)
	if err != nil {
		return err
	}
	for _, l := range u.links {
		real, err := filepath.EvalSymlinks(l)
		if err != nil || !within(root, real) {
			rel, _ := filepath.Rel(u.dest, l)
			return fmt.Errorf("unsafe link in archive: %s", rel)
		}
	}
	return nil
}
