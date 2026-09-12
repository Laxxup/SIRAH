package voice

import (
	"context"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"time"
)

type Synthesizer interface {
	Synthesize(context.Context, string) ([]byte, error)
}

type Stub struct{}

func (Stub) Synthesize(_ context.Context, text string) ([]byte, error) { return []byte(text), nil }

type Piper struct {
	Command string
	Script  string
	Model   string
	client  *exec.Cmd
	stdin   io.WriteCloser
	stdout  io.ReadCloser
	mu      sync.Mutex
	ioMu    sync.Mutex
	closed  bool
	rate    int
}

type piperConfig struct {
	Audio struct {
		SampleRate int `json:"sample_rate"`
	} `json:"audio"`
}

const PiperVersion = "1.7.0"

func NewPiper(command, script, model string) (*Piper, error) {
	if command == "" {
		command = "python3"
	}
	if script == "" {
		script = "scripts/piper_server.py"
	}
	if model == "" {
		model = "models/voices/sirah.onnx"
	}
	if !commandAvailable(command) {
		return nil, fmt.Errorf("Piper command unavailable: %s", command)
	}
	if _, err := os.Stat(script); err != nil {
		return nil, fmt.Errorf("Piper server script unavailable: %w", err)
	}
	if _, err := os.Stat(model); err != nil {
		return nil, fmt.Errorf("Piper voice model unavailable: %w", err)
	}
	configPath := model + ".json"
	data, err := os.ReadFile(configPath)
	if err != nil {
		return nil, fmt.Errorf("Piper voice config unavailable: %w", err)
	}
	var config piperConfig
	if err := json.Unmarshal(data, &config); err != nil || config.Audio.SampleRate <= 0 {
		return nil, fmt.Errorf("Piper voice config has no valid audio.sample_rate")
	}
	return &Piper{Command: command, Script: script, Model: model, rate: config.Audio.SampleRate}, nil
}

func (p *Piper) Start(ctx context.Context) error {
	if p == nil {
		return fmt.Errorf("Piper is nil")
	}
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.client != nil {
		return nil
	}
	if p.closed {
		return fmt.Errorf("Piper is closed")
	}
	cmd := exec.CommandContext(ctx, p.Command, "-u", p.Script, "--model", p.Model)
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	stdin, err := cmd.StdinPipe()
	if err != nil {
		return err
	}
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		_ = stdin.Close()
		return err
	}
	cmd.Stderr = os.Stderr
	if err := cmd.Start(); err != nil {
		_ = stdin.Close()
		_ = stdout.Close()
		return fmt.Errorf("start Piper %s: %w", PiperVersion, err)
	}
	p.client, p.stdin, p.stdout = cmd, stdin, stdout
	return nil
}

func (p *Piper) SampleRate() int {
	if p == nil {
		return 0
	}
	return p.rate
}

func (p *Piper) Synthesize(ctx context.Context, text string) ([]byte, error) {
	var output []byte
	err := p.SynthesizeStream(ctx, text, func(chunk []byte) error {
		output = append(output, chunk...)
		return nil
	})
	return output, err
}

func (p *Piper) SynthesizeStream(ctx context.Context, text string, emit func([]byte) error) error {
	if strings.TrimSpace(text) == "" {
		return fmt.Errorf("Piper received empty text")
	}
	if emit == nil {
		return fmt.Errorf("Piper output callback is nil")
	}
	p.ioMu.Lock()
	defer p.ioMu.Unlock()
	stopWatcher := make(chan struct{})
	watcherDone := make(chan struct{})
	go func() {
		defer close(watcherDone)
		select {
		case <-ctx.Done():
			p.terminateProcess()
		case <-stopWatcher:
		}
	}()
	defer func() {
		close(stopWatcher)
		<-watcherDone
	}()
	p.mu.Lock()
	if p.client == nil || p.stdin == nil || p.stdout == nil {
		p.mu.Unlock()
		return fmt.Errorf("Piper is not started")
	}
	if p.closed {
		p.mu.Unlock()
		return fmt.Errorf("Piper is closed")
	}
	stdin, stdout := p.stdin, p.stdout
	p.mu.Unlock()
	if _, err := io.WriteString(stdin, strings.ReplaceAll(text, "\n", " ")+"\n"); err != nil {
		return fmt.Errorf("write Piper request: %w", err)
	}
	var length [4]byte
	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}
		if _, err := io.ReadFull(stdout, length[:]); err != nil {
			return fmt.Errorf("read Piper audio: %w", err)
		}
		size := binary.BigEndian.Uint32(length[:])
		if size == 0 {
			return nil
		}
		chunk := make([]byte, size)
		if _, err := io.ReadFull(stdout, chunk); err != nil {
			return fmt.Errorf("read Piper PCM: %w", err)
		}
		if err := emit(chunk); err != nil {
			return err
		}
	}
}

func (p *Piper) Close() error {
	if p == nil {
		return nil
	}
	p.mu.Lock()
	if p.closed {
		p.mu.Unlock()
		return nil
	}
	p.closed = true
	cmd, stdin, stdout := p.client, p.stdin, p.stdout
	p.mu.Unlock()
	if stdin != nil {
		_ = stdin.Close()
	}
	if stdout != nil {
		_ = stdout.Close()
	}
	if cmd == nil {
		return nil
	}
	done := make(chan error, 1)
	go func() { done <- cmd.Wait() }()
	select {
	case err := <-done:
		return err
	case <-time.After(500 * time.Millisecond):
		if cmd.Process != nil {
			_ = syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
		}
		return <-done
	}
}

func (p *Piper) terminateProcess() {
	p.mu.Lock()
	cmd, stdin, stdout := p.client, p.stdin, p.stdout
	p.client, p.stdin, p.stdout = nil, nil, nil
	p.mu.Unlock()
	if stdin != nil {
		_ = stdin.Close()
	}
	if stdout != nil {
		_ = stdout.Close()
	}
	if cmd != nil && cmd.Process != nil {
		_ = syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
		_ = cmd.Wait()
	}
}

type PCMPlayer struct {
	Command      string
	Device       string
	Rate         int
	OnStart      func(time.Duration)
	OnFirstWrite func(time.Duration)
	OnEvent      func(string, time.Time, int)
	cmd          *exec.Cmd
	stdin        io.WriteCloser
	mu           sync.Mutex
}

func NewPCMPlayer(command, device string, rate int) PCMPlayer {
	if command == "" {
		command = "aplay"
	}
	return PCMPlayer{Command: command, Device: device, Rate: rate}
}

func (p *PCMPlayer) Start() error {
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.cmd != nil {
		return nil
	}
	if p.Rate <= 0 {
		return fmt.Errorf("invalid PCM sample rate")
	}
	args := []string{"-q", "-f", "S16_LE", "-c", "1", "-r", fmt.Sprint(p.Rate), "-t", "raw"}
	if p.Device != "" {
		args = append([]string{"-D", p.Device}, args...)
	}
	cmd := exec.Command(p.Command, args...)
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	stdin, err := cmd.StdinPipe()
	if err != nil {
		return err
	}
	if err := cmd.Start(); err != nil {
		_ = stdin.Close()
		return fmt.Errorf("start PCM player: %w", err)
	}
	p.cmd, p.stdin = cmd, stdin
	return nil
}

func (p *PCMPlayer) Play(ctx context.Context, chunks <-chan []byte, prebuffer time.Duration) error {
	startedAt := time.Now()
	if err := p.Start(); err != nil {
		return err
	}
	if p.OnStart != nil {
		p.OnStart(time.Since(startedAt))
	}
	minimum := p.Rate * 2 * int(prebuffer) / int(time.Second)
	buffered := 0
	started := false
	wrote := false
	var preloaded []byte
	for {
		select {
		case <-ctx.Done():
			_ = p.Close()
			return ctx.Err()
		case chunk, ok := <-chunks:
			if !ok {
				if !started && len(preloaded) > 0 {
					started = true
					chunk = preloaded
					preloaded = nil
				} else {
					return p.finishPlayback()
				}
			}
			if !ok && len(chunk) == 0 {
				return nil
			}
			if len(chunk) == 0 {
				continue
			}
			if !started {
				buffered += len(chunk)
				preloaded = append(preloaded, chunk...)
				if buffered < minimum {
					continue
				}
				started = true
				chunk = preloaded
				preloaded = nil
			}
			if p.OnEvent != nil {
				p.OnEvent("pcm_dequeue", time.Now(), len(chunk))
			}
			writeBytes := p.Rate * 2 / 10
			if writeBytes < 2 {
				writeBytes = 2
			}
			for offset := 0; offset < len(chunk); {
				end := offset + writeBytes
				if end > len(chunk) {
					end = len(chunk)
				}
				piece := chunk[offset:end]
				firstWrite := !wrote
				if p.OnEvent != nil {
					p.OnEvent("speaker_write_start", time.Now(), len(piece))
				}
				p.mu.Lock()
				_, err := p.stdin.Write(piece)
				p.mu.Unlock()
				if p.OnEvent != nil {
					p.OnEvent("speaker_write_done", time.Now(), len(piece))
				}
				if firstWrite && p.OnFirstWrite != nil {
					p.OnFirstWrite(time.Since(startedAt))
				}
				wrote = true
				if err != nil {
					return fmt.Errorf("write PCM: %w", err)
				}
				offset = end
			}
		}
	}
}

func (p *PCMPlayer) Close() error {
	if p == nil {
		return nil
	}
	p.mu.Lock()
	cmd, stdin := p.cmd, p.stdin
	p.cmd, p.stdin = nil, nil
	p.mu.Unlock()
	if stdin != nil {
		_ = stdin.Close()
	}
	if cmd == nil {
		return nil
	}
	done := make(chan error, 1)
	go func() { done <- cmd.Wait() }()
	select {
	case err := <-done:
		return err
	case <-time.After(500 * time.Millisecond):
		if cmd.Process != nil {
			_ = syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
		}
		return <-done
	}
}

func (p *PCMPlayer) finishPlayback() error {
	if p == nil {
		return nil
	}
	p.mu.Lock()
	cmd, stdin := p.cmd, p.stdin
	p.cmd, p.stdin = nil, nil
	p.mu.Unlock()
	if stdin != nil {
		_ = stdin.Close()
	}
	if cmd == nil {
		return nil
	}
	return cmd.Wait()
}

type ConsoleSpeaker struct{}

func (ConsoleSpeaker) Play(_ context.Context, audio []byte) error {
	if len(audio) == 0 {
		return fmt.Errorf("speaker received empty audio")
	}
	fmt.Printf("Speaker: %d bytes\n", len(audio))
	return nil
}

func commandAvailable(command string) bool {
	if filepath.IsAbs(command) || strings.ContainsRune(command, filepath.Separator) {
		info, err := os.Stat(command)
		return err == nil && !info.IsDir()
	}
	_, err := exec.LookPath(command)
	return err == nil
}
