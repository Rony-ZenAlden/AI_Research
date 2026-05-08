// NeuroSeek Realtime Hub
//
// Single binary that:
//   - terminates WebSocket connections from browsers
//   - authenticates each connection by validating a Django-issued JWT
//   - subscribes to Redis "user:*" pub/sub channels
//   - fans out events to the right user's open connections
//
// HTTP REST stays in Django. This service does I/O concurrency, nothing else.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/redis/go-redis/v9"

	"neuroseek/realtime/internal/auth"
	"neuroseek/realtime/internal/config"
	"neuroseek/realtime/internal/hub"
	"neuroseek/realtime/internal/pubsub"
	"neuroseek/realtime/internal/ws"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	}))
	slog.SetDefault(logger)

	cfg, err := config.Load()
	if err != nil {
		logger.Error("config", "err", err)
		os.Exit(1)
	}

	opts, err := redis.ParseURL(cfg.RedisURL)
	if err != nil {
		logger.Error("parse REDIS_URL", "err", err)
		os.Exit(1)
	}
	rdb := redis.NewClient(opts)
	defer rdb.Close()

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	if err := rdb.Ping(ctx).Err(); err != nil {
		logger.Error("redis ping", "err", err)
		os.Exit(1)
	}

	h := hub.New(logger)
	verifier := auth.NewVerifier(cfg.JWTSecret)
	sub := pubsub.New(rdb, h, logger)

	// Run subscriber in the background.
	subDone := make(chan error, 1)
	go func() { subDone <- sub.Run(ctx) }()

	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", healthz(h))
	mux.Handle("/ws/user/", ws.UserHandler(h, verifier, cfg.AllowedOrigins, logger))

	server := &http.Server{
		Addr:              ":" + cfg.Port,
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
	}

	logger.Info("realtime hub listening", "port", cfg.Port)
	srvErr := make(chan error, 1)
	go func() {
		if err := server.ListenAndServe(); !errors.Is(err, http.ErrServerClosed) {
			srvErr <- err
		}
	}()

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	select {
	case <-sigCh:
		logger.Info("shutdown signal received")
	case err := <-srvErr:
		logger.Error("http server", "err", err)
	case err := <-subDone:
		logger.Error("subscriber exited", "err", err)
	}

	cancel()
	shutdownCtx, sCancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer sCancel()
	if err := server.Shutdown(shutdownCtx); err != nil {
		logger.Warn("server shutdown", "err", err)
	}
	logger.Info("bye")
}

func healthz(h *hub.Hub) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"status":          "ok",
			"connected_users": h.ConnectedUsers(),
		})
	}
}
