package sirah

import (
	"strings"
	"unicode/utf8"
)

// SpeechChunker emits complete speech units, never individual tokens.
type SpeechChunker struct {
	text      strings.Builder
	minimum   int
	maxLength int
}

func NewSpeechChunker() *SpeechChunker {
	return &SpeechChunker{minimum: 24, maxLength: 180}
}

func (c *SpeechChunker) Push(text string) []string {
	if c == nil || text == "" {
		return nil
	}
	// Whitespace-only fragments are kept: dropping a lone " " between words
	// would glue them ("Hola"+" "+"mundo" -> "Holamundo"). Drain emits only
	// non-empty trimmed chunks, so Piper never receives blank text.
	c.text.WriteString(text)
	return c.drain(false)
}

func (c *SpeechChunker) Flush() []string {
	if c == nil {
		return nil
	}
	return c.drain(true)
}

// FlushStable emits only complete sentences or sufficiently long clauses.
// It is safe to call from a short streaming timeout without splitting a word.
func (c *SpeechChunker) FlushStable() []string {
	if c == nil {
		return nil
	}
	return c.drain(false)
}

func (c *SpeechChunker) drain(final bool) []string {
	value := c.text.String()
	if strings.TrimSpace(value) == "" {
		// Keep whitespace for later text when streaming; only drop it at
		// the end. Emitted chunks are trimmed individually below.
		if final {
			c.text.Reset()
		}
		return nil
	}
	var chunks []string
	start := 0
	for start < len(value) {
		cut := sentenceCut(value[start:])
		if cut == 0 {
			clause := clauseCut(value[start:])
			if clause >= c.minimum {
				cut = clause
			}
		}
		if cut == 0 && len(value[start:]) >= c.maxLength {
			end := start + c.maxLength
			if end > len(value) {
				end = len(value)
			}
			cut = clauseCut(value[start:end])
			if cut == 0 {
				cut = end - start
			}
		}
		if cut == 0 || (!final && cut < c.minimum && len(value[start:]) < c.maxLength) {
			break
		}
		cut = runeBoundary(value, start, cut)
		chunk := strings.TrimSpace(value[start : start+cut])
		if chunk != "" {
			chunks = append(chunks, chunk)
		}
		start += cut
	}
	remaining := value[start:]
	c.text.Reset()
	c.text.WriteString(remaining)
	if final && strings.TrimSpace(remaining) != "" {
		chunks = append(chunks, strings.TrimSpace(remaining))
		c.text.Reset()
	}
	return chunks
}

// runeBoundary moves cut back to a UTF-8 rune boundary so the 180-byte
// fallback never splits a multibyte character. start is always at a
// boundary, so the loop terminates with cut > 0.
func runeBoundary(value string, start, cut int) int {
	if cut > len(value)-start {
		cut = len(value) - start
	}
	for cut > 0 && start+cut < len(value) && !utf8.RuneStart(value[start+cut]) {
		cut--
	}
	return cut
}

func sentenceCut(value string) int {
	for index, r := range value {
		if r != '.' && r != '?' && r != '!' {
			continue
		}
		return index + len(string(r))
	}
	return 0
}

func clauseCut(value string) int {
	last := 0
	for index, r := range value {
		if r == ',' || r == ';' || r == ':' {
			last = index + len(string(r))
		}
	}
	return last
}
