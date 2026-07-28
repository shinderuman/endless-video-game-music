const FADE_SECONDS = 4;
const audio = new Audio();
const state = {
  playlists: [],
  tracks: [],
  visibleTracks: [],
  currentPlaylist: "",
  currentTrackId: null,
  mode: "loop",
  analysis: null,
  candidateIndex: 0,
  playing: false,
  shuffle: false,
  muted: false,
  transitionTimer: null,
  nextTimer: null,
  renderTimer: null,
  requestToken: 0,
  renderLimit: 250,
};

const elements = {
  serverDot: document.querySelector("#server-dot"),
  serverMessage: document.querySelector("#server-message"),
  refreshLibrary: document.querySelector("#refresh-library"),
  playlistCount: document.querySelector("#playlist-count"),
  playlistSearch: document.querySelector("#playlist-search"),
  playlistList: document.querySelector("#playlist-list"),
  playlistTitle: document.querySelector("#playlist-title"),
  trackCount: document.querySelector("#track-count"),
  trackSearch: document.querySelector("#track-search"),
  albumFilter: document.querySelector("#album-filter"),
  trackList: document.querySelector("#track-list"),
  artwork: document.querySelector("#artwork"),
  artworkFallback: document.querySelector("#artwork-fallback"),
  analysisOverlay: document.querySelector("#analysis-overlay"),
  nowTitle: document.querySelector("#now-title"),
  nowArtist: document.querySelector("#now-artist"),
  nowAlbum: document.querySelector("#now-album"),
  modeNormal: document.querySelector("#mode-normal"),
  modeLoop: document.querySelector("#mode-loop"),
  candidatePrev: document.querySelector("#candidate-prev"),
  candidateNext: document.querySelector("#candidate-next"),
  candidateLabel: document.querySelector("#candidate-label"),
  candidateScore: document.querySelector("#candidate-score"),
  loopProgress: document.querySelector("#loop-progress"),
  loopStart: document.querySelector("#loop-start"),
  loopEnd: document.querySelector("#loop-end"),
  shuffle: document.querySelector("#shuffle"),
  previous: document.querySelector("#previous"),
  playPause: document.querySelector("#play-pause"),
  next: document.querySelector("#next"),
  mute: document.querySelector("#mute"),
  rotationMinutes: document.querySelector("#rotation-minutes"),
  playerMessage: document.querySelector("#player-message"),
};

const api = async (url, options = {}) => {
  const response = await fetch(url, options);
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      message = (await response.json()).error || message;
    } catch {
      // An empty artwork response is expected when Music.app has no jacket image.
    }
    throw new Error(message);
  }
  return response;
};

const currentTrack = () => state.tracks.find((track) => track.id === state.currentTrackId);

const formatTime = (seconds) => {
  if (!Number.isFinite(seconds)) {
    return "—";
  }
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${Math.floor(seconds % 60).toString().padStart(2, "0")}`;
};

const setMessage = (message) => {
  elements.playerMessage.textContent = message;
};

const showAnalysis = (visible) => {
  elements.analysisOverlay.hidden = !visible;
};

const initialize = async () => {
  bindEvents();
  audio.addEventListener("ended", () => playAdjacent(1));
  audio.addEventListener("timeupdate", () => {
    enforceLoop();
    renderProgress();
  });
  audio.addEventListener("error", () => {
    if (audio.src) {
      setMessage("音声ファイルを再生できませんでした。");
    }
  });
  try {
    const status = await (await api("/api/status")).json();
    elements.serverDot.classList.add("ready");
    elements.serverMessage.textContent = status.pymusiclooperAvailable
      ? "サーバー準備完了"
      : "PyMusicLooperが見つかりません";
    await loadPlaylists();
  } catch (error) {
    elements.serverMessage.textContent = `接続エラー: ${error.message}`;
  }
  state.renderTimer = window.setInterval(renderProgress, 150);
};

const bindEvents = () => {
  elements.playlistSearch.addEventListener("input", renderPlaylists);
  elements.trackSearch.addEventListener("input", resetTrackLimit);
  elements.albumFilter.addEventListener("change", resetTrackLimit);
  elements.refreshLibrary.addEventListener("click", refreshLibrary);
  elements.modeNormal.addEventListener("click", () => setMode("normal"));
  elements.modeLoop.addEventListener("click", () => setMode("loop"));
  elements.candidatePrev.addEventListener("click", () => changeCandidate(-1));
  elements.candidateNext.addEventListener("click", () => changeCandidate(1));
  elements.previous.addEventListener("click", () => playAdjacent(-1));
  elements.next.addEventListener("click", () => playAdjacent(1));
  elements.playPause.addEventListener("click", togglePlayback);
  elements.shuffle.addEventListener("click", toggleShuffle);
  elements.mute.addEventListener("click", toggleMute);
  elements.rotationMinutes.addEventListener("change", scheduleTransition);
};

const loadPlaylists = async () => {
  const payload = await (await api("/api/playlists")).json();
  state.playlists = payload.playlists;
  elements.playlistCount.textContent = state.playlists.length;
  renderPlaylists();
  if (state.playlists.length === 0) {
    elements.serverMessage.textContent = "Music.appの読み込み許可が必要です";
    elements.trackList.innerHTML =
      '<div class="empty-message">Music.appの操作を許可して「Musicを再読込」を押してください。</div>';
    return;
  }
  const preferred = state.playlists.find((playlist) => playlist.name === "GAME");
  if (preferred) {
    await selectPlaylist(preferred.name);
  } else if (state.playlists.length > 0) {
    await selectPlaylist(state.playlists[0].name);
  }
};

const refreshLibrary = async () => {
  elements.refreshLibrary.disabled = true;
  elements.serverMessage.textContent = "Music.appを読み込み中";
  try {
    await api("/api/library/refresh", {method: "POST"});
    await loadPlaylists();
    elements.serverMessage.textContent = "Music.appを再読込しました";
  } catch (error) {
    elements.serverMessage.textContent = `再読込失敗: ${error.message}`;
  } finally {
    elements.refreshLibrary.disabled = false;
  }
};

const renderPlaylists = () => {
  const query = elements.playlistSearch.value.trim().toLocaleLowerCase();
  const playlists = state.playlists.filter((playlist) =>
    playlist.name.toLocaleLowerCase().includes(query),
  );
  elements.playlistList.replaceChildren(
    ...playlists.map((playlist) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `playlist-item${playlist.name === state.currentPlaylist ? " active" : ""}`;
      const name = document.createElement("span");
      name.textContent = playlist.name;
      const count = document.createElement("small");
      count.textContent = playlist.availableTrackCount;
      button.append(name, count);
      button.addEventListener("click", () => selectPlaylist(playlist.name));
      return button;
    }),
  );
};

const selectPlaylist = async (name) => {
  const payload = await (await api(`/api/playlist?name=${encodeURIComponent(name)}`)).json();
  state.currentPlaylist = name;
  state.tracks = payload.tracks;
  state.renderLimit = 250;
  elements.playlistTitle.textContent = name;
  elements.trackCount.textContent = state.tracks.length;
  elements.trackSearch.value = "";
  populateAlbums();
  renderPlaylists();
  renderTracks();
};

const populateAlbums = () => {
  const albums = [...new Set(state.tracks.map((track) => track.album).filter(Boolean))]
    .sort((left, right) => left.localeCompare(right, "ja"));
  const all = document.createElement("option");
  all.value = "";
  all.textContent = "すべてのアルバム";
  elements.albumFilter.replaceChildren(
    all,
    ...albums.map((album) => {
      const option = document.createElement("option");
      option.value = album;
      option.textContent = album;
      return option;
    }),
  );
};

const renderTracks = () => {
  const query = elements.trackSearch.value.trim().toLocaleLowerCase();
  const album = elements.albumFilter.value;
  state.visibleTracks = state.tracks.filter((track) => {
    const matchesAlbum = !album || track.album === album;
    const haystack = `${track.name}\0${track.artist}\0${track.album}`.toLocaleLowerCase();
    return matchesAlbum && haystack.includes(query);
  });
  if (state.visibleTracks.length === 0) {
    const message = document.createElement("div");
    message.className = "empty-message";
    message.textContent = "条件に一致する曲がありません。";
    elements.trackList.replaceChildren(message);
    return;
  }
  const renderedTracks = state.visibleTracks.slice(0, state.renderLimit);
  const trackButtons = renderedTracks.map((track) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `track-item${track.id === state.currentTrackId ? " active" : ""}`;
      button.disabled = !track.available;
      const number = document.createElement("span");
      number.className = "track-number";
      number.textContent = track.playlistIndex;
      const copy = document.createElement("span");
      copy.className = "track-copy";
      const title = document.createElement("strong");
      title.textContent = track.name || "名称不明";
      const meta = document.createElement("small");
      meta.textContent = [track.artist, track.album].filter(Boolean).join(" · ") || "情報なし";
      copy.append(title, meta);
      const availability = document.createElement("span");
      availability.className = `availability${track.available ? "" : " missing"}`;
      button.append(number, copy, availability);
      button.addEventListener("click", () => selectTrack(track.id, true));
      return button;
    });
  if (renderedTracks.length < state.visibleTracks.length) {
    const loadMore = document.createElement("button");
    loadMore.type = "button";
    loadMore.className = "quiet-button load-more";
    loadMore.textContent =
      `さらに表示（${renderedTracks.length} / ${state.visibleTracks.length}）`;
    loadMore.addEventListener("click", () => {
      state.renderLimit += 250;
      renderTracks();
    });
    trackButtons.push(loadMore);
  }
  elements.trackList.replaceChildren(...trackButtons);
};

const resetTrackLimit = () => {
  state.renderLimit = 250;
  renderTracks();
};

const selectTrack = async (trackId, autoplay) => {
  const track = state.tracks.find((candidate) => candidate.id === trackId);
  if (!track || !track.available) {
    setMessage("ローカル音声ファイルが見つかりません。");
    return;
  }
  const token = ++state.requestToken;
  stopPlayback();
  state.currentTrackId = track.id;
  state.analysis = null;
  state.candidateIndex = 0;
  updateTrackDetails(track);
  renderTracks();
  if (!autoplay) {
    return;
  }
  try {
    if (state.mode === "normal") {
      await playNormal(track);
    } else {
      await playLoop(track, token);
    }
  } catch (error) {
    if (token === state.requestToken) {
      showAnalysis(false);
      setMessage(`再生できませんでした: ${error.message}`);
    }
  }
};

const updateTrackDetails = (track) => {
  elements.nowTitle.textContent = track.name || "名称不明";
  elements.nowArtist.textContent = track.artist || track.albumArtist || "アーティスト不明";
  elements.nowAlbum.textContent = track.album;
  elements.artwork.hidden = true;
  elements.artworkFallback.hidden = false;
  elements.artwork.src = "";
  if (track.artworkUrl) {
    elements.artwork.onload = () => {
      elements.artwork.hidden = false;
      elements.artworkFallback.hidden = true;
    };
    elements.artwork.onerror = () => {
      elements.artwork.hidden = true;
      elements.artworkFallback.hidden = false;
    };
    elements.artwork.src = `${track.artworkUrl}?v=${encodeURIComponent(track.id)}`;
  }
  resetCandidateDisplay();
};

const resetCandidateDisplay = () => {
  elements.candidateLabel.textContent = "ループ候補 —";
  elements.candidateScore.textContent =
    state.mode === "loop" ? "解析待ち" : "通常再生では使用しません";
  elements.loopStart.textContent = "START —";
  elements.loopEnd.textContent = "END —";
  elements.loopProgress.style.width = "0";
};

const playNormal = async (track) => {
  showAnalysis(false);
  audio.src = track.audioUrl;
  audio.volume = state.muted ? 0 : 1;
  await audio.play();
  state.playing = true;
  updatePlayButton();
  setMessage("通常再生中");
  scheduleTransition();
  prefetchNext();
};

const playLoop = async (track, token) => {
  showAnalysis(true);
  setMessage("PyMusicLooperでループ位置を解析しています。");
  audio.src = track.audioUrl;
  audio.volume = 0;
  try {
    await audio.play();
    audio.pause();
    audio.currentTime = 0;
  } catch (error) {
    if (error.name !== "NotAllowedError") {
      throw error;
    }
  }
  const analysis = await (
    await api(`/api/tracks/${track.id}/analyze`, {method: "POST"})
  ).json();
  if (token !== state.requestToken) {
    return;
  }
  showAnalysis(false);
  state.analysis = analysis;
  if (analysis.candidates.length === 0) {
    setMessage("ループ候補がないため通常再生します。");
    await playNormal(track);
    return;
  }
  audio.volume = state.muted ? 0 : 1;
  renderCandidate();
  prefetchNext();
  try {
    await audio.play();
    state.playing = true;
    setMessage(`${analysis.candidateCount}件の候補をスコア順に読み込みました。`);
    scheduleTransition();
  } catch (error) {
    if (error.name !== "NotAllowedError") {
      throw error;
    }
    state.playing = false;
    setMessage(
      `${analysis.candidateCount}件の候補を読み込みました。再生ボタンを押してください。`,
    );
  }
  updatePlayButton();
};

const enforceLoop = () => {
  if (state.mode !== "loop" || !state.analysis?.candidates.length) {
    return;
  }
  const candidate = state.analysis.candidates[state.candidateIndex];
  if (audio.currentTime >= candidate.loopEndSeconds - 0.04) {
    audio.currentTime = candidate.loopStartSeconds;
  }
};

const stopPlayback = () => {
  window.clearTimeout(state.transitionTimer);
  window.clearTimeout(state.nextTimer);
  state.transitionTimer = null;
  state.nextTimer = null;
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
  state.playing = false;
  updatePlayButton();
};

const togglePlayback = async () => {
  const track = currentTrack();
  if (!track) {
    const first = state.visibleTracks.find((candidate) => candidate.available);
    if (first) {
      await selectTrack(first.id, true);
    }
    return;
  }
  if (audio.paused) {
    try {
      await audio.play();
      state.playing = true;
      scheduleTransition();
    } catch (error) {
      state.playing = false;
      setMessage(`再生できませんでした: ${error.message}`);
    }
  } else {
    audio.pause();
    state.playing = false;
    window.clearTimeout(state.transitionTimer);
  }
  updatePlayButton();
};

const updatePlayButton = () => {
  elements.playPause.textContent = state.playing ? "❚❚" : "▶";
  elements.playPause.setAttribute("aria-label", state.playing ? "一時停止" : "再生");
};

const setMode = async (mode) => {
  if (state.mode === mode) {
    return;
  }
  state.mode = mode;
  elements.modeNormal.classList.toggle("active", mode === "normal");
  elements.modeLoop.classList.toggle("active", mode === "loop");
  resetCandidateDisplay();
  if (currentTrack()) {
    await selectTrack(state.currentTrackId, true);
  }
};

const changeCandidate = async (delta) => {
  const candidates = state.analysis?.candidates;
  const track = currentTrack();
  if (!track || !candidates?.length || state.mode !== "loop") {
    return;
  }
  state.candidateIndex = (state.candidateIndex + delta + candidates.length) % candidates.length;
  audio.currentTime = candidates[state.candidateIndex].loopStartSeconds;
  renderCandidate();
  scheduleTransition();
};

const renderCandidate = () => {
  const candidates = state.analysis?.candidates;
  if (!candidates?.length) {
    resetCandidateDisplay();
    return;
  }
  const candidate = candidates[state.candidateIndex];
  elements.candidateLabel.textContent =
    `ループ候補 ${state.candidateIndex + 1} / ${candidates.length}`;
  elements.candidateScore.textContent = `スコア ${candidate.score.toFixed(6)}（高い順）`;
  elements.loopStart.textContent = `START ${formatTime(candidate.loopStartSeconds)}`;
  elements.loopEnd.textContent = `END ${formatTime(candidate.loopEndSeconds)}`;
};

const renderProgress = () => {
  const candidates = state.analysis?.candidates;
  if (state.mode !== "loop" || !candidates?.length) {
    if (audio.duration) {
      elements.loopProgress.style.width = `${(audio.currentTime / audio.duration) * 100}%`;
    }
    return;
  }
  const candidate = candidates[state.candidateIndex];
  const duration = candidate.loopEndSeconds - candidate.loopStartSeconds;
  const elapsed = audio.currentTime;
  const position = elapsed < candidate.loopStartSeconds
    ? elapsed / candidate.loopEndSeconds
    : (elapsed - candidate.loopStartSeconds) % duration / duration;
  elements.loopProgress.style.width = `${Math.max(0, Math.min(position * 100, 100))}%`;
};

const playAdjacent = async (direction) => {
  const playable = state.visibleTracks.filter((track) => track.available);
  if (playable.length === 0) {
    return;
  }
  let next;
  if (state.shuffle && playable.length > 1) {
    const choices = playable.filter((track) => track.id !== state.currentTrackId);
    next = choices[Math.floor(Math.random() * choices.length)];
  } else {
    const currentIndex = playable.findIndex((track) => track.id === state.currentTrackId);
    const baseIndex = currentIndex < 0 ? 0 : currentIndex;
    next = playable[(baseIndex + direction + playable.length) % playable.length];
  }
  await selectTrack(next.id, true);
};

const toggleShuffle = () => {
  state.shuffle = !state.shuffle;
  elements.shuffle.classList.toggle("active", state.shuffle);
  setMessage(state.shuffle ? "ランダム再生を有効にしました。" : "曲順再生に戻しました。");
};

const toggleMute = () => {
  state.muted = !state.muted;
  audio.volume = state.muted ? 0 : 1;
  elements.mute.classList.toggle("active", state.muted);
  elements.mute.textContent = state.muted ? "○" : "◕";
};

const scheduleTransition = () => {
  window.clearTimeout(state.transitionTimer);
  const minutes = Number(elements.rotationMinutes.value);
  if (!minutes || !state.playing) {
    return;
  }
  const fadeAfter = Math.max(minutes * 60 - FADE_SECONDS, 0) * 1000;
  state.transitionTimer = window.setTimeout(fadeAndNext, fadeAfter);
};

const fadeAndNext = () => {
  if (!state.playing) {
    return;
  }
  const started = performance.now();
  const fade = () => {
    const progress = Math.min((performance.now() - started) / (FADE_SECONDS * 1000), 1);
    audio.volume = state.muted ? 0 : 1 - progress;
    if (progress < 1) {
      window.requestAnimationFrame(fade);
    }
  };
  fade();
  state.nextTimer = window.setTimeout(() => playAdjacent(1), FADE_SECONDS * 1000);
};

const prefetchNext = () => {
  if (state.mode !== "loop") {
    return;
  }
  const playable = state.visibleTracks.filter((track) => track.available);
  const index = playable.findIndex((track) => track.id === state.currentTrackId);
  const next = playable[(index + 1) % playable.length];
  if (next && next.id !== state.currentTrackId) {
    api(`/api/tracks/${next.id}/analyze`, {method: "POST"}).catch(() => {});
  }
};

initialize();
