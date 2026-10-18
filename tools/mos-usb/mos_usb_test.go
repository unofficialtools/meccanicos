package main

import (
	"bufio"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"
)

// A release like the real one: an ISO in parts, MeccanicOS-README.pdf, and
// SHA256SUMS. Files named in missing are listed in SHA256SUMS but not served.
func fakeRelease(t *testing.T, iso []byte, partSize int, missing ...string) *httptest.Server {
	t.Helper()
	files := map[string][]byte{}
	name := "meccanicos-26.05-20261008-x86_64-linux-abcdef12.iso"
	sum := func(b []byte) string { h := sha256.Sum256(b); return hex.EncodeToString(h[:]) }
	sums := sum(iso) + "  " + name + "\n"
	for i := 0; i*partSize < len(iso); i++ {
		end := min((i+1)*partSize, len(iso))
		part := fmt.Sprintf("%s.part%02d", name, i+1)
		files[part] = iso[i*partSize : end]
		sums += sum(files[part]) + "  " + part + "\n"
	}
	files["MeccanicOS-README.pdf"] = []byte("%PDF readme")
	sums += sum(files["MeccanicOS-README.pdf"]) + "  MeccanicOS-README.pdf\n"
	sums += sum([]byte("exe")) + "  mos-usb-windows.exe\n" // other release files are ignored
	files["SHA256SUMS"] = []byte(sums)
	for _, m := range missing {
		delete(files, m)
	}
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		b, ok := files[strings.TrimPrefix(r.URL.Path, "/")]
		if !ok {
			http.NotFound(w, r)
			return
		}
		http.ServeContent(w, r, "", time.Unix(0, 0), strings.NewReader(string(b)))
	}))
}

func TestFetchISO(t *testing.T) {
	iso := make([]byte, 2_500_000)
	for i := range iso {
		iso[i] = byte(i * 7)
	}
	srv := fakeRelease(t, iso, 1_000_000)
	defer srv.Close()
	t.Setenv("MOS_USB_RELEASE", srv.URL)
	cache := t.TempDir()

	// A half-downloaded first part, a stale ISO from an older release, and
	// a file of the user's.
	name := "meccanicos-26.05-20261008-x86_64-linux-abcdef12.iso"
	os.WriteFile(filepath.Join(cache, name+".part01"), iso[:400_000], 0o644)
	os.WriteFile(filepath.Join(cache, "meccanicos-old.iso"), []byte("old"), 0o644)
	os.WriteFile(filepath.Join(cache, "other.iso"), []byte("mine"), 0o644)

	got, err := fetchISO(cache)
	if err != nil {
		t.Fatal(err)
	}
	b, _ := os.ReadFile(got.Path)
	if got.Name != name || got.Size != int64(len(iso)) || string(b) != string(iso) {
		t.Fatalf("wrong ISO: %+v", got)
	}
	if string(got.Readme) != "%PDF readme" {
		t.Fatalf("MeccanicOS-README.pdf not downloaded: %q", got.Readme)
	}
	left, _ := filepath.Glob(filepath.Join(cache, "*"))
	if len(left) != 3 {
		t.Fatalf("cache should hold only the ISO, MeccanicOS-README.pdf and other.iso, has %v", left)
	}

	// Run again: the ISO in the cache is checked and reused.
	again, err := fetchISO(cache)
	if err != nil || again.Path != got.Path {
		t.Fatal("not reused:", err)
	}
}

// A release whose MeccanicOS-README.pdf cannot be downloaded: the ISO is
// fetched all the same, without it.
func TestFetchISOWithoutReadme(t *testing.T) {
	iso := []byte(strings.Repeat("y", 3000))
	srv := fakeRelease(t, iso, 1000, "MeccanicOS-README.pdf")
	defer srv.Close()
	t.Setenv("MOS_USB_RELEASE", srv.URL)
	got, err := fetchISO(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	if got.Readme != nil {
		t.Fatalf("no MeccanicOS-README.pdf to download, yet got %q", got.Readme)
	}
}

func TestFetchISODamaged(t *testing.T) {
	iso := []byte(strings.Repeat("x", 3000))
	srv := fakeRelease(t, iso, 1000)
	defer srv.Close()
	t.Setenv("MOS_USB_RELEASE", srv.URL)
	cache := t.TempDir()
	name := "meccanicos-26.05-20261008-x86_64-linux-abcdef12.iso"
	// A complete but wrong ISO in the cache: replaced.
	os.WriteFile(filepath.Join(cache, name), []byte("damaged"), 0o644)
	got, err := fetchISO(cache)
	if err != nil {
		t.Fatal(err)
	}
	if b, _ := os.ReadFile(got.Path); string(b) != string(iso) {
		t.Fatal("damaged ISO not replaced")
	}
}

func TestInside(t *testing.T) {
	if _, err := inside("/tmp/x", "../etc/passwd"); err == nil {
		t.Fatal("path outside the folder accepted")
	}
	if p, err := inside("/tmp/x", "ventoy-1.1/Ventoy2Disk.sh"); err != nil || p != "/tmp/x/ventoy-1.1/Ventoy2Disk.sh" {
		t.Fatal(p, err)
	}
}

func TestBootGuide(t *testing.T) {
	g := bootGuide(true)
	for _, want := range []string{"Secure Boot", "BitLocker", "Boot in normal mode", "F12", "MeccanicOS-README.pdf", "groups.google.com/g/meccanicos"} {
		if !strings.Contains(g, want) {
			t.Errorf("guide lacks %q", want)
		}
	}
	for _, line := range strings.Split(g, "\n") {
		if len([]rune(line)) > 80 {
			t.Errorf("line over 80 columns: %q", line)
		}
	}
}

// MOS_USB_NET=1 go test -run Ventoy -v: fetch and unpack Ventoy's real
// latest release (Linux and Windows only), and unpack it in a private folder.
func TestFetchVentoy(t *testing.T) {
	if os.Getenv("MOS_USB_NET") == "" {
		t.Skip("set MOS_USB_NET=1 to download Ventoy")
	}
	cache := t.TempDir()
	if err := downloadVentoy(cache); err != nil {
		t.Fatal(err)
	}
	dir, _, cleanup, err := prepareVentoy(cache)
	if err != nil {
		t.Fatal(err)
	}
	defer cleanup()
	t.Log("Ventoy2Disk in", dir)
}

// Erasing goes on only for a typed YES, in any case.
func TestConfirmErase(t *testing.T) {
	d := Disk{ID: "sdz", Path: "/dev/sdz", Model: "Test Stick", Size: 64e9}
	for in, want := range map[string]bool{
		"YES\n": true, "yes\n": true, " Yes \r\n": true, "YES": true,
		"y\n": false, "\n": false, "no\n": false, "YESS\n": false, "": false,
	} {
		stdin = bufio.NewReader(strings.NewReader(in))
		if got := confirmErase(d); got != want {
			t.Errorf("answer %q: confirmErase = %v, want %v", in, got, want)
		}
	}
}

// Ventoy's version is read from the end of the drive (its VTOYEFI partition).
func TestVentoyVersionOn(t *testing.T) {
	if runtime.GOOS != "linux" {
		t.Skip("the drive is a plain file only on Linux")
	}
	disk := func(size int64, at int64, text string) Disk {
		path := filepath.Join(t.TempDir(), "disk")
		f, err := os.Create(path)
		if err != nil {
			t.Fatal(err)
		}
		defer f.Close()
		if err := f.Truncate(size); err != nil { // sparse: no real 128 MB written
			t.Fatal(err)
		}
		if text != "" {
			if _, err := f.WriteAt([]byte(text), at); err != nil {
				t.Fatal(err)
			}
		}
		return Disk{ID: "sdz", Path: path, Size: size}
	}
	const size = 128 << 20
	cfg := "\nset VENTOY_VERSION=\"1.0.97\"\n"
	for _, c := range []struct {
		d    Disk
		want string
	}{
		{disk(size, size-20<<20, cfg), "1.0.97"},
		{disk(size, size-100<<20, cfg), ""}, // not in Ventoy's partition
		{disk(size, size-1<<20, `VENTOY_VERSION="x"`), ""},
		{disk(size, 0, ""), ""},
		{disk(32<<20, 1<<20, cfg), ""}, // smaller than Ventoy's partitions
	} {
		if got := ventoyVersionOn(c.d); got != c.want {
			t.Errorf("ventoyVersionOn = %q, want %q", got, c.want)
		}
	}
}

func TestOlderVersion(t *testing.T) {
	for _, c := range []struct {
		a, b string
		want bool
	}{
		{"1.0.97", "1.1.12", true},
		{"1.1.9", "1.1.12", true}, // numbers, not text
		{"1.1.12", "1.1.12", false},
		{"1.1.12", "1.0.99", false},
		{"1.1", "1.1.1", true},
		{"1.1.0", "1.1", false},
	} {
		if got := olderVersion(c.a, c.b); got != c.want {
			t.Errorf("olderVersion(%q, %q) = %v, want %v", c.a, c.b, got, c.want)
		}
	}
}
