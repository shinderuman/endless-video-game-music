on run argv
	set playlistName to item 1 of argv
	set trackIndex to item 2 of argv as integer
	set outputPath to item 3 of argv
	tell application "Music"
		set targetPlaylist to first user playlist whose name is playlistName
		set playlistTracks to every track of targetPlaylist
		if trackIndex > (count of playlistTracks) then return ""
		set currentTrack to item trackIndex of playlistTracks
		if (count of artworks of currentTrack) is 0 then return ""
		set artworkData to data of artwork 1 of currentTrack
	end tell
	set outputFile to open for access POSIX file outputPath with write permission
	try
		set eof outputFile to 0
		write artworkData to outputFile
		close access outputFile
	on error
		try
			close access outputFile
		end try
		error
	end try
	return outputPath
end run
