// El archivo action.go define las acciones de alto nivel que el LLM puede decidir.
// Son intenciones, nunca valores físicos (servo, PWM, grados...).
package sirah

// Action es una acción de alto nivel decidida por el LLM.
type Action string

func FilterActions(actions []Action, status HardwareStatus) []Action {
	filtered := make([]Action, 0, len(actions))
	for _, action := range actions {
		if ActionAvailable(action, status) {
			filtered = append(filtered, action)
		}
	}
	return filtered
}

func ActionAvailable(action Action, status HardwareStatus) bool {
	if status.Eyes == "" || (status.Eyes != "degraded" && status.Eyes != "failed" && status.Eyes != "unavailable") {
		return true
	}
	switch action {
	case ActionBlink, ActionTired, ActionNod, ActionCenter, ActionLookAtUser, ActionStopLooking, ActionFollowPerson:
		return false
	default:
		return true
	}
}

// Acciones discretas: se ejecutan una vez y terminan.
const (
	// ActionBlink indica un parpadeo.
	ActionBlink Action = "blink"
	// ActionTired muestra brevemente una expresion de parpados cansados.
	ActionTired Action = "tired"
	// ActionNod indica un asentimiento.
	ActionNod Action = "nod"
	// ActionCenter indica volver la mirada al centro.
	ActionCenter Action = "center"
)

// Acciones de estado: cambian el estado de Motion (p.ej. el modo de tracking).
const (
	// ActionLookAtUser activa el modo trackear el rostro del usuario.
	ActionLookAtUser Action = "look_at_user"
	// ActionStopLooking desactiva el tracking.
	ActionStopLooking Action = "stop_looking"
	// ActionFollowPerson activa seguimiento de persona.
	ActionFollowPerson Action = "follow_person"
)
