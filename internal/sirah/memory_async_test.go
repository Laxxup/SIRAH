package sirah

import (
	"context"
	"testing"
	"time"
)

func TestHybridMemoryCachedRecallDoesNotWaitForRemote(t *testing.T) {
	remoteCtx, cancelRemote := context.WithCancel(context.Background())
	memory := &HybridMemory{
		cache:        map[string]string{},
		refreshing:   map[string]bool{},
		remoteCtx:    remoteCtx,
		cancel:       cancelRemote,
		remoteRecall: func(ctx context.Context, _, _ string) (string, error) { <-ctx.Done(); return "", ctx.Err() },
	}
	start := time.Now()
	if got := memory.CachedRecall("user", "query"); got != "" {
		t.Fatalf("initial cached recall = %q", got)
	}
	if elapsed := time.Since(start); elapsed > 20*time.Millisecond {
		t.Fatalf("cached recall blocked for %s", elapsed)
	}
	closeCtx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	cancelRemote()
	_ = memory.Close(closeCtx)
}

func TestAgentBuildContextDoesNotWaitForSlowRemoteRecall(t *testing.T) {
	remoteCtx, cancelRemote := context.WithCancel(context.Background())
	memory := &HybridMemory{
		local:      NewLocalMemory(12),
		cache:      map[string]string{},
		refreshing: map[string]bool{},
		remoteCtx:  remoteCtx,
		cancel:     cancelRemote,
		remoteRecall: func(ctx context.Context, _, _ string) (string, error) {
			<-ctx.Done()
			return "", ctx.Err()
		},
	}
	agent := Agent{ConversationStore: memory, SessionID: "session", UserID: "user"}
	start := time.Now()
	agent.BuildContext(context.Background(), "hola")
	if elapsed := time.Since(start); elapsed > 20*time.Millisecond {
		t.Fatalf("BuildContext blocked for %s", elapsed)
	}
	closeCtx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	cancelRemote()
	_ = memory.Close(closeCtx)
}

func TestHybridMemoryKeepsLocalHistoryWhenRemoteIsUnavailable(t *testing.T) {
	memory := NewHybridMemory(NewLocalMemory(2), nil, nil)
	if err := memory.AppendTurn(context.Background(), Turn{SessionID: "session", UserText: "local", RobotText: "respuesta"}); err != nil {
		t.Fatal(err)
	}
	history, err := memory.Recent(context.Background(), "session", 2)
	if err != nil || len(history) != 1 || history[0].UserText != "local" {
		t.Fatalf("history=%#v err=%v", history, err)
	}
	_ = memory.Close(context.Background())
}

func TestHybridMemoryCachedValueIsStableUntilRefreshCompletes(t *testing.T) {
	memory := &HybridMemory{cache: map[string]string{}, refreshing: map[string]bool{}}
	memory.cache["user\x00query"] = "old"
	if got := memory.cache["user\x00query"]; got != "old" {
		t.Fatalf("cached value = %q", got)
	}
	if memory.cache["user\x00query"] == "new" {
		t.Fatal("remote value changed cached history retroactively")
	}
}

func TestHybridMemoryDoesNotStartRefreshAfterClose(t *testing.T) {
	remoteCtx, cancelRemote := context.WithCancel(context.Background())
	memory := &HybridMemory{cache: map[string]string{}, refreshing: map[string]bool{}, remoteCtx: remoteCtx, cancel: cancelRemote, remoteRecall: func(context.Context, string, string) (string, error) {
		return "unexpected", nil
	}}
	if err := memory.Close(context.Background()); err != nil {
		t.Fatal(err)
	}
	if got := memory.CachedRecall("user", "query"); got != "" {
		t.Fatalf("cached recall after close = %q", got)
	}
	if len(memory.refreshing) != 0 {
		t.Fatalf("refreshes after close = %#v", memory.refreshing)
	}
}
