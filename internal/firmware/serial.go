package firmware

import (
	"bufio"
	"context"
	"fmt"
	"io"
	"strconv"
	"strings"
	"sync"
	"time"
)

// NewSerial wraps an already opened serial stream.
func NewSerial(writer io.Writer) *Serial { return &Serial{Writer: writer} }

// Serial writes the small, line-oriented protocol used by the firmware.
type Serial struct {
	Writer      io.Writer
	Reader      io.Reader
	mu          sync.Mutex
	stateMu     sync.RWMutex
	nextID      uint64
	events      chan Event
	readerDone  chan struct{}
	readerStop  chan struct{}
	watcherDone chan struct{}
	closeOnce   sync.Once
	closeDone   chan struct{}
	started     bool
	ready       bool
}

func (s *Serial) Send(command Command) error {
	if s.Writer == nil {
		return ErrUnavailable
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	command = s.assignID(command)
	return s.write(command)
}

func (s *Serial) assignID(command Command) Command {
	if command.ID == 0 {
		s.nextID++
		command.ID = s.nextID
	}
	if command.ID > s.nextID {
		s.nextID = command.ID
	}
	return command
}

func (s *Serial) write(command Command) error {
	if command.Type == CommandMode {
		if command.Mode == "" {
			return fmt.Errorf("MODE requires a mode")
		}
		_, err := fmt.Fprintf(s.Writer, "%d %s %s\n", command.ID, command.Type, command.Mode)
		return err
	}
	if command.Type == CommandTarget {
		_, err := fmt.Fprintf(s.Writer, "%d %s %.3f %.3f\n", command.ID, command.Type, command.X, command.Y)
		return err
	}
	_, err := fmt.Fprintf(s.Writer, "%d %s\n", command.ID, command.Type)
	return err
}

// Start consumes firmware events until the context is cancelled or the reader closes.
func (s *Serial) Start(ctx context.Context) error {
	if s.Reader == nil {
		return ErrUnavailable
	}
	s.stateMu.Lock()
	if s.started {
		s.stateMu.Unlock()
		return nil
	}
	s.started = true
	s.events = make(chan Event, 16)
	s.readerDone = make(chan struct{})
	s.readerStop = make(chan struct{})
	s.watcherDone = make(chan struct{})
	s.closeDone = make(chan struct{})
	events := s.events
	readerDone := s.readerDone
	readerStop := s.readerStop
	watcherDone := s.watcherDone
	s.stateMu.Unlock()
	go func() {
		defer close(readerDone)
		scanner := bufio.NewScanner(s.Reader)
		for scanner.Scan() {
			event, err := ParseEvent(scanner.Text())
			if err != nil {
				continue
			}
			if event.Type == EventREADY {
				s.stateMu.Lock()
				s.ready = true
				s.stateMu.Unlock()
			}
			select {
			case events <- event:
			case <-ctx.Done():
				return
			}
		}
		close(events)
	}()
	go func() {
		defer close(watcherDone)
		select {
		case <-ctx.Done():
			if closer, ok := s.Reader.(io.Closer); ok {
				_ = closer.Close()
			}
		case <-readerStop:
		}
	}()
	return nil
}

// WaitReady blocks until the firmware reports READY or ctx expires.
// It observes the flag set by the reader; no polling of the device itself.
func (s *Serial) WaitReady(ctx context.Context) error {
	ticker := time.NewTicker(50 * time.Millisecond)
	defer ticker.Stop()
	for {
		s.stateMu.RLock()
		ready := s.ready
		s.stateMu.RUnlock()
		if ready {
			return nil
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
		}
	}
}

// Events exposes the single firmware event stream after Start. The runtime
// installs one permanent consumer after the synchronous startup handshake.
func (s *Serial) Events() <-chan Event {
	s.stateMu.RLock()
	defer s.stateMu.RUnlock()
	return s.events
}

// SendWithStatus waits for firmware acceptance and completion when events are available.
func (s *Serial) SendWithStatus(command Command) (DeliveryStatus, error) {
	if s.Writer == nil {
		return "", ErrUnavailable
	}
	s.mu.Lock()
	command = s.assignID(command)
	err := s.write(command)
	s.mu.Unlock()
	if err != nil {
		return DeliverySent, err
	}
	s.stateMu.RLock()
	started := s.started
	events := s.events
	s.stateMu.RUnlock()
	if !started || events == nil {
		return DeliverySent, nil
	}
	timeoutCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	acknowledged := false
	for {
		select {
		case event, ok := <-events:
			if !ok {
				return DeliverySent, io.EOF
			}
			switch event.Type {
			case EventACK:
				if event.CommandID == command.ID {
					acknowledged = true
				}
			case EventDONE:
				if event.CommandID == command.ID {
					return DeliveryCompleted, nil
				}
			case EventREADY:
				// STATUS/HEARTBEAT are answered with bare READY (no ACK/DONE).
				// A bare READY also means the firmware is alive, so it only
				// satisfies these two command types, never BLINK/TARGET/etc.
				if command.Type == CommandStatus || command.Type == CommandHeartbeat {
					return DeliveryAcknowledged, nil
				}
			case EventERR:
				return DeliverySent, fmt.Errorf("firmware error: %s", event.Code)
			}
		case <-timeoutCtx.Done():
			if acknowledged {
				return DeliveryAcknowledged, timeoutCtx.Err()
			}
			return DeliverySent, timeoutCtx.Err()
		}
	}
}

func (s *Serial) Ready() bool {
	s.stateMu.RLock()
	defer s.stateMu.RUnlock()
	return s.ready
}

func (s *Serial) Close() error {
	if s == nil {
		return nil
	}
	s.closeOnce.Do(func() {
		s.stateMu.RLock()
		readerDone, readerStop, watcherDone, closeDone := s.readerDone, s.readerStop, s.watcherDone, s.closeDone
		reader, writer := s.Reader, s.Writer
		s.stateMu.RUnlock()
		if readerStop != nil {
			close(readerStop)
		}
		if closer, ok := reader.(io.Closer); ok {
			_ = closer.Close()
		}
		if closer, ok := writer.(io.Closer); ok {
			_ = closer.Close()
		}
		if readerDone != nil {
			<-readerDone
		}
		if watcherDone != nil {
			<-watcherDone
		}
		if closeDone != nil {
			close(closeDone)
		}
	})
	if s.closeDone != nil {
		<-s.closeDone
	}
	return nil
}

type EventType string

const (
	EventACK   EventType = "ACK"
	EventDONE  EventType = "DONE"
	EventSTATE EventType = "STATE"
	EventREADY EventType = "READY"
	EventERR   EventType = "ERR"
)

type Event struct {
	Type      EventType
	CommandID uint64
	Mode      string
	Code      string
}

func ParseEvent(line string) (Event, error) {
	fields := strings.Fields(line)
	if len(fields) == 0 {
		return Event{}, fmt.Errorf("empty hardware event")
	}
	event := Event{Type: EventType(fields[0])}
	switch event.Type {
	case EventACK, EventDONE:
		if len(fields) != 2 {
			return Event{}, fmt.Errorf("%s requires command ID", event.Type)
		}
		id, err := strconv.ParseUint(fields[1], 10, 64)
		if err != nil || id == 0 {
			return Event{}, fmt.Errorf("invalid command ID %q", fields[1])
		}
		event.CommandID = id
	case EventSTATE:
		if len(fields) != 2 || !validMode(fields[1]) {
			return Event{}, fmt.Errorf("STATE requires IDLE, FACE, or PERSON")
		}
		event.Mode = fields[1]
	case EventREADY:
		if len(fields) != 1 {
			return Event{}, fmt.Errorf("READY has no arguments")
		}
	case EventERR:
		if len(fields) != 2 {
			return Event{}, fmt.Errorf("ERR requires an error code")
		}
		event.Code = fields[1]
	default:
		return Event{}, fmt.Errorf("unknown hardware event %q", fields[0])
	}
	return event, nil
}

func ReadEvent(scanner *bufio.Scanner) (Event, error) {
	if scanner == nil || !scanner.Scan() {
		if scanner != nil && scanner.Err() != nil {
			return Event{}, scanner.Err()
		}
		return Event{}, io.EOF
	}
	return ParseEvent(scanner.Text())
}

func validMode(mode string) bool {
	return mode == ModeIdle || mode == ModeFace || mode == ModePerson
}
