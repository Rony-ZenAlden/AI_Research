package hub

// WriteSend pushes a single message into the connection's send queue.
// Returns false if the queue is full so the caller can decide what to do.
func (c *Connection) WriteSend(msg []byte) bool {
	select {
	case c.send <- msg:
		return true
	default:
		return false
	}
}
