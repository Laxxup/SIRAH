package sirah

import (
	"strings"
	"testing"
	"time"

	"github.com/Laxxup/SIRAH/internal/vision"
)

func TestContextBuilderMarksStalePerceptionAsUnavailable(t *testing.T) {
	contextData := Context{
		Perception:       &vision.PerceptionSnapshot{FaceVisible: true, PersonVisible: true, FaceCount: 1, UpdatedAt: time.Now().Add(-3 * time.Second)},
		PerceptionMaxAge: time.Second,
	}

	content := contextData.SystemContent()
	if !strings.Contains(content, "fresh=false") || !strings.Contains(content, "face_visible=false") || !strings.Contains(content, "face_count=0") {
		t.Fatalf("stale perception content = %q", content)
	}
}

func TestContextBuilderPreservesFreshPerception(t *testing.T) {
	contextData := Context{
		Perception:       &vision.PerceptionSnapshot{FaceVisible: true, PersonVisible: true, FaceCount: 1, UpdatedAt: time.Now()},
		PerceptionMaxAge: time.Second,
	}

	content := contextData.SystemContent()
	if !strings.Contains(content, "fresh=true") || !strings.Contains(content, "face_visible=true") || !strings.Contains(content, "person_visible=true") || !strings.Contains(content, "face_count=1") {
		t.Fatalf("fresh perception content = %q", content)
	}
}

func TestDefaultContextRequestsVariedSpeechAndOptionalGestures(t *testing.T) {
	if !strings.Contains(DefaultPersonality, "Evita repetir literalmente") {
		t.Fatal("default personality does not discourage repeated replies")
	}
	if !strings.Contains(DefaultActions, "blink o tired espontáneamente") {
		t.Fatal("default actions do not allow occasional expressive gestures")
	}
	if !strings.Contains(DefaultActions, "¿puedes parpadear?") || !strings.Contains(DefaultActions, "mírame") {
		t.Fatal("default actions lost direct blink or tracking requests")
	}
}
