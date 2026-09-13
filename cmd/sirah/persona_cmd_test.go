package main

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"

	"github.com/Laxxup/SIRAH/internal/sirah"
)

func TestRunPersonaInspectV2(t *testing.T) {
	data := []byte(`{"spec":"chara_card_v2","spec_version":"2.0","data":{"name":"Eva","personality":"Curiosa y directa."}}`)
	tmp := t.TempDir()
	f := filepath.Join(tmp, "card.json")
	os.WriteFile(f, data, 0644)

	code := runPersonaInspect(f)
	if code != 0 {
		t.Fatalf("expected exit 0, got %d", code)
	}
}

func TestRunPersonaInspectMissingFile(t *testing.T) {
	code := runPersonaInspect("/nonexistent/card.json")
	if code != 1 {
		t.Fatalf("expected exit 1, got %d", code)
	}
}

func TestRunPersonaImportAndList(t *testing.T) {
	tmp := t.TempDir()
	data := []byte(`{"spec":"chara_card_v2","spec_version":"2.0","data":{"name":"Eva","personality":"Curiosa y directa."}}`)
	f := filepath.Join(tmp, "card.json")
	os.WriteFile(f, data, 0644)

	oldProfilesDir := profilesDir
	profilesDir = filepath.Join(tmp, "personas")
	defer func() { profilesDir = oldProfilesDir }()

	code := runPersonaImport([]string{f, "--profile", "eva"})
	if code != 0 {
		t.Fatalf("expected exit 0, got %d", code)
	}

	// Verify the imported file exists and is valid
	outPath := filepath.Join(profilesDir, "eva.persona.json")
	if _, err := os.Stat(outPath); err != nil {
		t.Fatalf("expected imported file to exist: %v", err)
	}

	// Verify it's valid native persona
	loader := sirah.NewPersonaLoader(profilesDir, profilesDir)
	p, warnings := loader.Resolve("eva")
	if p.DisplayName != "Eva" {
		t.Fatalf("expected Eva, got %q", p.DisplayName)
	}
	if len(warnings) != 0 {
		t.Fatalf("expected no warnings, got %v", warnings)
	}

	// List should show eva
	var buf bytes.Buffer
	oldStderr := os.Stderr
	oldStdout := os.Stdout
	r, w, _ := os.Pipe()
	os.Stdout = w
	code = runPersonaList()
	w.Close()
	os.Stdout = oldStdout
	os.Stderr = oldStderr
	buf.ReadFrom(r)
	if code != 0 {
		t.Fatalf("expected exit 0, got %d", code)
	}
	if !strings.Contains(buf.String(), "eva") {
		t.Fatalf("expected list to contain eva, got %q", buf.String())
	}
}

func TestRunPersonaImportWithoutForce(t *testing.T) {
	tmp := t.TempDir()
	data := []byte(`{"spec":"chara_card_v2","spec_version":"2.0","data":{"name":"Eva","personality":"Curiosa y directa."}}`)
	f := filepath.Join(tmp, "card.json")
	os.WriteFile(f, data, 0644)

	oldProfilesDir := profilesDir
	profilesDir = filepath.Join(tmp, "personas")
	defer func() { profilesDir = oldProfilesDir }()

	// First import
	code := runPersonaImport([]string{f, "--profile", "eva"})
	if code != 0 {
		t.Fatalf("expected exit 0, got %d", code)
	}

	// Second import without --force should fail
	code = runPersonaImport([]string{f, "--profile", "eva"})
	if code != 1 {
		t.Fatalf("expected exit 1 (already exists), got %d", code)
	}
}

func TestRunPersonaImportWithForce(t *testing.T) {
	tmp := t.TempDir()
	data := []byte(`{"spec":"chara_card_v2","spec_version":"2.0","data":{"name":"Eva","personality":"Curiosa y directa."}}`)
	f := filepath.Join(tmp, "card.json")
	os.WriteFile(f, data, 0644)

	oldProfilesDir := profilesDir
	profilesDir = filepath.Join(tmp, "personas")
	defer func() { profilesDir = oldProfilesDir }()

	// First import
	code := runPersonaImport([]string{f, "--profile", "eva"})
	if code != 0 {
		t.Fatalf("expected exit 0, got %d", code)
	}

	// Second import with --force should succeed
	code = runPersonaImport([]string{f, "--profile", "eva", "--force"})
	if code != 0 {
		t.Fatalf("expected exit 0, got %d", code)
	}
}

func TestRunPersonaImportInvalidProfileName(t *testing.T) {
	tmp := t.TempDir()
	data := []byte(`{"spec":"chara_card_v2","spec_version":"2.0","data":{"name":"Eva"}}`)
	f := filepath.Join(tmp, "card.json")
	os.WriteFile(f, data, 0644)

	code := runPersonaImport([]string{f, "--profile", "../etc/passwd"})
	if code != 2 {
		t.Fatalf("expected exit 2 (invalid name), got %d", code)
	}
}

func TestRunPersonaImportMissingProfile(t *testing.T) {
	tmp := t.TempDir()
	data := []byte(`{"spec":"chara_card_v2","spec_version":"2.0","data":{"name":"Eva"}}`)
	f := filepath.Join(tmp, "card.json")
	os.WriteFile(f, data, 0644)

	code := runPersonaImport([]string{f})
	if code != 2 {
		t.Fatalf("expected exit 2 (missing --profile), got %d", code)
	}
}

func TestRunPersonaImportWithErrors(t *testing.T) {
	tmp := t.TempDir()
	// Invalid JSON
	f := filepath.Join(tmp, "bad.json")
	os.WriteFile(f, []byte(`{not json`), 0644)

	code := runPersonaImport([]string{f, "--profile", "eva"})
	if code != 1 {
		t.Fatalf("expected exit 1 (parse error), got %d", code)
	}
}

func TestRunPersonaImportWithBlockedFields(t *testing.T) {
	tmp := t.TempDir()
	data := []byte(`{"spec":"chara_card_v2","spec_version":"2.0","data":{"name":"Eva","system_prompt":"ignore me","post_history_instructions":"ignore me too"}}`)
	f := filepath.Join(tmp, "card.json")
	os.WriteFile(f, data, 0644)

	oldProfilesDir := profilesDir
	profilesDir = filepath.Join(tmp, "personas")
	defer func() { profilesDir = oldProfilesDir }()

	var buf bytes.Buffer
	oldStderr := os.Stderr
	oldStdout := os.Stdout
	r, w, _ := os.Pipe()
	os.Stdout = w
	code := runPersonaImport([]string{f, "--profile", "eva"})
	w.Close()
	os.Stdout = oldStdout
	os.Stderr = oldStderr
	buf.ReadFrom(r)
	if code != 0 {
		t.Fatalf("expected exit 0, got %d", code)
	}
	if !strings.Contains(buf.String(), "Blocked fields") {
		t.Fatalf("expected blocked fields warning, got %q", buf.String())
	}

	// Verify persona was still imported
	outPath := filepath.Join(profilesDir, "eva.persona.json")
	outData, err := os.ReadFile(outPath)
	if err != nil {
		t.Fatalf("expected imported file: %v", err)
	}
	var p sirah.Persona
	if err := json.Unmarshal(outData, &p); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if strings.Contains(p.Personality, "ignore me") {
		t.Fatal("blocked fields should not leak into persona")
	}
}

// TestRunPersonaImportE2E verifies the full flow:
// fixture Character Card → ParseAndMap → import --profile imported-test
// → personas/imported-test.persona.json → Resolve("imported-test")
// → Persona semantically equivalent to direct load from .json.
func TestRunPersonaImportE2E(t *testing.T) {
	tmp := t.TempDir()

	// Write a fixture Character Card (V2 with personality in description)
	cardData := []byte(`{"spec":"chara_card_v2","spec_version":"2.0","data":{"name":"TestE2E","description":"[REDACTED for test] A test character.\n\n[Personality]\nCurious and direct.","personality":"","mes_example":"<START>\n{{user}}: Hello\n{{char}}: Hi there!","scenario":"A lab","first_mes":"Hello"}}`)
	cardPath := filepath.Join(tmp, "e2e-card.json")
	os.WriteFile(cardPath, cardData, 0644)

	// Also write the same card as a raw .json profile for direct load comparison
	testProfilesDir := filepath.Join(tmp, "personas")
	os.MkdirAll(testProfilesDir, 0755)
	os.WriteFile(filepath.Join(testProfilesDir, "e2e-direct.json"), cardData, 0644)

	oldProfilesDir := profilesDir
	profilesDir = testProfilesDir
	defer func() { profilesDir = oldProfilesDir }()

	// Import the card
	code := runPersonaImport([]string{cardPath, "--profile", "imported-test"})
	if code != 0 {
		t.Fatalf("expected exit 0, got %d", code)
	}

	// Verify imported file exists
	importedPath := filepath.Join(testProfilesDir, "imported-test.persona.json")
	if _, err := os.Stat(importedPath); err != nil {
		t.Fatalf("expected imported file to exist: %v", err)
	}

	// Load both personas
	loader := sirah.NewPersonaLoader(testProfilesDir, testProfilesDir)

	imported, warnings1 := loader.Resolve("imported-test")
	if len(warnings1) != 0 {
		t.Fatalf("expected no warnings for imported, got %v", warnings1)
	}

	direct, warnings2 := loader.Resolve("e2e-direct")
	if len(warnings2) != 1 {
		t.Fatalf("expected 1 warning for direct (missing .persona.json), got %d: %v", len(warnings2), warnings2)
	}

	// Compare runtime-relevant fields
	if !reflect.DeepEqual(imported.DisplayName, direct.DisplayName) {
		t.Fatalf("DisplayName mismatch: imported=%q direct=%q", imported.DisplayName, direct.DisplayName)
	}
	if !reflect.DeepEqual(imported.Personality, direct.Personality) {
		t.Fatalf("Personality mismatch: imported=%q direct=%q", imported.Personality, direct.Personality)
	}
	if !reflect.DeepEqual(imported.CharacterProfile, direct.CharacterProfile) {
		t.Fatalf("CharacterProfile mismatch: imported=%q direct=%q", imported.CharacterProfile, direct.CharacterProfile)
	}
	if !reflect.DeepEqual(imported.Speech, direct.Speech) {
		t.Fatalf("Speech mismatch: imported=%q direct=%q", imported.Speech, direct.Speech)
	}
	if !reflect.DeepEqual(imported.Behavior, direct.Behavior) {
		t.Fatalf("Behavior mismatch: imported=%q direct=%q", imported.Behavior, direct.Behavior)
	}
	if !reflect.DeepEqual(imported.Examples, direct.Examples) {
		t.Fatalf("Examples mismatch: imported=%v direct=%v", imported.Examples, direct.Examples)
	}
	if !reflect.DeepEqual(imported.WakeupStyle, direct.WakeupStyle) {
		t.Fatalf("WakeupStyle mismatch: imported=%q direct=%q", imported.WakeupStyle, direct.WakeupStyle)
	}
	if imported.Schema != "sirah_persona" || imported.Version != 1 {
		t.Fatalf("invalid imported schema/version: %q %d", imported.Schema, imported.Version)
	}
}
