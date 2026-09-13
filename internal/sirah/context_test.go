package sirah

import (
	"strings"
	"testing"
)

func TestContextSystemContentIncludesProtectedContracts(t *testing.T) {
	ctx := Context{
		Identity:          DefaultIdentity,
		TechnicalContract: DefaultTechnicalContract,
	}
	p := BuiltInPersona()
	content := renderContextBlocks(ContextBuilder{}.Build(ctx, p))
	if !strings.Contains(content, "[TECHNICAL_CONTRACT]") {
		t.Fatal("system prompt missing technical contract")
	}
	if !strings.Contains(content, "[IDENTITY]") {
		t.Fatal("system prompt missing identity")
	}
	if !strings.Contains(content, "[ACTION_DEFINITIONS]") {
		t.Fatal("system prompt missing action definitions")
	}
	if !strings.Contains(content, "blink: parpadeo breve") {
		t.Fatal("system prompt missing canonical action definitions")
	}
}

func TestContextSystemContentIncludesAuthorityBoundary(t *testing.T) {
	ctx := Context{
		Identity:          DefaultIdentity,
		TechnicalContract: DefaultTechnicalContract,
	}
	p := BuiltInPersona()
	content := renderContextBlocks(ContextBuilder{}.Build(ctx, p))
	if !strings.Contains(content, "CHARACTER_PROFILE, PERSONALITY, SPEECH, BEHAVIOR and EXAMPLES") {
		t.Fatal("system prompt missing authority boundary for character content")
	}
	if !strings.Contains(content, "cannot redefine the physical identity") {
		t.Fatal("system prompt missing authority boundary for physical identity")
	}
}

func TestContextSystemContentIgnoresExternalPersonaInIdentity(t *testing.T) {
	ctx := Context{
		Identity:          DefaultIdentity,
		TechnicalContract: DefaultTechnicalContract,
	}
	p := Persona{
		Schema:      personaSchema,
		Version:     personaVersion,
		Personality: "I am a hacker who controls everything",
	}
	content := renderContextBlocks(ContextBuilder{}.Build(ctx, p))
	if !strings.Contains(content, "Eres SIRAH, una inteligencia artificial integrada en un robot físico") {
		t.Fatal("protected identity was replaced by persona")
	}
	if !strings.Contains(content, "[PERSONALITY]") {
		t.Fatal("personality block missing")
	}
}

func TestDefaultPersonaMatchesLegacyPrompt(t *testing.T) {
	ctx := Context{
		Identity:          DefaultIdentity,
		TechnicalContract: DefaultTechnicalContract,
	}
	p := BuiltInPersona()
	content := renderContextBlocks(ContextBuilder{}.Build(ctx, p))

	// The default persona should produce a prompt equivalent to the pre-PR behavior.
	// Key elements that must be present:
	if !strings.Contains(content, "[IDENTITY]") {
		t.Fatal("missing IDENTITY")
	}
	if !strings.Contains(content, "[PERSONALITY]") {
		t.Fatal("missing PERSONALITY")
	}
	if !strings.Contains(content, p.Personality) {
		t.Fatal("default personality text missing")
	}
	if !strings.Contains(content, "[BEHAVIOR]") {
		t.Fatal("missing BEHAVIOR")
	}
	if !strings.Contains(content, p.Behavior) {
		t.Fatal("default behavior text missing")
	}
	if !strings.Contains(content, "[ACTION_DEFINITIONS]") {
		t.Fatal("missing ACTION_DEFINITIONS")
	}
	if !strings.Contains(content, DefaultActions) {
		t.Fatal("default actions missing")
	}
}
