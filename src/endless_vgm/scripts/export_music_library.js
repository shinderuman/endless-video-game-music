ObjC.import("Foundation");

const automationOptions = {timeout: 3600};

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

const waitForPlaylists = (app) => {
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
      // Music.appが起動処理中の場合は待機する。
    }
    delay(1);
  }
  throw new Error("Music.appのプレイリストを取得できませんでした");
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
    location: location ? nfc(location.toString()) : null,
  };
};

function run() {
  const app = Application("Music");
  app.includeStandardAdditions = true;
  return JSON.stringify(
    waitForPlaylists(app).map((playlist) => {
      const tracks = playlist.tracks(automationOptions);
      const properties = bulkProperties(playlist, tracks);
      return {
        name: nfc(playlist.name()),
        tracks: tracks.map((track, index) =>
          parseTrack(track, properties ? properties[index] : trackProperties(track)),
        ),
      };
    }),
  );
}
