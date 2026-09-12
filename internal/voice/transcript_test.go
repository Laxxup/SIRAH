package voice

import "testing"

func TestCleanTranscriptOnlyRemovesTransportNoise(t *testing.T) {
	raw := "  Hola,\tAna.\n\n¿Cómo estás?  "
	if got, want := CleanTranscript(raw), "Hola, Ana. ¿Cómo estás?"; got != want {
		t.Fatalf("clean transcript = %q, want %q", got, want)
	}
}

func TestCleanTranscriptPreservesMeaningfulCharacters(t *testing.T) {
	raw := "¿Qué? ¡Sí! 42% café niño"
	if got := CleanTranscript(raw); got != raw {
		t.Fatalf("clean transcript = %q, want %q", got, raw)
	}
}

func TestCleanTranscriptRejectsInvalidOrEmptyTransport(t *testing.T) {
	if got := CleanTranscript("\x00\x01 \n"); got != "" {
		t.Fatalf("clean transcript = %q, want empty", got)
	}
}
