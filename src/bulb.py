import yeelight
import yeelight.flows
from yeelight import Flow
from threading import Timer
from time import sleep
from time import perf_counter
import logging

_LOGGER = logging.getLogger(__name__)

class LightBulbState:
	bright = 0
	color_temperature = 0
	status = "off"
	rgb = 0
	group = ""
	music_mode = None
	flowing = False

	ip = ""
	name = ""
	yeelight = None # yeelight object

	temp = {
		"min": 1700,
		"max": 6500,
		"set": False
	}

	_processing_cmd = False

	def __init__(self, ip, group, yeelightObj):
		self.yeelight = yeelightObj
		self.group = group
		self.name = yeelightObj.__name__
		self.ip = ip
		self.logger = logging.getLogger(group + '/' + yeelightObj.__name__)

	def rate_limit(max_per_minute):
		min_interval = 60.0 / float(max_per_minute)
		def decorate(fn):
			def throttle(bulb, *args, **kwargs):
				def run():
					bulb._t = perf_counter()
					bulb._processing_cmd = False
					fn(bulb, *args, **kwargs)

				if fn.__name__ == "process_command":
					bulb._processing_cmd = True
				if fn.__name__ == "update_properties" and bulb._processing_cmd: # cancel updates
					bulb.logger.debug("!!! update_properties canceled.")
					return

				if not bulb.yeelight.music_mode: # rate limit if not music mode
					try:
						elapsed = perf_counter() - bulb._t
						wait_for = min_interval - elapsed
						if wait_for > 0:
							sleep(wait_for)
					except(AttributeError):
						pass
				elif fn.__name__ == "update_properties": # debounce updates in music mode
					try:
						bulb._d.cancel()
					except(AttributeError):
						pass
					bulb._d = Timer(2, run)
					bulb._d.start()
					return
				return run()
			return throttle
		return decorate

	@rate_limit(60)
	def update_properties(self, force = False, next = None):
		hashold = self.hash()
		try:
			if (force):
				self.yeelight.get_properties(["power", "rgb", "bright", "ct", "flowing"])
				if not self.temp["set"]:
					specs = self.yeelight.get_model_specs()
					if "color_temp" in specs:
						self.temp["min"] = specs["color_temp"]["min"]
						self.temp["max"] = specs["color_temp"]["max"]
						self.logger.info("Color temperature range is: %s-%s.", self.temp["min"], self.temp["max"])
					self.temp["set"] = True
			prop = self.yeelight.last_properties
		except yeelight.BulbException as e:
			prop = self.yeelight.last_properties
			if "socket error occurred" in str(e):
				prop["power"] = "disconnected"
			else:
				prop["power"] = "closed"
				self.logger.warning(e)

		if "bright" in prop:
			self.bright = prop["bright"]
		if "ct" in prop:
			self.color_temperature = prop["ct"]
		if "power" in prop:
			self.status = prop["power"]
		if "rgb" in prop:
			self.rgb = prop["rgb"]
		if "flowing" in prop:
			self.flowing = prop["flowing"]

		hashnew = self.hash()
		_LOGGER.debug("!!!! %s: %s -> %s %s", self.name, hashold, hashnew, '(updated)' if (hashold != hashnew) else '')
		if (hashold != hashnew) and next != None:
			next(self)

	def hash(self):
		return str(self.bright) + ":" + str(self.color_temperature) + ":" + str(self.status) + ":" + str(self.rgb) + ":" + str(self.flowing)

	def is_int(self, x):
		try:
			tmp = int(x)
			return True
		except Exception as e:
			return False

	def to_rgb(self, color: int):
		Blue =  color & 255
		Green = (color >> 8) & 255
		Red =   (color >> 16) & 255
		return Red, Green, Blue

	def decode_flow(self, seq:str):
		try:
			parts = seq.split("|")

			if not len(parts) > 2:
				raise Exception("sequence need at least 3 parts")

			loops = int(parts.pop(0))
			a = int(parts.pop(0))

			if a == 2:
				action = Flow.actions.stay
			elif a == 1:
				action = Flow.actions.off
			else:
				action = Flow.actions.recover

			transitions = []
			effect = [0,0,0,100]

			for part in parts:
				params = [int(x) for x in part.split(",")]

				for i, v in enumerate(params):
					effect[i] = v
				duration, mode, value, brightness = effect

				if (len(params) < 3 and mode != 7):
					raise Exception("each effect should contains at least 3 elements")

				if duration <= 50: duration = 50

				if mode == 1: # rgb color
					r, g, b = self.to_rgb(value)
					transition = yeelight.RGBTransition(r,g,b, duration, brightness)
				elif mode == 2: # temperature
					transition = yeelight.TemperatureTransition(value, duration, brightness)
				elif mode == 7: # sleep
					transition = yeelight.SleepTransition(duration=duration)
				else:
					continue
				transitions.append(transition)

			return Flow(loops, action, transitions)

		except Exception as e:
			self.logger.warn("Malformed flow sequence: %s.", str(e))
			return None

	def get_scene(self, name):
		# TODO: some presets accept opts, how can I do??
		# https://yeelight.readthedocs.io/en/stable/yeelight.html#flow-objects
		presets = {
			"alarm": yeelight.flows.alarm,
			"candle_flicker": yeelight.flows.candle_flicker,
			"christmas": yeelight.flows.christmas,
			"date_night": yeelight.flows.date_night,
			"disco": yeelight.flows.disco,
			"happy_birthday": yeelight.flows.happy_birthday,
			"home": yeelight.flows.home,
			"lsd": yeelight.flows.lsd,
			"movie": yeelight.flows.movie,
			"night_mode": yeelight.flows.night_mode,
			"police": yeelight.flows.police,
			"police2": yeelight.flows.police2,
			"pulse": yeelight.flows.pulse,
			"random_loop": yeelight.flows.random_loop,
			"rgb": yeelight.flows.rgb,
			"romance": yeelight.flows.romance,
			"slowdown": yeelight.flows.slowdown,
			"strobe": yeelight.flows.strobe,
			"strobe_color": yeelight.flows.strobe_color,
			"sunrise": yeelight.flows.sunrise,
			"sunset": yeelight.flows.sunset,
			"temp": yeelight.flows.temp
		}
		return presets.get(name, None)

	def reject(self, message, *args):
		self.logger.warning(message, *args)
		return False

	def _run(self, yeelight_cmd, *args):
		if self.status == 'off':
			self.yeelight.turn_on()
			self.status = 'on'
			sleep(1)
		yeelight_cmd(*args)

	@rate_limit(60)
	def process_command(self, param, value, update_state):
		try:
			action = param.lower()

			if (action == 'status') or (action == 'power'):
				state = str(value).lower()
				if (state == "on"):
					self.logger.info("Turning on.")
					self.status = 'on'
					self.yeelight.turn_on()
				elif (state == "off"):
					self.logger.info("Turning off.")
					self.yeelight.turn_off()
				elif (state == "toggle"):
					self.logger.info("Toggle bulb state.")
					self.yeelight.toggle()
				elif (state == ''):
					self._processing_cmd = False
					update_state()
				else:
					return self.reject("Unknow status command: %s", action)
			elif (value == ''):
				return False

			elif (action == 'bright'):
				if self.is_int(value):
					self.logger.info("Setting brightness to %d%%.", value)
					self._run(self.yeelight.set_brightness, int(value))
				elif value == '+' or value == 'up':
					self.logger.info("Increasing brightness.")
					self._run(self.yeelight.set_adjust, 'increase', 'bright')
				elif value == '-' or value == 'down':
					self.logger.info("Lowering brightness.")
					self._run(self.yeelight.set_adjust, 'decrease', 'bright')
				else:
					return self.reject('Cannot set brightness to %s.', str(value))

			elif (action == 'ct'):
				if self.is_int(value) and value >= self.temp["min"] and value <= self.temp["max"]:
					self.logger.info("Setting temperature to %d.", value)
					self._run(self.yeelight.set_color_temp, int(value))
				elif value == '+' or value == 'up':
					self.logger.info("Increasing color temperature.")
					self._run(self.yeelight.set_adjust, 'increase', 'ct')
				elif value == '-' or value == 'down':
					self.logger.info("Lowering color temperature.")
					self._run(self.yeelight.set_adjust, 'decrease', 'ct')
				else:
					return self.reject("Color temperature out-of-range, min %d max %d, given %s.", self.temp["min"], self.temp["max"], str(value))

			elif (action == 'rgb') or (action == 'color'):
				color = str(value)
				adjust = False
				if len(color) == 7 and color[0] == "#":
					hex = color[1:]
					Red, Green, Blue = [int(hex[i:i+2],16) for i in range(0, len(hex), 2)]
				elif "," in color:
					Red, Green, Blue = [int(v) for v in color.split(",")]
				elif self.is_int(color):
					Red, Green, Blue = self.to_rgb(int(color))
				elif color in ['switch', '+', '-', 'up', 'down']:
					adjust = True
				else:
					return self.reject("Bad color format.")

				if adjust:
					self.logger.info("Switching color.")
					self._run(self.yeelight.set_adjust, 'circle', 'color')
				else:
					self.logger.debug("R%d G%d B%d", Red, Green, Blue)
					self.logger.info("Setting rgb color to %s.", color)
					self._run(self.yeelight.set_rgb, Red, Green, Blue)

			elif (value == 'stop' and (action == 'flow' or action == 'scene')):
				self.logger.info("Stopping %s.", action)
				self.yeelight.stop_flow()

			elif (action == 'flow'):
				flow = self.decode_flow(value)
				if flow is not None:
					self.logger.info("Starting custom flow sequence...")
					self._run(self.yeelight.start_flow, flow)
				else:
					return False

			elif (action == 'scene'):
				flow = self.get_scene(value)
				if flow is not None:
					self.logger.info("Applying scene %s to %s", value, self.name)
					self._run(self.yeelight.start_flow, flow())
				else:
					return self.reject("Unknow scene name: %s.", value)

			elif (action == 'music'):
				state = str(value)
				if self.music_mode == None:
					return self.reject('Music mode settings not found.')
				ip = self.music_mode.get('ip')
				port = self.music_mode.get('port')
				if state == 'on':
					self._run(self.yeelight.start_music, port, ip)
				elif state == 'off':
					try:
						self.yeelight.stop_music()
					except yeelight.BulbException as e:
						pass
				else:
					return self.reject('Cannot set music mode to "%s".', state)

				self.logger.info("Music mode is %s.", "ON" if self.yeelight.music_mode else "OFF")

			elif (action == 'effect'):
				if value == 'smooth' or value == 'sudden':
					self.logger.info('Switched effect mode to %s', value)
					self.yeelight.effect = value
				else:
					return self.reject("Only smooth and sudden values allowed.")

			elif (action == 'duration') and self.is_int(value):
				self.logger.info('Setting transition duration to %s', str(value))
				self.yeelight.duration = max(30, value)

			else:
				return self.reject("Unknow command \"%s\" or incorrect value given.", action)

			update_state()

		except yeelight.BulbException as e:
			return self.reject(e.get('message') + '(' + e.get('code') + ')')

		except Exception as e:
			_LOGGER.error("Error while set value of bulb %s error: %s", self.name, e, exc_info=1)
			return False
