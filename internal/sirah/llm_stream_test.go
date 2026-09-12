package sirah

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestSpeechStreamParserEmitsOnlySpeech(t *testing.T) {
	parser := &speechStreamParser{}
	var got strings.Builder
	for _, fragment := range []string{`{"speech":"Hola, `, `mundo","actions":["nod"]}`} {
		if err := parser.Feed(fragment, func(value string) error { got.WriteString(value); return nil }); err != nil {
			t.Fatal(err)
		}
	}
	if got.String() != "Hola, mundo" {
		t.Fatalf("speech = %q", got.String())
	}
}

func TestLLMStreamUsesSSEAndValidatesCompleteResponse(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if got := r.Header.Get("X-Test-Session"); got != "session-123" {
			t.Errorf("X-Test-Session = %q", got)
		}
		var request map[string]any
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			t.Fatal(err)
		}
		if request["stream"] != true {
			t.Fatal("stream flag missing")
		}
		w.Header().Set("Content-Type", "text/event-stream")
		writeEvent := func(content string) {
			event := map[string]any{"choices": []any{map[string]any{"delta": map[string]any{"content": content}}}}
			encoded, _ := json.Marshal(event)
			_, _ = w.Write(append(append([]byte("data: "), encoded...), []byte("\n\n")...))
		}
		writeEvent(`{"speech":"Buenos `)
		writeEvent(`días","actions":[]}`)
		_, _ = w.Write([]byte("data: [DONE]\n\n"))
	}))
	defer server.Close()

	llm := NewOpenAICompatibleLLM("key", "model", server.URL, server.Client())
	llm.RequestHeaders = map[string]string{"X-Test-Session": "session-123"}
	var speech strings.Builder
	response, err := llm.Stream(context.Background(), Context{UserInput: "hola"}, func(value string) error { speech.WriteString(value); return nil })
	if err != nil {
		t.Fatal(err)
	}
	if response.Speech != "Buenos días" || speech.String() != response.Speech {
		t.Fatalf("response=%#v streamed=%q", response, speech.String())
	}
}

func TestNemotronStreamUsesPlainSpeechAndDisablesActions(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var request map[string]any
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			t.Fatal(err)
		}
		if _, ok := request["response_format"]; ok {
			t.Fatal("Nemotron must not receive response_format")
		}
		w.Header().Set("Content-Type", "text/event-stream")
		for _, content := range []string{"Hola, ", "puedo hacer blink, pero no ejecutaré acciones."} {
			event := map[string]any{"choices": []any{map[string]any{"delta": map[string]any{"content": content}}}}
			encoded, _ := json.Marshal(event)
			_, _ = w.Write(append(append([]byte("data: "), encoded...), []byte("\n\n")...))
		}
		_, _ = w.Write([]byte("data: [DONE]\n\n"))
	}))
	defer server.Close()

	llm := NewOpenAICompatibleLLM("key", "nemotron-3-nano:30b", server.URL, server.Client())
	var speech strings.Builder
	response, err := llm.Stream(context.Background(), Context{UserInput: "hola"}, func(value string) error { speech.WriteString(value); return nil })
	if err != nil {
		t.Fatal(err)
	}
	if response.Speech != speech.String() || len(response.Actions) != 0 {
		t.Fatalf("response=%#v streamed=%q", response, speech.String())
	}
}
