const FADE_SECONDS = 4;
const MAX_LOOP_CANDIDATES = 20;
const PANEL_WIDTH_STORAGE_KEY = "endless-vgm-panel-widths";
const LIBRARY_STATE_STORAGE_KEY = "endless-vgm-library-state";
const PANEL_WIDTHS = {
  playlist: {property: "--playlist-width", min: 170, max: 480},
  album: {property: "--album-width", min: 200, max: 640},
  track: {property: "--track-width", min: 360, max: 900},
};
const audio = new Audio();
const state = {
  playlists: [],
  albums: [],
  tracks: [],
  visibleTracks: [],
  currentPlaylist: "",
  currentAlbumId: "",
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
  layout: document.querySelector(".layout"),
  panelResizers: [...document.querySelectorAll(".panel-resizer")],
  serverDot: document.querySelector("#server-dot"),
  serverMessage: document.querySelector("#server-message"),
  refreshLibrary: document.querySelector("#refresh-library"),
  playlistCount: document.querySelector("#playlist-count"),
  playlistSearch: document.querySelector("#playlist-search"),
  playlistList: document.querySelector("#playlist-list"),
  albumCount: document.querySelector("#album-count"),
  albumSearch: document.querySelector("#album-search"),
  albumList: document.querySelector("#album-list"),
  trackCount: document.querySelector("#track-count"),
  trackSearch: document.querySelector("#track-search"),
  trackList: document.querySelector("#track-list"),
  artwork: document.querySelector("#artwork"),
  artworkFallback: document.querySelector("#artwork-fallback"),
  analysisOverlay: document.querySelector("#analysis-overlay"),
  nowTitle: document.querySelector("#now-title"),
  nowArtist: document.querySelector("#now-artist"),
  nowAlbum: document.querySelector("#now-album"),
  seekBar: document.querySelector("#seek-bar"),
  currentTime: document.querySelector("#current-time"),
  totalTime: document.querySelector("#total-time"),
  modeNormal: document.querySelector("#mode-normal"),
  modeLoop: document.querySelector("#mode-loop"),
  candidatePrev: document.querySelector("#candidate-prev"),
  candidateNext: document.querySelector("#candidate-next"),
  candidatePicker: document.querySelector("#candidate-picker"),
  candidatePanel: document.querySelector("#candidate-panel"),
  candidateList: document.querySelector("#candidate-list"),
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
  restorePanelWidths();
  restoreLibraryState();
  bindEvents();
  audio.addEventListener("ended", () => playAdjacent(1));
  audio.addEventListener("durationchange", renderSeek);
  audio.addEventListener("loadedmetadata", renderSeek);
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
  for (const resizer of elements.panelResizers) {
    resizer.addEventListener("pointerdown", beginPanelResize);
    resizer.addEventListener("keydown", resizePanelWithKeyboard);
  }
  elements.playlistSearch.addEventListener("input", () => {
    renderPlaylists();
    saveLibraryState();
  });
  elements.albumSearch.addEventListener("input", () => {
    renderAlbums();
    saveLibraryState();
  });
  elements.trackSearch.addEventListener("input", () => {
    resetTrackLimit();
    saveLibraryState();
  });
  elements.seekBar.addEventListener("input", seekAudio);
  elements.refreshLibrary.addEventListener("click", refreshLibrary);
  elements.modeNormal.addEventListener("click", () => setMode("normal"));
  elements.modeLoop.addEventListener("click", () => setMode("loop"));
  elements.candidatePrev.addEventListener("click", () => changeCandidate(-1));
  elements.candidateNext.addEventListener("click", () => changeCandidate(1));
  elements.candidatePicker.addEventListener("click", toggleCandidatePanel);
  elements.previous.addEventListener("click", () => playAdjacent(-1));
  elements.next.addEventListener("click", () => playAdjacent(1));
  elements.playPause.addEventListener("click", togglePlayback);
  elements.shuffle.addEventListener("click", toggleShuffle);
  elements.mute.addEventListener("click", toggleMute);
  elements.rotationMinutes.addEventListener("change", scheduleTransition);
};

const restorePanelWidths = () => {
  try {
    const widths = JSON.parse(localStorage.getItem(PANEL_WIDTH_STORAGE_KEY) || "{}");
    for (const [panel, width] of Object.entries(widths)) {
      setPanelWidth(panel, width);
    }
  } catch {
    // 保存値が壊れている場合はCSSの初期幅を使う。
  }
  syncResizerValues();
};

const setPanelWidth = (panel, requestedWidth) => {
  const config = PANEL_WIDTHS[panel];
  const width = Number(requestedWidth);
  if (!config || !Number.isFinite(width)) {
    return;
  }
  const clamped = Math.round(Math.max(config.min, Math.min(width, config.max)));
  elements.layout.style.setProperty(config.property, `${clamped}px`);
  const resizer = elements.panelResizers.find(
    (candidate) => candidate.dataset.panel === panel,
  );
  resizer?.setAttribute("aria-valuenow", String(clamped));
  resizer?.setAttribute("aria-valuemin", String(config.min));
  resizer?.setAttribute("aria-valuemax", String(config.max));
};

const panelWidth = (panel) => {
  const property = PANEL_WIDTHS[panel]?.property;
  return Number.parseFloat(getComputedStyle(elements.layout).getPropertyValue(property));
};

const savePanelWidths = () => {
  const widths = Object.fromEntries(
    Object.keys(PANEL_WIDTHS).map((panel) => [panel, panelWidth(panel)]),
  );
  try {
    localStorage.setItem(PANEL_WIDTH_STORAGE_KEY, JSON.stringify(widths));
  } catch {
    // 保存できない環境でも現在の画面では幅調整を利用できる。
  }
};

const syncResizerValues = () => {
  for (const panel of Object.keys(PANEL_WIDTHS)) {
    setPanelWidth(panel, panelWidth(panel));
  }
};

const restoreLibraryState = () => {
  try {
    const saved = JSON.parse(
      localStorage.getItem(LIBRARY_STATE_STORAGE_KEY) || "{}",
    );
    state.currentPlaylist =
      typeof saved.playlist === "string" ? saved.playlist : "";
    state.currentAlbumId =
      typeof saved.albumId === "string" ? saved.albumId : "";
    state.currentTrackId =
      typeof saved.trackId === "string" ? saved.trackId : null;
    elements.playlistSearch.value =
      typeof saved.playlistSearch === "string" ? saved.playlistSearch : "";
    elements.albumSearch.value =
      typeof saved.albumSearch === "string" ? saved.albumSearch : "";
    elements.trackSearch.value =
      typeof saved.trackSearch === "string" ? saved.trackSearch : "";
  } catch {
    // 保存値が壊れている場合は初期状態を使う。
  }
};

const saveLibraryState = () => {
  try {
    localStorage.setItem(
      LIBRARY_STATE_STORAGE_KEY,
      JSON.stringify({
        playlist: state.currentPlaylist,
        albumId: state.currentAlbumId,
        trackId: state.currentTrackId,
        playlistSearch: elements.playlistSearch.value,
        albumSearch: elements.albumSearch.value,
        trackSearch: elements.trackSearch.value,
      }),
    );
  } catch {
    // 保存できない環境でも選択と検索は現在の画面で利用できる。
  }
};

const beginPanelResize = (event) => {
  if (event.button !== 0) {
    return;
  }
  const resizer = event.currentTarget;
  const panel = resizer.dataset.panel;
  const startX = event.clientX;
  const startWidth = panelWidth(panel);
  resizer.classList.add("active");
  document.body.classList.add("resizing-panels");
  const move = (moveEvent) => {
    setPanelWidth(panel, startWidth + moveEvent.clientX - startX);
  };
  const finish = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", finish);
    window.removeEventListener("pointercancel", finish);
    resizer.classList.remove("active");
    document.body.classList.remove("resizing-panels");
    savePanelWidths();
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", finish);
  window.addEventListener("pointercancel", finish);
  event.preventDefault();
};

const resizePanelWithKeyboard = (event) => {
  if (!["ArrowLeft", "ArrowRight"].includes(event.key)) {
    return;
  }
  const panel = event.currentTarget.dataset.panel;
  const direction = event.key === "ArrowLeft" ? -1 : 1;
  setPanelWidth(panel, panelWidth(panel) + direction * 12);
  savePanelWidths();
  event.preventDefault();
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
  const preferred =
    state.playlists.find((playlist) => playlist.name === state.currentPlaylist)
    ?? state.playlists.find((playlist) => playlist.name === "GAME");
  if (preferred) {
    await selectPlaylist(preferred.name, true);
  } else if (state.playlists.length > 0) {
    await selectPlaylist(state.playlists[0].name, true);
  }
};

const refreshLibrary = async () => {
  setLibraryLoading(true);
  elements.serverMessage.textContent = "Music.appを読み込み中";
  try {
    await api("/api/library/refresh", {method: "POST"});
    await loadPlaylists();
    elements.serverMessage.textContent = "Music.appを再読込しました";
  } catch (error) {
    elements.serverMessage.textContent = `再読込失敗: ${error.message}`;
  } finally {
    setLibraryLoading(false);
  }
};

const setLibraryLoading = (loading) => {
  elements.refreshLibrary.disabled = loading;
  elements.refreshLibrary.classList.toggle("loading", loading);
  elements.refreshLibrary.setAttribute("aria-busy", String(loading));
  elements.refreshLibrary.textContent = loading ? "読み込み中" : "Musicを再読込";
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
      button.title = playlist.isLibrary
        ? "Music.appライブラリ内のすべての曲を表示します"
        : `プレイリスト「${playlist.name}」の曲を表示します`;
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

const selectPlaylist = async (name, restoring = false) => {
  const payload = await (await api(`/api/playlist?name=${encodeURIComponent(name)}`)).json();
  const playlistChanged = name !== state.currentPlaylist;
  state.currentPlaylist = name;
  state.tracks = payload.tracks;
  state.albums = payload.albums ?? legacyAlbumGroups(state.tracks);
  state.renderLimit = 250;
  if (!restoring || playlistChanged) {
    state.currentAlbumId = "";
    state.currentTrackId = null;
    elements.albumSearch.value = "";
    elements.trackSearch.value = "";
  }
  if (!state.albums.some((album) => album.id === state.currentAlbumId)) {
    state.currentAlbumId = "";
  }
  if (!state.tracks.some((track) => track.id === state.currentTrackId)) {
    state.currentTrackId = null;
  }
  elements.trackCount.textContent = state.tracks.length;
  elements.albumCount.textContent = state.albums.length;
  renderPlaylists();
  renderAlbums();
  renderTracks();
  const restoredTrack = state.tracks.find(
    (track) => track.id === state.currentTrackId && track.available,
  );
  if (restoring && restoredTrack && !audio.src) {
    await selectTrack(restoredTrack.id, false);
  } else {
    saveLibraryState();
  }
};

const legacyAlbumGroups = (tracks) => {
  const albums = new Map();
  for (const track of tracks) {
    if (!albums.has(track.album)) {
      albums.set(track.album, {
        id: `legacy-${albums.size}`,
        name: track.album || "アルバム不明",
        discCount: 1,
        trackCount: 0,
        trackIds: [],
      });
    }
    const album = albums.get(track.album);
    album.trackCount += 1;
    album.trackIds.push(track.id);
  }
  return [...albums.values()];
};

const renderAlbums = () => {
  const query = elements.albumSearch.value.trim().toLocaleLowerCase();
  const albums = state.albums.filter((album) =>
    album.name.toLocaleLowerCase().includes(query),
  );
  const allAlbums = {
    id: "",
    name: "すべてのアルバム",
    trackCount: state.tracks.length,
  };
  const visibleAlbums = query
    ? albums
    : [allAlbums, ...albums];
  elements.albumList.replaceChildren(
    ...visibleAlbums.map((album) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className =
        `album-item${album.id === state.currentAlbumId ? " active" : ""}`;
      button.title = album.id
        ? `アルバム「${album.name}」の曲を表示します`
        : "選択中のプレイリストにあるすべてのアルバムの曲を表示します";
      const copy = document.createElement("span");
      const name = document.createElement("strong");
      name.textContent = album.name;
      copy.append(name);
      if (album.discCount > 1) {
        const discs = document.createElement("small");
        discs.textContent = `${album.discCount}枚組`;
        copy.append(discs);
      }
      const count = document.createElement("small");
      count.textContent = album.trackCount;
      button.append(copy, count);
      button.addEventListener("click", () => selectAlbum(album.id));
      return button;
    }),
  );
};

const selectAlbum = (albumId) => {
  state.currentAlbumId = albumId;
  state.renderLimit = 250;
  elements.trackSearch.value = "";
  renderAlbums();
  renderTracks();
  saveLibraryState();
};

const renderTracks = () => {
  const query = elements.trackSearch.value.trim().toLocaleLowerCase();
  const selectedAlbum = state.albums.find(
    (album) => album.id === state.currentAlbumId,
  );
  const tracksById = new Map(state.tracks.map((track) => [track.id, track]));
  const albumTracks = selectedAlbum
    ? selectedAlbum.trackIds.map((trackId) => tracksById.get(trackId)).filter(Boolean)
    : state.tracks;
  state.visibleTracks = albumTracks.filter((track) => {
    const haystack = `${track.name}\0${track.artist}\0${track.album}`.toLocaleLowerCase();
    return haystack.includes(query);
  });
  const selectedIndex = state.visibleTracks.findIndex(
    (track) => track.id === state.currentTrackId,
  );
  if (selectedIndex >= state.renderLimit) {
    state.renderLimit = Math.ceil((selectedIndex + 1) / 250) * 250;
  }
  elements.trackCount.textContent = state.visibleTracks.length;
  if (state.visibleTracks.length === 0) {
    const message = document.createElement("div");
    message.className = "empty-message";
    message.textContent = "条件に一致する曲がありません。";
    elements.trackList.replaceChildren(message);
    return;
  }
  const renderedTracks = state.visibleTracks.slice(0, state.renderLimit);
  const trackNodes = [];
  let previousDisc = null;
  for (const track of renderedTracks) {
    if (
      selectedAlbum?.discCount > 1
      && track.discNumber !== previousDisc
      && track.discNumber !== null
    ) {
      const divider = document.createElement("div");
      divider.className = "disc-divider";
      divider.textContent = `DISC ${track.discNumber}`;
      trackNodes.push(divider);
      previousDisc = track.discNumber;
    }
      const button = document.createElement("button");
      button.type = "button";
      button.className = `track-item${track.id === state.currentTrackId ? " active" : ""}`;
      button.disabled = !track.available;
      button.title = track.available
        ? `「${track.name || "名称不明"}」を選択して再生します`
        : "ローカル音源ファイルの場所を確認できない曲です";
      const number = document.createElement("span");
      number.className = "track-number";
      number.textContent = selectedAlbum && track.trackNumber
        ? track.trackNumber.toString().padStart(2, "0")
        : track.playlistIndex;
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
      trackNodes.push(button);
  }
  if (renderedTracks.length < state.visibleTracks.length) {
    const loadMore = document.createElement("button");
    loadMore.type = "button";
    loadMore.className = "quiet-button load-more";
    loadMore.textContent =
      `さらに表示（${renderedTracks.length} / ${state.visibleTracks.length}）`;
    loadMore.title = "曲一覧をさらに250件表示します";
    loadMore.addEventListener("click", () => {
      state.renderLimit += 250;
      renderTracks();
    });
    trackNodes.push(loadMore);
  }
  elements.trackList.replaceChildren(...trackNodes);
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
  saveLibraryState();
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
  elements.seekBar.value = "0";
  elements.seekBar.disabled = true;
  elements.currentTime.textContent = "現在 0:00";
  elements.totalTime.textContent = "全長 —";
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
  setCandidatePanel(false);
  elements.candidateList.replaceChildren();
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
  const scoredCandidates = analysis.candidates.slice(0, MAX_LOOP_CANDIDATES);
  analysis.candidateCount = scoredCandidates.length;
  analysis.candidates = withHeadLoopCandidate(scoredCandidates, audio.duration);
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
  state.candidateIndex = scoredCandidates.length > 0 ? 1 : 0;
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

const withHeadLoopCandidate = (candidates, duration) => {
  const best = candidates[0];
  const loopEndSeconds = best?.loopEndSeconds ?? duration;
  if (!Number.isFinite(loopEndSeconds) || loopEndSeconds <= 0) {
    return candidates;
  }
  return [
    {
      ...(best ?? {}),
      loopStartSample: 0,
      loopStartSeconds: 0,
      loopEndSeconds,
      isHeadLoop: true,
      usesScoredLoopEnd: Boolean(best),
    },
    ...candidates,
  ];
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
  elements.playPause.title = state.playing ? "現在の曲を一時停止します" : "現在の曲を再生します";
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
  const index = (state.candidateIndex + delta + candidates.length) % candidates.length;
  selectCandidate(index, false);
};

const renderCandidate = () => {
  const candidates = state.analysis?.candidates;
  if (!candidates?.length) {
    resetCandidateDisplay();
    return;
  }
  const candidate = candidates[state.candidateIndex];
  const candidateNumber = candidate.isHeadLoop ? 0 : state.candidateIndex;
  elements.candidateLabel.textContent =
    `ループ候補 ${candidateNumber} / ${state.analysis.candidateCount}`;
  elements.candidateScore.textContent = candidate.isHeadLoop
    ? candidate.usesScoredLoopEnd
      ? "先頭0:00からループ（終了は候補1と共通）"
      : "先頭0:00から曲の終端までループ"
    : `スコア ${candidate.score.toFixed(6)}（高い順）`;
  elements.loopStart.textContent = `START ${formatTime(candidate.loopStartSeconds)}`;
  elements.loopEnd.textContent = `END ${formatTime(candidate.loopEndSeconds)}`;
  renderCandidateList();
};

const toggleCandidatePanel = () => {
  if (!state.analysis?.candidates.length) {
    return;
  }
  setCandidatePanel(elements.candidatePanel.hidden);
};

const setCandidatePanel = (open) => {
  elements.candidatePanel.hidden = !open;
  elements.candidatePicker.setAttribute("aria-expanded", String(open));
};

const selectCandidate = (index, closePanel) => {
  const candidates = state.analysis?.candidates;
  if (!candidates?.[index]) {
    return;
  }
  state.candidateIndex = index;
  audio.currentTime = candidates[index].loopStartSeconds;
  renderCandidate();
  scheduleTransition();
  if (closePanel) {
    setCandidatePanel(false);
  }
};

const renderCandidateList = () => {
  const candidates = state.analysis?.candidates ?? [];
  elements.candidateList.replaceChildren(
    ...candidates.map((candidate, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className =
        `candidate-option${index === state.candidateIndex ? " active" : ""}`;
      const candidateNumber = candidate.isHeadLoop ? 0 : index;
      button.title = `候補${candidateNumber}のループ位置へ切り替えます`;
      button.setAttribute("aria-label", `ループ候補${candidateNumber}を選択`);
      const label = document.createElement("strong");
      label.textContent = `候補 ${candidateNumber}`;
      const score = document.createElement("span");
      score.textContent = candidate.isHeadLoop
        ? "先頭固定"
        : candidate.score.toFixed(6);
      const times = document.createElement("small");
      times.textContent =
        `${formatTime(candidate.loopStartSeconds)} → ${formatTime(candidate.loopEndSeconds)}`;
      button.append(label, score, times);
      button.addEventListener("click", () => selectCandidate(index, true));
      return button;
    }),
  );
};

const renderProgress = () => {
  renderSeek();
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

const renderSeek = () => {
  const duration = Number.isFinite(audio.duration)
    ? audio.duration
    : state.analysis?.durationSeconds;
  const current = Number.isFinite(audio.currentTime) ? audio.currentTime : 0;
  elements.seekBar.disabled = !Number.isFinite(duration) || duration <= 0;
  elements.seekBar.value = duration > 0
    ? String(Math.round(Math.min(current / duration, 1) * 1000))
    : "0";
  elements.currentTime.textContent = `現在 ${formatTime(current)}`;
  elements.totalTime.textContent = `全長 ${formatTime(duration)}`;
};

const seekAudio = () => {
  const duration = Number.isFinite(audio.duration)
    ? audio.duration
    : state.analysis?.durationSeconds;
  if (!Number.isFinite(duration) || duration <= 0) {
    return;
  }
  audio.currentTime = Number(elements.seekBar.value) / 1000 * duration;
  renderProgress();
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
  elements.shuffle.title = state.shuffle
    ? "ランダム再生を解除して曲順再生へ戻します"
    : "次の曲をランダムに選ぶ状態へ切り替えます";
  setMessage(state.shuffle ? "ランダム再生を有効にしました。" : "曲順再生に戻しました。");
};

const toggleMute = () => {
  state.muted = !state.muted;
  audio.volume = state.muted ? 0 : 1;
  elements.mute.classList.toggle("active", state.muted);
  elements.mute.textContent = state.muted ? "○" : "◕";
  elements.mute.title = state.muted ? "消音を解除します" : "音を消します";
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
