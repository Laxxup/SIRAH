package sirah

import (
	"encoding/json"
	"fmt"
	"strings"
	"unicode/utf8"
)

// CardFormat identifies a Character Card version.
type CardFormat int

const (
	FormatUnknown CardFormat = iota
	FormatV1
	FormatV2
	FormatV3
)

func (f CardFormat) String() string {
	switch f {
	case FormatV1:
		return "V1"
	case FormatV2:
		return "V2"
	case FormatV3:
		return "V3"
	default:
		return "unknown"
	}
}

// DetectFormat inspects raw JSON bytes to determine the Character Card version.
func DetectFormat(data []byte) CardFormat {
	var envelope struct {
		Spec string `json:"spec"`
	}
	if err := json.Unmarshal(data, &envelope); err == nil {
		switch envelope.Spec {
		case "chara_card_v3":
			return FormatV3
		case "chara_card_v2":
			return FormatV2
		}
	}
	// V1 has no "spec" and no "data" wrapper.
	var v1 struct {
		Name string `json:"name"`
	}
	if err := json.Unmarshal(data, &v1); err == nil && v1.Name != "" {
		return FormatV1
	}
	return FormatUnknown
}

// CharacterCardV1 is the flat V1 format.
type CharacterCardV1 struct {
	Name        string `json:"name"`
	Description string `json:"description"`
	Personality string `json:"personality"`
	Scenario    string `json:"scenario"`
	FirstMes    string `json:"first_mes"`
	MesExample  string `json:"mes_example"`
}

// CharacterCardV2Data is the nested data object in V2/V3.
type CharacterCardV2Data struct {
	Name                    string `json:"name"`
	Description             string `json:"description"`
	Personality             string `json:"personality"`
	Scenario                string `json:"scenario"`
	FirstMes                string `json:"first_mes"`
	MesExample              string `json:"mes_example"`
	SystemPrompt            string `json:"system_prompt"`
	PostHistoryInstructions string `json:"post_history_instructions"`
}

// CharacterCardV2 wraps V2Data.
type CharacterCardV2 struct {
	Data CharacterCardV2Data `json:"data"`
}

// CharacterCardV3 wraps V2Data plus extra V3 fields we may read but not map.
type CharacterCardV3 struct {
	Data struct {
		CharacterCardV2Data
		Nickname string `json:"nickname"`
	} `json:"data"`
}

// ImportResult describes what happened during Character Card import.
type ImportResult struct {
	Format    CardFormat
	Accepted  []string
	Converted []string
	Ignored   []string
	Blocked   []string
	Warnings  []string
	Errors    []string
}

// ParseAndMap parses raw Character Card JSON and maps it to a SIRAH Persona.
func ParseAndMap(data []byte) (Persona, ImportResult, error) {
	format := DetectFormat(data)
	if format == FormatUnknown {
		return Persona{}, ImportResult{}, fmt.Errorf("unknown or unsupported character card format")
	}

	result := ImportResult{Format: format}

	var raw CharacterCardV2Data
	switch format {
	case FormatV1:
		var v1 CharacterCardV1
		if err := json.Unmarshal(data, &v1); err != nil {
			return Persona{}, result, fmt.Errorf("parse V1: %w", err)
		}
		raw = CharacterCardV2Data{
			Name:        v1.Name,
			Description: v1.Description,
			Personality: v1.Personality,
			Scenario:    v1.Scenario,
			FirstMes:    v1.FirstMes,
			MesExample:  v1.MesExample,
		}
	case FormatV2:
		var v2 CharacterCardV2
		if err := json.Unmarshal(data, &v2); err != nil {
			return Persona{}, result, fmt.Errorf("parse V2: %w", err)
		}
		raw = v2.Data
	case FormatV3:
		var v3 CharacterCardV3
		if err := json.Unmarshal(data, &v3); err != nil {
			return Persona{}, result, fmt.Errorf("parse V3: %w", err)
		}
		raw = v3.Data.CharacterCardV2Data
		// nickname handled below
		if v3.Data.Nickname != "" {
			result.Accepted = append(result.Accepted, "nickname → display_name")
			raw.Name = v3.Data.Nickname
		}
	}

	p, result := mapCardToPersona(raw, result)
	return p, result, nil
}

func mapCardToPersona(raw CharacterCardV2Data, result ImportResult) (Persona, ImportResult) {
	p := Persona{
		Schema:  personaSchema,
		Version: personaVersion,
	}

	// name → DisplayName
	name := strings.TrimSpace(raw.Name)
	if name != "" {
		p.DisplayName, result = truncateWithWarning(name, 64, "display_name", result)
		result.Accepted = append(result.Accepted, "name → display_name")
	}

	// personality
	personality := strings.TrimSpace(raw.Personality)
	if personality != "" {
		p.Personality, result = truncateWithWarning(personality, 8192, "personality", result)
		result.Accepted = append(result.Accepted, "personality → personality")
	}

	// description → CharacterProfile, with [Personality] extraction heuristic
	description := strings.TrimSpace(raw.Description)
	if description != "" {
		extracted, remainder := extractPersonalitySection(description)
		if extracted != "" && personality == "" {
			p.Personality, result = truncateWithWarning(extracted, 8192, "personality", result)
			result.Converted = append(result.Converted, "description[Personality] → personality")
			if remainder != "" {
				p.CharacterProfile, result = truncateWithWarning(remainder, 8192, "character_profile", result)
				result.Accepted = append(result.Accepted, "description remainder → character_profile")
			}
		} else {
			p.CharacterProfile, result = truncateWithWarning(description, 8192, "character_profile", result)
			result.Accepted = append(result.Accepted, "description → character_profile")
		}
	}

	if personality == "" && p.Personality == "" {
		result.Warnings = append(result.Warnings, "personality is empty and no [Personality] section found in description")
	}

	// mes_example → Examples
	examples := splitExamples(raw.MesExample)
	if len(examples) > 0 {
		if len(examples) > 10 {
			result.Warnings = append(result.Warnings, fmt.Sprintf("examples truncated from %d to 10 blocks", len(examples)))
			examples = examples[:10]
		}
		p.Examples = examples
		result.Accepted = append(result.Accepted, "mes_example → examples")
	}

	// Blocked fields
	if strings.TrimSpace(raw.SystemPrompt) != "" {
		result.Blocked = append(result.Blocked, "system_prompt")
	}
	if strings.TrimSpace(raw.PostHistoryInstructions) != "" {
		result.Blocked = append(result.Blocked, "post_history_instructions")
	}

	// Ignored fields
	if strings.TrimSpace(raw.Scenario) != "" {
		result.Ignored = append(result.Ignored, "scenario")
	}
	if strings.TrimSpace(raw.FirstMes) != "" {
		result.Ignored = append(result.Ignored, "first_mes")
	}

	// Validate the mapped persona
	if err := validatePersona(&p); err != nil {
		result.Errors = append(result.Errors, fmt.Sprintf("mapped persona validation: %v", err))
	}

	return p, result
}

// extractPersonalitySection searches for [Personality]... in text.
func extractPersonalitySection(text string) (extracted, remainder string) {
	start := strings.Index(strings.ToLower(text), "[personality]")
	if start == -1 {
		return "", text
	}
	end := start + len("[Personality]")
	// Find next bracket section or end of string
	nextBracket := strings.Index(text[end:], "[")
	if nextBracket == -1 {
		return strings.TrimSpace(text[end:]), ""
	}
	return strings.TrimSpace(text[end : end+nextBracket]), strings.TrimSpace(text[:start] + text[end+nextBracket:])
}

// splitExamples splits mes_example by <START> markers.
func splitExamples(mesExample string) []string {
	if strings.TrimSpace(mesExample) == "" {
		return nil
	}
	parts := strings.Split(mesExample, "<START>")
	var out []string
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}

func truncate(s string, maxRunes int) string {
	if utf8.RuneCountInString(s) <= maxRunes {
		return s
	}
	runes := []rune(s)
	return string(runes[:maxRunes])
}

func truncateWithWarning(s string, maxRunes int, field string, result ImportResult) (string, ImportResult) {
	if utf8.RuneCountInString(s) > maxRunes {
		result.Warnings = append(result.Warnings, fmt.Sprintf("%s truncated to %d runes", field, maxRunes))
	}
	return truncate(s, maxRunes), result
}
