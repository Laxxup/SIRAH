// El archivo response.go define la respuesta que produce el LLM (aún simulado).
package sirah

import (
	"fmt"
	"strings"
	"unicode/utf8"
)

// Response es lo que devuelve el Agent tras procesar el input del usuario.
// Speech va hacia TTS/Speaker; Actions van hacia Motion.
type Response struct {
	// Speech es el texto que el robot debe decir.
	Speech string
	// Actions son las acciones de alto nivel que Motion debe ejecutar.
	Actions []Action
}

const maxSpeechRunes = 2000

// ValidateResponse protects the runtime boundary independently of the LLM.
func ValidateResponse(response Response) error {
	if response.Speech != "" && strings.TrimSpace(response.Speech) == "" {
		return fmt.Errorf("speech cannot contain only whitespace")
	}
	if utf8.RuneCountInString(response.Speech) > maxSpeechRunes {
		return fmt.Errorf("speech exceeds %d characters", maxSpeechRunes)
	}
	seen := make(map[Action]struct{}, len(response.Actions))
	for _, action := range response.Actions {
		if strings.TrimSpace(string(action)) == "" {
			return fmt.Errorf("response contains an empty action")
		}
		if _, ok := seen[action]; ok {
			return fmt.Errorf("response contains duplicate action %q", action)
		}
		if !knownAction(action) {
			return fmt.Errorf("response contains unknown action %q", action)
		}
		seen[action] = struct{}{}
	}
	return nil
}

func knownAction(action Action) bool {
	switch action {
	case ActionBlink, ActionTired, ActionNod, ActionCenter, ActionLookAtUser, ActionStopLooking, ActionFollowPerson:
		return true
	default:
		return false
	}
}
