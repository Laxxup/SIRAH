package voice

import (
	"context"
	"errors"
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

type failingPCMWriter struct{}

func (failingPCMWriter) Write([]byte) (int, error) { return 0, errors.New("write failed") }
func (failingPCMWriter) Close() error              { return nil }

func TestPCMPlayerRecoversAfterWriteError(t *testing.T) {
	dir := t.TempDir()
	command := filepath.Join(dir, "player")
	if err := os.WriteFile(command, []byte("#!/bin/sh\nexit 0\n"), 0o700); err != nil {
		t.Fatal(err)
	}
	player := NewPCMPlayer(command, "", 16000)
	if err := player.Start(); err != nil {
		t.Fatal(err)
	}
	firstCommand := player.cmd
	player.mu.Lock()
	player.stdin = failingPCMWriter{}
	player.mu.Unlock()

	chunks := make(chan []byte, 1)
	chunks <- []byte{1, 2}
	close(chunks)
	if err := player.Play(context.Background(), chunks, 0); err == nil {
		t.Fatal("expected PCM write error")
	}
	if player.cmd != nil || player.stdin != nil {
		t.Fatal("PCM player state was not cleared after write error")
	}
	if err := player.Start(); err != nil {
		t.Fatal(err)
	}
	if player.cmd == nil || player.cmd == firstCommand {
		t.Fatal("PCM player did not start a fresh process after write error")
	}
	_ = player.Close()
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
