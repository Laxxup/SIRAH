package sirah

import (
	"context"
	"testing"
	"time"
)

type testLLM struct{}

func (testLLM) Complete(context.Context, Context) (Response, error) {
	return Response{Speech: "ok", Actions: []Action{ActionCenter}}, nil
}

func TestAgentReturnsSemanticResponse(t *testing.T) {
	agent := Agent{LLM: testLLM{}, AvailableActions: []Action{ActionCenter}}
	response, err := agent.Respond(context.Background(), "hola")
	if err != nil {
		t.Fatal(err)
	}
	if response.Speech != "ok" || response.Actions[0] != ActionCenter {
		t.Fatalf("unexpected response: %#v", response)
	}
}

type cancellationLLM struct{ cancelled chan struct{} }

func (llm cancellationLLM) Complete(ctx context.Context, _ Context) (Response, error) {
	<-ctx.Done()
	close(llm.cancelled)
	return Response{}, ctx.Err()
}

func TestAgentPropagatesTurnCancellationToLLM(t *testing.T) {
	cancelled := make(chan struct{})
	agent := Agent{LLM: cancellationLLM{cancelled: cancelled}, Timeout: 10 * time.Millisecond}

	_, err := agent.Respond(context.Background(), "hola")
	if err == nil {
		t.Fatal("expected cancelled response")
	}
	select {
	case <-cancelled:
	case <-time.After(time.Second):
		t.Fatal("LLM did not receive cancellation")
	}
}

func TestLocalMemoryKeepsRecentTurns(t *testing.T) {
	memory := NewLocalMemory(1)
	if err := memory.AppendTurn(context.Background(), Turn{SessionID: "s", UserText: "uno"}); err != nil {
		t.Fatal(err)
	}
	if err := memory.AppendTurn(context.Background(), Turn{SessionID: "s", UserText: "dos"}); err != nil {
		t.Fatal(err)
	}
	turns, err := memory.Recent(context.Background(), "s", 10)
	if err != nil || len(turns) != 1 || turns[0].UserText != "dos" {
		t.Fatalf("turns = %#v, err = %v", turns, err)
	}
}
