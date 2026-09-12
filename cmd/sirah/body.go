package main

import (
	"context"
	"errors"
	"fmt"
	"math/rand"
	"strings"
	"sync"
	"time"
	"unicode/utf8"

	"github.com/Laxxup/SIRAH/internal/sirah"
)

const defaultWakeupText = "Hola, hola... me acabo de despertar."

var errBodyQueueFull = errors.New("body action queue is full")

type motionExecutor interface {
	Execute(sirah.Action) error
}

type bodyControllerConfig struct {
	NaturalBlink bool
	NextBlink    func() time.Duration
	BlinkBusy    time.Duration
	TiredBusy    time.Duration
	OnResult     func(sirah.Action, bool, error, time.Duration)
}

type bodyController struct {
	ctx      context.Context
	executor motionExecutor
	config   bodyControllerConfig
	actions  chan sirah.Action
	natural  chan struct{}
	done     chan struct{}
}

func startBodyController(ctx context.Context, executor motionExecutor, config bodyControllerConfig) *bodyController {
	if config.NextBlink == nil {
		config.NextBlink = naturalBlinkInterval
	}
	if config.BlinkBusy <= 0 {
		config.BlinkBusy = 220 * time.Millisecond
	}
	if config.TiredBusy <= 0 {
		config.TiredBusy = 950 * time.Millisecond
	}
	body := &bodyController{
		ctx:      ctx,
		executor: executor,
		config:   config,
		actions:  make(chan sirah.Action, 16),
		natural:  make(chan struct{}, 1),
		done:     make(chan struct{}),
	}
	go body.run()
	return body
}

func (b *bodyController) EnableNaturalBlink() {
	if b == nil || !b.config.NaturalBlink {
		return
	}
	select {
	case b.natural <- struct{}{}:
	default:
	}
}

// Enqueue never performs hardware I/O. The voice pipeline either deposits the
// semantic action immediately or reports a bounded-queue failure.
func (b *bodyController) Enqueue(action sirah.Action) error {
	if b == nil {
		return fmt.Errorf("body controller is nil")
	}
	select {
	case <-b.ctx.Done():
		return b.ctx.Err()
	default:
	}
	select {
	case b.actions <- action:
		return nil
	default:
		return errBodyQueueFull
	}
}

func (b *bodyController) Wait() {
	if b != nil {
		<-b.done
	}
}

func (b *bodyController) run() {
	defer close(b.done)
	var lidsTimer *time.Timer
	var lidsDone <-chan time.Time
	lidsBusy := false
	actionInput := (<-chan sirah.Action)(b.actions)

	var naturalTimer *time.Timer
	var naturalDue <-chan time.Time
	defer func() {
		if naturalTimer != nil {
			naturalTimer.Stop()
		}
	}()
	resetNatural := func() {
		if naturalTimer == nil {
			return
		}
		if !naturalTimer.Stop() {
			select {
			case <-naturalTimer.C:
			default:
			}
		}
		naturalTimer.Reset(b.config.NextBlink())
	}
	setLidsBusy := func(duration time.Duration) {
		lidsBusy = true
		actionInput = nil
		if lidsTimer == nil {
			lidsTimer = time.NewTimer(duration)
		} else {
			if !lidsTimer.Stop() {
				select {
				case <-lidsTimer.C:
				default:
				}
			}
			lidsTimer.Reset(duration)
		}
		lidsDone = lidsTimer.C
	}
	defer func() {
		if lidsTimer != nil {
			lidsTimer.Stop()
		}
	}()
	dispatch := func(action sirah.Action, natural bool) bool {
		started := time.Now()
		err := b.executor.Execute(action)
		if b.config.OnResult != nil {
			b.config.OnResult(action, natural, err, time.Since(started))
		}
		if err != nil {
			return false
		}
		switch action {
		case sirah.ActionBlink:
			setLidsBusy(b.config.BlinkBusy)
		case sirah.ActionTired:
			setLidsBusy(b.config.TiredBusy)
		}
		return true
	}
	handleExplicit := func(action sirah.Action) {
		resetNatural()
		dispatch(action, false)
	}

	for {
		select {
		case <-b.ctx.Done():
			return
		case <-b.natural:
			if naturalTimer == nil {
				naturalTimer = time.NewTimer(b.config.NextBlink())
				naturalDue = naturalTimer.C
			}
		case action := <-actionInput:
			handleExplicit(action)
		case <-lidsDone:
			lidsBusy = false
			lidsDone = nil
			actionInput = b.actions
		case <-naturalDue:
			// Give an already queued explicit action priority over this cycle.
			select {
			case action := <-actionInput:
				handleExplicit(action)
			default:
				if !lidsBusy {
					dispatch(sirah.ActionBlink, true)
				}
				resetNatural()
			}
		}
	}
}

func naturalBlinkInterval() time.Duration {
	return 3*time.Second + time.Duration(rand.Int63n(int64(4*time.Second)))
}

type wakeSpeaker func(context.Context, string, func()) error

func generateCreativeWakeup(ctx context.Context, agent sirah.Agent, now time.Time) (string, error) {
	agent.ConversationStore = nil
	agent.AvailableActions = nil
	agent.Context.History = nil
	agent.Context.MemoryContext = ""
	agent.Context.AvailableActions = nil
	agent.Context.AvailableActionsSet = true

	prompt := agent.WakeupStyle
	if prompt == "" {
		prompt = sirah.DefaultWakeupStyle
	}
	fullPrompt := prompt + "\nIdentificador único de este arranque: " + now.UTC().Format(time.RFC3339Nano) + "."
	response, err := agent.RespondWithContext(ctx, fullPrompt, sirah.Context{})
	if err != nil {
		return "", err
	}
	if err := sirah.ValidateResponse(response); err != nil {
		return "", err
	}
	events := sirah.ParseTimeline(response.Speech)
	if len(response.Actions) > 0 || sirah.InlineActionCount(events) > 0 {
		return "", fmt.Errorf("creative wake-up returned physical actions")
	}
	text := strings.TrimSpace(sirah.CleanTimeline(events))
	if text == "" {
		return "", fmt.Errorf("creative wake-up returned empty speech")
	}
	if utf8.RuneCountInString(text) > 180 {
		return "", fmt.Errorf("creative wake-up exceeds 180 characters")
	}
	return text, nil
}

func runWakeup(ctx context.Context, text string, body *bodyController, speak wakeSpeaker) error {
	text = strings.TrimSpace(text)
	if text == "" || speak == nil {
		return nil
	}
	var once sync.Once
	var mu sync.Mutex
	var dispatchErr error
	err := speak(ctx, text, func() {
		once.Do(func() {
			for _, action := range []sirah.Action{sirah.ActionTired, sirah.ActionBlink, sirah.ActionCenter} {
				if enqueueErr := body.Enqueue(action); enqueueErr != nil {
					mu.Lock()
					dispatchErr = errors.Join(dispatchErr, enqueueErr)
					mu.Unlock()
				}
			}
		})
	})
	mu.Lock()
	defer mu.Unlock()
	return errors.Join(err, dispatchErr)
}
