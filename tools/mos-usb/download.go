package main

import (
	"bufio"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"
)

// ISO is the downloaded, checked MeccanicOS image.
type ISO struct {
	Path, Name, Sum string
	Size            int64
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
func fetchISO(cache string) (ISO, error) {
	base := strings.TrimSuffix(os.Getenv("MOS_USB_RELEASE"), "/")
	if base == "" {
		base = defaultRelease
	}
	step("Checking the latest MeccanicOS release.")
	sums, order, err := readSums(base + "/SHA256SUMS")
	if err != nil {
		return ISO{}, fmt.Errorf("could not read the release's SHA256SUMS: %w", err)
	}
	var iso ISO
	var parts []string
	partRe := regexp.MustCompile(`\.iso\.part\d+$`)
	for _, name := range order {
		if strings.HasSuffix(name, ".iso") && iso.Name == "" {
			iso.Name, iso.Sum = name, sums[name]
		} else if partRe.MatchString(name) {
			parts = append(parts, name)
		}
	}
	if iso.Name == "" {
		return ISO{}, fmt.Errorf("no .iso in SHA256SUMS")
	}
	sort.Strings(parts)
	iso.Path = filepath.Join(cache, iso.Name)
	note("Latest: %s", iso.Name)

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
	// Older ISOs in the cache are not needed any more.
	if old, _ := filepath.Glob(filepath.Join(cache, "*.iso")); old != nil {
		for _, f := range old {
			os.Remove(f)
		}
	}

	if len(parts) == 0 { // one file, no parts
		parts = []string{iso.Name}
	}
	step("Downloading MeccanicOS (%d part%s; an interrupted download resumes when run again).", len(parts), plural(len(parts)))
	for i, p := range parts {
		label := fmt.Sprintf("Part %d/%d", i+1, len(parts))
		if err := download(base+"/"+p, filepath.Join(cache, p), sums[p], label); err != nil {
			return ISO{}, err
		}
	}
	if len(parts) > 1 || parts[0] != iso.Name {
		step("Joining the parts.")
		if err := join(cache, parts, iso.Path+".tmp"); err != nil {
			return ISO{}, err
		}
		if err := os.Rename(iso.Path+".tmp", iso.Path); err != nil {
			return ISO{}, err
		}
	}
	step("Checking the ISO.")
	sum, err := hashFile(iso.Path, "Checking")
	if err != nil {
		return ISO{}, err
	}
	if sum != iso.Sum {
		os.Remove(iso.Path)
		return ISO{}, fmt.Errorf("the ISO does not match SHA256SUMS (damaged download); run again")
	}
	for _, p := range parts {
		if p != iso.Name {
			os.Remove(filepath.Join(cache, p))
		}
	}
	st, _ := os.Stat(iso.Path)
	iso.Size = st.Size()
	note("The ISO is correct (%s).", human(iso.Size))
	return iso, nil
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
	sums := map[string]string{}
	var order []string
	sc := bufio.NewScanner(resp.Body)
	for sc.Scan() {
		f := strings.Fields(sc.Text())
		if len(f) == 2 {
			name := strings.TrimPrefix(f[1], "*")
			sums[name] = strings.ToLower(f[0])
			order = append(order, name)
		}
	}
	return sums, order, sc.Err()
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
	st, _ := f.Stat()
	h := sha256.New()
	p := newProgress(label, st.Size(), 0)
	_, err = io.Copy(h, io.TeeReader(f, p))
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
