package voice

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestGroqLanguageSelection(t *testing.T) {
	seen := make(chan map[string]string, 2)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if err := r.ParseMultipartForm(1024 * 1024); err != nil {
			t.Fatal(err)
		}
		fields := map[string]string{}
		for key, values := range r.MultipartForm.Value {
			fields[key] = values[0]
		}
		seen <- fields
		_, _ = io.WriteString(w, `{"text":"ok"}`)
	}))
	defer server.Close()
	client := server.Client()
	groq := NewGroq("test", "whisper-large-v3-turbo", "es", server.URL, client)
	if _, err := groq.Transcribe(context.Background(), []byte("wav")); err != nil {
		t.Fatal(err)
	}
	if _, err := groq.TranscribeWithLanguage(context.Background(), []byte("wav"), ""); err != nil {
		t.Fatal(err)
	}
	es := <-seen
	auto := <-seen
	if es["language"] != "es" {
		t.Fatalf("es language = %q", es["language"])
	}
	if _, ok := auto["language"]; ok {
		t.Fatalf("auto request unexpectedly sent language=%q", auto["language"])
	}
	if es["model"] != "whisper-large-v3-turbo" || auto["response_format"] != "json" {
		t.Fatalf("unexpected fields: es=%v auto=%v", es, auto)
	}
}
