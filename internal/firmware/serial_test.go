package firmware

import (
	"bytes"
	"context"
	"os"
	"strings"
	"testing"
	"time"
)

func TestSerialUsesSemanticCommands(t *testing.T) {
	var output bytes.Buffer
	serial := NewSerial(&output)
	if err := serial.Send(Command{Type: CommandCenter}); err != nil {
		t.Fatal(err)
	}
	if output.String() != "1 CENTER\n" {
		t.Fatalf("output = %q", output.String())
	}
}

func TestSerialCloseStopsReader(t *testing.T) {
	reader, writer, err := os.Pipe()
	if err != nil {
		t.Fatal(err)
	}
	serial := NewSerial(writer)
	serial.Reader = reader
	if err := serial.Start(context.Background()); err != nil {
		t.Fatal(err)
	}
	done := make(chan struct{})
	go func() {
		_ = serial.Close()
		close(done)
	}()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("serial Close did not join reader")
	}
}

func TestSerialReadsReadyAckAndDone(t *testing.T) {
	var output bytes.Buffer
	serial := NewSerial(&output)
	serial.Reader = strings.NewReader("READY\nACK 1\nDONE 1\n")
	if err := serial.Start(context.Background()); err != nil {
		t.Fatal(err)
	}
	status, err := serial.SendWithStatus(Command{Type: CommandCenter})
	if err != nil || status != DeliveryCompleted {
		t.Fatalf("status = %q, err = %v", status, err)
	}
	if !serial.Ready() {
		t.Fatal("serial did not record READY")
	}
}

func TestDeliveryStatusSeparatesTransportFromCompletion(t *testing.T) {
	var output bytes.Buffer
	serial := NewSerial(&output)
	status, err := serial.SendWithStatus(Command{Type: CommandBlink})
	if err != nil {
		t.Fatal(err)
	}
	if status != DeliverySent {
		t.Fatalf("status = %q, want sent", status)
	}
	if output.String() != "1 BLINK\n" {
		t.Fatalf("output = %q", output.String())
	}
}

func TestStatusAcceptedByBareReady(t *testing.T) {
	var output bytes.Buffer
	serial := NewSerial(&output)
	serial.Reader = strings.NewReader("READY\n")
	if err := serial.Start(context.Background()); err != nil {
		t.Fatal(err)
	}
	status, err := serial.SendWithStatus(Command{Type: CommandStatus})
	if err != nil || status != DeliveryAcknowledged {
		t.Fatalf("status = %q, err = %v", status, err)
	}
	if output.String() != "1 STATUS\n" {
		t.Fatalf("output = %q", output.String())
	}
}

func TestBareReadyDoesNotCompleteBlink(t *testing.T) {
	var output bytes.Buffer
	serial := NewSerial(&output)
	// Boot READY followed by the real ACK/DONE for command 1.
	serial.Reader = strings.NewReader("READY\nACK 1\nDONE 1\n")
	if err := serial.Start(context.Background()); err != nil {
		t.Fatal(err)
	}
	status, err := serial.SendWithStatus(Command{Type: CommandBlink})
	if err != nil || status != DeliveryCompleted {
		t.Fatalf("status = %q, err = %v", status, err)
	}
}

func TestWaitReadyObservesReaderFlag(t *testing.T) {
	var output bytes.Buffer
	serial := NewSerial(&output)
	serial.Reader = strings.NewReader("READY\n")
	if err := serial.Start(context.Background()); err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	if err := serial.WaitReady(ctx); err != nil {
		t.Fatal(err)
	}
}

func TestWaitReadyTimesOutWithoutReady(t *testing.T) {
	var output bytes.Buffer
	serial := NewSerial(&output)
	serial.Reader = strings.NewReader("ACK 1\n")
	if err := serial.Start(context.Background()); err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()
	if err := serial.WaitReady(ctx); err == nil {
		t.Fatal("expected timeout without READY")
	}
}

func TestEventsExposePermanentReaderStream(t *testing.T) {
	var output bytes.Buffer
	serial := NewSerial(&output)
	serial.Reader = strings.NewReader("ACK 7\nDONE 7\n")
	if err := serial.Start(context.Background()); err != nil {
		t.Fatal(err)
	}
	events := serial.Events()
	first, ok := <-events
	if !ok || first.Type != EventACK || first.CommandID != 7 {
		t.Fatalf("first event = %#v, ok=%t", first, ok)
	}
	second, ok := <-events
	if !ok || second.Type != EventDONE || second.CommandID != 7 {
		t.Fatalf("second event = %#v, ok=%t", second, ok)
	}
}
