from twisted.internet.protocol import DatagramProtocol
from twisted.python import failure
from twisted.internet import error
from threading import Thread
import time
import json


connectionDone = failure.Failure(error.ConnectionDone())


class Game(Thread):
    tick = 1

    def __init__(self, channel):
        Thread.__init__(self, target=self.run)
        self.channel = channel

    def run(self):
        print('Game started')
        while True:
            self.do_tick()
            time.sleep(self.tick)

    def do_tick(self):
        """
        Override
        """
        self.channel.send_all({'time': time.time()})


class UDProtocol(DatagramProtocol, Thread):
    requests = ['connect', 'disconnect', 'ping']
    errors = {'001': 'Bad request', '002': 'Wrong request', '003': 'Connection first'}

    timeout = 5
    update = 1/2

    def __init__(self, ip, port, r, server):
        Thread.__init__(self, target=self.run)
        self.ip = ip
        self.port = port
        self.reactor = r
        self.server = server
        self.start()

    def datagramReceived(self, datagram, address):
        print("Datagram %s received from %s" % (repr(datagram), repr(address)))

        try:
            message = json.loads(datagram.decode('utf-8'))
            request = message.get('request')
            data = message.get('data')
            callback = message.get('callback')
            handler = self.server.handlers.get(address)
        except (UnicodeDecodeError, json.decoder.JSONDecodeError):
            self.send(self.get_error_message('001'), address)
            return

        if not handler and request != 'connect':
            self.send(self.get_error_message('003'), address, callback)
            return

        if request:
            try:
                if request not in self.requests:
                    raise Exception('002')
                response = getattr(self, request)(data, address)
            except Exception as ex:
                response = self.get_error_message(ex.args[0])
        else:
            response = handler['user'].on_message(message)
        self.send(response, address, callback)

    def get_error_message(self, error_id):
        return {'type': 'error', 'data': {'code': error_id, 'message': self.errors[error_id]}}

    def send(self, data, address, callback=None):
        if not data:
            return
        print('Send %s' % repr(data))
        if callback:
            data['callback'] = callback
        if type(address) == list:
            for addr in address:
                self.transport.write(json.dumps(data).encode('utf-8'), addr)
            return
        self.transport.write(json.dumps(data).encode('utf-8'), address)

    def connect(self, _, address):
        print('%s connected' % repr(address))
        if self.server.handlers.get(address):
            self.disconnect(None, address)
        self.server.handlers[address] = {'time': time.time(), 'user': User(address, self)}

    def disconnect(self, _, address):
        print('%s disconnected' % repr(address))
        if not self.server.handlers.get(address):
            return
        handler = self.server.handlers.pop(address)
        handler['user'].on_close()

    def ping(self, _, address):
        if not self.server.handlers.get(address):
            raise Exception('003')
        self.server.handlers[address]['time'] = time.time()

    def run(self):
        print('Protocol started')
        while True:
            t = time.time()
            for handler in self.server.handlers.copy().values():
                if t - handler['time'] > self.timeout:
                    self.disconnect(None, handler['user'].addr)
            time.sleep(self.update)


class User:
    def __init__(self, addr, udp):
        self.addr = addr
        self.name = None
        self.channel = None
        self.udp = udp

    def send(self, data):
        self.udp.send(data, self.addr)

    def on_message(self, message):
        """Override"""
        print(message)
        return {'type': 'ok', 'data': 'ok'}

    def on_close(self):
        """Override"""
        print('User disconnected %s' % repr(self.addr))


class Channel:
    """Rewrite"""
    def __init__(self, name, server):
        self.name = name
        self.server = server

    def send_all(self, data):
        for address in self.server.handlers:
            self.server.udp.send(data, address)
        return


class Server:
    def __init__(self, ip='0.0.0.0', port=8956):
        from twisted.internet import reactor

        self.ip = ip
        self.port = port

        self.handlers = {}
        self.channels = [Channel('main', self)]  # Rewrite

        self.reactor = reactor
        self.udp = UDProtocol(ip, port, reactor, self)
        reactor.listenUDP(port, self.udp)

    def run(self):
        print('Start at %s:%s' % (self.ip, self.port))
        self.reactor.run()


if __name__ == '__main__':
    s = Server()
    game = Game(s.channels[0])
    game.start()
    s.run()
