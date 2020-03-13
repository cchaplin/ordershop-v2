import functools
import json
import logging
import signal

from event_store.event_store_client import EventStoreClient, create_event, deduce_entities, track_entities
from message_queue.message_queue_client import Consumers


class ReadModel(object):
    """
    Read Model class.
    """

    def __init__(self):
        self.event_store = EventStoreClient()
        self.receivers = Consumers('read-model', [self.get_all_entities,
                                                  self.get_one_entity,
                                                  self.get_unbilled_orders])
        self.cache = {}
        self.subscriptions = {}

    def start(self):
        logging.info('starting ...')
        self.receivers.start()
        self.receivers.wait()

    def stop(self):
        for name, handler in self.subscriptions.items():
            self.event_store.unsubscribe(name, handler)
        self.receivers.stop()
        logging.info('stopped.')

    def get_all_entities(self, _req):
        return {
            'result': self._query_entities(_req['name'])
        }

    def get_one_entity(self, _req):
        return {
            'result': self._query_entities(_req['name']).get(_req['id'])
        }

    def get_unbilled_orders(self, _req):
        return {
            'result': self._unbilled_orders()
        }

    def _query_entities(self, _name):
        """
        Query all entities for a topic.

        :param _name: The entity topic.
        :return: A dict mapping entity ID -> entity.
        """
        if _name in self.cache:
            return self.cache[_name]

        events = self.event_store.get(_name)
        entities = deduce_entities(events)
        tracking_handler = functools.partial(track_entities, entities)
        self.event_store.subscribe(_name, tracking_handler)
        self.subscriptions[_name] = tracking_handler
        self.cache[_name] = entities

        return entities

    def _unbilled_orders(self):
        """
        Query all unbilled orders, i.e. orders w/o corresponding billing.

        :return: a dict mapping entity ID -> entity.
        """
        orders = self._query_entities('order')
        billings = self._query_entities('billing')

        unbilled = orders.copy()
        for billing_id, billing in billings.items():
            order_ids_to_remove = list(filter(lambda x: x == billing['order_id'], orders))
            if not order_ids_to_remove:
                raise Exception(f'could not find order {billing["order_id"]} for billing {billing_id}')

            if order_ids_to_remove[0] not in unbilled:
                raise Exception(f'could not find order {order_ids_to_remove[0]}')

            del unbilled[order_ids_to_remove[0]]

        return unbilled


logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)-6s] %(message)s')

r = ReadModel()

signal.signal(signal.SIGINT, lambda n, h: r.stop())
signal.signal(signal.SIGTERM, lambda n, h: r.stop())

r.start()
