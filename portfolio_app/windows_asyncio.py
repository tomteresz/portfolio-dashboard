"""Work around CPython's Windows transport cleanup after a peer reset."""
from functools import wraps
import logging
import sys


def install_transport_cleanup():
    if sys.platform != "win32":
        return
    from asyncio.proactor_events import _ProactorBasePipeTransport

    original = _ProactorBasePipeTransport._call_connection_lost
    if getattr(original, "_portfolio_cleanup", False):
        return

    @wraps(original)
    def connection_lost(self, exc):
        try:
            return original(self, exc)
        except ConnectionResetError as error:
            # Only handle a reset raised inside transport cleanup itself.
            # Exceptions from application/protocol callbacks still propagate.
            trace = error.__traceback__
            while trace.tb_next is not None:
                trace = trace.tb_next
            if getattr(error, "winerror", None) != 10054 or trace.tb_frame.f_code is not original.__code__:
                raise
            # CPython calls shutdown() before these steps. A reset can skip
            # all of them, leaving Server.wait_closed() waiting indefinitely.
            try:
                if self._sock is not None:
                    self._sock.close()
            finally:
                self._sock = None
                if self._server is not None:
                    self._server._detach()
                    self._server = None
                self._called_connection_lost = True
            logging.getLogger("portfolio.access").info("event=peer_reset_cleanup winerror=10054")

    connection_lost._portfolio_cleanup = True
    _ProactorBasePipeTransport._call_connection_lost = connection_lost
