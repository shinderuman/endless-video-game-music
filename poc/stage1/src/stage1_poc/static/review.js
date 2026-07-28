const state = {
  tracks: [],
  summary: null,
  currentIndex: 0,
  audioContext: null,
  previewSource: null,
  boundaryTimer: null,
  nextBoundaryAt: null,
  boundaryCycleSeconds: null,
  boundaryDisplayCycleSeconds: null,
  boundaryFlashUntil: null,
  boundaryCrossings: 0,
};

const elements = {
  reviewCard: document.querySelector(".review-card"),
  progress: document.querySelector("#progress"),
  trackPosition: document.querySelector("#track-position"),
  evaluationGroup: document.querySelector("#evaluation-group"),
  title: document.querySelector("#title"),
  album: document.querySelector("#album"),
  artist: document.querySelector("#artist"),
  analysisStatus: document.querySelector("#analysis-status"),
  loopStart: document.querySelector("#loop-start"),
  loopEnd: document.querySelector("#loop-end"),
  previewButton: document.querySelector("#preview-button"),
  stopButton: document.querySelector("#stop-button"),
  previewStatus: document.querySelector("#preview-status"),
  boundaryMonitor: document.querySelector("#boundary-monitor"),
  boundaryCountdown: document.querySelector("#boundary-countdown"),
  boundaryProgress: document.querySelector("#boundary-progress"),
  boundaryFlash: document.querySelector("#boundary-flash"),
  fullPlayer: document.querySelector("#full-player"),
  loopButton: document.querySelector("#loop-button"),
  nonLoopButton: document.querySelector("#non-loop-button"),
  badPointsButton: document.querySelector("#bad-points-button"),
  clearButton: document.querySelector("#clear-button"),
  previousButton: document.querySelector("#previous-button"),
  nextButton: document.querySelector("#next-button"),
  nextUnlabeledButton: document.querySelector("#next-unlabeled-button"),
  message: document.querySelector("#message"),
};

const currentTrack = () => state.tracks[state.currentIndex];

const formatSeconds = (seconds) => {
  if (seconds === null) {
    return "候補なし";
  }
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${(seconds % 60).toFixed(3).padStart(6, "0")}`;
};

const setMessage = (message) => {
  elements.message.textContent = message;
};

const stopPreview = () => {
  if (state.previewSource) {
    state.previewSource.stop();
    state.previewSource = null;
  }
  if (state.boundaryTimer) {
    clearInterval(state.boundaryTimer);
    state.boundaryTimer = null;
  }
  state.nextBoundaryAt = null;
  state.boundaryDisplayCycleSeconds = null;
  state.boundaryFlashUntil = null;
  state.boundaryCrossings = 0;
  elements.previewStatus.textContent = "";
  elements.boundaryCountdown.textContent = "停止中";
  elements.boundaryProgress.style.width = "0";
  elements.boundaryFlash.textContent = "";
  elements.boundaryMonitor.classList.remove("crossing");
  elements.reviewCard.classList.remove("boundary-crossed");
};

const updateSelection = (label) => {
  elements.loopButton.classList.toggle("selected", label === "loop");
  elements.nonLoopButton.classList.toggle("selected", label === "non_loop");
  elements.badPointsButton.classList.toggle("selected", label === "loop_bad_points");
};

const render = () => {
  stopPreview();
  elements.fullPlayer.pause();
  const track = currentTrack();
  elements.trackPosition.textContent = `${state.currentIndex + 1} / ${state.tracks.length}`;
  elements.evaluationGroup.hidden = !track.evaluationGroup;
  elements.evaluationGroup.textContent = track.evaluationGroup || "";
  elements.title.textContent = track.title;
  elements.album.textContent = track.album;
  elements.artist.textContent = track.artist;
  elements.analysisStatus.textContent =
    track.analysisStatus === "candidate" ? "候補あり" : "候補なし";
  elements.loopStart.textContent = formatSeconds(track.loopStartSeconds);
  elements.loopEnd.textContent = formatSeconds(track.loopEndSeconds);
  elements.previewButton.disabled = track.analysisStatus !== "candidate";
  elements.fullPlayer.src = `/audio/${state.currentIndex}`;
  elements.previousButton.disabled = state.currentIndex === 0;
  elements.nextButton.disabled = state.currentIndex === state.tracks.length - 1;
  updateSelection(track.userLabel);
  renderProgress();
};

const renderProgress = () => {
  const labeled = state.tracks.filter((track) => track.userLabel !== null).length;
  elements.progress.textContent = `判定済み ${labeled} / ${state.tracks.length}`;
};

const ensureAudioContext = () => {
  state.audioContext ??= new AudioContext();
  return state.audioContext;
};

const updateBoundaryMonitor = () => {
  const now = state.audioContext.currentTime;
  if (now >= state.nextBoundaryAt) {
    state.boundaryCrossings += 1;
    state.nextBoundaryAt += state.boundaryCycleSeconds;
    state.boundaryDisplayCycleSeconds = state.boundaryCycleSeconds;
    state.boundaryFlashUntil = now + 1.2;
  }
  if (now < state.boundaryFlashUntil) {
    elements.boundaryCountdown.textContent = "いま通過";
    elements.boundaryProgress.style.width = "100%";
    elements.boundaryFlash.textContent =
      `境界通過 → ループ開始（${state.boundaryCrossings}回目）`;
    elements.boundaryMonitor.classList.add("crossing");
    elements.reviewCard.classList.add("boundary-crossed");
    return;
  }
  const remaining = Math.max(state.nextBoundaryAt - now, 0);
  const progress = (1 - remaining / state.boundaryDisplayCycleSeconds) * 100;
  elements.boundaryCountdown.textContent = `あと ${remaining.toFixed(1)} 秒`;
  elements.boundaryProgress.style.width = `${Math.max(progress, 0)}%`;
  elements.boundaryFlash.textContent = "";
  elements.boundaryMonitor.classList.remove("crossing");
  elements.reviewCard.classList.remove("boundary-crossed");
};

const startBoundaryMonitor = (context, firstBoundarySeconds, loopSeconds) => {
  state.nextBoundaryAt = context.currentTime + firstBoundarySeconds;
  state.boundaryCycleSeconds = loopSeconds;
  state.boundaryDisplayCycleSeconds = firstBoundarySeconds;
  state.boundaryFlashUntil = 0;
  state.boundaryCrossings = 0;
  updateBoundaryMonitor();
  state.boundaryTimer = setInterval(updateBoundaryMonitor, 50);
};

const playPreview = async () => {
  const track = currentTrack();
  stopPreview();
  setMessage("");
  elements.previewStatus.textContent = "音源を読込中…";
  try {
    const context = ensureAudioContext();
    await context.resume();
    const response = await fetch(`/audio/${state.currentIndex}`);
    const buffer = await context.decodeAudioData(await response.arrayBuffer());
    const source = context.createBufferSource();
    source.buffer = buffer;
    source.loop = true;
    source.loopStart = track.loopStartSeconds;
    source.loopEnd = track.loopEndSeconds;
    source.connect(context.destination);
    const startOffset = Math.max(track.loopEndSeconds - 5, 0);
    source.start(0, startOffset);
    state.previewSource = source;
    startBoundaryMonitor(
      context,
      track.loopEndSeconds - startOffset,
      track.loopEndSeconds - track.loopStartSeconds,
    );
    elements.previewStatus.textContent = "ループ再生中";
  } catch (error) {
    elements.previewStatus.textContent = "";
    setMessage(`試聴できませんでした: ${error.message}`);
  }
};

const saveLabel = async (label) => {
  stopPreview();
  setMessage("保存中…");
  const response = await fetch("/api/label", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({index: state.currentIndex, label}),
  });
  if (!response.ok) {
    const payload = await response.json();
    throw new Error(payload.error || "ラベルを保存できませんでした");
  }
  state.tracks[state.currentIndex] = await response.json();
  updateSelection(label);
  renderProgress();
  setMessage("保存しました");
};

const move = (offset) => {
  state.currentIndex = Math.max(
    0,
    Math.min(state.currentIndex + offset, state.tracks.length - 1),
  );
  setMessage("");
  render();
};

const moveToNextUnlabeled = () => {
  const next = state.tracks.findIndex(
    (track, index) => index > state.currentIndex && track.userLabel === null,
  );
  const wrapped = state.tracks.findIndex((track) => track.userLabel === null);
  if (next >= 0 || wrapped >= 0) {
    state.currentIndex = next >= 0 ? next : wrapped;
    setMessage("");
    render();
    return;
  }
  setMessage("100曲すべて判定済みです");
};

const attachEvents = () => {
  elements.previewButton.addEventListener("click", playPreview);
  elements.stopButton.addEventListener("click", stopPreview);
  elements.loopButton.addEventListener("click", () => saveLabel("loop").catch(showError));
  elements.nonLoopButton.addEventListener("click", () =>
    saveLabel("non_loop").catch(showError),
  );
  elements.badPointsButton.addEventListener("click", () =>
    saveLabel("loop_bad_points").catch(showError),
  );
  elements.clearButton.addEventListener("click", () => saveLabel(null).catch(showError));
  elements.previousButton.addEventListener("click", () => move(-1));
  elements.nextButton.addEventListener("click", () => move(1));
  elements.nextUnlabeledButton.addEventListener("click", moveToNextUnlabeled);
};

const showError = (error) => {
  setMessage(error.message);
};

const main = async () => {
  attachEvents();
  try {
    const response = await fetch("/api/review");
    const payload = await response.json();
    state.tracks = payload.tracks;
    state.summary = payload.summary;
    render();
  } catch (error) {
    setMessage(`レビュー一覧を読み込めませんでした: ${error.message}`);
  }
};

main();
