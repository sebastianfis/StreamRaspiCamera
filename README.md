# StreamRaspiCamera
This is a minimal working example of how to stream the raspi camera using gstreamer and WebRTC in python. I needed this for a robot project and could not find any examples that would work straight out of the box.

## Notes

* This does not use a STUN server, so it will only work in a local network
* As it only connects through an unsecure websocket, it should not be used over the web anyway...
