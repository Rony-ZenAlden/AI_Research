// Package pubsub bridges Redis pub/sub messages on "user:<id>" channels into
// the Hub's per-user broadcast.
package pubsub

import (
	"context"
	"fmt"
	"log/slog"
	"strconv"
	"strings"

	"github.com/redis/go-redis/v9"

	"neuroseek/realtime/internal/hub"
)

const userChannelPattern = "user:*"

type Subscriber struct {
	rdb *redis.Client
	hub *hub.Hub
	log *slog.Logger
}

func New(rdb *redis.Client, h *hub.Hub, log *slog.Logger) *Subscriber {
	return &Subscriber{rdb: rdb, hub: h, log: log}
}

// Run subscribes to "user:*" and fans out received messages to the hub.
// Returns when ctx is canceled or the underlying connection closes.
func (s *Subscriber) Run(ctx context.Context) error {
	ps := s.rdb.PSubscribe(ctx, userChannelPattern)
	defer ps.Close()

	if _, err := ps.Receive(ctx); err != nil {
		return fmt.Errorf("psubscribe: %w", err)
	}
	s.log.Info("subscribed", "pattern", userChannelPattern)

	ch := ps.Channel()
	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case msg, ok := <-ch:
			if !ok {
				return fmt.Errorf("redis channel closed")
			}
			userID, err := parseUserChannel(msg.Channel)
			if err != nil {
				s.log.Warn("bad channel", "channel", msg.Channel, "err", err)
				continue
			}
			s.hub.BroadcastToUser(userID, []byte(msg.Payload))
		}
	}
}

func parseUserChannel(ch string) (int64, error) {
	parts := strings.SplitN(ch, ":", 2)
	if len(parts) != 2 || parts[0] != "user" {
		return 0, fmt.Errorf("expected 'user:<id>', got %q", ch)
	}
	id, err := strconv.ParseInt(parts[1], 10, 64)
	if err != nil {
		return 0, fmt.Errorf("parse user id %q: %w", parts[1], err)
	}
	return id, nil
}
