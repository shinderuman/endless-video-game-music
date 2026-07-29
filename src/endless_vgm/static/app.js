import {LoopAudioPlayer} from "./loop-audio-player.js";

const FADE_SECONDS = 4;
const MAX_LOOP_CANDIDATES = 20;
const PANEL_WIDTH_STORAGE_KEY = "endless-vgm-panel-widths";
const LIBRARY_STATE_STORAGE_KEY = "endless-vgm-library-state";
const LIBRARY_COLLATOR = new Intl.Collator("ja", {
  numeric: true,
  sensitivity: "base",
});
const PANEL_WIDTHS = {
  playlist: {property: "--playlist-width", min: 170, max: 480},
  album: {property: "--album-width", min: 200, max: 640},
  track: {property: "--track-width", min: 360, max: 900},
};
const mediaAudio = new Audio();
const loopAudio = new LoopAudioPlayer();
const state = {
  playlists: [],
  albums: [],
  tracks: [],
  visibleTracks: [],
  currentPlaylist: "",
  currentAlbumId: "",
  currentTrackId: null,
  playlistSort: {key: "title", direction: "asc"},
  albumSort: {key: "title", direction: "asc"},
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
  playlistSortTitle: document.querySelector("#playlist-sort-title"),
  playlistSortCount: document.querySelector("#playlist-sort-count"),
  playlistList: document.querySelector("#playlist-list"),
  albumCount: document.querySelector("#album-count"),
  albumSearch: document.querySelector("#album-search"),
  albumSortTitle: document.querySelector("#album-sort-title"),
  albumSortCount: document.querySelector("#album-sort-count"),
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
  recommendedCandidateList: document.querySelector("#recommended-candidate-list"),
  candidatePicker: document.querySelector("#candidate-picker"),
  candidateCount: document.querySelector("#candidate-count"),
  candidatePanel: document.querySelector("#candidate-panel"),
  candidateList: document.querySelector("#candidate-list"),
  candidateLabel: document.querySelector("#candidate-label"),
  candidateScore: document.querySelector("#candidate-score"),
  reanalyzeTrack: document.querySelector("#reanalyze-track"),
  loopSeekBar: document.querySelector("#loop-seek-bar"),
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
const activeAudio = () => state.mode === "loop" ? loopAudio : mediaAudio;

const formatTime = (seconds) => {
  if (!Number.isFinite(seconds)) {
    return "—";
  }
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${Math.floor(seconds % 60).toString().padStart(2, "0")}`;
};

const restoredSort = (saved) => {
  const key = saved?.key;
  const direction = saved?.direction;
  if (
    ["title", "count"].includes(key)
    && ["asc", "desc"].includes(direction)
  ) {
    return {key, direction};
  }
  return {key: "title", direction: "asc"};
};

const sortLibraryItems = (
  items,
  sort,
  titleOf,
  countOf,
  keepFirst = () => false,
) => [...items].sort((left, right) => {
  if (keepFirst(left) !== keepFirst(right)) {
    return keepFirst(left) ? -1 : 1;
  }
  let comparison = sort.key === "count"
    ? Number(countOf(left) ?? 0) - Number(countOf(right) ?? 0)
    : LIBRARY_COLLATOR.compare(titleOf(left), titleOf(right));
  if (comparison === 0) {
    comparison = LIBRARY_COLLATOR.compare(titleOf(left), titleOf(right));
  }
  return sort.direction === "desc" ? -comparison : comparison;
});

const toggleLibrarySort = (library, key) => {
  const stateKey = `${library}Sort`;
  const current = state[stateKey];
  state[stateKey] = {
    key,
    direction:
      current.key === key && current.direction === "asc" ? "desc" : "asc",
  };
  if (library === "playlist") {
    renderPlaylists();
  } else {
    renderAlbums();
  }
  saveLibraryState();
};

const renderSortControls = (library) => {
  const sort = state[`${library}Sort`];
  const controls = [
    ["title", elements[`${library}SortTitle`], "タイトル"],
    ["count", elements[`${library}SortCount`], "曲数"],
  ];
  for (const [key, button, label] of controls) {
    const active = sort.key === key;
    const direction = active ? sort.direction : "none";
    const arrow = direction === "asc" ? "↑" : direction === "desc" ? "↓" : "↕";
    const nextDirection =
      active && sort.direction === "asc" ? "降順" : "昇順";
    button.textContent = `${label} ${arrow}`;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
    button.title = `${label}の${nextDirection}へ切り替えます`;
  }
};

const refinementLabel = (method) => ({
  pmlDurationLocalWaveform: "標準",
  loopMusicEndpointPair: "位置調整",
  loopAuditioneerFiveSample: "つなぎ目優先",
})[method] ?? "波形補正";

const refinementDescription = (method) => ({
  pmlDurationLocalWaveform: "終端を波形で補正",
  loopMusicEndpointPair: "開始と終端を同時調整",
  loopAuditioneerFiveSample: "境界直前を細かく比較",
})[method] ?? "波形を再比較";

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
  mediaAudio.addEventListener("ended", () => playAdjacent(1));
  mediaAudio.addEventListener("durationchange", renderSeek);
  mediaAudio.addEventListener("loadedmetadata", renderSeek);
  mediaAudio.addEventListener("timeupdate", renderProgress);
  mediaAudio.addEventListener("error", () => {
    if (mediaAudio.src) {
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
  elements.playlistSortTitle.addEventListener(
    "click",
    () => toggleLibrarySort("playlist", "title"),
  );
  elements.playlistSortCount.addEventListener(
    "click",
    () => toggleLibrarySort("playlist", "count"),
  );
  elements.albumSearch.addEventListener("input", () => {
    renderAlbums();
    saveLibraryState();
  });
  elements.albumSortTitle.addEventListener(
    "click",
    () => toggleLibrarySort("album", "title"),
  );
  elements.albumSortCount.addEventListener(
    "click",
    () => toggleLibrarySort("album", "count"),
  );
  elements.trackSearch.addEventListener("input", () => {
    resetTrackLimit();
    saveLibraryState();
  });
  elements.seekBar.addEventListener("input", seekAudio);
  elements.loopSeekBar.addEventListener("input", seekLoopAudio);
  elements.refreshLibrary.addEventListener("click", refreshLibrary);
  elements.modeNormal.addEventListener("click", () => setMode("normal"));
  elements.modeLoop.addEventListener("click", () => setMode("loop"));
  elements.candidatePicker.addEventListener("click", toggleCandidatePanel);
  elements.reanalyzeTrack.addEventListener("click", reanalyzeCurrentTrack);
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
    state.playlistSort = restoredSort(saved.playlistSort);
    state.albumSort = restoredSort(saved.albumSort);
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
        playlistSort: state.playlistSort,
        albumSort: state.albumSort,
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
  const playlists = sortLibraryItems(
    state.playlists.filter((playlist) =>
      playlist.name.toLocaleLowerCase().includes(query),
    ),
    state.playlistSort,
    (playlist) => playlist.name,
    (playlist) => playlist.availableTrackCount,
    (playlist) => playlist.isLibrary,
  );
  renderSortControls("playlist");
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
  elements.trackList.scrollTop = 0;
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
  if (restoring && restoredTrack && !mediaAudio.src && !loopAudio.buffer) {
    await selectTrack(restoredTrack.id, false, true);
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
  const albums = sortLibraryItems(
    state.albums.filter((album) =>
      album.name.toLocaleLowerCase().includes(query),
    ),
    state.albumSort,
    (album) => album.name,
    (album) => album.trackCount,
  );
  renderSortControls("album");
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
  elements.trackList.scrollTop = 0;
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

const selectTrack = async (trackId, autoplay, prepare = false) => {
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
  if (!autoplay && !prepare) {
    return;
  }
  try {
    if (state.mode === "normal") {
      await playNormal(track, autoplay);
    } else {
      await playLoop(track, token, false, autoplay);
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
  elements.reanalyzeTrack.disabled = false;
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
  elements.recommendedCandidateList.replaceChildren();
  elements.candidateList.replaceChildren();
  elements.candidateCount.textContent = "—";
  elements.candidatePicker.disabled = true;
  elements.candidateLabel.textContent = "ループ候補 —";
  elements.candidateScore.textContent =
    state.mode === "loop" ? "解析待ち" : "通常再生では使用しません";
  elements.loopStart.textContent = "START —";
  elements.loopEnd.textContent = "END —";
  elements.loopSeekBar.value = "0";
  elements.loopSeekBar.disabled = true;
};

const playNormal = async (track, shouldPlay = true) => {
  showAnalysis(false);
  loopAudio.clear();
  mediaAudio.src = track.audioUrl;
  mediaAudio.volume = state.muted ? 0 : 1;
  if (!shouldPlay) {
    mediaAudio.load();
    state.playing = false;
    updatePlayButton();
    setMessage("再生の準備ができました。");
    prefetchNext();
    return;
  }
  await mediaAudio.play();
  state.playing = true;
  updatePlayButton();
  setMessage("通常再生中");
  scheduleTransition();
  prefetchNext();
};

const playLoop = async (track, token, force = false, shouldPlay = true) => {
  showAnalysis(true);
  setMessage("PyMusicLooperでループ位置を解析しています。");
  mediaAudio.pause();
  mediaAudio.removeAttribute("src");
  mediaAudio.load();
  await loopAudio.prepare();
  const [analysisResponse, audioLoaded] = await Promise.all([
    api(
      `/api/tracks/${track.id}/${force ? "reanalyze" : "analyze"}`,
      {method: "POST"},
    ),
    loopAudio.load(track.audioUrl),
  ]);
  const analysis = await analysisResponse.json();
  const scoredCandidates = analysis.candidates.slice(0, MAX_LOOP_CANDIDATES);
  analysis.candidateCount = scoredCandidates.length;
  analysis.candidates = [
    ...(analysis.refinedCandidates ?? []),
    ...scoredCandidates,
  ];
  if (token !== state.requestToken || !audioLoaded) {
    return;
  }
  showAnalysis(false);
  state.analysis = analysis;
  if (analysis.candidates.length === 0) {
    setMessage("ループ候補がないため通常再生します。");
    await playNormal(track);
    return;
  }
  state.candidateIndex = analysis.candidates.findIndex(
    (candidate) => candidate.rank === 0,
  );
  if (state.candidateIndex < 0) {
    state.candidateIndex = analysis.candidates.findIndex(
      (candidate) => candidate.rank === 1,
    );
  }
  if (state.candidateIndex < 0) {
    state.candidateIndex = 0;
  }
  const candidate = analysis.candidates[state.candidateIndex];
  loopAudio.setLoop(candidate.loopStartSeconds, candidate.loopEndSeconds);
  loopAudio.currentTime = 0;
  loopAudio.volume = state.muted ? 0 : 1;
  renderCandidate();
  prefetchNext();
  if (!shouldPlay) {
    state.playing = false;
    setMessage(
      `推奨候補と${analysis.candidateCount}件の補助候補を読み込みました。`,
    );
    updatePlayButton();
    return;
  }
  try {
    await loopAudio.play();
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

const reanalyzeCurrentTrack = async () => {
  const track = currentTrack();
  if (!track || elements.reanalyzeTrack.disabled) {
    return;
  }
  const token = ++state.requestToken;
  setReanalyzing(true);
  state.analysis = null;
  state.candidateIndex = 0;
  try {
    if (state.mode === "loop") {
      stopPlayback();
      await playLoop(track, token, true);
    } else {
      showAnalysis(true);
      setMessage("ループ位置を再解析しています。");
      await api(`/api/tracks/${track.id}/reanalyze`, {method: "POST"});
      showAnalysis(false);
      setMessage("再解析しました。ループ再生に切り替えると結果を読み込みます。");
    }
  } catch (error) {
    showAnalysis(false);
    setMessage(`再解析できませんでした: ${error.message}`);
  } finally {
    setReanalyzing(false);
  }
};

const setReanalyzing = (loading) => {
  elements.reanalyzeTrack.disabled = loading || !currentTrack();
  elements.reanalyzeTrack.classList.toggle("loading", loading);
  elements.reanalyzeTrack.setAttribute("aria-busy", String(loading));
  elements.reanalyzeTrack.textContent = loading ? "解析中" : "再解析";
};

const stopPlayback = () => {
  window.clearTimeout(state.transitionTimer);
  window.clearTimeout(state.nextTimer);
  state.transitionTimer = null;
  state.nextTimer = null;
  loopAudio.clear();
  mediaAudio.pause();
  mediaAudio.removeAttribute("src");
  mediaAudio.load();
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
  const audio = activeAudio();
  if (audio.paused) {
    try {
      await (audio === loopAudio ? loopAudio.play(true) : mediaAudio.play());
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

const renderCandidate = () => {
  const candidates = state.analysis?.candidates;
  if (!candidates?.length) {
    resetCandidateDisplay();
    return;
  }
  const candidate = candidates[state.candidateIndex];
  elements.candidateLabel.textContent = candidate.rank <= 0
    ? refinementLabel(candidate.method)
    : `PyMusicLooper候補 ${candidate.rank}`;
  elements.candidateScore.textContent = candidate.rank <= 0
    ? `${refinementLabel(candidate.method)}・一致度 ${candidate.score.toFixed(6)}`
    : `PyMusicLooperスコア ${candidate.score.toFixed(6)}（高い順）`;
  elements.loopStart.textContent = `START ${formatTime(candidate.loopStartSeconds)}`;
  elements.loopEnd.textContent = `END ${formatTime(candidate.loopEndSeconds)}`;
  renderCandidateList();
};

const toggleCandidatePanel = () => {
  if (!state.analysis?.candidates.some((candidate) => candidate.rank > 0)) {
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
  const candidate = candidates[index];
  loopAudio.setLoop(candidate.loopStartSeconds, candidate.loopEndSeconds);
  loopAudio.currentTime = 0;
  renderCandidate();
  scheduleTransition();
  if (closePanel) {
    setCandidatePanel(false);
  }
};

const renderCandidateList = () => {
  const candidates = state.analysis?.candidates ?? [];
  const recommended = candidates
    .map((candidate, index) => ({candidate, index}))
    .filter(({candidate}) => candidate.rank <= 0);
  const auxiliary = candidates
    .map((candidate, index) => ({candidate, index}))
    .filter(({candidate}) => candidate.rank > 0);
  elements.recommendedCandidateList.replaceChildren(
    ...recommended.map(({candidate, index}) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className =
        `recommended-candidate${index === state.candidateIndex ? " active" : ""}`;
      const name = refinementLabel(candidate.method);
      button.title = `${name}のループ位置を選び、曲の先頭から再生します`;
      button.setAttribute("aria-label", `${name}のループ候補を選択`);
      const label = document.createElement("strong");
      label.textContent = name;
      const method = document.createElement("span");
      method.textContent = refinementDescription(candidate.method);
      const times = document.createElement("small");
      times.textContent =
        `${formatTime(candidate.loopStartSeconds)} → ${formatTime(candidate.loopEndSeconds)}`;
      button.append(label, method, times);
      button.addEventListener("click", () => selectCandidate(index, false));
      return button;
    }),
  );
  elements.candidateCount.textContent = `${auxiliary.length}件`;
  elements.candidatePicker.disabled = auxiliary.length === 0;
  elements.candidateList.replaceChildren(
    ...auxiliary.map(({candidate, index}) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className =
        `candidate-option${index === state.candidateIndex ? " active" : ""}`;
      button.title =
        `PyMusicLooper候補${candidate.rank}を選び、曲の先頭から再生します`;
      button.setAttribute("aria-label", `ループ候補${candidate.rank}を選択`);
      const label = document.createElement("strong");
      label.textContent = `候補 ${candidate.rank}`;
      const score = document.createElement("span");
      score.textContent = candidate.score.toFixed(6);
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
  const audio = activeAudio();
  const candidates = state.analysis?.candidates;
  if (state.mode !== "loop" || !candidates?.length) {
    elements.loopSeekBar.value = "0";
    elements.loopSeekBar.disabled = true;
    return;
  }
  const candidate = candidates[state.candidateIndex];
  const position = audio.currentTime / candidate.loopEndSeconds;
  elements.loopSeekBar.disabled = false;
  elements.loopSeekBar.value =
    String(Math.round(Math.max(0, Math.min(position, 1)) * 1000));
};

const renderSeek = () => {
  const audio = activeAudio();
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
  const audio = activeAudio();
  const duration = Number.isFinite(audio.duration)
    ? audio.duration
    : state.analysis?.durationSeconds;
  if (!Number.isFinite(duration) || duration <= 0) {
    return;
  }
  audio.currentTime = Number(elements.seekBar.value) / 1000 * duration;
  renderProgress();
};

const seekLoopAudio = () => {
  const candidate = state.analysis?.candidates[state.candidateIndex];
  if (!candidate || state.mode !== "loop") {
    return;
  }
  loopAudio.currentTime =
    Number(elements.loopSeekBar.value) / 1000 * candidate.loopEndSeconds;
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
  mediaAudio.volume = state.muted ? 0 : 1;
  loopAudio.volume = state.muted ? 0 : 1;
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
  const audio = activeAudio();
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
