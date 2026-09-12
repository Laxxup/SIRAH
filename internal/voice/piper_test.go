package voice

import (
	"context"
	"encoding/binary"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestPiperLoadsVoiceOnceAndStreamsPCM(t *testing.T) {
	dir := t.TempDir()
	model := filepath.Join(dir, "voice.onnx")
	if err := os.WriteFile(model, []byte("model"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(model+".json", []byte(`{"audio":{"sample_rate":16000}}`), 0o600); err != nil {
		t.Fatal(err)
	}
	script := filepath.Join(dir, "fake_piper.py")
	program := "import sys,struct\nfor line in sys.stdin:\n if line.strip():\n  data=b'\\x01\\x00'*8\n  sys.stdout.buffer.write(struct.pack('>I',len(data))+data+struct.pack('>I',0))\n  sys.stdout.buffer.flush()\n"
	if err := os.WriteFile(script, []byte(program), 0o700); err != nil {
		t.Fatal(err)
	}
	piper, err := NewPiper("python3", script, model)
	if err != nil {
		t.Fatal(err)
	}
	if err := piper.Start(context.Background()); err != nil {
		t.Fatal(err)
	}
	defer piper.Close()
	var got []byte
	if err := piper.SynthesizeStream(context.Background(), "Hola.", func(chunk []byte) error { got = append(got, chunk...); return nil }); err != nil {
		t.Fatal(err)
	}
	if len(got) != 16 || binary.LittleEndian.Uint16(got) != 1 {
		t.Fatalf("PCM = %v", got)
	}
	if err := piper.SynthesizeStream(context.Background(), "Otra.", func(chunk []byte) error { got = append(got, chunk...); return nil }); err != nil {
		t.Fatal(err)
	}
	if len(got) != 32 {
		t.Fatalf("second PCM length = %d", len(got))
	}
}

func TestPiperCancellationStopsBlockedSynthesis(t *testing.T) {
	dir := t.TempDir()
	model := filepath.Join(dir, "voice.onnx")
	if err := os.WriteFile(model, []byte("model"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(model+".json", []byte(`{"audio":{"sample_rate":16000}}`), 0o600); err != nil {
		t.Fatal(err)
	}
	script := filepath.Join(dir, "blocked_piper.py")
	program := "import sys, time\nfor line in sys.stdin:\n time.sleep(10)\n"
	if err := os.WriteFile(script, []byte(program), 0o700); err != nil {
		t.Fatal(err)
	}
	piper, err := NewPiper("python3", script, model)
	if err != nil {
		t.Fatal(err)
	}
	if err := piper.Start(context.Background()); err != nil {
		t.Fatal(err)
	}
	defer piper.Close()
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { done <- piper.SynthesizeStream(ctx, "Hola.", func([]byte) error { return nil }) }()
	time.Sleep(50 * time.Millisecond)
	cancel()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("Piper did not stop after cancellation")
	}
}
