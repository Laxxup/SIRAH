package sirah

import (
	"context"
	"fmt"
	"strings"
	"sync"
	"testing"
	"time"
)

func TestParseTimelineKeepsOrder(t *testing.T) {
	events := ParseTimeline("Hola <BLINK> mundo")
	if len(events) != 3 {
		t.Fatalf("events = %#v, want 3", events)
	}
	if events[0].Kind != TimelineText || events[0].Text != "Hola " {
		t.Fatalf("first = %#v", events[0])
	}
	if events[1].Kind != TimelineAction || events[1].Action != ActionBlink {
		t.Fatalf("second = %#v", events[1])
	}
	if events[2].Kind != TimelineText || events[2].Text != " mundo" {
		t.Fatalf("third = %#v", events[2])
	}
}

func TestParseTimelineNeverSpeaksTags(t *testing.T) {
	events := ParseTimeline("Hola <BLINK> ¿cómo estás? <CENTER> Me alegra verte.")
	for _, event := range events {
		if event.Kind == TimelineText && strings.Contains(event.Text, "<") {
			t.Fatalf("tag leaked into speech: %q", event.Text)
		}
	}
	if got := CleanTimeline(events); got != "Hola ¿cómo estás? Me alegra verte." {
		t.Fatalf("clean = %q", got)
	}
}

func TestParseTimelineSplitFragments(t *testing.T) {
	filter := NewTimelineFilter()
	var events []TimelineEvent
	events = append(events, filter.Push("Hola <BL")...)
	events = append(events, filter.Push("INK> mundo")...)
	events = append(events, filter.Flush()...)
	if len(events) != 3 || events[1].Kind != TimelineAction || events[1].Action != ActionBlink {
		t.Fatalf("events = %#v", events)
	}
}

func TestParseTimelineMultipleActionsKeepOrder(t *testing.T) {
	events := ParseTimeline("A <BLINK> B <CENTER> C <NOD> D")
	var actions []Action
	for _, event := range events {
		if event.Kind == TimelineAction {
			actions = append(actions, event.Action)
		}
	}
	want := []Action{ActionBlink, ActionCenter, ActionNod}
	if fmt.Sprint(actions) != fmt.Sprint(want) {
		t.Fatalf("actions = %v, want %v", actions, want)
	}
}

func TestParseTimelineTiredIsSemanticAndNeverSpoken(t *testing.T) {
	events := ParseTimeline("Acabo de despertar. <tired> Dame un momento.")
	if len(events) != 3 || events[1].Kind != TimelineAction || events[1].Action != ActionTired {
		t.Fatalf("events = %#v", events)
	}
	if got := CleanTimeline(events); got != "Acabo de despertar. Dame un momento." {
		t.Fatalf("clean = %q", got)
	}
}

func TestParseTimelineWithoutActionsIsUnchanged(t *testing.T) {
	events := ParseTimeline("Hola, soy SIRAH.")
	if len(events) != 1 || events[0].Kind != TimelineText || events[0].Text != "Hola, soy SIRAH." {
		t.Fatalf("events = %#v", events)
	}
}

func TestParseTimelineInvalidActionIsDroppedSafely(t *testing.T) {
	events := ParseTimeline("Hola <POSE> mundo")
	for _, event := range events {
		if event.Kind == TimelineAction {
			t.Fatalf("invalid action produced event: %#v", event)
		}
	}
	if got := CleanTimeline(events); got != "Hola mundo" {
		t.Fatalf("clean = %q", got)
	}
}

func TestParseTimelineLiteralAngleBracketsSurvive(t *testing.T) {
	if got := CleanTimeline(ParseTimeline("a < b")); got != "a < b" {
		t.Fatalf("clean = %q", got)
	}
}

func TestParseTimelineCaseInsensitiveSelfClosing(t *testing.T) {
	events := ParseTimeline("Hola <Blink/> mundo")
	if len(events) != 3 || events[1].Action != ActionBlink {
		t.Fatalf("events = %#v", events)
	}
}

func TestAppendLegacyActionsIgnoredWhenInlinePresent(t *testing.T) {
	events := AppendLegacyActions(ParseTimeline("Hola <BLINK>"), []Action{ActionCenter})
	if InlineActionCount(events) != 1 || events[1].Action != ActionBlink {
		t.Fatalf("events = %#v", events)
	}
}

func TestAppendLegacyActionsKeptWithoutInline(t *testing.T) {
	events := AppendLegacyActions(ParseTimeline("Hola."), []Action{ActionBlink, "pose"})
	if len(events) != 2 || events[1].Action != ActionBlink {
		t.Fatalf("events = %#v", events)
	}
}

func TestFinalStreamSingleBlinkRunsOnce(t *testing.T) {
	assertStreamActionCount(t, "Hola <blink>.", []Action{ActionBlink}, ActionBlink, 1)
}

func TestFinalStreamSingleLookAtUserRunsOnce(t *testing.T) {
	assertStreamActionCount(t, "Voy a orientarme. <look_at_user>", []Action{ActionLookAtUser}, ActionLookAtUser, 1)
}

func TestFinalStreamSingleTiredRunsOnce(t *testing.T) {
	assertStreamActionCount(t, "Acabo de despertar. <tired>", []Action{ActionTired}, ActionTired, 1)
}

func TestFinalStreamTwoExplicitBlinksRunTwice(t *testing.T) {
	assertStreamActionCount(t, "<blink> Otra vez. <blink>", nil, ActionBlink, 2)
}

func TestFinalStreamLegacyActionRunsOnceWithoutMarker(t *testing.T) {
	assertStreamActionCount(t, "Claro.", []Action{ActionBlink}, ActionBlink, 1)
}

func assertStreamActionCount(t *testing.T, speech string, legacy []Action, wanted Action, count int) {
	t.Helper()
	consumed := 0
	for _, event := range ParseTimeline(speech) {
		if event.Kind == TimelineAction && event.Action == wanted {
			consumed++
		}
	}
	for _, action := range FinalStreamActions(speech, legacy) {
		if action == wanted {
			consumed++
		}
	}
	if consumed != count {
		t.Fatalf("action %s executed %d times, want %d", wanted, consumed, count)
	}
}

func TestSchedulerFiresInOrderAtRealPosition(t *testing.T) {
	var fired []Action
	scheduler := &ActionScheduler{Act: func(a Action) error { fired = append(fired, a); return nil }}
	scheduler.Schedule(10, ActionBlink)
	scheduler.Schedule(20, ActionCenter)
	scheduler.MaybeFire(context.Background(), 5)
	if len(fired) != 0 {
		t.Fatalf("fired early: %v", fired)
	}
	scheduler.MaybeFire(context.Background(), 10)
	if fmt.Sprint(fired) != fmt.Sprint([]Action{ActionBlink}) {
		t.Fatalf("fired = %v", fired)
	}
	scheduler.MaybeFire(context.Background(), 100)
	if fmt.Sprint(fired) != fmt.Sprint([]Action{ActionBlink, ActionCenter}) {
		t.Fatalf("fired = %v", fired)
	}
	if scheduler.PendingCount() != 0 {
		t.Fatal("pending actions remain")
	}
}

func TestSchedulerFailureNeverKillsVoice(t *testing.T) {
	var reported []Action
	scheduler := &ActionScheduler{
		Act:     func(a Action) error { return fmt.Errorf("serial down") },
		OnError: func(a Action, _ error) { reported = append(reported, a) },
	}
	scheduler.Schedule(0, ActionBlink)
	scheduler.Schedule(0, ActionCenter)
	scheduler.MaybeFire(context.Background(), 0)
	if fmt.Sprint(reported) != fmt.Sprint([]Action{ActionBlink, ActionCenter}) {
		t.Fatalf("reported = %v", reported)
	}
	if scheduler.PendingCount() != 0 {
		t.Fatal("failed actions must not stay queued")
	}
}

func TestSchedulerQueueIsBounded(t *testing.T) {
	reported := 0
	scheduler := &ActionScheduler{OnError: func(Action, error) { reported++ }}
	for i := 0; i < maxScheduledActions+2; i++ {
		scheduler.Schedule(int64(i), ActionBlink)
	}
	if scheduler.PendingCount() != maxScheduledActions {
		t.Fatalf("pending = %d, want %d", scheduler.PendingCount(), maxScheduledActions)
	}
	if reported != 2 {
		t.Fatalf("overflow reports = %d, want 2", reported)
	}
}

func TestSchedulerSerializesConcurrentDispatch(t *testing.T) {
	firstStarted := make(chan struct{})
	releaseFirst := make(chan struct{})
	var mu sync.Mutex
	var fired []Action
	scheduler := &ActionScheduler{Act: func(action Action) error {
		if action == ActionBlink {
			close(firstStarted)
			<-releaseFirst
		}
		mu.Lock()
		fired = append(fired, action)
		mu.Unlock()
		return nil
	}}
	scheduler.Schedule(0, ActionBlink)
	firstDone := make(chan struct{})
	go func() {
		scheduler.MaybeFire(context.Background(), 0)
		close(firstDone)
	}()
	<-firstStarted
	scheduler.Schedule(0, ActionCenter)
	secondDone := make(chan struct{})
	go func() {
		scheduler.MaybeFire(context.Background(), 0)
		close(secondDone)
	}()
	select {
	case <-secondDone:
		t.Fatal("second dispatch overtook the first")
	case <-time.After(20 * time.Millisecond):
	}
	close(releaseFirst)
	<-firstDone
	<-secondDone
	mu.Lock()
	defer mu.Unlock()
	if fmt.Sprint(fired) != fmt.Sprint([]Action{ActionBlink, ActionCenter}) {
		t.Fatalf("fired = %v", fired)
	}
}

func TestTruncatedTagAtEndNeverReachesTTS(t *testing.T) {
	for _, speech := range []string{"Hola <BLIN", "Hola <", "<BLINK"} {
		events := ParseTimeline(speech)
		for _, event := range events {
			if event.Kind == TimelineText && strings.Contains(event.Text, "<") {
				t.Fatalf("speech %q leaked %q to TTS", speech, event.Text)
			}
			if event.Kind == TimelineAction {
				t.Fatalf("speech %q produced action from truncated tag", speech)
			}
		}
		if got := CleanTimeline(events); strings.Contains(got, "<") {
			t.Fatalf("speech %q cleaned to %q", speech, got)
		}
	}
	if got := CleanTimeline(ParseTimeline("Hola <BLIN")); got != "Hola" {
		t.Fatalf("clean = %q", got)
	}
}

func TestTruncatedTagAcrossFlushDropped(t *testing.T) {
	filter := NewTimelineFilter()
	events := filter.Push("Hola <BL")
	events = append(events, filter.Flush()...)
	if len(events) != 1 || events[0].Kind != TimelineText || events[0].Text != "Hola " {
		t.Fatalf("events = %#v", events)
	}
}
