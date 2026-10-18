package main

import (
	"archive/tar"
	"archive/zip"
	"bytes"
	"compress/gzip"
	"crypto/sha256"
	"encoding/hex"
	"io"
	"os"
	"path/filepath"
	"runtime"
	"slices"
	"strconv"
	"strings"
	"testing"
)

const h64 = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"

func TestParseSums(t *testing.T) {
	sums, order, err := parseSums(strings.NewReader(h64 + "  a.iso\n\n" + strings.ToUpper(h64) + " *a.iso.part01\n"))
	if err != nil || !slices.Equal(order, []string{"a.iso", "a.iso.part01"}) || sums["a.iso.part01"] != h64 {
		t.Fatal(sums, order, err)
	}
	for _, bad := range []string{
		"abc  a.iso",                        // not a SHA-256
		h64 + "  a.iso\n" + h64 + "  a.iso", // twice
		h64 + "  ../a.iso", h64 + "  dir/a.iso", h64 + `  dir\a.iso`, h64 + "  C:a.iso", h64 + "  ..",
		h64 + "  a b.iso", // three fields
	} {
		if _, _, err := parseSums(strings.NewReader(bad)); err == nil {
			t.Errorf("accepted %q", bad)
		}
	}
}

func TestReleaseISO(t *testing.T) {
	order := []string{"m.iso", "other.iso.part1", "README.pdf"}
	for i := 12; i >= 1; i-- { // out of order, not zero-padded: part10 after part9
		order = append(order, "m.iso.part"+strconv.Itoa(i))
	}
	name, parts, err := releaseISO(order)
	if err != nil || name != "m.iso" || len(parts) != 12 || parts[8] != "m.iso.part9" || parts[9] != "m.iso.part10" {
		t.Fatal(name, parts, err)
	}
	if _, parts, err := releaseISO([]string{"m.iso"}); err != nil || len(parts) != 0 {
		t.Fatal("one file:", parts, err)
	}
	for _, bad := range [][]string{
		{"m.iso", "m.iso.part1", "m.iso.part3"},  // gap
		{"m.iso", "m.iso.part2"},                 // no first part
		{"m.iso", "m.iso.part1", "m.iso.part01"}, // part 1 twice
		{"m.iso", "m.iso.part0"},
		{"m.iso", "m.iso.part+1"},
		{"m.iso", "m.iso.partial"},
		{"README.pdf"}, // no ISO
	} {
		if _, _, err := releaseISO(bad); err == nil {
			t.Errorf("accepted %v", bad)
		}
	}
}

// checkISO (run as administrator) only reads the cache: it uses the ISO
// fetchISO left there, and changes nothing in it.
func TestCheckISO(t *testing.T) {
	iso := []byte(strings.Repeat("z", 3000))
	srv := fakeRelease(t, iso, 1000)
	defer srv.Close()
	t.Setenv("MOS_USB_RELEASE", srv.URL)

	empty := t.TempDir()
	if _, err := checkISO(empty); err == nil {
		t.Fatal("nothing downloaded, yet checkISO worked")
	}
	if left, _ := os.ReadDir(empty); len(left) != 0 {
		t.Fatalf("checkISO wrote in the cache: %v", left)
	}

	cache := t.TempDir()
	if _, err := fetchISO(cache); err != nil {
		t.Fatal(err)
	}
	before, _ := os.ReadDir(cache)
	got, err := checkISO(cache)
	if err != nil {
		t.Fatal(err)
	}
	if string(got.Readme) != "%PDF readme" {
		t.Fatalf("readme: %q", got.Readme)
	}
	// The file checked is the one read, even if the ISO is swapped afterwards.
	os.Rename(got.Path, got.Path+".old")
	os.WriteFile(got.Path, []byte("swapped"), 0o644)
	r, err := got.open()
	if err != nil {
		t.Fatal(err)
	}
	b, _ := io.ReadAll(r)
	if string(b) != string(iso) {
		t.Fatal("open did not give the file that was checked")
	}
	os.Remove(got.Path)
	os.Rename(got.Path+".old", got.Path)
	after, _ := os.ReadDir(cache)
	if len(before) != len(after) {
		t.Fatalf("checkISO changed the cache: %v -> %v", before, after)
	}

	// A link in place of the ISO is not followed.
	if runtime.GOOS != "windows" {
		os.Rename(got.Path, got.Path+".real")
		os.Symlink(got.Path+".real", got.Path)
		if _, err := checkISO(cache); err == nil {
			t.Fatal("followed a link in place of the ISO")
		}
	}
}

type entry struct {
	name string
	typ  byte
	link string
	body string
}

func makeTar(t *testing.T, entries ...entry) string {
	t.Helper()
	var buf bytes.Buffer
	gz := gzip.NewWriter(&buf)
	tw := tar.NewWriter(gz)
	for _, e := range entries {
		h := &tar.Header{Name: e.name, Typeflag: e.typ, Linkname: e.link, Mode: 0o755, Size: int64(len(e.body))}
		if e.typ != tar.TypeReg {
			h.Size = 0
		}
		if err := tw.WriteHeader(h); err != nil {
			t.Fatal(err)
		}
		tw.Write([]byte(e.body))
	}
	tw.Close()
	gz.Close()
	p := filepath.Join(t.TempDir(), "a.tar.gz")
	os.WriteFile(p, buf.Bytes(), 0o644)
	return p
}

func TestUntar(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("tar archives are unpacked on Linux only")
	}
	dir := func(n string) entry { return entry{name: n, typ: tar.TypeDir} }
	file := func(n, body string) entry { return entry{name: n, typ: tar.TypeReg, body: body} }
	sym := func(n, to string) entry { return entry{name: n, typ: tar.TypeSymlink, link: to} }

	// What a real archive may hold.
	top := t.TempDir()
	dest := filepath.Join(top, "dest")
	good := makeTar(t, dir("v/"), file("v/Ventoy2Disk.sh", "#!/bin/sh"), sym("v/l", "Ventoy2Disk.sh"),
		dir("v/tool/"), sym("v/tool/up", "../Ventoy2Disk.sh"), entry{name: "v/hard", typ: tar.TypeLink, link: "v/Ventoy2Disk.sh"})
	if err := untar(good, dest); err != nil {
		t.Fatal(err)
	}
	for _, f := range []string{"v/l", "v/tool/up", "v/hard"} {
		if b, err := os.ReadFile(filepath.Join(dest, f)); err != nil || string(b) != "#!/bin/sh" {
			t.Errorf("%s: %q %v", f, b, err)
		}
	}

	for what, entries := range map[string][]entry{
		"../ in a name":               {file("../out/x", "evil")},
		"absolute link":               {sym("l", top+"/out")},
		"relative link out":           {sym("l", "../out")},
		"link, then a file in it":     {dir("sub/"), sym("l", "sub"), file("l/x", "evil")},
		"link out, then a file in it": {sym("l", "../out"), file("l/x", "evil")},
		"chained links":               {sym("l1", "l2"), sym("l2", "../out"), file("l1/x", "evil")},
		"chain out through a link":    {dir("c/"), sym("b", "."), sym("a", "b/c/../../out")},
		"hard link out":               {entry{name: "h", typ: tar.TypeLink, link: "../out/x"}},
		"hard link to a link":         {dir("sub/"), sym("s", "sub"), entry{name: "h", typ: tar.TypeLink, link: "s"}},
		"device":                      {{name: "dev", typ: tar.TypeChar}},
	} {
		top := t.TempDir()
		os.Mkdir(filepath.Join(top, "out"), 0o755)
		os.WriteFile(filepath.Join(top, "out", "x"), []byte("mine"), 0o644)
		if err := untar(makeTar(t, entries...), filepath.Join(top, "dest")); err != nil {
			t.Logf("%s: %v", what, err)
		} else {
			t.Errorf("%s: accepted", what)
		}
		if b, _ := os.ReadFile(filepath.Join(top, "out", "x")); string(b) != "mine" {
			t.Errorf("%s: wrote outside the folder", what)
		}
	}

	defer func(m int64) { maxUnpacked = m }(maxUnpacked)
	maxUnpacked = 10
	if err := untar(makeTar(t, file("a", "12345"), file("b", "123456")), filepath.Join(t.TempDir(), "d")); err == nil {
		t.Error("more than maxUnpacked unpacked")
	}
}

func TestUnzip(t *testing.T) {
	for what, add := range map[string]func(*zip.Writer){
		"../ in a name": func(z *zip.Writer) { w, _ := z.Create("../x"); w.Write([]byte("evil")) },
		"link": func(z *zip.Writer) {
			h := &zip.FileHeader{Name: "l"}
			h.SetMode(os.ModeSymlink | 0o777)
			w, _ := z.CreateHeader(h)
			w.Write([]byte("/etc"))
		},
	} {
		var buf bytes.Buffer
		z := zip.NewWriter(&buf)
		add(z)
		z.Close()
		p := filepath.Join(t.TempDir(), "a.zip")
		os.WriteFile(p, buf.Bytes(), 0o644)
		if err := unzip(p, filepath.Join(t.TempDir(), "d")); err == nil {
			t.Errorf("%s: accepted", what)
		}
	}
}

func TestDiskSame(t *testing.T) {
	d := Disk{ID: "sdb", Path: "/dev/sdb", Model: "Stick", Serial: "S1", Size: 64e9}
	o := d
	if !d.same(o) {
		t.Fatal("same drive not recognised")
	}
	for _, change := range []func(*Disk){
		func(x *Disk) { x.Serial = "S2" },
		func(x *Disk) { x.Size++ },
		func(x *Disk) { x.Model = "Other" },
		func(x *Disk) { x.ID = "sdc" },
	} {
		o := d
		change(&o)
		if d.same(o) {
			t.Errorf("another drive taken for the same: %+v", o)
		}
	}
}

// A copy onto a Ventoy drive replaces the ISO already there only once it is
// complete and correct.
func TestCopyISO(t *testing.T) {
	src := filepath.Join(t.TempDir(), "m.iso")
	data := []byte(strings.Repeat("n", 5000))
	os.WriteFile(src, data, 0o644)
	sum := sha256.Sum256(data)
	iso := ISO{Path: src, Name: "m.iso", Sum: hex.EncodeToString(sum[:]), Size: int64(len(data)), Readme: []byte("pdf")}
	mnt := t.TempDir()
	old := filepath.Join(mnt, "m.iso")
	os.WriteFile(old, []byte("old"), 0o644)

	bad := iso
	bad.Sum = h64
	if err := copyISO(bad, mnt); err == nil {
		t.Fatal("damaged copy accepted")
	}
	if b, _ := os.ReadFile(old); string(b) != "old" {
		t.Fatal("old ISO not kept")
	}
	if _, err := os.Stat(old + ".part"); err == nil {
		t.Fatal(".part left behind")
	}

	if err := copyISO(iso, mnt); err != nil {
		t.Fatal(err)
	}
	if b, _ := os.ReadFile(old); string(b) != string(data) {
		t.Fatal("ISO not replaced")
	}
	if b, _ := os.ReadFile(filepath.Join(mnt, "MeccanicOS-README.pdf")); string(b) != "pdf" {
		t.Fatal("readme not copied")
	}
}
