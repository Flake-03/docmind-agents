# Voice test

## 1. Chạy lại hệ thống

Từ thư mục `/home/flake/Documents`:

```bash
docker compose up -d --build --force-recreate
docker compose logs -f --tail=100 agents
```

Kiểm tra API:

```bash
curl http://127.0.0.1:8080/health
```

Kết quả mong đợi:

```json
{"status":"ok"}
```

## 2. Test microphone

1. Mở <http://127.0.0.1:8080/docs> bằng Chrome hoặc Edge.
2. Mở Developer Tools, chọn tab **Console**.
3. Paste và chạy đoạn mã dưới đây.
4. Cho phép trình duyệt sử dụng microphone.
5. Nên dùng tai nghe để tránh microphone thu lại âm thanh từ Gemini.

```javascript
(async () => {
  const projectId = "agents";
  const threadId = `voice-${Date.now()}`;
  const ws = new WebSocket(
    `ws://127.0.0.1:8080/v1/live?project_id=${projectId}&thread_id=${threadId}`
  );

  ws.binaryType = "arraybuffer";

  const micContext = new AudioContext();
  const playContext = new AudioContext();
  const playing = new Set();
  let nextPlayTime = 0;

  function stopPlayback() {
    for (const source of playing) {
      try {
        source.stop();
      } catch {}
    }
    playing.clear();
    nextPlayTime = playContext.currentTime;
  }

  function playPcm24k(data) {
    const pcm = new Int16Array(data);
    const buffer = playContext.createBuffer(1, pcm.length, 24000);
    const channel = buffer.getChannelData(0);

    for (let i = 0; i < pcm.length; i++) {
      channel[i] = pcm[i] / 32768;
    }

    const source = playContext.createBufferSource();
    source.buffer = buffer;
    source.connect(playContext.destination);

    const startAt = Math.max(playContext.currentTime + 0.03, nextPlayTime);
    source.start(startAt);
    nextPlayTime = startAt + buffer.duration;

    playing.add(source);
    source.onended = () => playing.delete(source);
  }

  ws.onmessage = (event) => {
    if (typeof event.data === "string") {
      const message = JSON.parse(event.data);
      console.log(message);

      if (message.type === "interrupted") {
        stopPlayback();
      }
    } else {
      playPcm24k(event.data);
    }
  };

  ws.onclose = (event) => {
    console.log("WebSocket closed:", event.code, event.reason);
  };

  await new Promise((resolve, reject) => {
    ws.onopen = resolve;
    ws.onerror = reject;
  });

  await Promise.all([micContext.resume(), playContext.resume()]);

  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
    },
  });

  const microphone = micContext.createMediaStreamSource(stream);
  const processor = micContext.createScriptProcessor(2048, 1, 1);

  processor.onaudioprocess = (event) => {
    if (ws.readyState !== WebSocket.OPEN) return;

    const input = event.inputBuffer.getChannelData(0);
    const ratio = micContext.sampleRate / 16000;
    const pcm = new Int16Array(Math.floor(input.length / ratio));

    for (let i = 0; i < pcm.length; i++) {
      const start = Math.floor(i * ratio);
      const end = Math.max(start + 1, Math.floor((i + 1) * ratio));
      let total = 0;

      for (let j = start; j < end && j < input.length; j++) {
        total += input[j];
      }

      const sample = Math.max(-1, Math.min(1, total / (end - start)));
      pcm[i] = sample < 0 ? sample * 32768 : sample * 32767;
    }

    ws.send(pcm.buffer);
  };

  microphone.connect(processor);
  processor.connect(micContext.destination);

  window.stopVoiceTest = async () => {
    processor.disconnect();
    microphone.disconnect();
    stream.getTracks().forEach((track) => track.stop());
    stopPlayback();
    ws.close();
    await micContext.close();
    await playContext.close();
  };

  console.log("Voice test started. Hãy bắt đầu nói.");
  console.log("Dừng bằng: stopVoiceTest()");
})();
```

Thử nói:

> Xin chào, bạn có nghe thấy tôi không?

Một phiên hoạt động bình thường sẽ xuất hiện các event sau trong Console:

```text
session_ready
input_transcript
output_transcript
turn_complete
```

Khi hỏi về project, Console sẽ có thêm `knowledge_result`.

## 3. Dừng test

Chạy trong Console:

```javascript
stopVoiceTest();
```

## 4. Xử lý lỗi

Xem trạng thái container và log:

```bash
cd /home/flake/Documents
docker compose ps
docker compose logs -f --tail=100 agents
```

Lưu ý: `/v1/live` là WebSocket nên không xuất hiện trong Swagger.
