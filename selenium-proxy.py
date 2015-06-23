import asyncio
import logging

formatter = '%(asctime)-25s - %(levelname)-8s - %(message)s'
logging.basicConfig(format=formatter, level=logging.INFO)
log = logging.getLogger(__name__)


from selenium_proxy.app import app, Sessions


@asyncio.coroutine
def wait_connections_done(handler):
    log.info("Waiting for %s connections to done" % len(handler.connections))
    for connection in handler.connections:
        log.info(str(connection))
    while handler.connections:
        yield from asyncio.sleep(0)


handler = app.make_handler()

loop = asyncio.get_event_loop()
server_coroutine = loop.create_server(handler, '0.0.0.0', 8080)
server = loop.run_until_complete(server_coroutine)

log.info('Serving on %s' % str(server.sockets[0].getsockname()))
try:
    loop.run_forever()
except (KeyboardInterrupt, SystemExit):
    log.info("Shutting down...")
finally:
    server.close()
    loop.run_until_complete(server.wait_closed())
    loop.run_until_complete(wait_connections_done(handler))
    loop.run_until_complete(app.finish())
loop.close()
