package main

import (
	"bufio"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"
)

// ISO is the downloaded, checked MeccanicOS image.
type ISO struct {
	Path, Name, Sum string
	Size            int64
	Readme          []byte // the release's MeccanicOS-README.pdf, checked, or nil (older releases have none)
	file            *os.File
}

// open returns the ISO to read from its start: the file checkISO checked and
// kept open (so it cannot be swapped for another one after the check), or
// else the file at Path.
func (iso ISO) open() (io.ReadCloser, error) {
	if iso.file != nil {
		return io.NopCloser(io.NewSectionReader(iso.file, 0, iso.Size)), nil
	}
	return os.Open(iso.Path)
}

var client = &http.Client{Transport: &http.Transport{
	Proxy:                 http.ProxyFromEnvironment,
	ResponseHeaderTimeout: 60 * time.Second,
}}

func cacheDir() (string, error) {
	dir := os.Getenv("MOS_USB_CACHE")
	if dir == "" {
		base, err := os.UserCacheDir()
		if err != nil {
			base = os.TempDir()
		}
		dir = filepath.Join(base, "meccanicos")
	}
	return dir, os.MkdirAll(dir, 0o755)
}

// fetchISO downloads the latest release's ISO into the cache (its parts, each
// checked, then joined and checked), or reuses one downloaded before.
func fetchISO(cache string) (ISO, error) { return getISO(cache, false) }

// checkISO is fetchISO for the part run as administrator: it writes, deletes
// and downloads nothing in the cache (a folder of the user's), only checks
// the ISO fetchISO left there, and keeps it open for writing it.
func checkISO(cache string) (ISO, error) { return getISO(cache, true) }

var errNotDownloaded = errors.New("the MeccanicOS download is missing, or changed after it was checked: run mos-usb again")

func getISO(cache string, readOnly bool) (ISO, error) {
	base := strings.TrimSuffix(os.Getenv("MOS_USB_RELEASE"), "/")
	if base == "" {
		base = defaultRelease
	}
	step("Checking the latest MeccanicOS release.")
	sums, order, err := readSums(base + "/SHA256SUMS")
	if err != nil {
		return ISO{}, fmt.Errorf("could not read the release's SHA256SUMS: %w", err)
	}
	name, parts, err := releaseISO(order)
	if err != nil {
		return ISO{}, fmt.Errorf("the release's SHA256SUMS: %w", err)
	}
	iso := ISO{Name: name, Sum: sums[name], Path: filepath.Join(cache, name)}
	note("Latest: %s", iso.Name)
	iso.Readme = fetchReadme(base, cache, sums["MeccanicOS-README.pdf"], readOnly)

	if readOnly {
		f, err := openRegular(iso.Path)
		if err != nil {
			return ISO{}, errNotDownloaded
		}
		st, _ := f.Stat()
		step("Checking the downloaded copy.")
		if sum, err := hashReader(f, st.Size(), "Checking"); err != nil || sum != iso.Sum {
			f.Close()
			return ISO{}, errNotDownloaded
		}
		iso.file, iso.Size = f, st.Size()
		note("It is complete and correct.")
		return iso, nil
	}
	if st, err := os.Stat(iso.Path); err == nil {
		step("Checking the copy downloaded earlier.")
		if sum, err := hashFile(iso.Path, "Checking"); err == nil && sum == iso.Sum {
			iso.Size = st.Size()
			note("It is complete and correct.")
			return iso, nil
		}
		warn("The earlier copy is damaged: downloading it again.")
		os.Remove(iso.Path)
	}
	// Older MeccanicOS ISOs downloaded before are not needed any more; other
	// files in the folder are left alone.
	if old, _ := filepath.Glob(filepath.Join(cache, "meccanicos-*.iso")); old != nil {
		for _, f := range old {
			os.Remove(f)
		}
	}

	// The ISO is put together (or downloaded) under a temporary name, and
	// gets its own only once it is checked.
	tmp := iso.Path + ".tmp"
	files := parts
	if len(files) == 0 { // one file, no parts
		files = []string{iso.Name}
	}
	step("Downloading MeccanicOS (%d part%s; an interrupted download resumes when run again).", len(files), plural(len(files)))
	for i, p := range files {
		label := fmt.Sprintf("Part %d/%d", i+1, len(files))
		dest := filepath.Join(cache, p)
		if len(parts) == 0 {
			dest = tmp // checked against SHA256SUMS by download
		}
		if err := download(base+"/"+p, dest, sums[p], label); err != nil {
			return ISO{}, err
		}
	}
	if len(parts) > 0 {
		step("Joining the parts.")
		if err := join(cache, parts, tmp); err != nil {
			os.Remove(tmp)
			return ISO{}, err
		}
		step("Checking the ISO.")
		sum, err := hashFile(tmp, "Checking")
		if err != nil || sum != iso.Sum {
			os.Remove(tmp)
			return ISO{}, fmt.Errorf("the ISO does not match SHA256SUMS (damaged download); run again")
		}
	}
	if err := os.Rename(tmp, iso.Path); err != nil {
		return ISO{}, err
	}
	for _, p := range parts {
		os.Remove(filepath.Join(cache, p))
	}
	st, err := os.Stat(iso.Path)
	if err != nil {
		return ISO{}, err
	}
	iso.Size = st.Size()
	note("The ISO is correct (%s).", human(iso.Size))
	return iso, nil
}

// releaseISO picks the release's ISO (the first .iso in SHA256SUMS) and its
// parts in order: exactly NAME.part1 to NAME.partN (zero-padded or not),
// each once; parts of other ISOs are not used. No parts: the ISO is one file.
func releaseISO(order []string) (string, []string, error) {
	name := ""
	for _, n := range order {
		if strings.HasSuffix(n, ".iso") {
			name = n
			break
		}
	}
	if name == "" {
		return "", nil, fmt.Errorf("no .iso in it")
	}
	byNum := map[int]string{}
	for _, n := range order {
		num, ok := strings.CutPrefix(n, name+".part")
		if !ok {
			continue
		}
		i, err := strconv.Atoi(num)
		if err != nil || !digits.MatchString(num) || i < 1 {
			return "", nil, fmt.Errorf("%s: not a part number", n)
		}
		if byNum[i] != "" {
			return "", nil, fmt.Errorf("part %d is listed twice (%s, %s)", i, byNum[i], n)
		}
		byNum[i] = n
	}
	parts := make([]string, len(byNum))
	for i := range parts {
		p, ok := byNum[i+1]
		if !ok {
			return "", nil, fmt.Errorf("part %d of %s is missing", i+1, name)
		}
		parts[i] = p
	}
	return name, parts, nil
}

var digits = regexp.MustCompile(`^[0-9]+$`)

// fetchReadme downloads the release's MeccanicOS-README.pdf (the instructions
// put next to the ISO on a Ventoy stick), checked against SHA256SUMS, and
// returns it. It is optional: when the release has none, or it cannot be
// downloaded, it is skipped without a word and nil returned; the stick works
// without it. readOnly: only one downloaded before is used.
func fetchReadme(base, cache, sum string, readOnly bool) []byte {
	if sum == "" {
		return nil
	}
	dest := filepath.Join(cache, "MeccanicOS-README.pdf")
	checked := func() []byte {
		f, err := openRegular(dest)
		if err != nil {
			return nil
		}
		defer f.Close()
		b, err := io.ReadAll(io.LimitReader(f, 64<<20))
		if h := sha256.Sum256(b); err != nil || hex.EncodeToString(h[:]) != sum {
			return nil
		}
		return b
	}
	if b := checked(); b != nil || readOnly {
		return b // downloaded before
	}
	os.Remove(dest)
	resp, err := get(base+"/MeccanicOS-README.pdf", 0)
	if err != nil {
		return nil
	}
	defer resp.Body.Close()
	f, err := os.Create(dest)
	if err != nil {
		return nil
	}
	_, err = io.Copy(f, resp.Body)
	if cerr := f.Close(); err == nil {
		err = cerr
	}
	b := checked()
	if err != nil || b == nil {
		os.Remove(dest)
		return nil
	}
	return b
}

// openRegular opens a plain file for reading: not a link, a device or a pipe
// (a folder of the user's could hold any of them under the expected name).
func openRegular(path string) (*os.File, error) {
	if fi, err := os.Lstat(path); err != nil || !fi.Mode().IsRegular() {
		return nil, fmt.Errorf("%s: not a plain file", path)
	}
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	if fi, err := f.Stat(); err != nil || !fi.Mode().IsRegular() {
		f.Close()
		return nil, fmt.Errorf("%s: not a plain file", path)
	}
	return f, nil
}

func plural(n int) string {
	if n == 1 {
		return ""
	}
	return "s"
}

func readSums(url string) (map[string]string, []string, error) {
	resp, err := get(url, 0)
	if err != nil {
		return nil, nil, err
	}
	defer resp.Body.Close()
	return parseSums(resp.Body)
}

var sha256Hex = regexp.MustCompile(`^[0-9a-fA-F]{64}$`)

// parseSums reads a SHA256SUMS file ("HASH  NAME" lines): the sums by name,
// and the names in order. Anything else in it is refused, as are names
// listed twice and names that are not a plain file name (the names become
// file names in the download folder and on the USB drive).
func parseSums(r io.Reader) (map[string]string, []string, error) {
	sums := map[string]string{}
	var order []string
	sc := bufio.NewScanner(r)
	for n := 1; sc.Scan(); n++ {
		f := strings.Fields(sc.Text())
		if len(f) == 0 {
			continue
		}
		if len(f) != 2 || !sha256Hex.MatchString(f[0]) {
			return nil, nil, fmt.Errorf("line %d is not a SHA-256 and a file name", n)
		}
		name := strings.TrimPrefix(f[1], "*")
		if !safeName(name) {
			return nil, nil, fmt.Errorf("line %d: unsafe file name %q", n, name)
		}
		if _, dup := sums[name]; dup {
			return nil, nil, fmt.Errorf("line %d: %s is listed twice", n, name)
		}
		sums[name] = strings.ToLower(f[0])
		order = append(order, name)
	}
	return sums, order, sc.Err()
}

// safeName: a plain file name, with no folder in it and no way out of one.
func safeName(name string) bool {
	return name != "" && !strings.Contains(name, "..") && !strings.ContainsAny(name, "/\\:\x00")
}

func get(url string, from int64) (*http.Response, error) {
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", "mos-usb")
	if from > 0 {
		req.Header.Set("Range", fmt.Sprintf("bytes=%d-", from))
	}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusPartialContent {
		resp.Body.Close()
		return nil, fmt.Errorf("%s: %s", url, resp.Status)
	}
	return resp, nil
}

// download fetches url into dest, resuming a partial file, and checks it
// against sum (when given). A few retries for flaky connections.
func download(url, dest, sum, label string) error {
	if sum != "" {
		if got, err := hashFileQuiet(dest); err == nil && got == sum {
			note("%s: already downloaded.", label)
			return nil
		}
	}
	var lastErr error
	for try := 1; try <= 5; try++ {
		if try > 1 {
			warn("%v; retrying (%d/5).", lastErr, try)
			time.Sleep(time.Duration(try) * 2 * time.Second)
		}
		if lastErr = fetchOnce(url, dest, label); lastErr != nil {
			continue
		}
		if sum == "" {
			return nil
		}
		got, err := hashFileQuiet(dest)
		if err == nil && got == sum {
			return nil
		}
		os.Remove(dest) // damaged: start this file again
		lastErr = fmt.Errorf("%s does not match SHA256SUMS", filepath.Base(dest))
	}
	return fmt.Errorf("download failed: %w", lastErr)
}

func fetchOnce(url, dest, label string) error {
	var have int64
	if st, err := os.Stat(dest); err == nil {
		have = st.Size()
	}
	resp, err := get(url, have)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	flags := os.O_CREATE | os.O_WRONLY | os.O_APPEND
	if resp.StatusCode != http.StatusPartialContent {
		have = 0
		flags |= os.O_TRUNC
	}
	f, err := os.OpenFile(dest, flags, 0o644)
	if err != nil {
		return err
	}
	p := newProgress(label, have+resp.ContentLength, have)
	_, err = io.Copy(f, io.TeeReader(resp.Body, p))
	p.finish()
	if cerr := f.Close(); err == nil {
		err = cerr
	}
	return err
}

func join(dir string, parts []string, dest string) error {
	out, err := os.Create(dest)
	if err != nil {
		return err
	}
	var total int64
	for _, p := range parts {
		if st, err := os.Stat(filepath.Join(dir, p)); err == nil {
			total += st.Size()
		}
	}
	prog := newProgress("Joining", total, 0)
	for _, p := range parts {
		in, err := os.Open(filepath.Join(dir, p))
		if err != nil {
			out.Close()
			return err
		}
		_, err = io.Copy(out, io.TeeReader(in, prog))
		in.Close()
		if err != nil {
			out.Close()
			return err
		}
	}
	prog.finish()
	return out.Close()
}

func hashFile(path, label string) (string, error) {
	f, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer f.Close()
	st, err := f.Stat()
	if err != nil {
		return "", err
	}
	return hashReader(f, st.Size(), label)
}

// hashReader is the SHA-256 of r (size bytes), showing progress.
func hashReader(r io.Reader, size int64, label string) (string, error) {
	h := sha256.New()
	p := newProgress(label, size, 0)
	_, err := io.Copy(h, io.TeeReader(r, p))
	p.finish()
	return hex.EncodeToString(h.Sum(nil)), err
}

func hashFileQuiet(path string) (string, error) {
	f, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer f.Close()
	h := sha256.New()
	_, err = io.Copy(h, f)
	return hex.EncodeToString(h.Sum(nil)), err
}
