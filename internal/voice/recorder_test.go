package voice

import "testing"

func TestNewRecorderWithModeRaw(t *testing.T) {
	recorder, err := NewRecorderWithMode("arecord", "device", "raw")
	if err != nil {
		t.Fatal(err)
	}
	defer recorder.Close()
	if recorder.CaptureRate != 16000 || recorder.Preprocessor.InputRate() != 16000 || recorder.Preprocessor.OutputRate() != 16000 {
		t.Fatalf("raw rates = capture %d, input %d, output %d", recorder.CaptureRate, recorder.Preprocessor.InputRate(), recorder.Preprocessor.OutputRate())
	}
}

func TestNewRecorderWithModeRejectsUnknownMode(t *testing.T) {
	if _, err := NewRecorderWithMode("arecord", "device", "unknown"); err == nil {
		t.Fatal("accepted an unknown STT preprocessor")
	}
}

func TestEmptyDeviceUsesSystemDefault(t *testing.T) {
	recorder, err := NewRecorderWithMode("arecord", "", "raw")
	if err != nil {
		t.Fatal(err)
	}
	defer recorder.Close()
	if recorder.Device != "" {
		t.Fatalf("empty device should remain empty for ALSA default, got %q", recorder.Device)
	}
}

func TestExplicitDeviceIsPreserved(t *testing.T) {
	recorder, err := NewRecorderWithMode("arecord", "plughw:CARD=USB,DEV=0", "raw")
	if err != nil {
		t.Fatal(err)
	}
	defer recorder.Close()
	if recorder.Device != "plughw:CARD=USB,DEV=0" {
		t.Fatalf("explicit device not preserved, got %q", recorder.Device)
	}
}
