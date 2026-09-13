// Package agent define la identidad, personalidad, memoria, estado e historial del agente.
package sirah

import (
	"context"
	"fmt"
	"strings"
	"time"
)

type Responder interface {
	Respond(context.Context, string) (Response, error)
}

type ContextResponder interface {
	RespondWithContext(context.Context, string, Context) (Response, error)
}

type ConversationRecorder interface {
	RecordTurn(context.Context, string, Response) error
}

type ContextTiming struct {
	Total  time.Duration
	Recent time.Duration
	Recall time.Duration
}

// Agent es la "mente" del robot. Solo decide alto nivel: qué decir y qué acciones hacer.
type Agent struct {
	Name string
	// Persona describes the conversational personality.
	Persona Persona
	// State es el estado interno del agente.
	State State
	// Memory es la memoria de largo plazo.
	// ConversationStore contiene historial reciente y memoria futura.
	ConversationStore   Memory
	SessionID           string
	UserID              string
	HistoryLimit        int
	ContextDebug        func(historyTurns int, memoryRetrieved bool)
	ConversationWarning func(error)
	ContextTiming       func(ContextTiming)
	LLMDuration         func(time.Duration)
	// AvailableActions documenta qué acciones puede ejecutar (ver DefaultActions en context.go).
	AvailableActions  []Action
	LLM               LLM
	Context           Context
	Timeout           time.Duration
	TechnicalContract string
}

// Respond procesa el input del usuario y devuelve una Response de alto nivel.
func (a Agent) Respond(ctx context.Context, input string) (Response, error) {
	return a.respond(ctx, input, Context{})
}

func (a Agent) RespondWithContext(ctx context.Context, input string, runtime Context) (Response, error) {
	return a.respond(ctx, input, runtime)
}

func (a Agent) RespondWithContextStream(ctx context.Context, input string, runtime Context, emit func(string) error) (Response, error) {
	if a.LLM == nil {
		return Response{}, fmt.Errorf("LLM is not configured")
	}
	streamer, ok := a.LLM.(StreamingLLM)
	if !ok {
		return a.respond(ctx, input, runtime)
	}
	if a.Timeout > 0 {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, a.Timeout)
		defer cancel()
	}
	contextData := a.BuildContext(ctx, input)
	if runtime.Perception != nil || runtime.HardwareStatus != (HardwareStatus{}) || runtime.State != (State{}) {
		contextData.State, contextData.Perception, contextData.HardwareStatus = runtime.State, runtime.Perception, runtime.HardwareStatus
	}
	if runtime.HardwareStatus != (HardwareStatus{}) {
		contextData.AvailableActions = FilterActions(contextData.AvailableActions, runtime.HardwareStatus)
		contextData.AvailableActionsSet = true
	}
	started := time.Now()
	response, err := streamer.Stream(ctx, contextData, emit)
	if a.LLMDuration != nil {
		a.LLMDuration(time.Since(started))
	}
	if err == nil {
		err = ValidateResponse(response)
	}
	return response, err
}

func (a Agent) respond(ctx context.Context, input string, runtime Context) (Response, error) {
	if a.LLM == nil {
		return Response{}, fmt.Errorf("LLM is not configured")
	}
	if a.Timeout > 0 {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, a.Timeout)
		defer cancel()
	}
	contextData := a.BuildContext(ctx, input)
	if runtime.Perception != nil || runtime.HardwareStatus != (HardwareStatus{}) || runtime.State != (State{}) {
		contextData.State = runtime.State
		contextData.Perception = runtime.Perception
		contextData.HardwareStatus = runtime.HardwareStatus
	}
	if runtime.HardwareStatus != (HardwareStatus{}) {
		contextData.AvailableActions = FilterActions(contextData.AvailableActions, runtime.HardwareStatus)
		contextData.AvailableActionsSet = true
	}
	started := time.Now()
	response, err := a.LLM.Complete(ctx, contextData)
	if a.LLMDuration != nil {
		a.LLMDuration(time.Since(started))
	}
	return response, err
}

func (a Agent) BuildContext(ctx context.Context, input string) Context {
	started := time.Now()
	var recentDuration, recallDuration time.Duration
	defer func() {
		if a.ContextTiming != nil {
			a.ContextTiming(ContextTiming{Total: time.Since(started), Recent: recentDuration, Recall: recallDuration})
		}
	}()
	contextData := a.Context
	if a.TechnicalContract == "" {
		a.TechnicalContract = DefaultTechnicalContract
	}
	contextData.TechnicalContract = a.TechnicalContract
	contextData.Identity = DefaultIdentity
	contextData.State = a.State
	if a.ConversationStore != nil {
		historyLimit := a.HistoryLimit
		if historyLimit <= 0 {
			historyLimit = 12
		}
		recentStarted := time.Now()
		history, err := a.ConversationStore.Recent(ctx, a.SessionID, historyLimit)
		recentDuration = time.Since(recentStarted)
		if err == nil {
			contextData.History = history
		} else if a.ConversationWarning != nil {
			a.ConversationWarning(fmt.Errorf("recent conversation unavailable: %w", err))
		}
		recallStarted := time.Now()
		var memoryContext string
		var recallErr error
		if cached, ok := a.ConversationStore.(interface{ CachedRecall(string, string) string }); ok {
			memoryContext = cached.CachedRecall(a.UserID, input)
		} else {
			memoryCtx, cancel := context.WithTimeout(ctx, 150*time.Millisecond)
			memoryContext, recallErr = a.ConversationStore.Recall(memoryCtx, a.UserID, input)
			cancel()
		}
		recallDuration = time.Since(recallStarted)
		if recallErr == nil {
			contextData.MemoryContext = memoryContext
		} else if a.ConversationWarning != nil {
			a.ConversationWarning(fmt.Errorf("conversation memory unavailable: %w", recallErr))
		}
		if a.ContextDebug != nil {
			a.ContextDebug(len(contextData.History), strings.TrimSpace(contextData.MemoryContext) != "")
		}
	}
	if len(a.AvailableActions) > 0 {
		contextData.AvailableActions = a.AvailableActions
	}
	contextData.UserInput = input
	contextData.SystemContent = renderContextBlocks(ContextBuilder{}.Build(contextData, a.Persona))
	return contextData
}

func (a Agent) RecordTurn(ctx context.Context, input string, response Response) error {
	if a.ConversationStore == nil {
		return nil
	}
	return a.ConversationStore.AppendTurn(ctx, Turn{
		SessionID: a.SessionID,
		UserID:    a.UserID,
		UserText:  input,
		RobotText: response.Speech,
		CreatedAt: time.Now().UTC(),
	})
}
