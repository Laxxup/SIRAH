package voice

import (
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestPCMPlayerFlushesShortPrebufferAndKeepsPCM(t *testing.T) {
	dir := t.TempDir()
	output := filepath.Join(dir, "pcm")
	command := filepath.Join(dir, "player")
	program := "#!/bin/sh\ncat > '" + output + "'\n"
	if err := os.WriteFile(command, []byte(program), 0o700); err != nil {
		t.Fatal(err)
	}
	player := NewPCMPlayer(command, "", 16000)
	chunks := make(chan []byte, 1)
	chunks <- []byte{1, 2, 3, 4}
	close(chunks)
	if err := player.Play(context.Background(), chunks, 80*time.Millisecond); err != nil {
		t.Fatal(err)
	}
	_ = player.Close()
	data, err := os.ReadFile(output)
	if err != nil {
		t.Fatal(err)
	}
	if string(data) != string([]byte{1, 2, 3, 4}) {
		t.Fatalf("PCM = %v", data)
	}
}

func TestPCMPlayerCancellationStopsPlayback(t *testing.T) {
	dir := t.TempDir()
	command := filepath.Join(dir, "player")
	if err := os.WriteFile(command, []byte("#!/bin/sh\nsleep 10\n"), 0o700); err != nil {
		t.Fatal(err)
	}
	player := NewPCMPlayer(command, "", 16000)
	chunks := make(chan []byte)
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { done <- player.Play(ctx, chunks, 0) }()
	time.Sleep(50 * time.Millisecond)
	cancel()
	select {
	case err := <-done:
		if err == nil {
			t.Fatal("expected cancellation")
		}
	case <-time.After(time.Second):
		t.Fatal("PCM player did not stop")
	}
}
