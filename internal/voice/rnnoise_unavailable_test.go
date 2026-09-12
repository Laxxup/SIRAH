//go:build !rnnoise

package voice

import "testing"

func TestRNNoiseRequiresOptionalBuild(t *testing.T) {
	if _, err := NewRecorderWithMode("arecord", "device", "rnnoise"); err == nil {
		t.Fatal("rnnoise was accepted without the optional build tag")
	}
}
