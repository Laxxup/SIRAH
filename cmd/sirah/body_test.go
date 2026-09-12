package main

import (
	"context"
	"errors"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Laxxup/SIRAH/internal/sirah"
)

type bodyTestMotion struct {
	mu      sync.Mutex
	actions []sirah.Action
	called  chan sirah.Action
	block   <-chan struct{}
}

type creativeWakeupLLM struct {
	response sirah.Response
	context  sirah.Context
}

func (l *creativeWakeupLLM) Complete(_ context.Context, contextData sirah.Context) (sirah.Response, error) {
	l.context = contextData
	return l.response, nil
}

func (m *bodyTestMotion) Execute(action sirah.Action) error {
	m.mu.Lock()
	m.actions = append(m.actions, action)
	m.mu.Unlock()
	if m.called != nil {
		m.called <- action
	}
	if m.block != nil {
		<-m.block
	}
	return nil
}

func (m *bodyTestMotion) snapshot() []sirah.Action {
	m.mu.Lock()
	defer m.mu.Unlock()
	return append([]sirah.Action(nil), m.actions...)
}

func TestBodyEnqueueNeverWaitsForHardware(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	blocked := make(chan struct{})
	called := make(chan sirah.Action, 1)
	body := startBodyController(ctx, &bodyTestMotion{called: called, block: blocked}, bodyControllerConfig{})
	if err := body.Enqueue(sirah.ActionBlink); err != nil {
		t.Fatal(err)
	}
	<-called
	returned := make(chan error, 1)
	go func() { returned <- body.Enqueue(sirah.ActionCenter) }()
	select {
	case err := <-returned:
		if err != nil {
			t.Fatal(err)
		}
	case <-time.After(100 * time.Millisecond):
		t.Fatal("enqueue waited for blocked hardware")
	}
	close(blocked)
	cancel()
	body.Wait()
}

func TestBodyPreservesTwoExplicitBlinks(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	called := make(chan sirah.Action, 2)
	body := startBodyController(ctx, &bodyTestMotion{called: called}, bodyControllerConfig{BlinkBusy: time.Millisecond})
	defer func() { cancel(); body.Wait() }()
	if err := body.Enqueue(sirah.ActionBlink); err != nil {
		t.Fatal(err)
	}
	if err := body.Enqueue(sirah.ActionBlink); err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 2; i++ {
		select {
		case action := <-called:
			if action != sirah.ActionBlink {
				t.Fatalf("action = %q", action)
			}
		case <-time.After(100 * time.Millisecond):
			t.Fatal("second explicit blink was not preserved")
		}
	}
}

func TestNaturalBlinkSkipsCycleWhileLidsBusy(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	motion := &bodyTestMotion{called: make(chan sirah.Action, 4)}
	body := startBodyController(ctx, motion, bodyControllerConfig{
		NaturalBlink: true,
		NextBlink:    func() time.Duration { return 10 * time.Millisecond },
		BlinkBusy:    5 * time.Millisecond,
		TiredBusy:    80 * time.Millisecond,
	})
	defer func() { cancel(); body.Wait() }()
	if err := body.Enqueue(sirah.ActionTired); err != nil {
		t.Fatal(err)
	}
	if action := <-motion.called; action != sirah.ActionTired {
		t.Fatalf("first action = %q", action)
	}
	body.EnableNaturalBlink()
	time.Sleep(40 * time.Millisecond)
	if got := motion.snapshot(); len(got) != 1 {
		t.Fatalf("natural blink ran while tired was active: %v", got)
	}
	select {
	case action := <-motion.called:
		if action != sirah.ActionBlink {
			t.Fatalf("natural action = %q", action)
		}
	case <-time.After(100 * time.Millisecond):
		t.Fatal("natural blink did not resume after lids became idle")
	}
}

func TestWakeupDispatchStartsAfterFirstPCMWrite(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	motion := &bodyTestMotion{called: make(chan sirah.Action, 3)}
	body := startBodyController(ctx, motion, bodyControllerConfig{BlinkBusy: time.Millisecond, TiredBusy: time.Millisecond})
	defer func() { cancel(); body.Wait() }()
	pcmWritten := false
	err := runWakeup(ctx, "Hola.", body, func(_ context.Context, text string, firstPCMWrite func()) error {
		if text != "Hola." {
			t.Fatalf("text = %q", text)
		}
		if len(motion.snapshot()) != 0 {
			t.Fatal("motion started before PCM")
		}
		pcmWritten = true
		firstPCMWrite()
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	want := []sirah.Action{sirah.ActionTired, sirah.ActionBlink, sirah.ActionCenter}
	for i := 0; i < len(want); i++ {
		select {
		case action := <-motion.called:
			if action != want[i] {
				t.Fatalf("wake-up action %d = %q, want %q", i, action, want[i])
			}
		case <-time.After(100 * time.Millisecond):
			t.Fatal("wake-up action was not dispatched")
		}
	}
	if !pcmWritten {
		t.Fatal("wake-up did not write PCM")
	}
}

func TestGenerateCreativeWakeupDisablesActionsAndMemory(t *testing.T) {
	llm := &creativeWakeupLLM{response: sirah.Response{Speech: "Hoy sí desperté con dignidad."}}
	agent := sirah.Agent{
		LLM:               llm,
		AvailableActions:  []sirah.Action{sirah.ActionBlink},
		ConversationStore: sirah.NewLocalMemory(12),
		Context: sirah.Context{
			AvailableActions:    []sirah.Action{sirah.ActionBlink},
			AvailableActionsSet: true,
			History:             []sirah.Turn{{UserText: "hola", RobotText: "hola"}},
			MemoryContext:       "dato privado",
		},
	}

	text, err := generateCreativeWakeup(context.Background(), agent, time.Unix(1, 2))
	if err != nil {
		t.Fatal(err)
	}
	if text != "Hoy sí desperté con dignidad." {
		t.Fatalf("text = %q", text)
	}
	if !llm.context.AvailableActionsSet || len(llm.context.AvailableActions) != 0 {
		t.Fatalf("available actions = %v, set=%t", llm.context.AvailableActions, llm.context.AvailableActionsSet)
	}
	if len(llm.context.History) != 0 || llm.context.MemoryContext != "" {
		t.Fatalf("wake-up leaked conversation context: %#v", llm.context)
	}
	if !strings.Contains(llm.context.UserInput, "1970-01-01T00:00:01.000000002Z") {
		t.Fatalf("wake-up prompt lacks unique startup id: %q", llm.context.UserInput)
	}
}

func TestGenerateCreativeWakeupRejectsActions(t *testing.T) {
	llm := &creativeWakeupLLM{response: sirah.Response{Speech: "Hola. <blink>"}}
	agent := sirah.Agent{LLM: llm}
	if _, err := generateCreativeWakeup(context.Background(), agent, time.Unix(1, 0)); err == nil {
		t.Fatal("expected wake-up action to be rejected")
	}
}

func TestBodyStopsWithContext(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	body := startBodyController(ctx, &bodyTestMotion{}, bodyControllerConfig{NaturalBlink: true})
	body.EnableNaturalBlink()
	cancel()
	done := make(chan struct{})
	go func() { body.Wait(); close(done) }()
	select {
	case <-done:
	case <-time.After(100 * time.Millisecond):
		t.Fatal("body controller did not stop with context")
	}
	if err := body.Enqueue(sirah.ActionCenter); !errors.Is(err, context.Canceled) {
		t.Fatalf("enqueue after stop = %v", err)
	}
}
