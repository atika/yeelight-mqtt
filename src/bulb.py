import yeelight
import yeelight.flows

from yeelight import Flow

import logging

_LOGGER = logging.getLogger(__name__)

class LightBulbState:
	bright = 0
	color_temperature = 0
	status = "off"
	rgb = 0
	group = ""

	ip = ""
	name = ""
	yeelight = None # yeelight object

	temp = {
		"min": 1700,
		"max": 6500,
		"set": False
	}

	def __init__(self, ip, group, yeelightObj):
		self.yeelight = yeelightObj
		self.group = group
		self.name = yeelightObj.__name__
		self.ip = ip
		self.logger = logging.getLogger(yeelightObj.__name__)

	def update_properties(self, force = False):
		try:
			if (force):
				self.yeelight.get_properties(["power", "rgb", "bright", "ct"])
				if not self.temp["set"]:
					specs = self.yeelight.get_model_specs()
					if "color_temp" in specs:
						self.temp["min"] = specs["color_temp"]["min"]
						self.temp["max"] = specs["color_temp"]["max"]
						self.temp["set"] = True
						self.logger.info("Color temperature range is: %s-%s.", self.temp["min"], self.temp["max"])
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

	def hash(self):
		return str(self.bright) + ":" + str(self.color_temperature) + ":" + str(self.status) + ":" + str(self.rgb)

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

	def process_command(self, param, value):
		try:
			action = param.lower()

			if (action == 'status') or (action == 'power'):
				state = str(value).lower()
				if (state == "on"):
					self.logger.info("Turning on.")
					self.yeelight.turn_on()
				elif (state == "off"):
					self.logger.info("Turning off.")
					self.yeelight.turn_off()
				elif (state == "toggle"):
					self.logger.info("Toggle bulb state.")
					self.yeelight.toggle()
				else:
					self.reject("Unknow status command: %s", action)

			elif (action == 'bright' and self.is_int(value)):
				self.logger.info("Setting brightness to %d%%.", value)
				self.yeelight.set_brightness(int(value))

			elif (action == 'ct' and self.is_int(value)):
				if value >= self.temp["min"] and value <= self.temp["max"]:
					self.logger.info("Setting temperature to %d.", value)
					self.yeelight.set_color_temp(int(value))
				else:
					return self.reject("Color temperature out-of-range, min %d max %d, given %d.", self.temp["min"], self.temp["max"], int(value))

			elif (action == 'rgb') or (action == 'color'):
				color = str(value)
				if color[0] == "#" and len(color) == 7:
					color = color[1:]
					Red, Green, Blue = [int(color[i:i+2],16) for i in range(0, len(color), 2)]
				elif "," in color:
					Red, Green, Blue = [int(v) for v in color.split(",")]
				elif self.is_int(color):
					Red, Green, Blue = self.to_rgb(int(color))
				else:
					return self.reject("Bad color format.")

				self.logger.debug("R%d G%d B%d", Red, Green, Blue)
				self.logger.info("Setting rgb color to %s.", color)
				self.yeelight.set_rgb(Red, Green, Blue)

			elif (value == 'stop' and (action == 'flow' or action == 'scene')):
				self.logger.info("Stopping %s.", action)
				self.yeelight.stop_flow()

			elif (action == 'flow'):
				flow = self.decode_flow(value)
				if flow is not None:
					self.logger.info("Starting custom flow sequence...")
					self.yeelight.start_flow(flow)
				else:
					return False

			elif (action == 'scene'):
				flow = self.get_scene(value)
				if flow is not None:
					self.logger.info("Applying scene %s to %s", value, self.name)
					self.yeelight.start_flow(flow())
				else:
					return self.reject("Unknow scene name: %s.", value)
			else:
				return self.reject("Unknow command \"%s\" or incorrect value given.", action)

			return True

		except yeelight.BulbException as e:
			return self.reject(e)
		except Exception as e:
			_LOGGER.error("Error while set value of bulb %s error: %s", self.name, e, exc_info=1)
			return False
