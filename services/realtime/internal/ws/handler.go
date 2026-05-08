// Package ws upgrades HTTP requests to WebSockets after JWT validation.
package ws

import (
	"encoding/json"
	"log/slog"
	"net/http"
	"time"

	"github.com/gorilla/websocket"

	"neuroseek/realtime/internal/auth"
	"neuroseek/realtime/internal/hub"
)

func newUpgrader(allowedOrigins []string) websocket.Upgrader {
	return websocket.Upgrader{
		ReadBufferSize:  2048,
		WriteBufferSize: 4096,
		CheckOrigin:     originChecker(allowedOrigins),
	}
}

func originChecker(allowed []string) func(*http.Request) bool {
	allowAll := false
	for _, o := range allowed {
		if o == "*" {
			allowAll = true
			break
		}
	}
	return func(r *http.Request) bool {
		if allowAll {
			return true
		}
		origin := r.Header.Get("Origin")
		for _, o := range allowed {
			if o == origin {
				return true
			}
		}
		return false
	}
}

// UserHandler returns an http.HandlerFunc that authenticates the request via
// ?token=<JWT>, upgrades to WS, registers the connection with the hub, and
// runs read/write pumps until the client disconnects.
func UserHandler(h *hub.Hub, v *auth.Verifier, allowedOrigins []string, log *slog.Logger) http.HandlerFunc {
	upgrader := newUpgrader(allowedOrigins)
	return func(w http.ResponseWriter, r *http.Request) {
		token := r.URL.Query().Get("token")
		claims, err := v.Verify(token)
		if err != nil {
			http.Error(w, "unauthorized: "+err.Error(), http.StatusUnauthorized)
			return
		}
		ws, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			log.Warn("ws upgrade failed", "err", err)
			return
		}
		conn := h.NewConnection(claims.UserID, ws)
		h.Register(conn)

		// Send a hello frame so the client can confirm auth + subscription.
		// WriteSend is itself non-blocking (drops if the queue is full).
		if hello, err := json.Marshal(map[string]any{
			"type": "hello",
			"data": map[string]any{
				"user_id": claims.UserID,
				"hub":     "neuroseek-realtime",
			},
			"ts": time.Now().Unix(),
		}); err == nil {
			conn.WriteSend(hello)
		}

		go conn.WritePump()
		conn.ReadPump() // blocks until disconnect
	}
}
