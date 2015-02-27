from __future__ import division, with_statement
from time import time
from searx import logger
import threading

__all__ = ["Statistics", "Measure", "statistics", "record", "counter_inc", "counter_add",
           "start_timer", "end_timer", "measure", "counter", "init_measure"]

logger = logger.getChild('stat')


class Measure(object):

    def __init__(self, width=10, size=200):
        self.quartiles = [0] * size
        self.count = 0
        self.width = width
        self.size = size
        self.sum = long(0)

    def record(self, value):
        self.count += 1
        self.sum += value

        q = int(value / self.width)
        if q < 0:
            return
        if q >= self.size:
            q = self.size - 1
        self.quartiles[q] += 1

    def get_count(self):
        return self.count

    def get_average(self):
        if self.count != 0:
            return self.sum / self.count
        else:
            return 0

    def get_quartile(self):
        return self.quartiles

    def get_qp(self):
        ''' Quartile in percentage '''
        if self.count > 0:
            return [int(q*100/self.count) for q in self.quartiles]
        else:
            return self.quartiles

    def get_qpmap(self):
        result = {}
        x = 0
        if self.count > 0:
            for y in self.quartiles:
                yp = int(y*100/self.count)
                if yp != 0:
                    result[x] = yp
                x += self.width
            return result

    def __repr__(self):
        return "Measure<avg: " + str(self.get_average()) + ", count: " + str(self.get_count()) + ">"


class Statistics(object):

    def __init__(self):
        self.measures = {}
        self.counters = {}
        self.lock = threading.RLock()

    def init_measure(self, width, size, *args):
        with self.lock:
            measure = self.measures.get(args, None)
            if measure is None:
                measure = Measure(width, size)
                self.measures[args] = measure
            return measure

    def counter(self, *args):
        with self.lock:
            # logger.debug("Counter for {0} : {1}".format(args, self.counters.get(args, 0)))
            return self.counters.get(args, 0)

    def get(self, *args):
        with self.lock:
            measure = self.measures.get(args, None)
            if measure is None:
                measure = Measure()
                self.measures[args] = measure
            return measure

    def record(self, value, *args):
        with self.lock:
            self.get(*args).record(value)
            # logger.debug("Value for {0} : {1}".format(args, value))

    def counter_add(self, value, *args):
        with self.lock:
            self.counters[args] = value + self.counters.get(args, long(0))
            # logger.debug("Counter for {0} : {1}".format(args, self.counters[args]))


statistics = Statistics()

threadlocal_dict = threading.local()
threadlocal_dict.timers = {}
timers = threadlocal_dict.timers


def record(value, *args):
    global statistics
    statistics.record(value, *args)


def counter_inc(*args):
    global statistics
    statistics.counter_add(1, *args)


def counter_add(value, *args):
    global statistics
    statistics.counter_add(value, *args)


def start_timer(*args):
    global timers
    timers[args] = time()


def end_timer(*args):
    global timers, statistics
    if args in timers:
        previous_time = timers[args]
        if previous_time is not None:
            timers[args] = None
            duration = time() - previous_time
            statistics.record(duration, *args)


def measure(*args):
    global statistics
    return statistics.get(*args)


def counter(*args):
    global statistics
    return statistics.counter(*args)


def init_measure(width, size, *args):
    global statistics
    return statistics.init_measure(width, size, *args)
