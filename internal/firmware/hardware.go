package firmware

import "errors"

type CommandType string

const (
	CommandCenter    CommandType = "CENTER"
	CommandBlink     CommandType = "BLINK"
	CommandTired     CommandType = "TIRED"
	CommandNod       CommandType = "NOD"
	CommandTarget    CommandType = "TARGET"
	CommandMode      CommandType = "MODE"
	CommandHeartbeat CommandType = "HEARTBEAT"
	CommandStatus    CommandType = "STATUS"
)

type Command struct {
	ID   uint64
	Type CommandType
	Mode string
	X    float64
	Y    float64
}

const (
	ModeIdle   = "IDLE"
	ModeFace   = "FACE"
	ModePerson = "PERSON"
)

// DeliveryStatus describes how far a command got; it never implies physical completion.
type DeliveryStatus string

const (
	DeliverySent         DeliveryStatus = "sent"
	DeliveryAcknowledged DeliveryStatus = "acknowledged"
	DeliveryCompleted    DeliveryStatus = "completed"
)

// StatusDevice may provide stronger delivery guarantees than Device.Send.
// Device.Send alone only guarantees that the transport accepted the write.
type StatusDevice interface {
	Device
	SendWithStatus(Command) (DeliveryStatus, error)
}

type Device interface {
	Send(Command) error
}

var ErrUnavailable = errors.New("physical hardware unavailable")

// Unavailable makes absence of the physical body explicit.
type Unavailable struct{}

func (Unavailable) Send(Command) error { return ErrUnavailable }
