package voice

import (
	"strings"
	"unicode"
)

// CleanTranscript removes transport noise without changing spoken words.
func CleanTranscript(raw string) string {
	clean := strings.ToValidUTF8(raw, "")
	clean = strings.Map(func(r rune) rune {
		if unicode.IsControl(r) {
			return ' '
		}
		return r
	}, clean)
	return strings.Join(strings.Fields(clean), " ")
}
