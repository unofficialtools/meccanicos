package main

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// A release like the real one: an ISO in parts, and SHA256SUMS.
func fakeRelease(t *testing.T, iso []byte, partSize int) *httptest.Server {
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
	sums += sum([]byte("exe")) + "  mos-usb-windows.exe\n" // other release files are ignored
	files["SHA256SUMS"] = []byte(sums)
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

	// A half-downloaded first part and a stale ISO from an older release.
	name := "meccanicos-26.05-20261008-x86_64-linux-abcdef12.iso"
	os.WriteFile(filepath.Join(cache, name+".part01"), iso[:400_000], 0o644)
	os.WriteFile(filepath.Join(cache, "meccanicos-old.iso"), []byte("old"), 0o644)

	got, err := fetchISO(cache)
	if err != nil {
		t.Fatal(err)
	}
	b, _ := os.ReadFile(got.Path)
	if got.Name != name || got.Size != int64(len(iso)) || string(b) != string(iso) {
		t.Fatalf("wrong ISO: %+v", got)
	}
	left, _ := filepath.Glob(filepath.Join(cache, "*"))
	if len(left) != 1 {
		t.Fatalf("cache should hold only the ISO, has %v", left)
	}

	// Run again: the ISO in the cache is checked and reused.
	again, err := fetchISO(cache)
	if err != nil || again.Path != got.Path {
		t.Fatal("not reused:", err)
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
	for _, want := range []string{"Secure Boot", "BitLocker", "Boot in normal mode", "F12"} {
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
// latest release (Linux and Windows only).
func TestFetchVentoy(t *testing.T) {
	if os.Getenv("MOS_USB_NET") == "" {
		t.Skip("set MOS_USB_NET=1 to download Ventoy")
	}
	dir, err := fetchVentoy(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	t.Log("Ventoy2Disk in", dir)
}
