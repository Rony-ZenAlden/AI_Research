# --- build stage ---
FROM golang:1.23-alpine AS builder

WORKDIR /src

RUN apk add --no-cache git

COPY go.mod ./
COPY go.sum* ./

# First copy of source so go mod tidy can resolve indirect deps.
COPY . .

ENV CGO_ENABLED=0 GOOS=linux GOFLAGS="-trimpath"

RUN go mod tidy && go build -ldflags "-s -w" -o /out/realtime ./

# --- runtime stage ---
FROM alpine:3.20

RUN apk add --no-cache ca-certificates curl \
    && addgroup -S app && adduser -S app -G app

COPY --from=builder /out/realtime /usr/local/bin/realtime

USER app
EXPOSE 8001

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD curl -fsS http://localhost:8001/healthz || exit 1

ENTRYPOINT ["/usr/local/bin/realtime"]
