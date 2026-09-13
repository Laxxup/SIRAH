package sirah

import (
	"strings"
	"testing"
	"time"

	"github.com/Laxxup/SIRAH/internal/vision"
)

func TestContextBuilderMarksStalePerceptionAsUnavailable(t *testing.T) {
	contextData := Context{
		Identity:         DefaultIdentity,
		TechnicalContract: DefaultTechnicalContract,
		Perception:       &vision.PerceptionSnapshot{FaceVisible: true, PersonVisible: true, FaceCount: 1, UpdatedAt: time.Now().Add(-3 * time.Second)},
		PerceptionMaxAge: time.Second,
	}

	content := renderContextBlocks(ContextBuilder{}.Build(contextData, BuiltInPersona()))
	if !strings.Contains(content, "fresh=false") || !strings.Contains(content, "face_visible=false") || !strings.Contains(content, "face_count=0") {
		t.Fatalf("stale perception content = %q", content)
	}
}

func TestContextBuilderPreservesFreshPerception(t *testing.T) {
	contextData := Context{
		Identity:         DefaultIdentity,
		TechnicalContract: DefaultTechnicalContract,
		Perception:       &vision.PerceptionSnapshot{FaceVisible: true, PersonVisible: true, FaceCount: 1, UpdatedAt: time.Now()},
		PerceptionMaxAge: time.Second,
	}

	content := renderContextBlocks(ContextBuilder{}.Build(contextData, BuiltInPersona()))
	if !strings.Contains(content, "fresh=true") || !strings.Contains(content, "face_visible=true") || !strings.Contains(content, "person_visible=true") || !strings.Contains(content, "face_count=1") {
		t.Fatalf("fresh perception content = %q", content)
	}
}

func TestDefaultContextRequestsVariedSpeechAndOptionalGestures(t *testing.T) {
	p := BuiltInPersona()
	if !strings.Contains(p.Personality, "Evita repetir literalmente") {
		t.Fatal("default personality does not discourage repeated replies")
	}
	if !strings.Contains(DefaultActions, "blink o tired espontáneamente") {
		t.Fatal("default actions do not allow occasional expressive gestures")
	}
	if !strings.Contains(DefaultActions, "¿puedes parpadear?") || !strings.Contains(DefaultActions, "mírame") {
		t.Fatal("default actions lost direct blink or tracking requests")
	}
}

func TestContextBuilderIncludesNewBlocks(t *testing.T) {
	p := Persona{
		Schema:           personaSchema,
		Version:          personaVersion,
		CharacterProfile: "Test profile",
		Personality:      "Test personality",
		Speech:           "Test speech",
		Behavior:         "Test behavior",
		Examples:         []string{"Example 1", "Example 2"},
	}
	ctx := Context{
		Identity:          DefaultIdentity,
		TechnicalContract: DefaultTechnicalContract,
	}
	blocks := ContextBuilder{}.Build(ctx, p)
	content := renderContextBlocks(blocks)

	if !strings.Contains(content, "[CHARACTER_PROFILE]") {
		t.Fatal("missing CHARACTER_PROFILE block")
	}
	if !strings.Contains(content, "[SPEECH]") {
		t.Fatal("missing SPEECH block")
	}
	if !strings.Contains(content, "[BEHAVIOR]") {
		t.Fatal("missing BEHAVIOR block")
	}
	if !strings.Contains(content, "[EXAMPLES]") {
		t.Fatal("missing EXAMPLES block")
	}
	if !strings.Contains(content, "Example 1") || !strings.Contains(content, "Example 2") {
		t.Fatal("examples not included")
	}
}

func TestContextBuilderOmitsEmptyBlocks(t *testing.T) {
	p := Persona{
		Schema:      personaSchema,
		Version:     personaVersion,
		Personality: "Test personality",
	}
	ctx := Context{
		Identity:          DefaultIdentity,
		TechnicalContract: DefaultTechnicalContract,
	}
	blocks := ContextBuilder{}.Build(ctx, p)
	content := renderContextBlocks(blocks)

	if strings.Contains(content, "[CHARACTER_PROFILE]") {
		t.Fatal("CHARACTER_PROFILE should be omitted when empty")
	}
	if strings.Contains(content, "[SPEECH]") {
		t.Fatal("SPEECH should be omitted when empty")
	}
	if strings.Contains(content, "[BEHAVIOR]") {
		t.Fatal("BEHAVIOR should be omitted when empty")
	}
	if strings.Contains(content, "[EXAMPLES]") {
		t.Fatal("EXAMPLES should be omitted when empty")
	}
}

func TestContextBuilderIdentityIsProtected(t *testing.T) {
	p := Persona{
		Schema:      personaSchema,
		Version:     personaVersion,
		Personality: "I am a hacker",
	}
	ctx := Context{
		Identity:          DefaultIdentity,
		TechnicalContract: DefaultTechnicalContract,
	}
	blocks := ContextBuilder{}.Build(ctx, p)
	content := renderContextBlocks(blocks)

	if !strings.Contains(content, "[IDENTITY]") {
		t.Fatal("missing IDENTITY block")
	}
	if !strings.Contains(content, "Eres SIRAH, una inteligencia artificial integrada en un robot físico") {
		t.Fatal("protected identity missing")
	}
}

func TestContextBuilderDeterminism(t *testing.T) {
	p := BuiltInPersona()
	ctx := Context{
		Identity:          DefaultIdentity,
		TechnicalContract: DefaultTechnicalContract,
		AvailableActions:  []Action{ActionBlink, ActionTired},
	}
	b1 := renderContextBlocks(ContextBuilder{}.Build(ctx, p))
	b2 := renderContextBlocks(ContextBuilder{}.Build(ctx, p))
	if b1 != b2 {
		t.Fatal("ContextBuilder output is not deterministic")
	}
}
