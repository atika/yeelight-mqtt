import logging
import time
import threading
import yeelight
from bulb import LightBulbState

#mine
import mqtt
import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
_LOGGER = logging.getLogger(__name__)

interval = 2

bulbs=[]
processNow = False

def init_lamps(config):
	if config is None:
		raise "Config is None."
	sids = config.get("sids", "None")
	if sids is None:
		raise "Config -> sids is None."

	lamps=[]
	# sid is IP-address
	for sid in sids:
		if (sid is None):
			continue
		try:
			data            = sids[sid]
			name            = data.get("name", sid)
			group           = data.get("group", config.get("default_group", "light"))
			port            = data.get("port", 55443)
			effect          = data.get("effect", "smooth")
			duration        = data.get("duration", 300)
			light           = yeelight.Bulb(sid, port, effect, duration)
			light.__name__  = name #add name
			bulb            = LightBulbState(sid, group, light)
			bulb.music_mode = data.get("music_mode", config.get("music_mode", None))
			bulb.update_properties()
			lamps.append(bulb)
		except Exception as e:
			_LOGGER.error('Connection to ', str(sid) , ' error:', str(e))
	return lamps

def wait():
	global processNow
	rmax = int(interval / 0.2)
	for x in range(1,rmax):
		if (processNow):
			processNow=False
			break
		time.sleep(interval/rmax)

def process_lamp_states(c):
	global bulbs, client
	def publish_updates(bulb):
		try:
			data = {'status':bulb.status, 'ct':bulb.color_temperature, 'bright':bulb.bright, 'rgb':bulb.rgb, 'flowing':bulb.flowing} if bulb.status != "disconnected" else {'status': bulb.status}
			client.publish(bulb.group, bulb.name, data)
		except Exception as e:
			_LOGGER.error('Error while sending from gateway to mqtt: ', str(e))
	while True:
		wait();
		try:
			for bulb in bulbs:
				bulb.update_properties(force=True, next=publish_updates)
		except Exception as e:
			_LOGGER.error('Error while sending from gateway to mqtt: ', str(e))

def process_mqtt_messages(client):
	global processNow, bulbs
	def now():
		global processNow
		processNow = True
	while True:
		try:
			data = client._queue.get()
			_LOGGER.debug("data from mqtt: " + format(data))

			sid = data.get("sid", None)
			param = data.get("param", None)
			value = data.get("value", None)
			for bulb in bulbs:
				if (bulb.ip != sid):
					continue
				bulb.process_command(param, value, update_state=now)
			client._queue.task_done()
		except Exception as e:
			_LOGGER.error('Error while sending from mqtt to gateway: ', str(e))

if __name__ == "__main__":
	_LOGGER.info("Loading config file...")
	cfg = config.load_yaml('config/config.yaml')

	_LOGGER.info("Init mqtt client.")
	client = mqtt.Mqtt(cfg)
	client.connect()

	default_group = cfg.get("default_group", "light")
	cmd_suffix = cfg.get("mqtt", {}).get("cmd_suffix", "set")
	groups = set([props.get("group", default_group) for sid,props in cfg.get("sids", {}).items() if type(props) == dict])
	for group in groups:
		client.subscribe(group, "+", "+", cmd_suffix)

	bulbs = init_lamps(cfg)

	interval = max(2, cfg.get("interval", 2))

	t1 = threading.Thread(target=process_lamp_states, args=[client])
	t1.daemon = True
	t1.start()

	t2 = threading.Thread(target=process_mqtt_messages, args=[client])
	t2.daemon = True
	t2.start()

	if interval > 4:
		time.sleep(4)
		processNow = True

	while True:
		time.sleep(10)
