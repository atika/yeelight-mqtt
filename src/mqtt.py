import paho.mqtt.client as mqtt
import os
import logging
import json
from queue import Queue
from threading import Thread

_LOGGER = logging.getLogger(__name__)

class Mqtt:
	username = ""
	password = ""
	server = "localhost"
	port = 1883
	client_id = ""
	topic = ""

	_client = None
	_sids = None
	_queue = None
	_threads = None
	_g_index = -1
	_publish_as_json = False
	_default_group = "light"

	def __init__(self, config):
		if (config == None):
			raise "Config is null"

		#load sids dictionary
		self._sids = config.get("sids", None)
		if (self._sids == None):
			self._sids = dict({})

		#load mqtt settings
		mqttConfig = config.get("mqtt", None)
		if (mqttConfig == None):
			raise "Config mqtt section is null"

		self.username = mqttConfig.get("username", "")
		self.password = mqttConfig.get("password", "")
		self.server = mqttConfig.get("server", "localhost")
		self.port = mqttConfig.get("port", 1883)
		self.client_id = mqttConfig.get("uid", "")
		self.topic = "{topic}/{{sid}}/{{prop}}".format(topic=mqttConfig.get("topic", "home/{group}"))
		self.g_index = self.topic.split("/").index("{group}")
		self._default_group = config.get("default_group", "light")
		self._publish_as_json = config.get("json_payload", False)
		self._queue = Queue()
		self._threads = []

	def connect(self):
		_LOGGER.info("Connecting to MQTT server " + self.server + ":" + str(self.port) + " with username " + self.username)
		self._client = mqtt.Client(self.client_id)
		if (self.username != "" and self.password != ""):
			self._client.username_pw_set(self.username, self.password)
		self._client.on_message = self._mqtt_process_message
		self._client.on_connect = self._mqtt_on_connect
		self._client.connect(self.server, self.port, 60)

        #run message processing loop
		t1 = Thread(target=self._mqtt_loop)
		t1.start()
		self._threads.append(t1)

	def subscribe(self, group="+", name="+", prop="+", command="set"):
		topic = self.topic.format(group=group, sid=name, prop=prop) + "/" + command
		_LOGGER.info("Subscribing to " + topic + ".")
		self._client.subscribe(topic)

	def publish(self, group, sid, data, retain=True):
		sidprops = self._sids.get(sid, None)
		if (sidprops != None):
			group = sidprops.get("group", group)
			sid = sidprops.get("name", sid)

		if self._publish_as_json:
			payload = json.dumps(data)
			topic = self.topic.format(group=group, sid=sid, prop="")
			self._publish(topic[:-1], payload, retain)
		else:
			for key, payload in data.items():
				topic = self.topic.format(group=group, sid=sid, prop=key)
				self._publish(topic, payload, retain)

	def _publish(self, topic, payload, retain=True):
		_LOGGER.info("Publishing message to {}: {}.".format(topic, str(payload)))
		self._client.publish(topic, payload=payload, qos=0, retain=retain)

	def _mqtt_on_connect(self, client, userdata, rc, unk):
		_LOGGER.info("Connected to mqtt server.")

	def _mqtt_process_message(self, client, userdata, msg):
		_LOGGER.info("Processing message in " + str(msg.topic) + ": " + str(msg.payload) + ".")
		parts = msg.topic.split("/")
		parts.reverse()
		len_parts = len(parts)
		min_parts = len(self.topic.split("/")) + 1
		if (len_parts != min_parts):
			return
		query_sid = parts[2] #sid or name part
		param = parts[1] #param part
		group = parts[(len_parts - self.g_index - 1)]
		value = (msg.payload).decode('utf-8')
		if self._is_int(value):
			value = int(value)
		name = "" # we will find it next
		sid = query_sid

		for current_sid in self._sids:
			if (current_sid == None):
				continue
			sidprops = self._sids.get(current_sid, None)
			if sidprops == None:
				continue
			sidname = sidprops.get("name", current_sid)
			sidgroup = sidprops.get("group", self._default_group)
			if (sidname == query_sid and sidgroup == group):
				sid = current_sid
				name = sidname
				break
			else:
				_LOGGER.debug(sidgroup + "-" + sidname + " is not " + group + "-" + query_sid + ".")
				continue

		# fix for rgb format
		# if ((param == "rgb" or param == "color") and "," in str(value)):
		# 	arr = value.split(",")
		# 	r = int(arr[0])
		# 	g = int(arr[1])
		# 	b = int(arr[2])
		# 	value = int('%02x%02x%02x%02x' % (255, r, g, b), 16)

		if name == "":
			return

		data = {'sid': sid, 'group': group, 'name': name, 'param':param, 'value':value}
		# put in process queuee
		self._queue.put(data)

	def _mqtt_loop(self):
		_LOGGER.info("Starting mqtt loop.")
		self._client.loop_forever()

	def _is_int(self, x):
		try:
			tmp = int(x)
			return True
		except Exception as e:
			return False
