ObjC.import("Foundation");

const automationOptions = {timeout: 3600};
const ALL_TRACKS_NAME = "すべての楽曲";

const nfc = (value) => {
  if (value === null || value === undefined) return "";
  return ObjC.unwrap($(value).precomposedStringWithCanonicalMapping);
};

const readValue = (getter, fallback) => {
  try {
    const value = getter();
    return value === null || value === undefined ? fallback : value;
  } catch (error) {
    return fallback;
  }
};

const errorMessage = (error) => {
  const number = readValue(
    () => error.errorNumber,
    readValue(() => error.number, null),
  );
  const message = readValue(() => error.message, String(error));
  return number === null ? message : `${message} (${number})`;
};

const throwIfAutomationDenied = (error) => {
  if (error.automationDenied === true) throw error;
  const number = readValue(
    () => error.errorNumber,
    readValue(() => error.number, null),
  );
  if (number !== -1743) return;
  const denied = new Error(
    "Music.appへのアクセスがmacOSに拒否されました。システム設定の" +
      "「プライバシーとセキュリティ」→「オートメーション」で、" +
      "サーバーを起動したアプリによるMusicの操作を許可してください (-1743)",
  );
  denied.automationDenied = true;
  throw denied;
};

const isLibraryPlaylist = (playlist) => {
  const className = String(readValue(() => playlist.class(), "")).toLowerCase();
  const specialKind = String(
    readValue(() => playlist.specialKind(), ""),
  ).toLowerCase();
  return (
    className.includes("library") ||
    specialKind === "library" ||
    specialKind === "music"
  );
};

const waitForPlaylists = (app) => {
  let lastError = null;
  for (let elapsed = 0; elapsed < 60; elapsed += 1) {
    try {
      const playlists = app.userPlaylists();
      if (
        playlists.length > 0 &&
        playlists.every((playlist) => playlist.name() !== null)
      ) {
        return playlists;
      }
    } catch (error) {
      throwIfAutomationDenied(error);
      lastError = error;
      try {
        const playlists = app
          .playlists()
          .filter((playlist) => !isLibraryPlaylist(playlist));
        if (
          playlists.length > 0 &&
          playlists.every((playlist) => playlist.name() !== null)
        ) {
          return playlists;
        }
      } catch (fallbackError) {
        throwIfAutomationDenied(fallbackError);
        lastError = fallbackError;
      }
    }
    delay(1);
  }
  const detail = lastError ? `: ${errorMessage(lastError)}` : "";
  throw new Error(`Music.appのプレイリストを取得できませんでした${detail}`);
};

const waitForLibraryPlaylist = (app) => {
  let lastError = null;
  for (let elapsed = 0; elapsed < 60; elapsed += 1) {
    try {
      const sources = app.sources();
      for (const source of sources) {
        try {
          const playlists = source.libraryPlaylists();
          if (playlists.length > 0) return playlists[0];
        } catch (error) {
          throwIfAutomationDenied(error);
          lastError = error;
        }
      }
      for (const playlist of app.playlists()) {
        if (isLibraryPlaylist(playlist)) return playlist;
      }
    } catch (error) {
      throwIfAutomationDenied(error);
      lastError = error;
    }
    delay(1);
  }
  const detail = lastError ? `: ${errorMessage(lastError)}` : "";
  throw new Error(`Music.appのライブラリを取得できませんでした${detail}`);
};

const bulkProperties = (playlist, tracks) => {
  if (tracks.length > 1000) return null;
  const candidates = [
    () => playlist.tracks.properties(automationOptions),
    () => tracks.properties(automationOptions),
  ];
  for (const candidate of candidates) {
    try {
      const properties = candidate();
      if (properties && properties.length === tracks.length) return properties;
    } catch (error) {
      // OSバージョンによって一括取得できない場合は曲単位へフォールバックする。
    }
  }
  return null;
};

const trackProperties = (track) => {
  try {
    return track.properties(automationOptions);
  } catch (error) {
    return null;
  }
};

const parseTrack = (track, properties) => {
  const value = (name, fallback) =>
    properties ? readValue(() => properties[name], fallback) : fallback;
  const location = properties
    ? readValue(() => properties.location, null)
    : readValue(() => track.location(), null);
  return {
    name: nfc(properties ? value("name", "") : readValue(() => track.name(), "")),
    artist: nfc(properties ? value("artist", "") : readValue(() => track.artist(), "")),
    album_artist: nfc(
      properties
        ? value("albumArtist", "")
        : readValue(() => track.albumArtist(), ""),
    ),
    album: nfc(properties ? value("album", "") : readValue(() => track.album(), "")),
    disc_number: properties
      ? value("discNumber", null)
      : readValue(() => track.discNumber(), null),
    track_number: properties
      ? value("trackNumber", null)
      : readValue(() => track.trackNumber(), null),
    location: location ? nfc(location.toString()) : null,
  };
};

const trackPersistentIds = (playlist, tracks) => {
  try {
    const ids = playlist.tracks.persistentID(automationOptions);
    if (ids.length === tracks.length) return ids.map((value) => nfc(value));
  } catch (error) {
    // 一括取得できない場合だけ曲単位へフォールバックする。
  }
  return tracks.map((track) =>
    nfc(readValue(() => track.persistentID(), "")),
  );
};

const parseLibraryPlaylist = (
  playlist,
  tracks,
  persistentIds,
  trackCache,
  onTrack,
) => {
  const properties = bulkProperties(playlist, tracks);
  const parsedTracks = tracks.map((track, index) => {
    const parsed = parseTrack(
      track,
      properties ? properties[index] : trackProperties(track),
    );
    const persistentId = persistentIds[index];
    if (persistentId) trackCache.set(persistentId, parsed);
    onTrack(index + 1, tracks.length, parsed);
    return parsed;
  });
  return {
    name: ALL_TRACKS_NAME,
    is_library: true,
    tracks: parsedTracks,
  };
};

const parseCachedPlaylist = (playlist, name, persistentIds, trackCache) => {
  let tracks = null;
  const parsedTracks = persistentIds.map((persistentId, index) => {
    const cached = trackCache.get(persistentId);
    if (cached) return cached;
    tracks ??= playlist.tracks(automationOptions);
    const parsed = parseTrack(tracks[index], trackProperties(tracks[index]));
    if (persistentId) trackCache.set(persistentId, parsed);
    return parsed;
  });
  return {
    name,
    is_library: false,
    tracks: parsedTracks,
  };
};

const progressReporter = () => {
  let lastReportedAt = 0;
  return (percent, message, force = false) => {
    const now = Date.now();
    if (!force && now - lastReportedAt < 1000) return;
    lastReportedAt = now;
    const normalized = Math.max(0, Math.min(100, percent));
    console.log(`進捗 ${normalized.toFixed(1)}%: ${message}`);
  };
};

function run() {
  const app = Application("Music");
  app.includeStandardAdditions = true;
  const library = waitForLibraryPlaylist(app);
  const playlists = waitForPlaylists(app).filter(
    (playlist) =>
      playlist.name() !== ALL_TRACKS_NAME && !isLibraryPlaylist(playlist),
  );
  const libraryTracks = library.tracks(automationOptions);
  const libraryIds = trackPersistentIds(library, libraryTracks);
  const playlistReferences = playlists.map((playlist) => ({
    playlist,
    name: nfc(playlist.name()),
    ids: trackPersistentIds(playlist, playlist.tracks(automationOptions)),
  }));
  const reportProgress = progressReporter();
  const trackCache = new Map();
  const result = [];
  reportProgress(0, "全曲メタデータを準備中");
  result.push(
    parseLibraryPlaylist(
      library,
      libraryTracks,
      libraryIds,
      trackCache,
      (completed, total, parsed) =>
        reportProgress(
          total > 0 ? (completed / total) * 95 : 95,
          `全曲メタデータ ${completed} / ${total}曲: ${parsed.name || "曲名なし"}`,
        ),
    ),
  );
  playlistReferences.forEach((reference, index) => {
    result.push(
      parseCachedPlaylist(
        reference.playlist,
        reference.name,
        reference.ids,
        trackCache,
      ),
    );
    reportProgress(
      95 + ((index + 1) / playlistReferences.length) * 5,
      `プレイリスト ${index + 1} / ${playlistReferences.length}: ${reference.name}`,
      true,
    );
  });
  reportProgress(100, "Music.appライブラリの取得完了", true);
  return JSON.stringify(result);
}
