ObjC.import("Foundation");

// lightweight manifest of user-managed playlists for change polling.
// full metadata export lives in export_music_library.js; this script only reads
// the stable identity (playlist persistent ID + name + ordered track persistent IDs)
// so the watchdog can detect structural changes cheaply (~seconds, not minutes).
// the playlist set must match export_music_library.js so a changed fingerprint
// always corresponds to what a full refresh would write.

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

const trackPersistentIds = (playlist, tracks) => {
  try {
    const ids = playlist.tracks.persistentID(automationOptions);
    if (ids.length === tracks.length) return ids.map((value) => nfc(value));
  } catch (error) {
    // OSバージョンによって一括取得できない場合は曲単位へフォールバックする。
  }
  return tracks.map((track) =>
    nfc(readValue(() => track.persistentID(), "")),
  );
};

const parsePlaylist = (playlist, name) => {
  const tracks = playlist.tracks(automationOptions);
  return {
    id: nfc(readValue(() => playlist.persistentID(), "")),
    name,
    tracks: trackPersistentIds(playlist, tracks),
  };
};

function run() {
  const app = Application("Music");
  app.includeStandardAdditions = true;
  const playlists = waitForPlaylists(app).filter(
    (playlist) =>
      playlist.name() !== ALL_TRACKS_NAME && !isLibraryPlaylist(playlist),
  );
  return JSON.stringify(
    playlists.map((playlist) => parsePlaylist(playlist, nfc(playlist.name()))),
  );
}
