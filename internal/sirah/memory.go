package sirah

import (
	"context"
	"sync"
	"time"

	zep "github.com/getzep/zep-go/v3"
	zepclient "github.com/getzep/zep-go/v3/client"
)

// Turn is one complete user/assistant exchange.
type Turn struct {
	SessionID string
	UserID    string
	UserText  string
	RobotText string
	CreatedAt time.Time
}

// Memory keeps local history primary and optionally mirrors it to Zep.
type Memory interface {
	Recent(context.Context, string, int) ([]Turn, error)
	Recall(context.Context, string, string) (string, error)
	AppendTurn(context.Context, Turn) error
}

type LocalMemory struct {
	mu    sync.RWMutex
	limit int
	turns map[string][]Turn
}

func NewLocalMemory(limit int) *LocalMemory {
	if limit <= 0 {
		limit = 12
	}
	return &LocalMemory{limit: limit, turns: make(map[string][]Turn)}
}

func (m *LocalMemory) Recent(ctx context.Context, session string, limit int) ([]Turn, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	if session == "" || limit <= 0 {
		return nil, nil
	}
	m.mu.RLock()
	defer m.mu.RUnlock()
	turns := m.turns[session]
	if len(turns) > limit {
		turns = turns[len(turns)-limit:]
	}
	return append([]Turn(nil), turns...), nil
}

func (m *LocalMemory) Recall(ctx context.Context, _, _ string) (string, error) {
	return "", ctx.Err()
}

func (m *LocalMemory) AppendTurn(ctx context.Context, turn Turn) error {
	if err := ctx.Err(); err != nil {
		return err
	}
	if turn.SessionID == "" {
		return nil
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	turns := append(m.turns[turn.SessionID], turn)
	if len(turns) > m.limit {
		turns = turns[len(turns)-m.limit:]
	}
	m.turns[turn.SessionID] = turns
	return nil
}

type HybridMemory struct {
	local        *LocalMemory
	remote       *ZepMemory
	onWarning    func(error)
	pending      sync.WaitGroup
	remoteCtx    context.Context
	cancel       context.CancelFunc
	cacheMu      sync.Mutex
	cache        map[string]string
	refreshing   map[string]bool
	remoteRecall func(context.Context, string, string) (string, error)
	closed       bool
}

func NewHybridMemory(local *LocalMemory, remote *ZepMemory, onWarning func(error)) *HybridMemory {
	ctx, cancel := context.WithCancel(context.Background())
	var remoteRecall func(context.Context, string, string) (string, error)
	if remote != nil {
		remoteRecall = remote.Recall
	}
	return &HybridMemory{local: local, remote: remote, onWarning: onWarning, remoteCtx: ctx, cancel: cancel, cache: make(map[string]string), refreshing: make(map[string]bool), remoteRecall: remoteRecall}
}

func (m *HybridMemory) Recent(ctx context.Context, session string, limit int) ([]Turn, error) {
	if m.local == nil {
		return nil, nil
	}
	return m.local.Recent(ctx, session, limit)
}

func (m *HybridMemory) Recall(ctx context.Context, user, query string) (string, error) {
	if m.remote == nil {
		return "", nil
	}
	return m.remote.Recall(ctx, user, query)
}

// CachedRecall never waits for remote memory. It returns the latest successful
// result for this query and refreshes it asynchronously for a future turn.
func (m *HybridMemory) CachedRecall(user, query string) string {
	if m == nil || m.remoteRecall == nil || (m.remote != nil && m.remote.client == nil) {
		return ""
	}
	key := user + "\x00" + query
	m.cacheMu.Lock()
	if m.closed {
		m.cacheMu.Unlock()
		return m.cache[key]
	}
	value := m.cache[key]
	if !m.refreshing[key] {
		m.refreshing[key] = true
		m.pending.Add(1)
		go m.refreshRecall(key, user, query)
	}
	m.cacheMu.Unlock()
	return value
}

func (m *HybridMemory) refreshRecall(key, user, query string) {
	defer m.pending.Done()
	defer func() {
		m.cacheMu.Lock()
		delete(m.refreshing, key)
		m.cacheMu.Unlock()
	}()
	ctx, cancel := context.WithTimeout(m.remoteCtx, 5*time.Second)
	defer cancel()
	value, err := m.remoteRecall(ctx, user, query)
	if err != nil {
		if m.onWarning != nil {
			m.onWarning(err)
		}
		return
	}
	m.cacheMu.Lock()
	m.cache[key] = value
	m.cacheMu.Unlock()
}

func (m *HybridMemory) AppendTurn(ctx context.Context, turn Turn) error {
	if m.local != nil {
		if err := m.local.AppendTurn(ctx, turn); err != nil {
			return err
		}
	}
	if m.remote != nil {
		m.pending.Add(1)
		go func() {
			defer m.pending.Done()
			ctx, cancel := context.WithTimeout(m.remoteCtx, 5*time.Second)
			defer cancel()
			if err := m.remote.AppendTurn(ctx, turn); err != nil && m.onWarning != nil {
				m.onWarning(err)
			}
		}()
	}
	return nil
}

func (m *HybridMemory) Close(ctx context.Context) error {
	m.cacheMu.Lock()
	if !m.closed {
		m.closed = true
		if m.cancel != nil {
			m.cancel()
		}
	}
	m.cacheMu.Unlock()
	done := make(chan struct{})
	go func() { m.pending.Wait(); close(done) }()
	select {
	case <-done:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

type ZepMemory struct {
	client  *zepclient.Client
	mu      sync.Mutex
	users   map[string]bool
	threads map[string]bool
}

func NewZepMemory(client *zepclient.Client) *ZepMemory {
	return &ZepMemory{client: client, users: make(map[string]bool), threads: make(map[string]bool)}
}

func (m *ZepMemory) AppendTurn(ctx context.Context, turn Turn) error {
	if err := m.ensureUser(ctx, turn.UserID); err != nil {
		return err
	}
	if err := m.ensureThread(ctx, turn.SessionID, turn.UserID); err != nil {
		return err
	}
	created := turn.CreatedAt.UTC().Format(time.RFC3339Nano)
	_, err := m.client.Thread.AddMessages(ctx, turn.SessionID, &zep.AddThreadMessagesRequest{Messages: []*zep.Message{
		{Content: turn.UserText, Role: zep.RoleTypeUserRole, CreatedAt: &created},
		{Content: turn.RobotText, Role: zep.RoleTypeAssistantRole, CreatedAt: &created},
	}})
	return err
}

func (m *ZepMemory) Recent(ctx context.Context, session string, limit int) ([]Turn, error) {
	result, err := m.client.Thread.Get(ctx, session, &zep.ThreadGetRequest{Lastn: &limit})
	if err != nil {
		return nil, err
	}
	turns := make([]Turn, 0, len(result.Messages)/2)
	var current Turn
	for _, message := range result.Messages {
		if message == nil {
			continue
		}
		if message.Role == zep.RoleTypeUserRole {
			current = Turn{SessionID: session, UserText: message.Content}
		}
		if message.Role == zep.RoleTypeAssistantRole && current.UserText != "" {
			current.RobotText = message.Content
			turns = append(turns, current)
			current = Turn{}
		}
	}
	return turns, nil
}

func (m *ZepMemory) Recall(ctx context.Context, user, query string) (string, error) {
	result, err := m.client.Graph.Search(ctx, &zep.GraphSearchQuery{Query: query, UserID: &user, Scope: zep.GraphSearchScopeAuto.Ptr(), Limit: intPtr(10)})
	if err != nil || result == nil || result.Context == nil {
		return "", err
	}
	return *result.Context, nil
}

func (m *ZepMemory) ensureUser(ctx context.Context, user string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.users[user] {
		return nil
	}
	if _, err := m.client.User.Get(ctx, user); err != nil {
		if _, err = m.client.User.Add(ctx, &zep.CreateUserRequest{UserID: user}); err != nil {
			return err
		}
	}
	m.users[user] = true
	return nil
}

func (m *ZepMemory) ensureThread(ctx context.Context, session, user string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.threads[session] {
		return nil
	}
	if _, err := m.client.Thread.Get(ctx, session, &zep.ThreadGetRequest{Lastn: intPtr(1)}); err != nil {
		if _, err = m.client.Thread.Create(ctx, &zep.CreateThreadRequest{ThreadID: session, UserID: user}); err != nil {
			return err
		}
	}
	m.threads[session] = true
	return nil
}

func intPtr(v int) *int { return &v }
