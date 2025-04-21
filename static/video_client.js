const pc = new RTCPeerConnection();
const ws = new WebSocket('ws://' + window.location.host + '/ws');
const video = document.getElementById('video');

console.log("JS loaded, connecting to WS...");

pc.ontrack = (event) => {
  console.log("📺 Received track:", event);
  video.srcObject = event.streams[0];
  video.muted = true;
  video.play();
};

pc.onicecandidate = ({ candidate }) => {
  console.log('🧊 Local ICE candidate:', candidate);
  if (candidate) {
    ws.send(JSON.stringify({ ice: candidate }));
  }
};

ws.onopen = () => {
  console.log("✅ WebSocket connected");
};

ws.onerror = (err) => {
  console.error("❌ WebSocket error:", err);
};

ws.onmessage = async ({ data }) => {
  console.log("📩 WS message from server:", data);
  const msg = JSON.parse(data);

  if (msg.sdp) {
    console.log("📜 Received SDP:", msg.sdp.type);
    await pc.setRemoteDescription(new RTCSessionDescription(msg.sdp));
    const answer = await pc.createAnswer();
    await pc.setLocalDescription(answer);
    console.log("📤 Sending answer SDP");
    ws.send(JSON.stringify({ sdp: pc.localDescription }));
  } else if (msg.ice) {
    console.log("➕ Adding ICE candidate from server");
    await pc.addIceCandidate(new RTCIceCandidate(msg.ice));
  }
};