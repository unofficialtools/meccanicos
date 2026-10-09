package main

import (
	"bufio"
	"fmt"
	"os"
	"strings"
	"time"
	"unicode/utf8"
)

var stdin = bufio.NewReader(os.Stdin)

// colors is false where the console cannot show them (old Windows consoles).
var colors = true

func title(s string)          { fmt.Printf("\n%s\n%s\n\n", s, strings.Repeat("=", len(s))) }
func step(f string, a ...any) { fmt.Printf("> "+f+"\n", a...) }
func note(f string, a ...any) { fmt.Printf("  "+f+"\n", a...) }
func warn(f string, a ...any) { fmt.Printf("! WARNING: "+f+"\n", a...) }
func done(f string, a ...any) { fmt.Printf("\n* "+f+"\n", a...) }
func fail(f string, a ...any) { fmt.Fprintf(os.Stderr, "\n! ERROR: "+f+"\n", a...) }

// dangerBox prints lines in a big red box.
func dangerBox(lines ...string) {
	w := 0
	for _, l := range lines {
		w = max(w, utf8.RuneCountInString(l))
	}
	red, reset := "\x1b[1;31m", "\x1b[0m"
	if !colors {
		red, reset = "", ""
	}
	fmt.Println()
	fmt.Println(red + "╔" + strings.Repeat("═", w+4) + "╗")
	for _, l := range lines {
		fmt.Println("║  " + l + strings.Repeat(" ", w-utf8.RuneCountInString(l)) + "  ║")
	}
	fmt.Println("╚" + strings.Repeat("═", w+4) + "╝" + reset)
}

// confirmErase shows the big red warning for d; true only if the user types
// YES (any case).
func confirmErase(d Disk) bool {
	dangerBox(
		"WARNING: EVERYTHING ON THIS USB DRIVE WILL BE ERASED",
		"",
		d.String(),
		"All the files on it will be lost. This cannot be undone.",
		"",
		"Type YES and press Enter to erase it. Anything else cancels.",
	)
	fmt.Printf("\n  Erase %s? Type YES: ", d.Name())
	answer, _ := stdin.ReadString('\n')
	return strings.EqualFold(strings.TrimSpace(answer), "yes")
}

func human(n int64) string {
	switch {
	case n >= 1e9:
		return fmt.Sprintf("%.1f GB", float64(n)/1e9)
	case n >= 1e6:
		return fmt.Sprintf("%.0f MB", float64(n)/1e6)
	default:
		return fmt.Sprintf("%d KB", n/1000)
	}
}

// progress prints one updating line: label, percent, amount, speed, time left.
type progress struct {
	label       string
	total, done int64
	start, last time.Time
}

func newProgress(label string, total, already int64) *progress {
	return &progress{label: label, total: total, done: already, start: time.Now()}
}

func (p *progress) Write(b []byte) (int, error) {
	p.add(int64(len(b)))
	return len(b), nil
}

func (p *progress) add(n int64) {
	p.done += n
	if time.Since(p.last) < 250*time.Millisecond {
		return
	}
	p.last = time.Now()
	p.print()
}

func (p *progress) print() {
	pct := 0.0
	if p.total > 0 {
		pct = 100 * float64(p.done) / float64(p.total)
	}
	secs := time.Since(p.start).Seconds()
	speed, left := "", ""
	if secs > 1 && p.done > 0 {
		rate := float64(p.done) / secs
		speed = human(int64(rate)) + "/s"
		if p.total > p.done && rate > 0 {
			left = (time.Duration(float64(p.total-p.done)/rate) * time.Second).String() + " left"
		}
	}
	fmt.Printf("\r  %s %5.1f%%  %s / %s  %s  %s      ", p.label, pct, human(p.done), human(p.total), speed, left)
}

func (p *progress) finish() {
	p.print()
	fmt.Println()
}

func diskNames(ds []Disk) string {
	s := make([]string, len(ds))
	for i, d := range ds {
		s[i] = d.String()
	}
	return strings.Join(s, ", ")
}
