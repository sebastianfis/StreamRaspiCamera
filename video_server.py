import asyncio
import json
from aiohttp import web
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstWebRTC', '1.0')
from gi.repository import Gst, GstWebRTC, GObject, GstSdp

Gst.init(None)

pcs = set()


async def index(request):
    return web.FileResponse('./static/minimal_index.html')


async def javascript(request):
    print('sending js file')
    return web.FileResponse('./static/video_client.js')


async def websocket_handler(request):
    loop = asyncio.get_running_loop()
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    pipeline = Gst.Pipeline.new("webrtc-pipeline")

    # Create elements
    src = Gst.ElementFactory.make("libcamerasrc", "source")
    # src = Gst.ElementFactory.make("videotestsrc", "source")
    conv = Gst.ElementFactory.make("videoconvert", "convert")
    scale = Gst.ElementFactory.make("videoscale", "scale")
    caps = Gst.ElementFactory.make("capsfilter", "caps")
    encoder = Gst.ElementFactory.make("vp8enc", "encoder")
    payloader = Gst.ElementFactory.make("rtpvp8pay", "pay")
    webrtc = Gst.ElementFactory.make("webrtcbin", "sendrecv")

    # Set element properties
    # src.set_property("is-live", True)
    caps.set_property("caps", Gst.Caps.from_string("video/x-raw,width=640,height=480,framerate=30/1"))
    encoder.set_property("deadline", 1)

    # Add elements to pipeline
    for elem in [src, conv, scale, caps, encoder, payloader, webrtc]:
        pipeline.add(elem)

    # Create a src pad and add it to webrtcbin as a sendonly stream
    # webrtc.emit('add-transceiver', GstWebRTC.WebRTCRTPTransceiverDirection.SENDONLY, None)

    # Link static pads
    src.link(conv)
    conv.link(scale)
    scale.link(caps)
    caps.link(encoder)
    encoder.link(payloader)
    payloader_src = payloader.get_static_pad("src")
    webrtc_sink = webrtc.get_request_pad("sink_%u")
    if payloader_src.link(webrtc_sink) != Gst.PadLinkReturn.OK:
        print("❌ Failed to link payloader to webrtcbin")
    else:
        print("✅ Linked payloader to webrtcbin")

    pcs.add(ws)

    def on_negotiation_needed(element):
        print("Negotiation needed")
        promise = Gst.Promise.new_with_change_func(on_offer_created, ws, None)
        webrtc.emit('create-offer', None, promise)

    def on_offer_created(promise, ws_conn, _user_data):
        print("Offer created")
        reply = promise.get_reply()
        offer = reply.get_value("offer")
        webrtc.emit('set-local-description', offer, None)

        sdp_msg = json.dumps({'sdp': {
            'type': 'offer',
            'sdp': offer.sdp.as_text()
        }})
        print("✅ Sending SDP offer to browser")
        if ws.closed:
            print("❌ WebSocket is already closed — cannot send message.")
        else:
            future = asyncio.run_coroutine_threadsafe(ws.send_str(sdp_msg), loop)
            try:
                future.result(timeout=5)
                print("✅ SDP offer sent successfully")
            except Exception as e:
                print("❌ Failed to send SDP offer:", e)

    def on_ice_candidate(_, mlineindex, candidate):
        print("Python sending ICE:", candidate)
        ice_msg = json.dumps({'ice': {
            'candidate': candidate,
            'sdpMLineIndex': mlineindex,
        }})
        if ws.closed:
            print("❌ WebSocket is already closed — cannot send message.")
        else:
            future = asyncio.run_coroutine_threadsafe(ws.send_str(ice_msg), loop)
            try:
                future.result(timeout=5)
                print("✅ ICE candidate sent")
            except Exception as e:
                print("❌ Failed to send ICE candidate:", e)

    webrtc.connect('on-negotiation-needed', on_negotiation_needed)
    webrtc.connect('on-ice-candidate', on_ice_candidate)

    pipeline.set_state(Gst.State.PLAYING)

    async for msg in ws:
        print(f"WS message: {msg.data}")
        if msg.type == web.WSMsgType.TEXT:
            data = json.loads(msg.data)

            if 'sdp' in data:
                sdp = data['sdp']
                res, sdpmsg = GstSdp.SDPMessage.new_from_text(sdp['sdp'])
                if res != GstSdp.SDPResult.OK:
                    print("❌ Failed to parse SDP answer")
                    return
                answer = GstWebRTC.WebRTCSessionDescription.new(GstWebRTC.WebRTCSDPType.ANSWER, sdpmsg)
                webrtc.emit('set-remote-description', answer, None)
                print("✅ SDP answer set")
            elif 'ice' in data:
                ice = data['ice']
                webrtc.emit('add-ice-candidate', ice['sdpMLineIndex'], ice['candidate'])

    pipeline.set_state(Gst.State.NULL)
    return ws

app = web.Application()
app.router.add_get('/', index)
app.router.add_get('/static/video_client.js', javascript)
app.router.add_get('/ws', websocket_handler)

web.run_app(app, port=4664)
