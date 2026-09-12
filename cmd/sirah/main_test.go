package main

import (
	"context"
	"errors"
	"slices"
	"testing"

	"github.com/Laxxup/SIRAH/internal/firmware"
	"github.com/Laxxup/SIRAH/internal/motion"
	"github.com/Laxxup/SIRAH/internal/sirah"
)

func TestProviderRequestHeadersOnlyConfiguresOpenCodeGo(t *testing.T) {
	headers := providerRequestHeaders("https://opencode.ai/zen/go/v1", "session-123")
	if headers["X-Opencode-Session"] != "session-123" || headers["User-Agent"] != "sirah/0.1" {
		t.Fatalf("OpenCode Go headers = %#v", headers)
	}

	for _, baseURL := range []string{
		"https://api.groq.com/openai/v1",
		"https://opencode.ai/v1",
		"https://opencode.ai.example/zen/go/v1",
	} {
		if headers := providerRequestHeaders(baseURL, "session-123"); headers != nil {
			t.Fatalf("headers for %q = %#v, want nil", baseURL, headers)
		}
	}
}

func TestRunFirmwareEventsPermanentlyConsumesUntilClosed(t *testing.T) {
	events := make(chan firmware.Event, 2)
	events <- firmware.Event{Type: firmware.EventREADY}
	events <- firmware.Event{Type: firmware.EventSTATE, Mode: firmware.ModeFace}
	close(events)
	mot := motion.New(firmware.Unavailable{})
	mot.ConfirmAppliedMode(motion.TrackingIdle)
	if err := mot.Execute("look_at_user"); err != firmware.ErrUnavailable {
		t.Fatalf("execute error = %v", err)
	}
	runFirmwareEvents(context.Background(), events, mot)
	_, applied, health, _, _ := mot.Snapshot()
	if applied != motion.TrackingFace || health != motion.HardwareReady {
		t.Fatalf("applied=%q health=%q", applied, health)
	}
}

func routeResponseActions(t *testing.T, available []sirah.Action, speech string, jsonActions []sirah.Action, streamFragments []string) (string, []sirah.Action) {
	t.Helper()
	var enqueued []sirah.Action
	enqueue := newTurnActionEnqueuer(available, func(action sirah.Action) error {
		enqueued = append(enqueued, action)
		return nil
	})

	var events []sirah.TimelineEvent
	if streamFragments != nil {
		filter := sirah.NewTimelineFilter()
		for _, fragment := range streamFragments {
			events = append(events, filter.Push(fragment)...)
		}
		events = append(events, filter.Flush()...)
	} else {
		events = sirah.AppendLegacyActions(sirah.ParseTimeline(speech), jsonActions)
	}
	for _, event := range events {
		if event.Kind == sirah.TimelineAction {
			if err := enqueue(event.Action); err != nil {
				t.Fatalf("enqueue %q: %v", event.Action, err)
			}
		}
	}
	return sirah.CleanTimeline(events), enqueued
}

func TestTurnAvailableActionsApplyTheSamePolicyToJSONAndInline(t *testing.T) {
	available := []sirah.Action{sirah.ActionBlink}
	tests := []struct {
		name            string
		speech          string
		jsonActions     []sirah.Action
		streamFragments []string
		wantSpeech      string
		wantActions     []sirah.Action
	}{
		{name: "announced JSON action", speech: "Hola.", jsonActions: []sirah.Action{sirah.ActionBlink}, wantSpeech: "Hola.", wantActions: []sirah.Action{sirah.ActionBlink}},
		{name: "unannounced JSON action", speech: "Hola.", jsonActions: []sirah.Action{sirah.ActionNod}, wantSpeech: "Hola.", wantActions: nil},
		{name: "announced inline action", streamFragments: []string{"Hola <bli", "nk>mundo."}, wantSpeech: "Hola mundo.", wantActions: []sirah.Action{sirah.ActionBlink}},
		{name: "unannounced inline action", streamFragments: []string{"Hola <no", "d>mundo."}, wantSpeech: "Hola mundo.", wantActions: nil},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			spoken, enqueued := routeResponseActions(t, available, test.speech, test.jsonActions, test.streamFragments)
			if spoken != test.wantSpeech {
				t.Fatalf("spoken = %q, want %q", spoken, test.wantSpeech)
			}
			if !slices.Equal(enqueued, test.wantActions) {
				t.Fatalf("body.Enqueue calls = %v, want %v", enqueued, test.wantActions)
			}
		})
	}
}

func TestTurnAvailableActionsKeepValidAndDropOnlyInvalid(t *testing.T) {
	available := []sirah.Action{sirah.ActionBlink}
	tests := []struct {
		name            string
		speech          string
		jsonActions     []sirah.Action
		streamFragments []string
		wantSpeech      string
	}{
		{name: "JSON", speech: "Sigo hablando.", jsonActions: []sirah.Action{sirah.ActionNod, sirah.ActionBlink}, wantSpeech: "Sigo hablando."},
		{name: "inline", streamFragments: []string{"Antes <nod>todavía ", "hablo <blink>después."}, wantSpeech: "Antes todavía hablo después."},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			spoken, enqueued := routeResponseActions(t, available, test.speech, test.jsonActions, test.streamFragments)
			if spoken != test.wantSpeech {
				t.Fatalf("spoken = %q, want %q", spoken, test.wantSpeech)
			}
			if !slices.Equal(enqueued, []sirah.Action{sirah.ActionBlink}) {
				t.Fatalf("body.Enqueue calls = %v, want one blink", enqueued)
			}
		})
	}
}

func TestTurnWithoutActionsKeepsSpeechUnchanged(t *testing.T) {
	const speech = "Texto sin acciones: 2 < 3."
	spoken, enqueued := routeResponseActions(t, []sirah.Action{sirah.ActionBlink}, speech, nil, nil)
	if spoken != speech {
		t.Fatalf("spoken = %q, want unchanged %q", spoken, speech)
	}
	if len(enqueued) != 0 {
		t.Fatalf("body.Enqueue calls = %v, want none", enqueued)
	}
}

func TestRejectedTurnActionIsSuccessfulNoOp(t *testing.T) {
	wantErr := errors.New("body enqueue failed")
	calls := 0
	enqueue := newTurnActionEnqueuer([]sirah.Action{sirah.ActionBlink}, func(sirah.Action) error {
		calls++
		return wantErr
	})
	if err := enqueue(sirah.ActionNod); err != nil {
		t.Fatalf("rejected action returned error: %v", err)
	}
	if calls != 0 {
		t.Fatalf("rejected action reached body.Enqueue %d times", calls)
	}
	if err := enqueue(sirah.ActionBlink); !errors.Is(err, wantErr) {
		t.Fatalf("announced action error = %v, want body.Enqueue error", err)
	}
	if calls != 1 {
		t.Fatalf("announced action reached body.Enqueue %d times, want once", calls)
	}
}
