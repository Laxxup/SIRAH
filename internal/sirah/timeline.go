// Timeline intercala segmentos de voz y acciones fisicas en el orden en que
// el LLM los escribio: "Hola <BLINK> mundo" -> TEXT, ACTION, TEXT.
//
// El runtime reproduce TEXT por TTS y dispara ACTION a Motion/Serial cuando
// el audio previo ya se escribio realmente al altavoz ( AppendLegacyActions,
// ActionScheduler ). No hay sleeps de sincronizacion: la posicion se mide en
// bytes PCM confirmados por el reproductor. Las etiquetas nunca llegan al TTS,
// al subtitulo impreso ni al historial ( CleanTimeline ).
package sirah

import (
	"context"
	"errors"
	"strings"
	"sync"
)

const maxScheduledActions = 16

var errActionSchedulerFull = errors.New("action scheduler queue is full")

// TimelineKind distingue un segmento hablado de una accion fisica.
type TimelineKind string

const (
	TimelineText   TimelineKind = "text"
	TimelineAction TimelineKind = "action"
)

// TimelineEvent es un paso de la secuencia ordenada de una respuesta.
type TimelineEvent struct {
	Kind   TimelineKind
	Text   string
	Action Action
}

// maxTagLength limita cuanto texto se retiene esperando un '>' antes de
// tratar '<' como texto literal. El marcador valido mas largo es
// <follow_person/> (17 caracteres).
const maxTagLength = 32

var timelineActions = map[string]Action{
	"blink":         ActionBlink,
	"tired":         ActionTired,
	"nod":           ActionNod,
	"center":        ActionCenter,
	"look_at_user":  ActionLookAtUser,
	"stop_looking":  ActionStopLooking,
	"follow_person": ActionFollowPerson,
}

// TimelineFilter extrae eventos de un flujo de caracteres. Tolera que un
// marcador llegue partido entre fragmentos. Un marcador bien formado con
// nombre desconocido se elimina en silencio (nunca se pronuncia) sin romper
// la conversacion. '<' sin forma de marcador se conserva como texto.
type TimelineFilter struct {
	pending strings.Builder
}

// NewTimelineFilter crea un filtro vacio para una respuesta.
func NewTimelineFilter() *TimelineFilter { return &TimelineFilter{} }

// Push procesa un fragmento y devuelve los eventos ya completos.
func (f *TimelineFilter) Push(fragment string) []TimelineEvent {
	if f == nil || fragment == "" {
		return nil
	}
	f.pending.WriteString(fragment)
	events, rest := splitTimeline(f.pending.String(), false)
	f.pending.Reset()
	f.pending.WriteString(rest)
	return events
}

// Flush libera el texto retenido al cerrar el flujo.
func (f *TimelineFilter) Flush() []TimelineEvent {
	if f == nil {
		return nil
	}
	events, _ := splitTimeline(f.pending.String(), true)
	f.pending.Reset()
	return events
}

func splitTimeline(buffer string, final bool) ([]TimelineEvent, string) {
	var events []TimelineEvent
	for {
		open := strings.IndexByte(buffer, '<')
		if open < 0 {
			if buffer != "" {
				events = append(events, TimelineEvent{Kind: TimelineText, Text: buffer})
			}
			return events, ""
		}
		if open > 0 {
			events = append(events, TimelineEvent{Kind: TimelineText, Text: buffer[:open]})
			buffer = buffer[open:]
		}
		close := strings.IndexByte(buffer, '>')
		if close < 0 {
			if !final && len(buffer) <= maxTagLength+1 {
				return events, buffer
			}
			if final {
				// Al cerrar el flujo, un "<..." incompleto con forma de
				// marcador se descarta: un tag truncado nunca debe llegar
				// al TTS. Un "<" seguido de espacios es texto literal.
				if !strings.ContainsAny(buffer[1:], " \t\n\r") {
					return events, ""
				}
			}
			events = append(events, TimelineEvent{Kind: TimelineText, Text: buffer})
			return events, ""
		}
		inner := strings.TrimSpace(buffer[1:close])
		inner = strings.TrimSuffix(strings.TrimSpace(strings.TrimPrefix(inner, "/")), "/")
		rest := buffer[close+1:]
		if action, ok := timelineActions[strings.ToLower(strings.TrimSpace(inner))]; ok && !strings.ContainsAny(inner, " \t\n\r") {
			events = append(events, TimelineEvent{Kind: TimelineAction, Action: action})
			buffer = rest
			continue
		}
		if isTagShape(inner) {
			// Marcador desconocido: se elimina, no se pronuncia, no actua.
			buffer = rest
			continue
		}
		// '<' literal (p. ej. "a < b"): se conserva y se sigue buscando.
		events = append(events, TimelineEvent{Kind: TimelineText, Text: "<"})
		buffer = buffer[1:]
	}
}

func isTagShape(inner string) bool {
	trimmed := strings.TrimSpace(inner)
	if trimmed == "" || strings.ContainsAny(trimmed, " \t\n\r") {
		return false
	}
	for _, r := range trimmed {
		if r != '/' && r != '_' && (r < 'a' || r > 'z') && (r < 'A' || r > 'Z') {
			return false
		}
	}
	return true
}

// ParseTimeline convierte una respuesta completa en eventos ordenados.
func ParseTimeline(speech string) []TimelineEvent {
	filter := NewTimelineFilter()
	events := filter.Push(speech)
	return append(events, filter.Flush()...)
}

// InlineActionCount cuenta acciones embebidas en los eventos.
func InlineActionCount(events []TimelineEvent) int {
	count := 0
	for _, event := range events {
		if event.Kind == TimelineAction {
			count++
		}
	}
	return count
}

// AppendLegacyActions conserva el array "actions" solo cuando la respuesta no
// trae marcadores intercalados. Si hay marcadores, el array se ignora para no
// ejecutar dos veces. Las acciones se disparan al terminar el audio.
func AppendLegacyActions(events []TimelineEvent, actions []Action) []TimelineEvent {
	if InlineActionCount(events) > 0 {
		return events
	}
	for _, action := range actions {
		if knownAction(action) {
			events = append(events, TimelineEvent{Kind: TimelineAction, Action: action})
		}
	}
	return events
}

// FinalStreamActions returns only legacy actions that were not represented by
// inline markers. Inline markers are already consumed while streaming and must
// never be dispatched again from the completed response.
func FinalStreamActions(speech string, actions []Action) []Action {
	if InlineActionCount(ParseTimeline(speech)) > 0 {
		return nil
	}
	filtered := make([]Action, 0, len(actions))
	for _, action := range actions {
		if knownAction(action) {
			filtered = append(filtered, action)
		}
	}
	return filtered
}

// CleanTimeline devuelve el texto hablable: solo segmentos TEXT con espacios
// normalizados, sin marcadores. Para historial, subtitulo y depuracion.
func CleanTimeline(events []TimelineEvent) string {
	var builder strings.Builder
	for _, event := range events {
		if event.Kind == TimelineText {
			builder.WriteString(event.Text)
		}
	}
	return strings.Join(strings.Fields(builder.String()), " ")
}

// scheduledAction dispara action cuando el audio hasta pos ya sono.
type scheduledAction struct {
	pos    int64
	action Action
}

// ActionScheduler dispara acciones fisicas en orden cuando el reproductor
// confirma los bytes indicados. No bloquea la alimentacion de audio ni usa
// temporizadores: depende del conteo real de bytes escritos.
type ActionScheduler struct {
	mu         sync.Mutex
	dispatchMu sync.Mutex
	pending    []scheduledAction
	Act        func(Action) error
	OnError    func(Action, error)
}

// Schedule registra action para cuando se hayan escrito pos bytes.
func (s *ActionScheduler) Schedule(pos int64, action Action) {
	if s == nil || !knownAction(action) {
		return
	}
	s.mu.Lock()
	if len(s.pending) >= maxScheduledActions {
		onError := s.OnError
		s.mu.Unlock()
		if onError != nil {
			onError(action, errActionSchedulerFull)
		}
		return
	}
	s.pending = append(s.pending, scheduledAction{pos: pos, action: action})
	s.mu.Unlock()
}

// MaybeFire dispara en orden las acciones cuyo audio previo ya sono.
// Un fallo fisico se reporta y la secuencia continua: nunca mata la voz.
func (s *ActionScheduler) MaybeFire(_ context.Context, written int64) {
	if s == nil {
		return
	}
	s.dispatchMu.Lock()
	defer s.dispatchMu.Unlock()
	s.mu.Lock()
	var due []scheduledAction
	rest := s.pending[:0]
	for _, item := range s.pending {
		if item.pos <= written {
			due = append(due, item)
		} else {
			rest = append(rest, item)
		}
	}
	s.pending = rest
	act, onError := s.Act, s.OnError
	s.mu.Unlock()
	for _, item := range due {
		if act == nil {
			continue
		}
		if err := act(item.action); err != nil && onError != nil {
			onError(item.action, err)
		}
	}
}

// PendingCount devuelve acciones aun no disparadas (para tests y debug).
func (s *ActionScheduler) PendingCount() int {
	if s == nil {
		return 0
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	return len(s.pending)
}
