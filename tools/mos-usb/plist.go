package main

import (
	"bytes"
	"encoding/xml"
	"fmt"
	"strconv"
	"strings"
)

// parsePlist reads an XML property list into Go values: map[string]any,
// []any, string, int64, float64, bool.
func parsePlist(b []byte) (any, error) {
	dec := xml.NewDecoder(bytes.NewReader(b))
	for {
		tok, err := dec.Token()
		if err != nil {
			return nil, fmt.Errorf("plist: %w", err)
		}
		if se, ok := tok.(xml.StartElement); ok && se.Name.Local != "plist" {
			return plistValue(dec, se)
		}
	}
}

func plistValue(dec *xml.Decoder, se xml.StartElement) (any, error) {
	switch se.Name.Local {
	case "dict":
		m := map[string]any{}
		key := ""
		for {
			tok, err := dec.Token()
			if err != nil {
				return nil, err
			}
			switch t := tok.(type) {
			case xml.StartElement:
				if t.Name.Local == "key" {
					var k string
					if err := dec.DecodeElement(&k, &t); err != nil {
						return nil, err
					}
					key = k
					continue
				}
				v, err := plistValue(dec, t)
				if err != nil {
					return nil, err
				}
				m[key] = v
			case xml.EndElement:
				return m, nil
			}
		}
	case "array":
		var a []any
		for {
			tok, err := dec.Token()
			if err != nil {
				return nil, err
			}
			switch t := tok.(type) {
			case xml.StartElement:
				v, err := plistValue(dec, t)
				if err != nil {
					return nil, err
				}
				a = append(a, v)
			case xml.EndElement:
				return a, nil
			}
		}
	case "true", "false":
		dec.Skip()
		return se.Name.Local == "true", nil
	default:
		var s string
		if err := dec.DecodeElement(&s, &se); err != nil {
			return nil, err
		}
		switch se.Name.Local {
		case "integer":
			return strconv.ParseInt(strings.TrimSpace(s), 10, 64)
		case "real":
			return strconv.ParseFloat(strings.TrimSpace(s), 64)
		}
		return s, nil
	}
}
