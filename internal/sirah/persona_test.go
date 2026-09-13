package sirah

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestResolveEmptyUsesDefault(t *testing.T) {
	dir := t.TempDir()
	loader := NewPersonaLoader(dir, dir)
	p, warnings := loader.Resolve("")
	if p.Schema != personaSchema {
		t.Fatalf("expected built-in persona, got schema %q", p.Schema)
	}
	if len(warnings) != 2 {
		t.Fatalf("expected 2 warnings, got %d: %v", len(warnings), warnings)
	}
}

func TestResolveCustomProfile(t *testing.T) {
	dir := t.TempDir()
	custom := Persona{
		Schema:      personaSchema,
		Version:     personaVersion,
		DisplayName: "Eva",
		Personality: "Custom personality",
	}
	data, _ := json.Marshal(custom)
	os.WriteFile(filepath.Join(dir, "eva.persona.json"), data, 0644)

	loader := NewPersonaLoader(dir, dir)
	p, warnings := loader.Resolve("eva")
	if p.DisplayName != "Eva" {
		t.Fatalf("expected Eva, got %q", p.DisplayName)
	}
	if len(warnings) != 0 {
		t.Fatalf("expected no warnings, got %v", warnings)
	}
}

func TestResolveMissingProfileFallsBack(t *testing.T) {
	dir := t.TempDir()
	loader := NewPersonaLoader(dir, dir)
	p, warnings := loader.Resolve("missing")
	if p.Schema != personaSchema {
		t.Fatalf("expected built-in fallback")
	}
	if len(warnings) != 2 {
		t.Fatalf("expected 2 warnings, got %d: %v", len(warnings), warnings)
	}
}

func TestResolveInvalidName(t *testing.T) {
	dir := t.TempDir()
	loader := NewPersonaLoader(dir, dir)
	p, warnings := loader.Resolve("../etc/passwd")
	if p.Schema != personaSchema {
		t.Fatalf("expected built-in fallback")
	}
	found := false
	for _, w := range warnings {
		if strings.Contains(w, "invalid profile name") {
			found = true
			break
		}
	}
	if !found {
		t.Fatalf("expected invalid profile name warning, got %v", warnings)
	}
}

func TestResolveDefaultFile(t *testing.T) {
	dir := t.TempDir()
	defaultP := Persona{
		Schema:      personaSchema,
		Version:     personaVersion,
		DisplayName: "DefaultTest",
		Personality: "Default personality",
	}
	data, _ := json.Marshal(defaultP)
	os.WriteFile(filepath.Join(dir, "default.persona.json"), data, 0644)

	loader := NewPersonaLoader(dir, dir)
	p, warnings := loader.Resolve("nonexistent")
	if p.DisplayName != "DefaultTest" {
		t.Fatalf("expected DefaultTest, got %q", p.DisplayName)
	}
	if len(warnings) != 1 {
		t.Fatalf("expected 1 warning (missing profile), got %d: %v", len(warnings), warnings)
	}
}

func TestResolveCustomInvalidFallsBackToDefault(t *testing.T) {
	dir := t.TempDir()
	// Write an invalid custom file
	os.WriteFile(filepath.Join(dir, "bad.persona.json"), []byte(`{"schema":"wrong"}`), 0644)
	// Write a valid default
	defaultP := Persona{
		Schema:      personaSchema,
		Version:     personaVersion,
		DisplayName: "DefaultTest",
		Personality: "Default personality",
	}
	data, _ := json.Marshal(defaultP)
	os.WriteFile(filepath.Join(dir, "default.persona.json"), data, 0644)

	loader := NewPersonaLoader(dir, dir)
	p, warnings := loader.Resolve("bad")
	if p.DisplayName != "DefaultTest" {
		t.Fatalf("expected DefaultTest fallback, got %q", p.DisplayName)
	}
	if len(warnings) != 1 {
		t.Fatalf("expected 1 warning (invalid custom), got %d: %v", len(warnings), warnings)
	}
}

func TestValidateSchemaWrong(t *testing.T) {
	p := Persona{Schema: "wrong", Version: personaVersion}
	err := validatePersona(&p)
	if err == nil || !strings.Contains(err.Error(), "invalid schema") {
		t.Fatalf("expected schema error, got %v", err)
	}
}

func TestValidateVersionWrong(t *testing.T) {
	p := Persona{Schema: personaSchema, Version: 2}
	err := validatePersona(&p)
	if err == nil || !strings.Contains(err.Error(), "invalid version") {
		t.Fatalf("expected version error, got %v", err)
	}
}

func TestValidateDisplayNameTooLong(t *testing.T) {
	p := Persona{
		Schema:      personaSchema,
		Version:     personaVersion,
		DisplayName: strings.Repeat("x", 65),
	}
	err := validatePersona(&p)
	if err == nil {
		t.Fatal("expected error for long display_name")
	}
}

func TestValidateExamplesTooMany(t *testing.T) {
	p := Persona{
		Schema:   personaSchema,
		Version:  personaVersion,
		Examples: make([]string, 11),
	}
	err := validatePersona(&p)
	if err == nil {
		t.Fatal("expected error for too many examples")
	}
}

func TestValidateUnknownField(t *testing.T) {
	dir := t.TempDir()
	data := []byte(`{"schema":"sirah_persona","version":1,"unknown_field":"x"}`)
	path := filepath.Join(dir, "test.json")
	os.WriteFile(path, data, 0644)

	loader := NewPersonaLoader(dir, dir)
	_, err := loader.tryLoad(path)
	if err == nil || !strings.Contains(err.Error(), "unknown field") {
		t.Fatalf("expected unknown field error, got %v", err)
	}
}

func TestDefaultPersonaFileMatchesBuiltIn(t *testing.T) {
	builtIn := BuiltInPersona()

	data, err := os.ReadFile("../../config/persona/default.persona.json")
	if err != nil {
		t.Skipf("default.persona.json not found: %v", err)
	}

	dec := json.NewDecoder(bytes.NewReader(data))
	dec.DisallowUnknownFields()
	var filePersona Persona
	if err := dec.Decode(&filePersona); err != nil {
		t.Fatalf("default.persona.json invalid: %v", err)
	}

	if filePersona.Schema != builtIn.Schema ||
		filePersona.Version != builtIn.Version ||
		filePersona.DisplayName != builtIn.DisplayName ||
		filePersona.Personality != builtIn.Personality ||
		filePersona.Behavior != builtIn.Behavior ||
		filePersona.WakeupStyle != builtIn.WakeupStyle {
		t.Fatal("default.persona.json does not match BuiltInPersona(); regenerate it")
	}
}

func TestBuiltInPersonaIsValid(t *testing.T) {
	p := BuiltInPersona()
	if err := validatePersona(&p); err != nil {
		t.Fatalf("BuiltInPersona() failed validation: %v", err)
	}
}

func TestResolveEmptyWithActive(t *testing.T) {
	dir := t.TempDir()
	active := Persona{
		Schema:      personaSchema,
		Version:     personaVersion,
		DisplayName: "ActiveTest",
		Personality: "Active personality",
	}
	data, _ := json.Marshal(active)
	os.WriteFile(filepath.Join(dir, "active.persona.json"), data, 0644)

	loader := NewPersonaLoader(dir, dir)
	p, warnings := loader.Resolve("")
	if p.DisplayName != "ActiveTest" {
		t.Fatalf("expected ActiveTest, got %q", p.DisplayName)
	}
	if len(warnings) != 0 {
		t.Fatalf("expected no warnings, got %v", warnings)
	}
}
