// Thin WebSocket wrapper with exponential-backoff reconnect.

export function createChatSocket({
    onOpen,
    onMessage,
    onClose,
    onError,
    onStateChange,
    getSessionId,
    maxReconnectAttempts = 5,
}) {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    let socket = null;
    let reconnectAttempts = 0;

    function buildUrl(sessionId) {
        const base = `${wsProtocol}//${window.location.host}/ws/chat/`;
        return sessionId ? `${base}${sessionId}/` : base;
    }

    function connect(sessionId) {
        // Null out the old socket's onclose before closing it so the
        // reconnect logic in onclose is not triggered for an intentional
        // switch/replacement (e.g. switching sessions or starting a new chat).
        if (socket && socket.readyState <= WebSocket.OPEN) {
            socket.onclose = null;
            socket.close();
        }

        onStateChange('connecting');
        socket = new WebSocket(buildUrl(sessionId));

        socket.onopen = function () {
            reconnectAttempts = 0; // only reset on successful connection
            onStateChange('connected');
            if (onOpen) onOpen();
        };

        socket.onmessage = function (e) {
            const data = JSON.parse(e.data);
            onMessage(data);
        };

        socket.onclose = function () {
            if (reconnectAttempts < maxReconnectAttempts) {
                reconnectAttempts++;
                onStateChange('reconnecting');
                const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
                setTimeout(() => connect(getSessionId()), delay);
            } else {
                onStateChange('failed');
                if (onClose) onClose();
            }
        };

        socket.onerror = function (e) {
            console.error('WebSocket error:', e);
            if (onError) onError(e);
        };
    }

    function send(payload) {
        if (!socket || socket.readyState !== WebSocket.OPEN) return false;
        socket.send(JSON.stringify(payload));
        return true;
    }

    function isOpen() {
        return socket && socket.readyState === WebSocket.OPEN;
    }

    function closeNoReconnect() {
        if (socket && socket.readyState <= WebSocket.OPEN) {
            socket.onclose = null;
            socket.close();
        }
    }

    return { connect, send, isOpen, closeNoReconnect };
}
