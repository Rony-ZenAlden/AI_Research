// Package hub holds the per-user WebSocket connection registry and the
// goroutine pumps that read/write each connection.
package hub

import (
	"log/slog"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

const (
	writeWait      = 10 * time.Second
	pongWait       = 60 * time.Second
	pingPeriod     = (pongWait * 9) / 10
	maxMessageSize = 4096
	sendBuffer     = 64 // dropped messages count as backpressure
)

// Connection represents one open WebSocket.
type Connection struct {
	UserID int64
	ws     *websocket.Conn
	send   chan []byte
	hub    *Hub
	log    *slog.Logger
}

// Hub fans messages out to a user's open connections.
type Hub struct {
	mu    sync.RWMutex
	conns map[int64]map[*Connection]struct{}
	log   *slog.Logger
}

func New(log *slog.Logger) *Hub {
	return &Hub{
		conns: make(map[int64]map[*Connection]struct{}),
		log:   log,
	}
}

// NewConnection wires a Connection but does not register it. Caller must call Register.
func (h *Hub) NewConnection(userID int64, ws *websocket.Conn) *Connection {
	return &Connection{
		UserID: userID,
		ws:     ws,
		send:   make(chan []byte, sendBuffer),
		hub:    h,
		log:    h.log.With("user_id", userID),
	}
}

func (h *Hub) Register(c *Connection) {
	h.mu.Lock()
	defer h.mu.Unlock()
	set, ok := h.conns[c.UserID]
	if !ok {
		set = make(map[*Connection]struct{})
		h.conns[c.UserID] = set
	}
	set[c] = struct{}{}
	h.log.Debug("connection registered", "user_id", c.UserID, "total", len(set))
}

func (h *Hub) Unregister(c *Connection) {
	h.mu.Lock()
	defer h.mu.Unlock()
	if set, ok := h.conns[c.UserID]; ok {
		if _, present := set[c]; present {
			delete(set, c)
			close(c.send)
		}
		if len(set) == 0 {
			delete(h.conns, c.UserID)
		}
	}
	h.log.Debug("connection unregistered", "user_id", c.UserID)
}

// BroadcastToUser delivers msg to every open connection of userID.
// Drops the message for any connection whose send buffer is full, rather than
// blocking — backpressure must not stall the Redis subscriber.
func (h *Hub) BroadcastToUser(userID int64, msg []byte) {
	h.mu.RLock()
	defer h.mu.RUnlock()
	set, ok := h.conns[userID]
	if !ok {
		return
	}
	for c := range set {
		select {
		case c.send <- msg:
		default:
			h.log.Warn("send buffer full, dropping", "user_id", userID)
		}
	}
}

// ConnectedUsers reports how many distinct users have at least one open conn.
func (h *Hub) ConnectedUsers() int {
	h.mu.RLock()
	defer h.mu.RUnlock()
	return len(h.conns)
}

// ReadPump consumes incoming frames (mostly pongs). Exits on error.
func (c *Connection) ReadPump() {
	defer func() {
		c.hub.Unregister(c)
		_ = c.ws.Close()
	}()
	c.ws.SetReadLimit(maxMessageSize)
	_ = c.ws.SetReadDeadline(time.Now().Add(pongWait))
	c.ws.SetPongHandler(func(string) error {
		return c.ws.SetReadDeadline(time.Now().Add(pongWait))
	})
	for {
		// We don't expect inbound messages in Phase 1; just drain.
		if _, _, err := c.ws.ReadMessage(); err != nil {
			if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseAbnormalClosure) {
				c.log.Warn("read error", "err", err)
			}
			return
		}
	}
}

// WritePump pulls from c.send and pings periodically.
func (c *Connection) WritePump() {
	ticker := time.NewTicker(pingPeriod)
	defer func() {
		ticker.Stop()
		_ = c.ws.Close()
	}()
	for {
		select {
		case msg, ok := <-c.send:
			_ = c.ws.SetWriteDeadline(time.Now().Add(writeWait))
			if !ok {
				_ = c.ws.WriteMessage(websocket.CloseMessage, nil)
				return
			}
			if err := c.ws.WriteMessage(websocket.TextMessage, msg); err != nil {
				return
			}
		case <-ticker.C:
			_ = c.ws.SetWriteDeadline(time.Now().Add(writeWait))
			if err := c.ws.WriteMessage(websocket.PingMessage, nil); err != nil {
				return
			}
		}
	}
}
