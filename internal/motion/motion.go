package motion

import (
	"fmt"
	"github.com/Laxxup/SIRAH/internal/firmware"
	"github.com/Laxxup/SIRAH/internal/sirah"
	"math"
	"sync"
)

type TrackingMode string

const (
	TrackingIdle   TrackingMode = "IDLE"
	TrackingFace   TrackingMode = "FACE"
	TrackingPerson TrackingMode = "PERSON"
)

type Motion struct {
	mu            sync.RWMutex
	Hardware      firmware.Device
	RequestedMode TrackingMode
	AppliedMode   TrackingMode
	Health        HardwareHealth
	LastDelivery  firmware.DeliveryStatus
	LatestTarget  *Target
	nextCommandID uint64
	commands      map[uint64]commandRecord
}

type commandRecord struct {
	command    firmware.Command
	status     firmware.DeliveryStatus
	persistent bool
}

type HardwareHealth string

const (
	HardwareUnknown  HardwareHealth = "unknown"
	HardwareReady    HardwareHealth = "ready"
	HardwareDegraded HardwareHealth = "degraded"
	HardwareFailed   HardwareHealth = "failed"
)

func IsPersistentAction(action sirah.Action) bool {
	switch action {
	case sirah.ActionLookAtUser, sirah.ActionFollowPerson, sirah.ActionStopLooking:
		return true
	default:
		return false
	}
}

func IsDiscreteAction(action sirah.Action) bool {
	switch action {
	case sirah.ActionBlink, sirah.ActionTired, sirah.ActionNod, sirah.ActionCenter:
		return true
	default:
		return false
	}
}

type Target struct{ X, Y float64 }

func New(device firmware.Device) *Motion {
	return &Motion{Hardware: device, RequestedMode: TrackingIdle, AppliedMode: TrackingIdle, Health: HardwareUnknown, commands: make(map[uint64]commandRecord)}
}

// Execute changes persistent modes or attempts one discrete action. It never
// runs the persistent tracking loop; that loop submits targets separately.
func (m *Motion) Execute(action sirah.Action) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	switch action {
	case sirah.ActionLookAtUser:
		m.RequestedMode = TrackingFace
		return m.send(firmware.Command{Type: firmware.CommandMode, Mode: firmware.ModeFace})
	case sirah.ActionFollowPerson:
		m.RequestedMode = TrackingPerson
		return m.send(firmware.Command{Type: firmware.CommandMode, Mode: firmware.ModePerson})
	case sirah.ActionStopLooking:
		m.RequestedMode = TrackingIdle
		return m.send(firmware.Command{Type: firmware.CommandMode, Mode: firmware.ModeIdle})
	case sirah.ActionBlink:
		return m.send(firmware.Command{Type: firmware.CommandBlink})
	case sirah.ActionTired:
		return m.send(firmware.Command{Type: firmware.CommandTired})
	case sirah.ActionNod:
		return m.send(firmware.Command{Type: firmware.CommandNod})
	case sirah.ActionCenter:
		return m.send(firmware.Command{Type: firmware.CommandCenter})
	default:
		return fmt.Errorf("unknown motion action: %q", action)
	}
}

// UpdateTarget implements latest-wins for the local tracking target.
func (m *Motion) UpdateTarget(target Target) error {
	if math.IsNaN(target.X) || math.IsNaN(target.Y) || math.IsInf(target.X, 0) || math.IsInf(target.Y, 0) {
		return fmt.Errorf("target coordinates must be finite")
	}
	if target.X < -1 || target.X > 1 || target.Y < -1 || target.Y > 1 {
		return fmt.Errorf("target coordinates must be in [-1,1]")
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	copy := target
	m.LatestTarget = &copy
	if m.RequestedMode == TrackingIdle {
		return nil
	}
	return m.send(firmware.Command{Type: firmware.CommandTarget, X: target.X, Y: target.Y})
}

func (m *Motion) send(command firmware.Command) error {
	if command.ID == 0 {
		m.nextCommandID++
		command.ID = m.nextCommandID
	}
	if m.commands == nil {
		m.commands = make(map[uint64]commandRecord)
	}
	tracked := command.Type != firmware.CommandTarget
	if tracked {
		if command.Type == firmware.CommandMode {
			for id, record := range m.commands {
				if record.persistent {
					delete(m.commands, id)
				}
			}
		}
		m.commands[command.ID] = commandRecord{command: command, status: firmware.DeliverySent, persistent: command.Type == firmware.CommandMode}
	}
	if m.Hardware == nil {
		m.Health = HardwareDegraded
		delete(m.commands, command.ID)
		return firmware.ErrUnavailable
	}
	err := m.Hardware.Send(command)
	if err != nil {
		m.Health = HardwareDegraded
		delete(m.commands, command.ID)
		return err
	}
	m.LastDelivery = firmware.DeliverySent
	return nil
}

// HandleHardwareEvent applies an event only to the command or mode it names.
// Unknown and duplicate events are ignored by design.
func (m *Motion) HandleHardwareEvent(event firmware.Event) {
	m.mu.Lock()
	defer m.mu.Unlock()
	switch event.Type {
	case firmware.EventACK:
		record, ok := m.commands[event.CommandID]
		if !ok || record.status == firmware.DeliveryCompleted {
			return
		}
		record.status = firmware.DeliveryAcknowledged
		m.commands[event.CommandID] = record
		m.LastDelivery = firmware.DeliveryAcknowledged
		m.Health = HardwareReady
	case firmware.EventDONE:
		record, ok := m.commands[event.CommandID]
		if !ok || record.persistent || record.status == firmware.DeliveryCompleted {
			return
		}
		delete(m.commands, event.CommandID)
		m.LastDelivery = firmware.DeliveryCompleted
		m.Health = HardwareReady
	case firmware.EventSTATE:
		mode, ok := trackingMode(event.Mode)
		if !ok || mode != m.RequestedMode {
			return
		}
		m.AppliedMode = mode
		m.Health = HardwareReady
		for id, record := range m.commands {
			if record.persistent && record.command.Mode == event.Mode {
				delete(m.commands, id)
			}
		}
	case firmware.EventREADY:
		m.Health = HardwareReady
	case firmware.EventERR:
		m.Health = HardwareFailed
	}
}

func (m *Motion) CommandStatus(id uint64) (firmware.Command, firmware.DeliveryStatus, bool) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	record, ok := m.commands[id]
	if !ok {
		return firmware.Command{}, "", false
	}
	return record.command, record.status, true
}

func trackingMode(mode string) (TrackingMode, bool) {
	switch mode {
	case firmware.ModeIdle:
		return TrackingIdle, true
	case firmware.ModeFace:
		return TrackingFace, true
	case firmware.ModePerson:
		return TrackingPerson, true
	default:
		return "", false
	}
}

func (m *Motion) Snapshot() (TrackingMode, TrackingMode, HardwareHealth, firmware.DeliveryStatus, *Target) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	var target *Target
	if m.LatestTarget != nil {
		copy := *m.LatestTarget
		target = &copy
	}
	return m.RequestedMode, m.AppliedMode, m.Health, m.LastDelivery, target
}

// ConfirmAppliedMode records an explicit hardware acknowledgement. Motion does
// not infer physical state from a successful transport write.
func (m *Motion) ConfirmAppliedMode(mode TrackingMode) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if mode == TrackingIdle || mode == TrackingFace || mode == TrackingPerson {
		m.AppliedMode = mode
		m.Health = HardwareReady
	}
}
