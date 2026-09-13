package sirah

import (
	"encoding/json"
	"os"
	"strings"
	"testing"
	"unicode/utf8"
)

func loadFixture(t *testing.T, name string) []byte {
	t.Helper()
	data, err := os.ReadFile("testdata/" + name)
	if err != nil {
		t.Fatalf("load fixture %s: %v", name, err)
	}
	return data
}

func TestDetectV1(t *testing.T) {
	data := loadFixture(t, "card_v1.json")
	if f := DetectFormat(data); f != FormatV1 {
		t.Fatalf("expected V1, got %v", f)
	}
}

func TestDetectV2(t *testing.T) {
	data := loadFixture(t, "card_v2.json")
	if f := DetectFormat(data); f != FormatV2 {
		t.Fatalf("expected V2, got %v", f)
	}
}

func TestDetectV3(t *testing.T) {
	data := loadFixture(t, "card_v3.json")
	if f := DetectFormat(data); f != FormatV3 {
		t.Fatalf("expected V3, got %v", f)
	}
}

func TestDetectUnknown(t *testing.T) {
	if f := DetectFormat([]byte(`{"foo":"bar"}`)); f != FormatUnknown {
		t.Fatalf("expected Unknown, got %v", f)
	}
}

func TestParseV1Valid(t *testing.T) {
	data := loadFixture(t, "card_v1.json")
	p, result, err := ParseAndMap(data)
	if err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if p.DisplayName != "Eva" {
		t.Fatalf("display_name = %q", p.DisplayName)
	}
	if !strings.Contains(p.Personality, "Curiosa") {
		t.Fatalf("personality = %q", p.Personality)
	}
	if result.Format != FormatV1 {
		t.Fatalf("format = %v", result.Format)
	}
}

func TestParseV2Valid(t *testing.T) {
	data := loadFixture(t, "card_v2.json")
	p, result, err := ParseAndMap(data)
	if err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if p.DisplayName != "Eva" {
		t.Fatalf("display_name = %q", p.DisplayName)
	}
	if result.Format != FormatV2 {
		t.Fatalf("format = %v", result.Format)
	}
}

func TestParseV3Valid(t *testing.T) {
	data := loadFixture(t, "card_v3.json")
	p, result, err := ParseAndMap(data)
	if err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if p.DisplayName != "Evie" {
		t.Fatalf("expected nickname Evie, got %q", p.DisplayName)
	}
	if result.Format != FormatV3 {
		t.Fatalf("format = %v", result.Format)
	}
}

func TestParseCorruptJSON(t *testing.T) {
	_, _, err := ParseAndMap([]byte(`{not json`))
	if err == nil {
		t.Fatal("expected error for corrupt JSON")
	}
}

func TestMapSystemPromptBlocked(t *testing.T) {
	data := loadFixture(t, "card_v2.json")
	_, result, err := ParseAndMap(data)
	if err != nil {
		t.Fatalf("parse error: %v", err)
	}
	found := false
	for _, b := range result.Blocked {
		if b == "system_prompt" {
			found = true
			break
		}
	}
	if !found {
		t.Fatalf("system_prompt not blocked: %v", result.Blocked)
	}
}

func TestMapPostHistoryBlocked(t *testing.T) {
	data := loadFixture(t, "card_v2.json")
	_, result, err := ParseAndMap(data)
	if err != nil {
		t.Fatalf("parse error: %v", err)
	}
	found := false
	for _, b := range result.Blocked {
		if b == "post_history_instructions" {
			found = true
			break
		}
	}
	if !found {
		t.Fatalf("post_history_instructions not blocked: %v", result.Blocked)
	}
}

func TestMapPersonalityEmptyExtractFromDescription(t *testing.T) {
	data := loadFixture(t, "card_v2_personality_in_desc.json")
	p, result, err := ParseAndMap(data)
	if err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if !strings.Contains(p.Personality, "Curiosa y directa") {
		t.Fatalf("expected extracted personality, got %q", p.Personality)
	}
	if !strings.Contains(p.CharacterProfile, "Scenario") || !strings.Contains(p.CharacterProfile, "laboratorio") {
		t.Fatalf("expected remainder in character_profile, got %q", p.CharacterProfile)
	}
	found := false
	for _, c := range result.Converted {
		if strings.Contains(c, "description[Personality]") {
			found = true
			break
		}
	}
	if !found {
		t.Fatalf("expected conversion note, got %v", result.Converted)
	}
}

func TestMapMesExampleToExamples(t *testing.T) {
	data := loadFixture(t, "card_v1.json")
	p, _, err := ParseAndMap(data)
	if err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if len(p.Examples) != 1 {
		t.Fatalf("expected 1 example, got %d", len(p.Examples))
	}
	if !strings.Contains(p.Examples[0], "Hola, soy Eva") {
		t.Fatalf("example content = %q", p.Examples[0])
	}
}

func TestMapUnknownFieldsIgnored(t *testing.T) {
	data := []byte(`{"spec":"chara_card_v2","spec_version":"2.0","data":{"name":"X","personality":"Y","extra_field":"ignored"}}`)
	_, result, err := ParseAndMap(data)
	if err != nil {
		t.Fatalf("parse error: %v", err)
	}
	// extra_field is silently ignored; no error
	if len(result.Errors) > 0 {
		t.Fatalf("unexpected errors: %v", result.Errors)
	}
}

func TestMapLimitsEnforced(t *testing.T) {
	data := []byte(`{"spec":"chara_card_v2","spec_version":"2.0","data":{"name":"` + strings.Repeat("x", 100) + `","personality":"` + strings.Repeat("y", 9000) + `"}}`)
	p, result, err := ParseAndMap(data)
	if err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if utf8.RuneCountInString(p.DisplayName) != 64 {
		t.Fatalf("expected display_name truncated to 64, got %d", utf8.RuneCountInString(p.DisplayName))
	}
	if len(result.Warnings) == 0 {
		t.Fatal("expected truncation warning")
	}
}

func TestDirectLoadEqualsImportResult(t *testing.T) {
	data := loadFixture(t, "card_v2.json")
	p1, _, err := ParseAndMap(data)
	if err != nil {
		t.Fatalf("direct load error: %v", err)
	}

	// Simulate import: save to file, load as native
	dir := t.TempDir()
	path := dir + "/eva.persona.json"
	b, _ := json.Marshal(p1)
	os.WriteFile(path, b, 0644)

	loader := NewPersonaLoader(dir, dir)
	p2, _ := loader.tryLoad(path)

	if p1.DisplayName != p2.DisplayName || p1.Personality != p2.Personality {
		t.Fatal("direct load and import produced different personas")
	}
}

func TestMapScenarioIgnored(t *testing.T) {
	data := loadFixture(t, "card_v2.json")
	_, result, err := ParseAndMap(data)
	if err != nil {
		t.Fatalf("parse error: %v", err)
	}
	found := false
	for _, i := range result.Ignored {
		if i == "scenario" {
			found = true
			break
		}
	}
	if !found {
		t.Fatalf("scenario not ignored: %v", result.Ignored)
	}
}

func TestMapFirstMesIgnored(t *testing.T) {
	data := loadFixture(t, "card_v2.json")
	_, result, err := ParseAndMap(data)
	if err != nil {
		t.Fatalf("parse error: %v", err)
	}
	found := false
	for _, i := range result.Ignored {
		if i == "first_mes" {
			found = true
			break
		}
	}
	if !found {
		t.Fatalf("first_mes not ignored: %v", result.Ignored)
	}
}

func TestMapPersonalityEmptyWarning(t *testing.T) {
	data := []byte(`{"spec":"chara_card_v2","spec_version":"2.0","data":{"name":"X","description":"No personality here.","personality":""}}`)
	_, result, err := ParseAndMap(data)
	if err != nil {
		t.Fatalf("parse error: %v", err)
	}
	found := false
	for _, w := range result.Warnings {
		if strings.Contains(w, "personality is empty") {
			found = true
			break
		}
	}
	if !found {
		t.Fatalf("expected empty personality warning, got %v", result.Warnings)
	}
}
