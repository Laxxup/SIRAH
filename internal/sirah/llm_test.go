package sirah

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestLLMSchemaIncludesTiredAction(t *testing.T) {
	llm := NewOpenAICompatibleLLM("key", "model", "https://example.com/v1", http.DefaultClient)
	payload, err := llm.requestPayload(Context{TechnicalContract: "contract", UserInput: "hola"}, true)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Contains(payload, []byte(`"tired"`)) {
		t.Fatalf("schema does not include tired: %s", payload)
	}
}

func TestLLMIgnoresSeparateReasoningField(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{"choices": []any{map[string]any{"message": map[string]any{"content": `{"speech":"respuesta visible","actions":[]}`, "reasoning": "secreto interno"}}}})
	}))
	defer server.Close()

	llm := NewOpenAICompatibleLLM("test-key", "test-model", server.URL, server.Client())
	response, err := llm.Complete(context.Background(), Context{TechnicalContract: DefaultTechnicalContract, UserInput: "hola"})
	if err != nil {
		t.Fatal(err)
	}
	if response.Speech != "respuesta visible" {
		t.Fatalf("speech = %q", response.Speech)
	}
	if response.Speech == "secreto interno" {
		t.Fatal("reasoning reached speech")
	}
}

func TestLLMRejectsMarkdownWrappedResponse(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{"choices": []any{map[string]any{"message": map[string]any{"content": "```json\n{\"speech\":\"respuesta\",\"actions\":[]}\n```"}}}})
	}))
	defer server.Close()

	llm := NewOpenAICompatibleLLM("test-key", "test-model", server.URL, server.Client())
	response, err := llm.Complete(context.Background(), Context{TechnicalContract: DefaultTechnicalContract, UserInput: "hola"})
	if err != nil || response.Speech != "respuesta" {
		t.Fatalf("response=%#v, err=%v", response, err)
	}
}

func TestLLMRejectsTextOutsideMarkdownFence(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{"choices": []any{map[string]any{"message": map[string]any{"content": "antes\n```json\n{\"speech\":\"respuesta\",\"actions\":[]}\n```"}}}})
	}))
	defer server.Close()

	llm := NewOpenAICompatibleLLM("test-key", "test-model", server.URL, server.Client())
	if _, err := llm.Complete(context.Background(), Context{TechnicalContract: DefaultTechnicalContract, UserInput: "hola"}); err == nil {
		t.Fatal("expected text outside markdown fence to be rejected")
	}
}

func requestTemperature(t *testing.T, env string) any {
	t.Helper()
	t.Setenv("LLM_TEMPERATURE", env)
	var got any
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var payload map[string]any
		if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
			t.Error(err)
		}
		got = payload["temperature"]
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{"choices": []any{map[string]any{"message": map[string]any{"content": `{"speech":"hola","actions":[]}`}}}})
	}))
	defer server.Close()
	llm := NewOpenAICompatibleLLM("test-key", "test-model", server.URL, server.Client())
	if _, err := llm.Complete(context.Background(), Context{TechnicalContract: DefaultTechnicalContract, UserInput: "hola"}); err != nil {
		t.Fatal(err)
	}
	return got
}

func TestLLMTemperatureDefaultsToZero(t *testing.T) {
	if got := requestTemperature(t, ""); got != float64(0) {
		t.Fatalf("temperature = %v, want 0", got)
	}
}

func TestLLMTemperatureFromEnv(t *testing.T) {
	if got := requestTemperature(t, "0.55"); got != float64(0.55) {
		t.Fatalf("temperature = %v, want 0.55", got)
	}
}

func TestLLMTemperatureRejectsOutOfRange(t *testing.T) {
	if got := requestTemperature(t, "5"); got != float64(0) {
		t.Fatalf("temperature = %v, want 0", got)
	}
}

func TestLLMReasoningEffortDefaultsToNone(t *testing.T) {
	t.Setenv("LLM_REASONING_EFFORT", "")
	llm := NewOpenAICompatibleLLM("key", "model", "https://example.com/v1", http.DefaultClient)
	if llm.ReasoningEffort != "none" {
		t.Fatalf("reasoning effort = %q, want none", llm.ReasoningEffort)
	}
}

func TestLLMCompleteSendsConfiguredRequestHeaders(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if got := r.Header.Get("X-Test-Session"); got != "session-123" {
			t.Errorf("X-Test-Session = %q", got)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"{\"speech\":\"hola\",\"actions\":[]}"}}]}`))
	}))
	defer server.Close()

	llm := NewOpenAICompatibleLLM("key", "model", server.URL, server.Client())
	llm.RequestHeaders = map[string]string{"X-Test-Session": "session-123"}
	if _, err := llm.Complete(context.Background(), Context{UserInput: "hola"}); err != nil {
		t.Fatal(err)
	}
}
