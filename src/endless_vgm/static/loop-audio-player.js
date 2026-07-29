const AUDIO_CONTEXT_RESUME_TIMEOUT_MS = 250;
const USER_RESUME_TIMEOUT_MS = 3_000;

export class LoopAudioPlayer {
  constructor() {
    this.context = null;
    this.buffer = null;
    this.source = null;
    this.gain = null;
    this.offset = 0;
    this.startedAt = 0;
    this.loopStart = 0;
    this.loopEnd = 0;
    this.playing = false;
    this.outputVolume = 1;
    this.loadToken = 0;
  }

  get currentTime() {
    if (!this.buffer) {
      return 0;
    }
    const elapsed = this.playing
      ? this.context.currentTime - this.startedAt
      : 0;
    return this.#wrapTime(this.offset + elapsed);
  }

  set currentTime(value) {
    const nextOffset = this.#clampTime(value);
    if (!this.playing) {
      this.offset = nextOffset;
      return;
    }
    this.#stopSource();
    this.offset = nextOffset;
    this.#startSource();
  }

  get duration() {
    return this.buffer?.duration ?? Number.NaN;
  }

  get paused() {
    return !this.playing;
  }

  get volume() {
    return this.outputVolume;
  }

  set volume(value) {
    this.outputVolume = Math.max(0, Math.min(Number(value), 1));
    if (this.gain) {
      this.gain.gain.value = this.outputVolume;
    }
  }

  async prepare() {
    if (!this.context) {
      this.context = new AudioContext();
      this.gain = this.context.createGain();
      this.gain.gain.value = this.outputVolume;
      this.gain.connect(this.context.destination);
    }
  }

  async load(url) {
    const token = ++this.loadToken;
    await this.prepare();
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`${response.status} ${response.statusText}`);
    }
    const encodedAudio = await response.arrayBuffer();
    const decodedAudio = await this.context.decodeAudioData(encodedAudio);
    if (token !== this.loadToken) {
      return false;
    }
    this.#stopSource();
    this.buffer = decodedAudio;
    this.offset = 0;
    this.loopStart = 0;
    this.loopEnd = decodedAudio.duration;
    return true;
  }

  setLoop(loopStart, loopEnd) {
    if (!this.buffer) {
      return;
    }
    this.loopStart = this.#clampTime(loopStart);
    this.loopEnd = this.#clampTime(loopEnd);
    if (this.loopEnd <= this.loopStart) {
      this.loopStart = 0;
      this.loopEnd = this.buffer.duration;
    }
    if (this.source) {
      this.source.loopStart = this.loopStart;
      this.source.loopEnd = this.loopEnd;
    }
  }

  async play(userInitiated = false) {
    if (!this.buffer || this.playing) {
      return;
    }
    await this.prepare();
    if (this.context.state !== "running") {
      const resumed = this.context.resume();
      await Promise.race([
        resumed,
        new Promise((resolve) => {
          window.setTimeout(
            resolve,
            userInitiated
              ? USER_RESUME_TIMEOUT_MS
              : AUDIO_CONTEXT_RESUME_TIMEOUT_MS,
          );
        }),
      ]);
      if (this.context.state !== "running") {
        throw new DOMException(
          "再生ボタンを押してください。",
          "NotAllowedError",
        );
      }
    }
    this.#startSource();
  }

  pause() {
    if (!this.playing) {
      return;
    }
    this.offset = this.currentTime;
    this.#stopSource();
  }

  stop() {
    this.#stopSource();
    this.offset = 0;
  }

  clear() {
    this.stop();
    this.loadToken += 1;
    this.buffer = null;
    this.loopStart = 0;
    this.loopEnd = 0;
  }

  #startSource() {
    const source = this.context.createBufferSource();
    source.buffer = this.buffer;
    source.loop = true;
    source.loopStart = this.loopStart;
    source.loopEnd = this.loopEnd;
    source.connect(this.gain);
    source.start(0, this.#clampTime(this.offset));
    this.source = source;
    this.startedAt = this.context.currentTime;
    this.playing = true;
  }

  #stopSource() {
    if (this.source) {
      this.source.onended = null;
      this.source.stop();
      this.source.disconnect();
      this.source = null;
    }
    this.playing = false;
  }

  #clampTime(value) {
    if (!this.buffer || !Number.isFinite(Number(value))) {
      return 0;
    }
    return Math.max(0, Math.min(Number(value), this.buffer.duration));
  }

  #wrapTime(value) {
    if (
      value < this.loopEnd
      || this.loopEnd <= this.loopStart
    ) {
      return this.#clampTime(value);
    }
    const loopDuration = this.loopEnd - this.loopStart;
    return this.loopStart + (value - this.loopStart) % loopDuration;
  }
}
