//go:build rnnoise

package voice

import (
	"bytes"
	"testing"
)

func TestRNNoisePreprocessorUsesNativeFrameAndResamples(t *testing.T) {
	preprocessor, err := NewRNNoisePreprocessor()
	if err != nil {
		t.Fatal(err)
	}
	defer preprocessor.Close()
	if preprocessor.InputRate() != 48000 || preprocessor.OutputRate() != 16000 {
		t.Fatalf("rates = %d -> %d", preprocessor.InputRate(), preprocessor.OutputRate())
	}
	if _, err := preprocessor.Process(make([]byte, 320)); err == nil {
		t.Fatal("accepted a non-48 kHz RNNoise frame")
	}
	input := bytes.Repeat([]byte{0x40, 0x00}, 480)
	outputLength := 0
	for i := 0; i < 30; i++ {
		output, err := preprocessor.Process(input)
		if err != nil {
			t.Fatal(err)
		}
		if len(output)%2 != 0 {
			t.Fatalf("invalid resampled output length: %d", len(output))
		}
		if i < 3 {
			t.Logf("frame %d output bytes=%d", i, len(output))
		}
		outputLength += len(output)
	}
	if outputLength == 0 {
		t.Fatal("resampler produced no output after 30 frames")
	}
	if outputLength < 8000 || outputLength > 10000 {
		t.Fatalf("unexpected output duration after 300 ms: %d bytes", outputLength)
	}
}
