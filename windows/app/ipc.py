"""Single-instance handling: the first copy listens on a local port, later copies just send it a message."""
import queue
import socket
import threading

PORT = 47653


class Listener:
    def __init__(self, port: int = PORT) -> None:
        self.port = port
        self.queue: "queue.Queue[str]" = queue.Queue()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def start(self) -> bool:
        """False if another copy of the app already owns the port."""
        try:
            self._sock.bind(("127.0.0.1", self.port))
            self._sock.listen(5)
        except OSError:
            return False
        threading.Thread(target=self._serve, daemon=True).start()
        return True

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            try:
                conn.settimeout(2)
                data = conn.recv(64).decode("utf-8", "ignore").strip()
                if data:
                    self.queue.put(data)
            except OSError:
                pass
            finally:
                conn.close()


def send(message: str, port: int = PORT) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2) as s:
            s.sendall(message.encode("utf-8"))
        return True
    except OSError:
        return False
