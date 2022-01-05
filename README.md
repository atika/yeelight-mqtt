# Yeelight to MQTT bridge

Works with Yeelight WiFi bulbs (color and monochrome).

You need to activate developer mode (http://forum.yeelight.com/t/trying-to-enable-developer-mode-with-yeelight-app-lamp-always-offline/137)

Bridge accept following MQTT set:
```
"home/light/main-color/status/set" -> on
```

will turn on light and translate devices state from gateway:
```
"home/light/main-color/status" on
"home/light/main-color/ct" 3500
"home/light/main-color/bright" 3
"home/light/main-color/rgb" 1247743
```

## Config
Edit file config/config-sample.yaml and rename it to __config/config.yaml__

* mqtt
  - __server__: Server IP address
  - __port__: Port (Default: 1883)
  - __uid__: Client unique ID
  - __username__: Mqtt username (optional)
  - __password__: Mqtt password (optional)
  - __topic__: Topic format with "{group}" in it (default: "home/{group}")
  - __cmd_suffix__: Command endpoint verb (default: "set")
* sids:
  - "Bulb IP Address":
    - __name__: Name for the light (required, without space)
    - __group__: Light group (optional, replaced in the topic)
    - __effect__: The type of transition, can be "smooth" or "sudden"
    - __duration__: Effect duration in ms (used by smooth transition)
    - __port__: Port to reach the bulb (optional, default: 55443)
* __interval__: Status query interval in seconds (query is also sent when a command is processed) (default: 2s)
* __json_payload__: True to send a global json payload or each characteristic indivilually in different topic. (optional, default: false)
* __default_group__: The group for the lights without a group (default "light").

### Example:

With a __topic__ defined to `home/{group}/lights` and __default_group__ to `room`:
  - The topic for the bulb __light1__ without group will be: `home/room/lights/light1`
  - The topic for the bulb __mainlight__ with the "kitchen" group will be: `home/kitchen/lights/mainlight`

You can turn on the bulb __light1__ by sending a payload to `home/room/lights/light1/status/set` <- "on"<br>
or adjust the brightness of the kitchen __mainlight__ to 50% by sending to `home/kitchen/lights/mainlight/bright/set` <- 50

And the gateway will send the status:

If `json_payload` is __true__:

`home/room/lights/light1` -> `{"status": "on", "ct": 1700, "bright": "40", "rgb": "16711680"}`

or by default for each characteristics:

```
  home/room/lights/light1/status -> "on"
  home/room/lights/light1/ct -> "1700"
  home/room/lights/light1/bright -> "40"
  home/room/lights/light1/rgb -> "16711680"
```

## Command

### Status (status or power)

You can send "on", "off" or "toggle" to `home/<group>/<name>/<status, power>/set`

### Brightness (bright)
Send a number between 0 and 100 to `home/<group>/<name>/bright/set`

### Color temperature (ct)
Send a number to `home/<group>/<name>/ct/set`

### Color (rgb or color)
To control the __color__ of the bulb you can send a payload to the `home/<group>/<name>/<color, rgb>/set` of type:
  - Decimal value (default, ex: 16711680)
  - Hex value (ex: #FF0000)
  - RGB (ex: 255,0,0)

### Scene
Choose a predefined scene between the list below and send the name to `home/<group>/<name>/scene/set`<br>
To stop the scene, send "stop".

__Predefined Scenes (flows)__

* alarm
* candle_flicker
* christmas
* date_night
* disco
* happy_birthday
* home
* lsd
* movie
* night_mode
* police
* police2
* pulse
* random_loop
* rgb
* romance
* slowdown
* strobe
* strobe_color
* sunrise
* sunset
* temp

### Flow
Create effects by sending a custom flow sequence to `home/<group>/<name>/flow/set`<br>
To stop the flow, send "stop".

__Flow sequence definition:__

Sequence: `<loops>|<action>|<effect 1>|<effect 2>|<effect N>`

* __loops__: Number of times this sequence will be run (0 for infinite)
* __action__: Post action after the sequence was running:
  - 0: Restore to the initial state (default)
  - 1: Turn off
  - 2: Stay with the last state
* __effect__: `<duration>,<mode>,<value>,<bright>`
  - __duration__: Duration of the effect (in ms)
  - __mode__:
    * 1: Color
    * 2: Color Temperature
    * 7: Delay
  - __value__: The value of the effect (not used for __delay__)
  - __bright__: The brightness (optional, default 100)

With the __police__ effect example below:
  - Loop 10 times
  - Restore the state at the end
  - Blue color during 300ms (brightness 100)
  - Red color during 300ms (brightness 100)

You can omit the brightness value, and for the __delay__, also the value (ex: 500,7 to sleep 500ms).

__Example:__

* Police: `10|0|300,1,45,100|300,1,16711680,100`
* RGB Jump: `0|0|100,1,255,100|500,7,0,0|100,1,65280,100|500,7,0,0|100,1,16711680,100|500,7,0,0`
* Blink Green: `12|0|300,1,65280,100|100,7,0,0|300,1,65280,1|100,7,0,0`
* Demo: `0|0|5000,1,255,100|5000,1,16711680,100`

## Docker-Compose
Sample docker-compose.yaml file for user:
```
yeelight:
  image: "monster1025/yeelight-mqtt"
  container_name: yeelight
  volumes:
    - "./config:/app/config"
  restart: always
```

or to build from the source:

```
yeelight:
  build:
    context: .
    dockerfile: Dockerfile-arm
  image: "yeelight:latest"
  volumes:
    - "./config:/app/config"
  restart: always
```

