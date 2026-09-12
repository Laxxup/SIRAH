package sirah

import (
	"testing"
	"unicode/utf8"
)

func TestSpeechChunkerPrefersSentenceBoundaries(t *testing.T) {
	chunker := NewSpeechChunker()
	got := chunker.Push("Hola, estoy bien. ¿Y tú cómo estás?")
	got = append(got, chunker.Flush()...)
	want := []string{"Hola, estoy bien.", "¿Y tú cómo estás?"}
	if len(got) != len(want) {
		t.Fatalf("chunks = %#v, want %#v", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("chunk %d = %q, want %q", i, got[i], want[i])
		}
	}
}

func TestSpeechChunkerDoesNotEmitTinyClauses(t *testing.T) {
	chunker := NewSpeechChunker()
	if got := chunker.Push("Sí,"); len(got) != 0 {
		t.Fatalf("chunks = %#v", got)
	}
	if got := chunker.Flush(); len(got) != 1 || got[0] != "Sí," {
		t.Fatalf("flush = %#v", got)
	}
}

func TestSpeechChunkerFlushesIncompleteText(t *testing.T) {
	chunker := NewSpeechChunker()
	chunker.Push("Entiendo lo que dices")
	got := chunker.Flush()
	if len(got) != 1 || got[0] != "Entiendo lo que dices" {
		t.Fatalf("chunks = %#v", got)
	}
}

func TestSpeechChunkerStableFlushDoesNotSplitIncompleteText(t *testing.T) {
	chunker := NewSpeechChunker()
	got := chunker.Push("Esta es una cláusula suficientemente larga, pero")
	if len(got) != 1 || got[0] != "Esta es una cláusula suficientemente larga," {
		t.Fatalf("push chunks = %#v", got)
	}
	if got = chunker.FlushStable(); len(got) != 0 {
		t.Fatalf("stable chunks = %#v", got)
	}
	if got = chunker.Flush(); len(got) != 1 || got[0] != "pero" {
		t.Fatalf("final chunks = %#v", got)
	}
}

func TestSpeechChunkerKeepsWhitespaceOnlyFragments(t *testing.T) {
	chunker := NewSpeechChunker()
	for _, fragment := range []string{"Hola", " ", "mundo. Adiós."} {
		chunker.Push(fragment)
	}
	got := chunker.Flush()
	joined := ""
	for _, chunk := range got {
		joined += chunk + " "
	}
	if joined != "Hola mundo. Adiós. " {
		t.Fatalf("chunks = %#v", got)
	}
}

func TestSpeechChunkerNeverSplitsUTF8Rune(t *testing.T) {
	// 200 'é' (2 bytes each) with no punctuation: forces the byte fallback.
	chunker := NewSpeechChunker()
	text := ""
	for i := 0; i < 200; i++ {
		text += "é"
	}
	got := append(chunker.Push(text), chunker.Flush()...)
	if len(got) == 0 {
		t.Fatal("no chunks produced")
	}
	for _, chunk := range got {
		if !utf8.ValidString(chunk) {
			t.Fatalf("chunk is not valid UTF-8: %q", chunk)
		}
	}
}
