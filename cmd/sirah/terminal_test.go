package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/Laxxup/SIRAH/internal/voice"
)

// Run the real entry point in a fresh process, directory and environment.
// No local .env, audio tools or device paths are inherited.
func TestTerminalProcess(t *testing.T) {
	if os.Getenv("SIRAH_TEST_PROCESS") == "1" {
		if os.Getenv("SIRAH_TEST_CAPTURE") == "1" {
			ctx, cancel := context.WithTimeout(context.Background(), 5*time.Millisecond)
			defer cancel()
			runVoice(ctx, func(context.Context, string, time.Duration, time.Duration) {}, voice.NewRecorder("/nonexistent/arecord", "unused"), voice.Groq{}, false)
			os.Exit(0)
		}
		os.Args = append([]string{"sirah"}, os.Args[3:]...)
		main()
		return
	}
}

func TestCaptureFailureVisibleWithoutDebug(t *testing.T) {
	output, code := terminalProcess(t, "", []string{"SIRAH_TEST_CAPTURE=1"})
	if code != 0 || !strings.Contains(output, "Voice: WARNING") || !strings.Contains(output, "/nonexistent/arecord") {
		t.Fatalf("exit=%d output=%s", code, output)
	}
}

func TestVoiceRequiresPlaybackCommandBeforeStartingPiper(t *testing.T) {
	dir := t.TempDir()
	model := filepath.Join(dir, "voice.onnx")
	for path, content := range map[string]string{model: "test model", model + ".json": `{"audio":{"sample_rate":16000}}`} {
		if err := os.WriteFile(path, []byte(content), 0600); err != nil {
			t.Fatal(err)
		}
	}
	output, code := terminalProcess(t, "", []string{
		"LLM_API_KEY=test", "GROQ_API_KEY=test", "PIPER_COMMAND=/bin/true",
		"PIPER_SCRIPT=" + model, "PIPER_MODEL=" + model,
		"PIPER_AUDIO_COMMAND=/nonexistent/aplay",
	}, "-voice")
	if code != 1 || !strings.Contains(output, "PIPER_AUDIO_COMMAND") || strings.Contains(output, "shutdown timeout") {
		t.Fatalf("exit=%d output=%s", code, output)
	}
}

func terminalProcess(t *testing.T, input string, settings []string, args ...string) (string, int) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, os.Args[0], append([]string{"-test.run=^TestTerminalProcess$", "--"}, args...)...)
	cmd.Dir = t.TempDir()
	cmd.Env = append([]string{"SIRAH_TEST_PROCESS=1", "PATH=/nonexistent"}, settings...)
	cmd.Stdin = strings.NewReader(input)
	output, err := cmd.CombinedOutput()
	if ctx.Err() != nil {
		t.Fatalf("CLI did not terminate: %s", output)
	}
	if err != nil {
		if exit, ok := err.(*exec.ExitError); ok {
			return string(output), exit.ExitCode()
		}
		t.Fatal(err)
	}
	return string(output), 0
}

func TestTextConversationWithoutAudioOrHardware(t *testing.T) {
	requests := make(chan string, 2)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var request struct {
			Stream   bool `json:"stream"`
			Messages []struct {
				Content string `json:"content"`
			} `json:"messages"`
		}
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil || !request.Stream {
			t.Error("expected the existing streaming LLM request")
		}
		requests <- request.Messages[len(request.Messages)-1].Content
		chunk, _ := json.Marshal(map[string]any{"choices": []any{map[string]any{"delta": map[string]string{"content": `{"speech":"Hola. <blink>","actions":[]}`}}}})
		fmt.Fprintf(w, "data: %s\n\ndata: [DONE]\n\n", chunk)
	}))
	defer server.Close()
	output, code := terminalProcess(t, "hola\notra\n", []string{"LLM_API_KEY=test", "LLM_BASE_URL=" + server.URL, "STT_PREPROCESSOR=invalid", "PIPER_COMMAND=/missing"})
	if code != 0 || strings.Count(output, "Robot: Hola.") != 2 || !strings.Contains(output, "Ctrl+D") {
		t.Fatalf("exit=%d output=%s", code, output)
	}
	for _, unwanted := range []string{"Piper", "Vision:", "Firmware:", "<blink>", "CRITICAL"} {
		if strings.Contains(output, unwanted) {
			t.Errorf("unexpected %q in %s", unwanted, output)
		}
	}
	if len(requests) != 2 {
		t.Fatalf("requests=%d", len(requests))
	}
}

func TestTextProviderFailureReturnsNonzero(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "invalid test credential", http.StatusUnauthorized)
	}))
	defer server.Close()
	output, code := terminalProcess(t, "hola\n", []string{"LLM_API_KEY=test", "LLM_BASE_URL=" + server.URL})
	if code != 1 || !strings.Contains(output, "conversation failed") || strings.Contains(output, "Robot:") {
		t.Fatalf("exit=%d output=%s", code, output)
	}
}

func TestPreviewFlagPrecedenceOverVisionEnv(t *testing.T) {
	for _, tc := range []struct {
		preview       bool
		visionEnabled string
		want          bool
	}{
		{false, "", false},
		{false, "true", true},
		{true, "", true},
		{true, "false", true},
	} {
		t.Run(fmt.Sprintf("preview=%v/env=%q", tc.preview, tc.visionEnabled), func(t *testing.T) {
			if tc.visionEnabled != "" {
				t.Setenv("VISION_ENABLED", tc.visionEnabled)
			}
			if got := visionShouldStart(tc.preview); got != tc.want {
				t.Fatalf("visionShouldStart(%v) with VISION_ENABLED=%q = %v, want %v", tc.preview, tc.visionEnabled, got, tc.want)
			}
		})
	}
}

func TestCLIInitializationAndUsage(t *testing.T) {
	for _, tc := range []struct {
		name    string
		args    []string
		env     []string
		code    int
		message string
	}{
		{"help", []string{"--help"}, nil, 0, "Ejemplos:"},
		{"short help", []string{"-h"}, nil, 0, "Modo texto"},
		{"positional", []string{"hello"}, nil, 2, "unexpected positional"},
		{"missing key", nil, nil, 1, "LLM_API_KEY"},
		{"voice key", []string{"-voice"}, []string{"LLM_API_KEY=test"}, 1, "GROQ_API_KEY"},
		{"preprocessor", []string{"-voice"}, []string{"LLM_API_KEY=test", "GROQ_API_KEY=test", "STT_PREPROCESSOR=invalid"}, 1, "STT preprocessor"},
		{"piper", []string{"-voice"}, []string{"LLM_API_KEY=test", "GROQ_API_KEY=test"}, 1, "Piper command unavailable"},
		{"selftest", []string{"-selftest"}, nil, 1, "FIRMWARE_SERIAL"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			output, code := terminalProcess(t, "", tc.env, tc.args...)
			if code != tc.code || !strings.Contains(output, tc.message) || strings.Contains(output, "shutdown timeout") {
				t.Fatalf("exit=%d output=%s", code, output)
			}
		})
	}
}
