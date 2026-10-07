package main

import "testing"

func TestParsePlist(t *testing.T) {
	v, err := parsePlist([]byte(`<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>WholeDisks</key><array><string>disk4</string><string>disk5</string></array>
  <key>TotalSize</key><integer>32017047552</integer>
  <key>Internal</key><false/>
  <key>BusProtocol</key><string>USB</string>
  <key>Partitions</key><array><dict><key>Size</key><integer>1</integer></dict></array>
</dict></plist>`))
	if err != nil {
		t.Fatal(err)
	}
	m := v.(map[string]any)
	if w := m["WholeDisks"].([]any); len(w) != 2 || w[1] != "disk5" {
		t.Fatal(w)
	}
	if m["TotalSize"].(int64) != 32017047552 || m["Internal"].(bool) || m["BusProtocol"] != "USB" {
		t.Fatal(m)
	}
}
